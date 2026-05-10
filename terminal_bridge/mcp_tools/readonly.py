from __future__ import annotations

import fnmatch
from collections.abc import Callable

from terminal_bridge.browsing import (
    _is_safe_visible_path,
    _iter_visible_paths,
    _tree_workspace,
)
from terminal_bridge.models import (
    CommandResult,
    FileMatchEntry,
    FindFilesResult,
    ProjectSnapshotResult,
    ReadManyFileEntry,
    ReadManyFilesResult,
    SearchTextMatch,
    SearchTextResult,
)
from terminal_bridge.patches import _truncate
from terminal_bridge.safety import _relative, _resolve_workspace_path
from terminal_bridge.storage import _sha256_bytes


RunCommand = Callable[..., CommandResult]


def find_files(
    path: str = ".",
    pattern: str = "*",
    include_files: bool = True,
    include_directories: bool = False,
    max_entries: int = 100,
) -> FindFilesResult:
    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {_relative(target)}")

    if pattern.strip() == "":
        raise ValueError("pattern cannot be empty.")

    scan_limit = min(max(max_entries * 20, 500), 3000)
    paths, scan_truncated = _iter_visible_paths(target, scan_limit)

    entries: list[FileMatchEntry] = []
    truncated = scan_truncated

    for item in paths:
        rel = _relative(item)
        kind = "directory" if item.is_dir() else "file" if item.is_file() else "other"

        if kind == "file" and not include_files:
            continue
        if kind == "directory" and not include_directories:
            continue

        if not (fnmatch.fnmatch(item.name, pattern) or fnmatch.fnmatch(rel, pattern)):
            continue

        size_bytes: int | None = None
        if item.is_file():
            try:
                size_bytes = item.stat().st_size
            except OSError:
                size_bytes = None

        entries.append(FileMatchEntry(path=rel, kind=kind, size_bytes=size_bytes))

        if len(entries) >= max_entries:
            truncated = True
            break

    return FindFilesResult(
        path=_relative(target),
        pattern=pattern,
        entries=entries,
        count=len(entries),
        truncated=truncated,
    )


def search_text(
    query: str,
    path: str = ".",
    file_glob: str = "*",
    case_sensitive: bool = False,
    max_matches: int = 100,
    max_file_bytes: int = 500_000,
) -> SearchTextResult:
    if query == "":
        raise ValueError("query cannot be empty.")

    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {_relative(target)}")

    needle = query if case_sensitive else query.lower()
    paths, scan_truncated = _iter_visible_paths(target, 5000)

    matches: list[SearchTextMatch] = []
    truncated = scan_truncated

    for item in paths:
        if not item.is_file():
            continue

        rel = _relative(item)

        if not (
            fnmatch.fnmatch(item.name, file_glob) or fnmatch.fnmatch(rel, file_glob)
        ):
            continue

        try:
            if item.stat().st_size > max_file_bytes:
                continue
        except OSError:
            continue

        try:
            text = item.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError:
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            haystack = line if case_sensitive else line.lower()
            if needle not in haystack:
                continue

            display_line = line
            if len(display_line) > 500:
                display_line = display_line[:500] + "..."

            matches.append(
                SearchTextMatch(
                    path=rel,
                    line_number=line_number,
                    line=display_line,
                )
            )

            if len(matches) >= max_matches:
                truncated = True
                return SearchTextResult(
                    query=query,
                    path=_relative(target),
                    matches=matches,
                    count=len(matches),
                    truncated=truncated,
                )

    return SearchTextResult(
        query=query,
        path=_relative(target),
        matches=matches,
        count=len(matches),
        truncated=truncated,
    )


def read_many_files(
    paths: list[str],
    limit_per_file: int = 20_000,
    total_limit: int = 100_000,
) -> ReadManyFilesResult:
    if not paths:
        raise ValueError("paths cannot be empty.")

    entries: list[ReadManyFileEntry] = []
    remaining = total_limit
    truncated = False

    for raw_path in paths:
        if remaining <= 0:
            truncated = True
            entries.append(
                ReadManyFileEntry(
                    path=raw_path,
                    error="Total output limit reached before reading this file.",
                    truncated=True,
                )
            )
            continue

        try:
            target = _resolve_workspace_path(raw_path)

            if not target.exists():
                raise FileNotFoundError(f"File does not exist: {_relative(target)}")

            if not target.is_file():
                raise IsADirectoryError(f"Path is not a file: {_relative(target)}")

            raw = target.read_bytes()
            text = raw.decode("utf-8")

            local_limit = min(limit_per_file, remaining)
            content, file_truncated = _truncate(text, local_limit)
            remaining -= len(content)
            truncated = truncated or file_truncated or len(content) < len(text)

            entries.append(
                ReadManyFileEntry(
                    path=_relative(target),
                    content=content,
                    truncated=file_truncated,
                    size_bytes=len(raw),
                    sha256=_sha256_bytes(raw),
                )
            )

        except Exception as exc:
            entries.append(
                ReadManyFileEntry(
                    path=raw_path,
                    error=f"{type(exc).__name__}: {exc}",
                    truncated=False,
                )
            )

    return ReadManyFilesResult(entries=entries, count=len(entries), truncated=truncated)


def project_snapshot(
    run_command: RunCommand,
    path: str = ".",
    max_depth: int = 2,
    max_entries: int = 120,
) -> ProjectSnapshotResult:
    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {_relative(target)}")

    tree_result = _tree_workspace(
        path=_relative(target),
        max_depth=max_depth,
        max_entries=max_entries,
    )

    key_names = [
        "README.md",
        "pyproject.toml",
        "uv.lock",
        "package.json",
        "go.mod",
        "Cargo.toml",
        "requirements.txt",
        "Makefile",
        "Dockerfile",
        ".python-version",
    ]

    key_files: list[str] = []
    for name in key_names:
        candidate = target / name
        if candidate.exists() and candidate.is_file() and _is_safe_visible_path(candidate):
            key_files.append(_relative(candidate))

    git_status_result = run_command(
        cwd=_relative(target),
        command=["git", "status", "--short", "--branch"],
        timeout_seconds=15,
    )

    git_status = git_status_result.stdout
    if git_status_result.stderr:
        git_status = (git_status + "\n" + git_status_result.stderr).strip()

    return ProjectSnapshotResult(
        path=_relative(target),
        tree=tree_result.entries,
        key_files=key_files,
        git_status=git_status,
        truncated=tree_result.truncated or git_status_result.truncated,
    )
