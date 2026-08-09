from __future__ import annotations

import contextlib
import hashlib
import heapq
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from terminal_bridge.config import (
    COMMAND_BUNDLE_APPLIED_DIR,
    COMMAND_BUNDLE_FAILED_DIR,
    COMMAND_BUNDLE_INTERRUPTED_DIR,
    COMMAND_BUNDLE_PENDING_DIR,
    COMMAND_BUNDLE_REJECTED_DIR,
    COMMAND_BUNDLE_RUNNING_DIR,
)
from terminal_bridge.handoffs import write_handoff_from_bundle
from terminal_bridge.storage import _fsync_directory, _now_iso, _read_json, _write_json


TERMINAL_BUNDLE_STATUSES = frozenset({"applied", "failed", "interrupted"})
ACTIVE_BUNDLE_STATUSES = frozenset({"pending", "running"})
REQUEST_KEY_TERMINAL_FALLBACK_LIMIT = 128
GENERATION_FILE_NAME = ".generation.json"
REQUEST_KEY_INDEX_DIR_NAME = "request_keys"

_generation_observation_lock = threading.Lock()
_generation_observations: dict[str, tuple[str, tuple[tuple[str, int], ...]]] = {}


class BundleStateError(RuntimeError):
    """The requested bundle lifecycle transition is not currently valid."""


class BundleClaimError(BundleStateError):
    """A pending bundle could not be claimed for exclusive execution."""


def _command_bundle_dirs() -> list[Path]:
    return [
        COMMAND_BUNDLE_RUNNING_DIR,
        COMMAND_BUNDLE_PENDING_DIR,
        COMMAND_BUNDLE_APPLIED_DIR,
        COMMAND_BUNDLE_REJECTED_DIR,
        COMMAND_BUNDLE_FAILED_DIR,
        COMMAND_BUNDLE_INTERRUPTED_DIR,
    ]


def _command_bundle_dirs_for_root(root: Path) -> list[Path]:
    return [
        root / "running",
        root / "pending",
        root / "applied",
        root / "rejected",
        root / "failed",
        root / "interrupted",
    ]


def _command_bundle_directory_for_status(
    status: str,
    *,
    directories: list[Path] | None = None,
) -> Path:
    if directories is None:
        return _command_bundle_path("cmd-directory-probe", status).parent
    for directory in directories:
        if directory.name == status:
            return directory
    raise ValueError(f"Unknown command bundle status: {status}")


def _new_command_bundle_id() -> str:
    return f"cmd-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _command_bundle_path(bundle_id: str, status: str = "pending") -> Path:
    if not bundle_id.startswith("cmd-"):
        raise ValueError("Invalid command bundle id.")

    mapping = {
        "pending": COMMAND_BUNDLE_PENDING_DIR,
        "running": COMMAND_BUNDLE_RUNNING_DIR,
        "applied": COMMAND_BUNDLE_APPLIED_DIR,
        "rejected": COMMAND_BUNDLE_REJECTED_DIR,
        "failed": COMMAND_BUNDLE_FAILED_DIR,
        "interrupted": COMMAND_BUNDLE_INTERRUPTED_DIR,
    }
    directory = mapping.get(status)
    if directory is None:
        raise ValueError(f"Unknown command bundle status: {status}")

    return directory / f"{bundle_id}.json"


def _find_command_bundle(
    bundle_id: str,
    *,
    directories: list[Path] | None = None,
) -> tuple[Path, dict[str, object]]:
    for directory in directories or _command_bundle_dirs():
        path = directory / f"{bundle_id}.json"
        if path.exists():
            record = _read_json(path)
            if directory.name in {
                "pending",
                "running",
                "applied",
                "rejected",
                "failed",
                "interrupted",
            }:
                record["status"] = directory.name
            return path, record
    raise FileNotFoundError(f"Command bundle not found: {bundle_id}")


def _write_command_bundle(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, record)


def _command_bundles_root(*, pending_dir: Path | None = None) -> Path:
    return (pending_dir or COMMAND_BUNDLE_PENDING_DIR).parent


