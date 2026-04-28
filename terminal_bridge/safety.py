from __future__ import annotations

import fnmatch
from pathlib import Path

from terminal_bridge.config import BLOCKED_DIR_NAMES, BLOCKED_FILE_PATTERNS, WORKSPACE_ROOT
from terminal_bridge.storage import _sha256_bytes


def _is_blocked_name(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in BLOCKED_FILE_PATTERNS)


def _resolve_workspace_path(path: str) -> Path:
    if not WORKSPACE_ROOT.exists() or not WORKSPACE_ROOT.is_dir():
        raise FileNotFoundError(f"Workspace root does not exist: {WORKSPACE_ROOT}")

    if not path or path.strip() == "":
        path = "."

    raw = Path(path).expanduser()

    if raw.is_absolute():
        raise ValueError("Absolute paths are not allowed. Use a path relative to WORKSPACE_ROOT.")

    candidate = (WORKSPACE_ROOT / raw).resolve(strict=False)

    if candidate != WORKSPACE_ROOT and not candidate.is_relative_to(WORKSPACE_ROOT):
        raise ValueError("Path escapes WORKSPACE_ROOT and is rejected.")

    relative_parts = candidate.relative_to(WORKSPACE_ROOT).parts

    for part in relative_parts:
        if part == "..":
            raise ValueError("Path traversal is not allowed.")
        if part in BLOCKED_DIR_NAMES:
            raise PermissionError(f"Blocked directory name: {part}")

    if _is_blocked_name(candidate.name):
        raise PermissionError(f"Blocked secret-like file name: {candidate.name}")

    return candidate


def _relative(path: Path) -> str:
    if path == WORKSPACE_ROOT:
        return "."
    return str(path.relative_to(WORKSPACE_ROOT))


def _validate_expected_sha256(path: Path, expected_sha256: str | None) -> None:
    if expected_sha256 is None:
        return
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Cannot check sha256 because file does not exist: {_relative(path)}")
    actual = _sha256_bytes(path.read_bytes())
    if actual != expected_sha256:
        raise ValueError(
            f"sha256 mismatch for {_relative(path)}. expected={expected_sha256}, actual={actual}"
        )
