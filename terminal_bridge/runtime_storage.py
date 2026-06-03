from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROTECTED_ROOT_FILES = {"session.json", "session.env", "intent_hmac_secret"}
PROTECTED_PID_GLOB = "processes/*.pid"

LOG_SIZE_LIMIT_BYTES = 10 * 1024 * 1024
DEFAULT_OLDER_THAN_BUNDLE_DAYS = 60
CLEANUP_POLICY_FILENAME = "cleanup_policy.json"


@dataclass(frozen=True)
class StorageEntry:
    name: str
    path: Path
    exists: bool
    bytes: int
    files: int
    dirs: int


@dataclass(frozen=True)
class CleanupPolicy:
    keep_applied: int = 1000
    keep_failed: int = 500
    keep_rejected: int = 200
    keep_tool_calls: int = 2000
    keep_handoffs: int = 1000
    keep_text_payloads: int = 500
    older_than_text_payload_days: int = 14
    older_than_operations_days: int = 30
    older_than_backups_days: int = 30
    include_backups_by_default: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CleanupCandidate:
    path: Path
    kind: str
    bytes: int
    reason: str
    action: str = "delete"


@dataclass(frozen=True)
class CleanupError:
    path: Path
    error: str


@dataclass(frozen=True)
class CleanupResult:
    dry_run: bool
    candidates: list[CleanupCandidate]
    deleted_files: int
    deleted_dirs: int
    reclaimed_bytes: int
    errors: list[CleanupError]


class CleanupPolicyValidationError(ValueError):
    """Raised when a runtime cleanup policy cannot be validated."""


_POLICY_INT_FIELDS = (
    "keep_applied",
    "keep_failed",
    "keep_rejected",
    "keep_tool_calls",
    "keep_handoffs",
    "keep_text_payloads",
    "older_than_text_payload_days",
    "older_than_operations_days",
    "older_than_backups_days",
)
_POLICY_BOOL_FIELDS = ("include_backups_by_default",)


def default_cleanup_policy() -> CleanupPolicy:
    return CleanupPolicy()


def cleanup_policy_path(root: Path) -> Path:
    return root.expanduser().resolve(strict=False) / CLEANUP_POLICY_FILENAME


def _coerce_policy_int(name: str, value: object, default: int, *, allow_zero: bool) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise CleanupPolicyValidationError(f"{name} must be an integer")
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise CleanupPolicyValidationError(f"{name} must be an integer") from exc
    if coerced < 0:
        raise CleanupPolicyValidationError(f"{name} must not be negative")
    if coerced == 0 and not allow_zero:
        raise CleanupPolicyValidationError(f"{name} must be greater than zero")
    return coerced