def _command_bundle_generation_path(*, root: Path | None = None) -> Path:
    return (root or _command_bundles_root()) / GENERATION_FILE_NAME


def _new_generation_token() -> str:
    return str(uuid.uuid4())


def _read_command_bundle_generation(*, root: Path | None = None) -> str | None:
    path = _command_bundle_generation_path(root=root)
    try:
        record = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    token = record.get("generation")
    if not isinstance(token, str):
        return None
    try:
        return str(uuid.UUID(token))
    except ValueError:
        return None


def _bump_command_bundle_generation(*, root: Path | None = None) -> str:
    token = _new_generation_token()
    _write_json(
        _command_bundle_generation_path(root=root),
        {"version": 1, "generation": token},
    )
    return token


def _bundle_directory_signature(directories: list[Path]) -> tuple[tuple[str, int], ...]:
    signature: list[tuple[str, int]] = []
    for directory in directories:
        try:
            mtime_ns = directory.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0
        signature.append((str(directory), mtime_ns))
    return tuple(signature)


def _command_bundle_generation(
    *,
    root: Path | None = None,
    directories: list[Path] | None = None,
    reconcile_directory_metadata: bool = False,
) -> str:
    """Read the compact generation signal, optionally reconciling legacy changes."""

    bundle_root = root or _command_bundles_root()
    observed_directories = directories or _command_bundle_dirs()
    signature = _bundle_directory_signature(observed_directories)
    cache_key = str(bundle_root.resolve(strict=False))

    with _generation_observation_lock:
        token = _read_command_bundle_generation(root=bundle_root)
        previous = _generation_observations.get(cache_key)
        needs_reconciliation = token is None
        if reconcile_directory_metadata:
            needs_reconciliation = needs_reconciliation or previous is None
            if previous is not None:
                previous_token, previous_signature = previous
                needs_reconciliation = needs_reconciliation or (
                    signature != previous_signature and token == previous_token
                )

        if needs_reconciliation:
            token = _bump_command_bundle_generation(root=bundle_root)

        assert token is not None
        _generation_observations[cache_key] = (token, signature)
        return token


def _request_key_index_dir(*, root: Path | None = None) -> Path:
    return (root or _command_bundles_root()) / REQUEST_KEY_INDEX_DIR_NAME


def _request_key_digest(request_key: str) -> str:
    return hashlib.sha256(request_key.encode("utf-8")).hexdigest()


def _request_key_slot_path(request_key: str, *, root: Path | None = None) -> Path:
    return _request_key_index_dir(root=root) / f"{_request_key_digest(request_key)}.json"


def _request_key_lock_path(request_key: str, *, root: Path) -> Path:
    return _request_key_index_dir(root=root) / ".locks" / f"{_request_key_digest(request_key)}.lock"


