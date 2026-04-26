from __future__ import annotations

import subprocess
from pathlib import Path

from terminal_bridge.commands import _safe_env
from terminal_bridge.config import BLOCKED_DIR_NAMES, MAX_STDERR_CHARS, MAX_STDOUT_CHARS, WORKSPACE_ROOT
from terminal_bridge.models import CommandResult
from terminal_bridge.safety import _is_blocked_name, _relative, _resolve_workspace_path


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _clean_patch_path(raw_path: str) -> str | None:
    value = raw_path.strip()

    if "\t" in value:
        value = value.split("\t", 1)[0]

    if value == "/dev/null":
        return None

    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]

    if value == "":
        return None

    path = Path(value)

    if path.is_absolute() or value.startswith("~") or ".." in path.parts:
        raise ValueError(f"Unsafe patch path: {raw_path}")

    if value.startswith(".git/") or "/.git/" in value:
        raise PermissionError(f"Patch path touches .git: {raw_path}")

    return value


def _extract_patch_paths(patch: str) -> list[str]:
    paths: set[str] = set()

    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                for raw in (parts[2], parts[3]):
                    cleaned = _clean_patch_path(raw)
                    if cleaned is not None:
                        paths.add(cleaned)

        elif line.startswith("--- ") or line.startswith("+++ "):
            cleaned = _clean_patch_path(line[4:])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("rename from "):
            cleaned = _clean_patch_path(line[len("rename from ") :])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("rename to "):
            cleaned = _clean_patch_path(line[len("rename to ") :])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("copy from "):
            cleaned = _clean_patch_path(line[len("copy from ") :])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("copy to "):
            cleaned = _clean_patch_path(line[len("copy to ") :])
            if cleaned is not None:
                paths.add(cleaned)

    if not paths:
        raise ValueError("No patch file paths were found.")

    return sorted(paths)


def _resolve_patch_path(cwd: Path, patch_path: str) -> Path:
    cwd_rel = _relative(cwd)
    if cwd_rel == ".":
        combined = Path(patch_path)
    else:
        combined = Path(cwd_rel) / patch_path

    return _resolve_workspace_path(str(combined))


def _validate_patch_paths(cwd: Path, patch_paths: list[str]) -> None:
    for patch_path in patch_paths:
        target = _resolve_patch_path(cwd, patch_path)

        for part in target.relative_to(WORKSPACE_ROOT).parts:
            if part in BLOCKED_DIR_NAMES:
                raise PermissionError(f"Patch path touches blocked directory: {patch_path}")

        if _is_blocked_name(target.name):
            raise PermissionError(f"Patch path touches blocked file: {patch_path}")


def _run_git_apply_with_stdin(
    cwd: Path,
    args: list[str],
    patch: str,
    timeout_seconds: int,
) -> CommandResult:
    completed = subprocess.run(
        ["git", "apply", *args],
        input=patch,
        cwd=str(cwd),
        env=_safe_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
        shell=False,
        check=False,
    )

    stdout, out_truncated = _truncate(completed.stdout, MAX_STDOUT_CHARS)
    stderr, err_truncated = _truncate(completed.stderr, MAX_STDERR_CHARS)

    return CommandResult(
        cwd=_relative(cwd),
        command=["git", "apply", *args],
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        truncated=out_truncated or err_truncated,
    )