def _coerce_policy_bool(name: str, value: object, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise CleanupPolicyValidationError(f"{name} must be a boolean")


def validate_cleanup_policy(data: CleanupPolicy | dict[str, object] | None, *, allow_zero: bool = False) -> CleanupPolicy:
    if data is None:
        return default_cleanup_policy()
    if isinstance(data, CleanupPolicy):
        data = data.as_dict()
    if not isinstance(data, dict):
        raise CleanupPolicyValidationError("cleanup policy must be a mapping")

    defaults = default_cleanup_policy().as_dict()
    values: dict[str, object] = {}
    for name in _POLICY_INT_FIELDS:
        values[name] = _coerce_policy_int(name, data.get(name, defaults[name]), int(defaults[name]), allow_zero=allow_zero)
    for name in _POLICY_BOOL_FIELDS:
        values[name] = _coerce_policy_bool(name, data.get(name, defaults[name]), bool(defaults[name]))
    return CleanupPolicy(**values)


def load_cleanup_policy(root: Path) -> CleanupPolicy:
    path = cleanup_policy_path(root)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return validate_cleanup_policy(data)
    except (OSError, json.JSONDecodeError, CleanupPolicyValidationError):
        return default_cleanup_policy()


def save_cleanup_policy(root: Path, policy: CleanupPolicy | dict[str, object]) -> CleanupPolicy:
    validated = validate_cleanup_policy(policy)
    path = cleanup_policy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(validated.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)
    return validated


def runtime_paths(root: Path, workspace_root: Path) -> list[tuple[str, Path]]:
    return [
        ("Project checkout", Path(__file__).resolve().parent.parent),
        ("Runtime data", root),
        ("Session config", root / "session.json"),
        ("Legacy session env", root / "session.env"),
        ("Intent HMAC secret", root / "intent_hmac_secret"),
        ("Cleanup policy", cleanup_policy_path(root)),
        ("Process/log directory", root / "processes"),
        ("Command bundles directory", root / "command_bundles"),
        ("Backups directory", root / "backups"),
        ("Trash directory", root / "trash"),
        ("Workspace root", workspace_root),
    ]


def category_paths(root: Path) -> list[tuple[str, Path]]:
    return [
        ("audit.jsonl", root / "audit.jsonl"),
        ("processes", root / "processes"),
        ("command_bundles", root / "command_bundles"),
        ("command_bundle_file_backups", root / "command_bundle_file_backups"),
        ("backups", root / "backups"),
        ("trash", root / "trash"),
        ("operations", root / "operations"),
        ("tasks", root / "tasks"),
        ("text_payloads", root / "text_payloads"),
        ("tool_calls", root / "tool_calls"),
        ("handoffs", root / "handoffs"),
        ("intent_imports", root / "intent_imports"),
    ]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_child(path: Path, root: Path) -> bool:
    try:
        resolved_root = root.resolve(strict=False)
        resolved_path = path.resolve(strict=False)
    except OSError:
        return False
    return resolved_path == resolved_root or _is_relative_to(resolved_path, resolved_root)


def _entry_size(path: Path) -> tuple[int, int, int]:
    if not path.exists() or path.is_symlink():
        return (0, 0, 0)
    if path.is_file():
        try:
            return (path.stat().st_size, 1, 0)
        except OSError:
            return (0, 0, 0)
    if not path.is_dir():
        return (0, 0, 0)

    total = 0
    files = 0
    dirs = 0
    for child in path.rglob("*"):
        try:
            if child.is_symlink():
                continue
            if child.is_file():
                total += child.stat().st_size
                files += 1
            elif child.is_dir():
                dirs += 1
        except OSError:
            continue
    return (total, files, dirs)


def storage_summary(root: Path) -> list[StorageEntry]:
    entries: list[StorageEntry] = []
    for name, path in category_paths(root):
        size, files, dirs = _entry_size(path)
        entries.append(StorageEntry(name=name, path=path, exists=path.exists(), bytes=size, files=files, dirs=dirs))
    return sorted(entries, key=lambda entry: entry.bytes, reverse=True)


def total_storage(root: Path) -> StorageEntry:
    size, files, dirs = _entry_size(root)
    return StorageEntry(name="runtime_root", path=root, exists=root.exists(), bytes=size, files=files, dirs=dirs)


def format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{value} B"


def _mtime_older_than(path: Path, cutoff: float) -> bool:
    try:
        return path.stat().st_mtime < cutoff
    except OSError:
        return False


def _path_size(path: Path) -> int:
    return _entry_size(path)[0]


def _candidate_kind(path: Path) -> str:
    return "dir" if path.is_dir() and not path.is_symlink() else "file"


def _add_candidate(candidates: list[CleanupCandidate], root: Path, child: Path, reason: str) -> None:
    if child.is_symlink() or not _safe_child(child, root):
        return
    candidates.append(
        CleanupCandidate(
            path=child,
            kind=_candidate_kind(child),
            bytes=_path_size(child),
            reason=reason,
        )
    )


def _add_children_older_than(
    candidates: list[CleanupCandidate],
    root: Path,
    directory: Path,
    days: int,
    reason: str,
) -> None:
    if not directory.exists() or directory.is_symlink() or not directory.is_dir():
        return
    cutoff = time.time() - (days * 86400)
    for child in directory.iterdir():
        if child.name in PROTECTED_ROOT_FILES:
            continue
        if _mtime_older_than(child, cutoff):
            _add_candidate(candidates, root, child, reason)


def _timestamp_from_value(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _metadata_timestamp(path: Path) -> float | None:
    if not path.is_file() or path.suffix.lower() != ".json":
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for key in ("updated_at", "completed_at", "created_at", "started_at", "timestamp", "archived_at"):
        timestamp = _timestamp_from_value(data.get(key))
        if timestamp is not None:
            return timestamp
    return None


def _record_timestamp(path: Path) -> float:
    metadata_time = _metadata_timestamp(path)
    if metadata_time is not None:
        return metadata_time
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _sorted_record_children(root: Path, directory: Path) -> list[Path]:
    if not directory.exists() or directory.is_symlink() or not directory.is_dir():
        return []
    children: list[Path] = []
    for child in directory.iterdir():
        if child.is_symlink() or not _safe_child(child, root):
            continue
        children.append(child)
    return sorted(children, key=_record_timestamp, reverse=True)


def _add_count_candidates(
    candidates: list[CleanupCandidate],
    root: Path,
    directory: Path,
    keep_count: int,
    reason: str,
) -> None:
    children = _sorted_record_children(root, directory)
    for child in children[keep_count:]:
        _add_candidate(candidates, root, child, reason)


def _add_all_children(candidates: list[CleanupCandidate], root: Path, directory: Path, reason: str) -> None:
    for child in _sorted_record_children(root, directory):
        _add_candidate(candidates, root, child, reason)


def _dedupe_candidates(candidates: list[CleanupCandidate], root: Path) -> list[CleanupCandidate]:
    deduped: dict[Path, CleanupCandidate] = {}
    for candidate in candidates:
        if not is_deletable_candidate(candidate, root):
            continue
        key = candidate.path.resolve(strict=False)
        if key not in deduped:
            deduped[key] = candidate
    return list(deduped.values())


def cleanup_candidates(
    root: Path,
    *,
    older_than_days: int | None = None,
    include_backups: bool | None = None,
    policy: CleanupPolicy | dict[str, object] | None = None,
    prune_all_history: bool = False,
) -> list[CleanupCandidate]:
    candidates: list[CleanupCandidate] = []
    root = root.expanduser().resolve(strict=False)
    resolved_policy = validate_cleanup_policy(policy) if policy is not None else load_cleanup_policy(root)
    include_backup_candidates = resolved_policy.include_backups_by_default if include_backups is None else include_backups

    if prune_all_history:
        for state in ("applied", "failed", "rejected"):
            _add_all_children(
                candidates,
                root,
                root / "command_bundles" / state,
                f"clear-history command bundle {state}",
            )
        for name in ("tool_calls", "handoffs", "operations", "text_payloads", "intent_imports", "trash"):
            _add_all_children(candidates, root, root / name, "clear-history eligible record")
        if include_backup_candidates:
            for name in ("backups", "command_bundle_file_backups"):
                _add_all_children(candidates, root, root / name, "clear-history backup/trash eligible record")
        return _dedupe_candidates(candidates, root)

    operational_days = older_than_days or resolved_policy.older_than_operations_days
    bundle_days = older_than_days or DEFAULT_OLDER_THAN_BUNDLE_DAYS
    payload_days = older_than_days or resolved_policy.older_than_text_payload_days
    backup_days = older_than_days or resolved_policy.older_than_backups_days

    for name in ("tool_calls", "operations", "handoffs", "intent_imports"):
        _add_children_older_than(candidates, root, root / name, operational_days, f"older than {operational_days} days")

    for state in ("applied", "rejected", "failed"):
        _add_children_older_than(
            candidates,
            root,
            root / "command_bundles" / state,
            bundle_days,
            f"command bundle {state} older than {bundle_days} days",
        )

    _add_children_older_than(candidates, root, root / "text_payloads", payload_days, f"older than {payload_days} days")

    _add_count_candidates(
        candidates,
        root,
        root / "command_bundles" / "applied",
        resolved_policy.keep_applied,
        f"older than newest {resolved_policy.keep_applied} applied bundle records",
    )
    _add_count_candidates(
        candidates,
        root,
        root / "command_bundles" / "failed",
        resolved_policy.keep_failed,
        f"older than newest {resolved_policy.keep_failed} failed bundle records",
    )
    _add_count_candidates(
        candidates,
        root,
        root / "command_bundles" / "rejected",
        resolved_policy.keep_rejected,
        f"older than newest {resolved_policy.keep_rejected} rejected bundle records",
    )
    _add_count_candidates(
        candidates,
        root,
        root / "tool_calls",
        resolved_policy.keep_tool_calls,
        f"older than newest {resolved_policy.keep_tool_calls} tool call records",
    )
    _add_count_candidates(
        candidates,
        root,
        root / "handoffs",
        resolved_policy.keep_handoffs,
        f"older than newest {resolved_policy.keep_handoffs} handoff records",
    )
    _add_count_candidates(
        candidates,
        root,
        root / "text_payloads",
        resolved_policy.keep_text_payloads,
        f"older than newest {resolved_policy.keep_text_payloads} text payload records",
    )

    if include_backup_candidates:
        for name in ("backups", "command_bundle_file_backups", "trash"):
            _add_children_older_than(candidates, root, root / name, backup_days, f"backup/trash older than {backup_days} days")

    processes = root / "processes"
    if processes.exists() and processes.is_dir() and not processes.is_symlink():
        for path in processes.glob("*.log"):
            if path.is_symlink() or not _safe_child(path, root):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > LOG_SIZE_LIMIT_BYTES:
                candidates.append(CleanupCandidate(path=path, kind="file", bytes=size, reason="process log exceeds 10 MB", action="candidate"))

    audit_log = root / "audit.jsonl"
    if audit_log.exists() and not audit_log.is_symlink():
        try:
            size = audit_log.stat().st_size
        except OSError:
            size = 0
        if size > LOG_SIZE_LIMIT_BYTES:
            candidates.append(CleanupCandidate(path=audit_log, kind="file", bytes=size, reason="audit log exceeds 10 MB", action="candidate"))

    return _dedupe_candidates(candidates, root)


def is_deletable_candidate(candidate: CleanupCandidate, root: Path) -> bool:
    path = candidate.path
    root = root.expanduser().resolve(strict=False)
    if candidate.action != "delete":
        return True
    if path.is_symlink() or not _safe_child(path, root):
        return False
    try:
        rel = path.resolve(strict=False).relative_to(root)
    except ValueError:
        return False
    if rel.parts and rel.parts[0] == "command_bundles" and len(rel.parts) > 1 and rel.parts[1] == "pending":
        return False
    if len(rel.parts) == 1 and rel.parts[0] in PROTECTED_ROOT_FILES:
        return False
    if len(rel.parts) == 2 and rel.parts[0] == "processes" and rel.parts[1].endswith(".pid"):
        return False
    return True


def _delete_path(path: Path) -> tuple[int, int]:
    if path.is_dir() and not path.is_symlink():
        files = 0
        dirs = 1
        for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if child.is_symlink():
                child.unlink()
                files += 1
            elif child.is_file():
                child.unlink()
                files += 1
            elif child.is_dir():
                child.rmdir()
                dirs += 1
        path.rmdir()
        return files, dirs
    path.unlink()
    return 1, 0


def cleanup_runtime(
    root: Path,
    *,
    dry_run: bool = True,
    older_than_days: int | None = None,
    include_backups: bool | None = None,
    policy: CleanupPolicy | dict[str, object] | None = None,
    prune_all_history: bool = False,
) -> CleanupResult:
    root = root.expanduser().resolve(strict=False)
    candidates = cleanup_candidates(
        root,
        older_than_days=older_than_days,
        include_backups=include_backups,
        policy=policy,
        prune_all_history=prune_all_history,
    )
    if dry_run:
        return CleanupResult(True, candidates, 0, 0, 0, [])

    deleted_files = 0
    deleted_dirs = 0
    reclaimed = 0
    errors: list[CleanupError] = []

    for candidate in candidates:
        if candidate.action != "delete":
            continue
        if not is_deletable_candidate(candidate, root):
            continue
        try:
            files, dirs = _delete_path(candidate.path)
            deleted_files += files
            deleted_dirs += dirs
            reclaimed += candidate.bytes
        except Exception as exc:
            errors.append(CleanupError(candidate.path, f"{type(exc).__name__}: {exc}"))

    return CleanupResult(False, candidates, deleted_files, deleted_dirs, reclaimed, errors)