@contextlib.contextmanager
def _request_key_lock(request_key: str, *, root: Path):
    lock_path = _request_key_lock_path(request_key, root=root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 5.0

    while True:
        try:
            lock_path.mkdir()
            break
        except FileExistsError:
            try:
                stale = time.time() - lock_path.stat().st_mtime > 30.0
            except OSError:
                stale = False
            if stale:
                with contextlib.suppress(OSError):
                    lock_path.rmdir()
                continue
            if time.monotonic() >= deadline:
                raise BundleStateError("Timed out waiting for request-key index ownership.")
            time.sleep(0.01)

    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock_path.rmdir()


def _request_key_from_record(record: dict[str, object]) -> str | None:
    request_key = record.get("request_key")
    return request_key if isinstance(request_key, str) and request_key else None


def _sync_request_key_slot(
    bundle_path: Path,
    record: dict[str, object],
    *,
    root: Path | None = None,
) -> None:
    request_key = _request_key_from_record(record)
    if request_key is None:
        return
    bundle_id = str(record.get("bundle_id", bundle_path.stem))
    _write_json(
        _request_key_slot_path(request_key, root=root or bundle_path.parent.parent),
        {
            "version": 1,
            "request_key": request_key,
            "bundle_id": bundle_id,
            "status": bundle_path.parent.name,
            "updated_at": record.get("updated_at"),
        },
    )


def _publish_command_bundle_change(bundle_path: Path, record: dict[str, object]) -> None:
    """Publish rebuildable derived state without overriding canonical JSON authority."""

    root = bundle_path.parent.parent
    try:
        _sync_request_key_slot(bundle_path, record, root=root)
    except (OSError, TypeError, ValueError):
        # A later keyed lookup rebuilds the slot from the canonical record.
        pass
    try:
        _bump_command_bundle_generation(root=root)
    except OSError:
        # Review polling reconciles status-directory metadata when this write fails.
        pass


def _claim_lock_path(bundle_id: str, running_dir: Path) -> Path:
    return running_dir / f".{bundle_id}.claim"


def _release_claim_lock(bundle_id: str, running_dir: Path) -> None:
    with contextlib.suppress(OSError):
        _claim_lock_path(bundle_id, running_dir).rmdir()


def _acquire_claim_lock(bundle_id: str, running_dir: Path) -> Path:
    running_dir.mkdir(parents=True, exist_ok=True)
    lock_path = _claim_lock_path(bundle_id, running_dir)
    try:
        lock_path.mkdir()
    except FileExistsError as exc:
        raise BundleClaimError(f"Command bundle is already claimed: {bundle_id}") from exc
    return lock_path


def _claim_pending_command_bundle(
    bundle_id: str,
    *,
    pending_dir: Path | None = None,
    running_dir: Path | None = None,
    execution_id: str | None = None,
    pid: int | None = None,
) -> tuple[Path, dict[str, object], str]:
    """Atomically claim a pending bundle before any execution side effect."""

    if not bundle_id.startswith("cmd-"):
        raise ValueError("Invalid command bundle id.")

    pending_root = pending_dir or COMMAND_BUNDLE_PENDING_DIR
    running_root = running_dir or COMMAND_BUNDLE_RUNNING_DIR
    pending_path = pending_root / f"{bundle_id}.json"
    running_path = running_root / f"{bundle_id}.json"
    _acquire_claim_lock(bundle_id, running_root)
    running_state_published = False

    try:
        if running_path.exists():
            raise BundleClaimError(f"Command bundle is already running: {bundle_id}")
        if not pending_path.exists():
            raise BundleClaimError(f"Command bundle is no longer pending: {bundle_id}")

        record = _read_json(pending_path)
        current_status = str(record.get("status", "pending"))
        if current_status != "pending":
            raise BundleClaimError(
                f"Only pending bundles can be claimed. Current status: {current_status}"
            )

        claim_id = execution_id or f"exec-{uuid.uuid4().hex}"
        started_at = _now_iso()
        record.update(
            {
                "status": "running",
                "approval_required": False,
                "updated_at": started_at,
                "execution": {
                    "execution_id": claim_id,
                    "pid": os.getpid() if pid is None else pid,
                    "started_at": started_at,
                },
                "recovery": {
                    "automatic_replay": False,
                    "needs_review_on_restart": True,
                },
            }
        )
        os.replace(pending_path, running_path)
        running_state_published = True
        _fsync_directory(pending_root)
        _fsync_directory(running_root)
        _write_command_bundle(running_path, record)
        _publish_command_bundle_change(running_path, record)
        return running_path, record, claim_id
    except Exception:
        if not running_state_published:
            _release_claim_lock(bundle_id, running_root)
        raise


def _terminal_bundle_directory(
    status: str,
    *,
    applied_dir: Path,
    failed_dir: Path,
    interrupted_dir: Path,
) -> Path:
    mapping = {
        "applied": applied_dir,
        "failed": failed_dir,
        "interrupted": interrupted_dir,
    }
    try:
        return mapping[status]
    except KeyError as exc:
        raise ValueError(f"Invalid terminal bundle status: {status}") from exc


def _finalize_running_command_bundle(
    bundle_id: str,
    execution_id: str | None,
    status: str,
    updates: dict[str, object] | None = None,
    *,
    running_dir: Path | None = None,
    applied_dir: Path | None = None,
    failed_dir: Path | None = None,
    interrupted_dir: Path | None = None,
) -> dict[str, object]:
    """Publish one owned running bundle into a canonical terminal state."""

    if status not in TERMINAL_BUNDLE_STATUSES:
        raise ValueError(f"Invalid terminal bundle status: {status}")

    running_root = running_dir or COMMAND_BUNDLE_RUNNING_DIR
    running_path = running_root / f"{bundle_id}.json"
    if not running_path.exists():
        raise BundleStateError(f"Running command bundle not found: {bundle_id}")

    record = _read_json(running_path)
    execution = record.get("execution")
    execution_record = dict(execution) if isinstance(execution, dict) else {}
    stored_execution_id = execution_record.get("execution_id")
    if execution_id is not None and stored_execution_id != execution_id:
        raise BundleStateError(f"Command bundle execution ownership changed: {bundle_id}")

    target_root = _terminal_bundle_directory(
        status,
        applied_dir=applied_dir or COMMAND_BUNDLE_APPLIED_DIR,
        failed_dir=failed_dir or COMMAND_BUNDLE_FAILED_DIR,
        interrupted_dir=interrupted_dir or COMMAND_BUNDLE_INTERRUPTED_DIR,
    )
    target_root.mkdir(parents=True, exist_ok=True)
    target_path = target_root / running_path.name
    if target_path.exists():
        raise BundleStateError(f"Terminal command bundle already exists: {bundle_id}")

    finished_at = _now_iso()
    execution_record["finished_at"] = finished_at
    record.update(
        {
            "status": status,
            "approval_required": False,
            "updated_at": finished_at,
            "execution": execution_record,
        }
    )
    if updates:
        record.update(updates)
    if status == "interrupted":
        record["recovery"] = {
            "automatic_replay": False,
            "needs_review": True,
        }
    else:
        record.pop("recovery", None)

    _write_command_bundle(running_path, record)
    os.replace(running_path, target_path)
    _fsync_directory(running_root)
    _fsync_directory(target_root)
    _publish_command_bundle_change(target_path, record)
    try:
        write_handoff_from_bundle(record)
    finally:
        _release_claim_lock(bundle_id, running_root)
    return record


def _parse_bundle_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _process_is_alive(value: object) -> bool | None:
    """Return process liveness when a usable PID was recorded."""

    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _interrupt_stale_running_bundles(
    *,
    running_dir: Path,
    interrupted_dir: Path,
    stale_after_seconds: float,
    now: datetime | None = None,
) -> list[str]:
    """Move provably old running records to interrupted without replaying them."""

    interrupted: list[str] = []
    if not running_dir.exists():
        return interrupted

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    for path in sorted(running_dir.glob("cmd-*.json")):
        try:
            record = _read_json(path)
        except Exception:
            continue
        execution = record.get("execution")
        execution_record = execution if isinstance(execution, dict) else {}
        started_at = _parse_bundle_timestamp(
            execution_record.get("started_at") or record.get("updated_at")
        )
        process_alive = _process_is_alive(execution_record.get("pid"))
        stale_by_age = (
            started_at is not None
            and (current_time - started_at).total_seconds() >= stale_after_seconds
        )
        if process_alive is True or (process_alive is None and not stale_by_age):
            continue

        bundle_id = str(record.get("bundle_id", path.stem))
        stored_execution_id = execution_record.get("execution_id")
        expected_execution_id = (
            str(stored_execution_id) if isinstance(stored_execution_id, str) else None
        )
        reason = (
            "Execution was marked interrupted after stale running state was found during "
            "watcher startup. Automatic replay is disabled; review the workspace before retrying."
        )
        try:
            _finalize_running_command_bundle(
                bundle_id,
                expected_execution_id,
                "interrupted",
                {"error": reason},
                running_dir=running_dir,
                interrupted_dir=interrupted_dir,
            )
        except (OSError, ValueError, BundleStateError):
            continue
        interrupted.append(bundle_id)

    return interrupted


def _reject_pending_command_bundle(
    bundle_id: str,
    updates: dict[str, object] | None = None,
    *,
    pending_dir: Path | None = None,
    running_dir: Path | None = None,
    rejected_dir: Path | None = None,
) -> dict[str, object]:
    """Atomically consume a pending bundle without racing an execution claim."""

    pending_root = pending_dir or COMMAND_BUNDLE_PENDING_DIR
    running_root = running_dir or COMMAND_BUNDLE_RUNNING_DIR
    rejected_root = rejected_dir or COMMAND_BUNDLE_REJECTED_DIR
    pending_path = pending_root / f"{bundle_id}.json"
    running_path = running_root / f"{bundle_id}.json"
    rejected_path = rejected_root / f"{bundle_id}.json"
    _acquire_claim_lock(bundle_id, running_root)
    rejected_state_published = False
    transition_completed = False

    try:
        if running_path.exists():
            raise BundleStateError(f"Command bundle is already running: {bundle_id}")
        if not pending_path.exists():
            raise BundleStateError(f"Command bundle is no longer pending: {bundle_id}")
        if rejected_path.exists():
            raise BundleStateError(f"Rejected command bundle already exists: {bundle_id}")

        record = _read_json(pending_path)
        current_status = str(record.get("status", "pending"))
        if current_status != "pending":
            raise BundleStateError(
                f"Only pending bundles can be rejected. Current status: {current_status}"
            )

        now = _now_iso()
        record.update(
            {
                "status": "rejected",
                "approval_required": False,
                "updated_at": now,
            }
        )
        if updates:
            record.update(updates)
        rejected_root.mkdir(parents=True, exist_ok=True)
        os.replace(pending_path, rejected_path)
        rejected_state_published = True
        transition_completed = True
        _fsync_directory(pending_root)
        _fsync_directory(rejected_root)
        _write_command_bundle(rejected_path, record)
        _publish_command_bundle_change(rejected_path, record)
        write_handoff_from_bundle(record)
        return record
    finally:
        if not rejected_state_published or transition_completed:
            _release_claim_lock(bundle_id, running_root)


def _canonicalize_request_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonicalize_request_value(value.model_dump())

    if isinstance(value, dict):
        return {str(key): _canonicalize_request_value(item) for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))}

    if isinstance(value, list | tuple):
        return [_canonicalize_request_value(item) for item in value]

    if isinstance(value, Path):
        return str(value)

    return value


