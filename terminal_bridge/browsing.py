from __future__ import annotations

from pathlib import Path

from terminal_bridge.config import BLOCKED_DIR_NAMES, MAX_READ_CHARS, MAX_TREE_ENTRIES, WORKSPACE_ROOT
from terminal_bridge.models import ListEntry, ListResult, ReadFileResult, TreeResult
from terminal_bridge.safety import _is_blocked_name, _relative, _resolve_workspace_path
from terminal_bridge.storage import _sha256_bytes


def _is_safe_visible_path(path: Path) -> bool:
    try:
        rel_parts = path.resolve(strict=False).relative_to(WORKSPACE_ROOT).parts
    except ValueError:
        return False

    if any(part in BLOCKED_DIR_NAMES for part in rel_parts):
        return False

    if path.name.startswith(".") or _is_blocked_name(path.name):
        return False

    return True


def _iter_visible_paths(root: Path, max_entries: int) -> tuple[list[Path], bool]:
    paths: list[Path] = []
    truncated = False

    def walk(current: Path) -> None:
        nonlocal truncated

        if truncated:
            return

        try:
            children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return

        for child in children:
            if not _is_safe_visible_path(child):
                continue

            paths.append(child)
            if len(paths) >= max_entries:
                truncated = True
                return

            if child.is_dir():
                walk(child)

    walk(root)
    return paths, truncated


def _list_workspace(path: str, include_hidden: bool) -> ListResult:
    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {_relative(target)}")

    entries: list[ListEntry] = []

    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if not include_hidden and child.name.startswith("."):
            continue
        if child.name in BLOCKED_DIR_NAMES or _is_blocked_name(child.name):
            continue

        kind = "directory" if child.is_dir() else "file" if child.is_file() else "other"

        size_bytes: int | None = None
        if child.is_file():
            try:
                size_bytes = child.stat().st_size
            except OSError:
                size_bytes = None

        entries.append(
            ListEntry(
                name=child.name,
                path=_relative(child),
                kind=kind,
                size_bytes=size_bytes,
            )
        )

    return ListResult(path=_relative(target), entries=entries)


def _tree_workspace(path: str, max_depth: int, max_entries: int) -> TreeResult:
    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {_relative(target)}")

    max_entries = min(max_entries, MAX_TREE_ENTRIES)
    lines: list[str] = []
    truncated = False

    def walk(current: Path, depth: int, prefix: str = "") -> None:
        nonlocal truncated

        if truncated or depth > max_depth:
            return

        try:
            children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as exc:
            lines.append(f"{prefix}[error: {exc}]")
            return

        visible_children = [
            child
            for child in children
            if child.name not in BLOCKED_DIR_NAMES
            and not _is_blocked_name(child.name)
            and not child.name.startswith(".")
        ]

        for index, child in enumerate(visible_children):
            if len(lines) >= max_entries:
                truncated = True
                return

            connector = "└── " if index == len(visible_children) - 1 else "├── "
            suffix = "/" if child.is_dir() else ""
            lines.append(f"{prefix}{connector}{child.name}{suffix}")

            if child.is_dir():
                extension = "    " if index == len(visible_children) - 1 else "│   "
                walk(child, depth + 1, prefix + extension)

    lines.append(f"{_relative(target)}/")
    walk(target, 1)

    return TreeResult(path=_relative(target), entries=lines, truncated=truncated)


def _read_workspace_file(path: str, offset: int, limit: int) -> ReadFileResult:
    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"File does not exist: {_relative(target)}")

    if not target.is_file():
        raise IsADirectoryError(f"Path is not a file: {_relative(target)}")

    raw = target.read_bytes()

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Only UTF-8 text files are supported.") from exc

    limit = min(limit, MAX_READ_CHARS)
    sliced = text[offset : offset + limit]
    truncated = offset + limit < len(text)

    return ReadFileResult(
        path=_relative(target),
        content=sliced,
        truncated=truncated,
        size_bytes=len(raw),
        sha256=_sha256_bytes(raw),
    )
