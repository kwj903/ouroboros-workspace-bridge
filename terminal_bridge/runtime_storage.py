from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


PROTECTED_ROOT_FILES = {"session.json", "session.env", "intent_hmac_secret"}
PROTECTED_PID_GLOB = "processes/*.pid"

LOG_SIZE_LIMIT_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class StorageEntry:
    name: str
    path: Path
    exists: bool
    bytes: int
    files: int
    dirs: int


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


def runtime_paths(root: Path, workspace_root: Path) -> list[tuple[str, Path]]:
    return [
        ("Project checkout", Path(__file__).resolve().parent.parent),
        ("Runtime data", root),
        ("Session config", root / "session.json"),
        ("Legacy session env", root / "session.env"),
        ("Intent HMAC secret", root / "intent_hmac_secret"),
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
        if child.is_symlink() or not _safe_child(child, root):
            continue
        if child.name in PROTECTED_ROOT_FILES:
            continue
        if _mtime_older_than(child, cutoff):
            candidates.append(
                CleanupCandidate(
                    path=child,
                    kind="dir" if child.is_dir() else "file",
                    bytes=_path_size(child),
                    reason=reason,
                )
            )


def cleanup_candidates(root: Path, *, older_than_days: int | None = None, include_backups: bool = False) -> list[CleanupCandidate]:
    candidates: list[CleanupCandidate] = []
    root = root.expanduser().resolve(strict=False)
    operational_days = older_than_days or 30
    bundle_days = older_than_days or 60
    payload_days = older_than_days or 14
    backup_days = older_than_days or 30

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

    if include_backups:
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

    return [candidate for candidate in candidates if is_deletable_candidate(candidate, root)]


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
    include_backups: bool = False,
) -> CleanupResult:
    root = root.expanduser().resolve(strict=False)
    candidates = cleanup_candidates(root, older_than_days=older_than_days, include_backups=include_backups)
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