def _canonical_request_json(value: dict[str, object]) -> str:
    canonical = _canonicalize_request_value(value)
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _request_key(value: dict[str, object]) -> str:
    payload = _canonical_request_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _normalize_bundle_cwd(cwd: object) -> str:
    normalized = "" if cwd is None else str(cwd)
    return normalized or "."


def _default_command_bundle_metadata(cwd: object) -> dict[str, object]:
    normalized_cwd = _normalize_bundle_cwd(cwd)
    return {
        "task_id": None,
        "client_id": "default",
        "session_id": "default",
        "project_id": _request_key({"kind": "project", "cwd": normalized_cwd}),
    }


def _clean_command_bundle_metadata_text(value: object, field_name: str, *, strict: bool) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        if strict:
            raise ValueError(f"{field_name} must be a string when provided.")
        return None

    normalized = value.strip()
    return normalized or None


def _merge_command_bundle_metadata(
    cwd: object,
    raw_metadata: dict[str, object] | None = None,
    *,
    validate_workspace_mode: bool = False,
) -> dict[str, object]:
    defaults = _default_command_bundle_metadata(cwd)
    if not isinstance(raw_metadata, dict):
        return defaults

    normalized = dict(defaults)
    obsolete_routing_keys = {"workspace_mode", "source_cwd", "effective_cwd"}
    for key, value in raw_metadata.items():
        if not isinstance(key, str) or key in defaults:
            continue
        if validate_workspace_mode and key in obsolete_routing_keys:
            if key == "workspace_mode" and str(value or "").strip() not in {"", "direct"}:
                raise ValueError("workspace_mode='task-workspace' has been removed; new bundles use direct mode only.")
            continue
        # Historical records may contain retired routing keys or custom metadata.
        # Keep them readable without allowing them to affect new bundle routing.
        normalized[key] = value

    task_id = _clean_command_bundle_metadata_text(
        raw_metadata.get("task_id"),
        "task_id",
        strict=validate_workspace_mode,
    )
    normalized["task_id"] = task_id

    for key in ("client_id", "session_id", "project_id"):
        value = _clean_command_bundle_metadata_text(raw_metadata.get(key), key, strict=validate_workspace_mode)
        if value is not None:
            normalized[key] = value

    return normalized


def _normalize_command_bundle_metadata(record: dict[str, object]) -> dict[str, object]:
    raw_metadata = record.get("metadata")
    return _merge_command_bundle_metadata(record.get("cwd", "."), raw_metadata if isinstance(raw_metadata, dict) else None)


def _indexed_command_bundle_by_request_key(
    request_key: str,
    *,
    root: Path,
) -> tuple[Path, dict[str, object]] | None:
    slot_path = _request_key_slot_path(request_key, root=root)
    if not slot_path.exists():
        return None

    try:
        slot = _read_json(slot_path)
        bundle_id = slot.get("bundle_id")
        if slot.get("request_key") != request_key or not isinstance(bundle_id, str):
            raise ValueError("Stale request-key slot.")
        bundle_path, record = _find_command_bundle(
            bundle_id,
            directories=_command_bundle_dirs_for_root(root),
        )
        if record.get("request_key") != request_key:
            raise ValueError("Request-key slot does not match its canonical bundle.")
    except (OSError, ValueError, json.JSONDecodeError, FileNotFoundError):
        slot_path.unlink(missing_ok=True)
        return None

    if slot.get("status") != bundle_path.parent.name:
        _sync_request_key_slot(bundle_path, record, root=root)
    return bundle_path, record


def _scan_request_key_directories(
    request_key: str,
    directories: list[Path],
) -> tuple[Path, dict[str, object]] | None:
    for directory in directories:
        if not directory.exists():
            continue
        for path in directory.glob("cmd-*.json"):
            try:
                record = _read_json(path)
            except Exception:
                continue
            if record.get("request_key") != request_key:
                continue
            record["status"] = directory.name
            return path, record
    return None


def _recent_terminal_bundle_paths(
    directories: list[Path],
    *,
    limit: int = REQUEST_KEY_TERMINAL_FALLBACK_LIMIT,
) -> list[Path]:
    """Select a bounded compatibility window using metadata only."""

    newest: list[tuple[int, str]] = []
    for directory in directories:
        try:
            entries = os.scandir(directory)
        except OSError:
            continue
        with entries:
            for entry in entries:
                if not entry.name.startswith("cmd-") or not entry.name.endswith(".json"):
                    continue
                try:
                    mtime_ns = entry.stat(follow_symlinks=False).st_mtime_ns
                except OSError:
                    continue
                candidate = (mtime_ns, entry.path)
                if len(newest) < limit:
                    heapq.heappush(newest, candidate)
                elif candidate > newest[0]:
                    heapq.heapreplace(newest, candidate)
    return [Path(path) for _, path in sorted(newest, reverse=True)]


def _scan_recent_terminal_bundles_by_request_key(
    request_key: str,
    directories: list[Path],
) -> tuple[Path, dict[str, object]] | None:
    for path in _recent_terminal_bundle_paths(directories):
        try:
            record = _read_json(path)
        except Exception:
            continue
        if record.get("request_key") != request_key:
            continue
        record["status"] = path.parent.name
        return path, record
    return None


def _has_command_bundle_files(directories: list[Path]) -> bool:
    for directory in directories:
        try:
            entries = os.scandir(directory)
        except OSError:
            continue
        with entries:
            if any(
                entry.name.startswith("cmd-") and entry.name.endswith(".json")
                for entry in entries
            ):
                return True
    return False


def _find_command_bundle_by_request_key(
    request_key: str,
    *,
    include_terminal_fallback: bool = True,
    root: Path | None = None,
) -> tuple[Path, dict[str, object]] | None:
    bundle_root = root or _command_bundles_root()
    indexed = _indexed_command_bundle_by_request_key(request_key, root=bundle_root)
    if indexed is not None:
        return indexed

    directories = _command_bundle_dirs_for_root(bundle_root)
    active_dirs = [directory for directory in directories if directory.name in ACTIVE_BUNDLE_STATUSES]
    active = _scan_request_key_directories(request_key, active_dirs)
    if active is not None:
        path, record = active
        _sync_request_key_slot(path, record, root=bundle_root)
        return active

    if not include_terminal_fallback:
        return None

    terminal_dirs = [directory for directory in directories if directory.name not in ACTIVE_BUNDLE_STATUSES]
    if not _has_command_bundle_files(terminal_dirs):
        return None
    terminal = _scan_recent_terminal_bundles_by_request_key(request_key, terminal_dirs)
    if terminal is not None:
        path, record = terminal
        _sync_request_key_slot(path, record, root=bundle_root)
    return terminal


def _write_pending_command_bundle(
    path: Path,
    record: dict[str, object],
) -> tuple[Path, dict[str, object], bool]:
    """Create one pending record and its request-key slot under a short lock."""

    request_key = _request_key_from_record(record)
    if request_key is None:
        _write_command_bundle(path, record)
        _publish_command_bundle_change(path, record)
        return path, record, True

    root = path.parent.parent
    with _request_key_lock(request_key, root=root):
        existing = _find_command_bundle_by_request_key(
            request_key,
            include_terminal_fallback=False,
            root=root,
        )
        if existing is not None:
            existing_path, existing_record = existing
            return existing_path, existing_record, False

        _write_command_bundle(path, record)
        _publish_command_bundle_change(path, record)
        return path, record, True


def _move_command_bundle(
    bundle_id: str,
    target_status: str,
    updates: dict[str, object] | None = None,
    *,
    directories: list[Path] | None = None,
) -> dict[str, object]:
    source_path, record = _find_command_bundle(bundle_id, directories=directories)
    if target_status == "rejected" and source_path.parent.name == "pending":
        return _reject_pending_command_bundle(
            bundle_id,
            updates,
            pending_dir=source_path.parent,
            running_dir=_command_bundle_directory_for_status(
                "running",
                directories=directories,
            ),
            rejected_dir=_command_bundle_directory_for_status(
                "rejected",
                directories=directories,
            ),
        )

    now = _now_iso()
    record["status"] = target_status
    record["updated_at"] = now

    if updates:
        record.update(updates)

    target_path = (
        _command_bundle_directory_for_status(target_status, directories=directories)
        / f"{bundle_id}.json"
    )
    if target_path != source_path and target_path.exists():
        raise BundleStateError(f"Target command bundle already exists: {bundle_id}")
    _write_command_bundle(source_path, record)
    if source_path != target_path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source_path, target_path)
        _fsync_directory(source_path.parent)
        _fsync_directory(target_path.parent)
    _publish_command_bundle_change(target_path, record)
    if target_status in {"applied", "failed", "interrupted", "rejected"}:
        write_handoff_from_bundle(record)

    return record


def _bundle_risk_rank(risk: str) -> int:
    order = {"low": 0, "medium": 1, "high": 2, "blocked": 3}
    return order.get(risk, 3)


def _combined_bundle_risk(
    risks: list[str],
) -> Literal["low", "medium", "high", "blocked"]:
    if not risks:
        return "low"
    worst = max(risks, key=_bundle_risk_rank)
    if worst not in {"low", "medium", "high", "blocked"}:
        return "blocked"
    return worst  # type: ignore[return-value]
