from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from terminal_bridge.config import (
    APPROVAL_REQUIRED_EXECUTABLES,
    APPROVAL_REQUIRED_PATTERNS,
    BLOCKED_DIR_NAMES,
    BLOCKED_EXECUTABLES,
    PROJECT_ROOT,
    SAFE_ARG_FLAGS,
    WORKSPACE_ROOT,
)
from terminal_bridge.safety import _is_blocked_name


def _safe_env() -> dict[str, str]:
    """Return a minimal child-process environment for workspace commands.

    Secret-bearing variables are intentionally not forwarded. PATH is preserved
    from the server process so uv, mise-managed Python, Homebrew tools, and the
    project .venv/bin can be resolved when the server was started from the
    user's private shell environment.
    """
    project_root = PROJECT_ROOT
    fallback_path = ":".join(
        [
            str(project_root / ".venv/bin"),
            str(Path.home() / ".local/bin"),
            str(Path.home() / ".local/share/mise/shims"),
            str(Path.home() / ".local/share/mise/installs/python/3.12/bin"),
            "/usr/local/bin",
            "/opt/homebrew/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
        ]
    )
    path_value = os.environ.get("PATH") or fallback_path

    safe_env = {
        "PATH": path_value,
        "HOME": os.environ.get("HOME", str(Path.home())),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
    }

    for key in ("USER", "LOGNAME", "SHELL", "TERM"):
        value = os.environ.get(key)
        if value:
            safe_env[key] = value

    return safe_env


def _validate_command_args(cwd: Path, args: list[str]) -> list[str]:
    safe_args: list[str] = []

    for arg in args:
        if not isinstance(arg, str):
            raise ValueError("All args must be strings.")

        if len(arg) > 200:
            raise ValueError(f"Argument too long: {arg[:40]}...")

        if "\x00" in arg or "\n" in arg or "\r" in arg:
            raise ValueError("Arguments cannot contain control characters.")

        if arg.startswith("-"):
            if arg not in SAFE_ARG_FLAGS:
                raise ValueError(f"Flag is not allowed in MVP: {arg}")
            safe_args.append(arg)
            continue

        if arg.startswith("~") or Path(arg).is_absolute() or ".." in Path(arg).parts:
            raise ValueError(f"Unsafe path argument: {arg}")

        if "://" in arg:
            raise ValueError(f"URL-like arguments are not allowed: {arg}")

        candidate = (cwd / arg).resolve(strict=False)
        if candidate != WORKSPACE_ROOT and not candidate.is_relative_to(WORKSPACE_ROOT):
            raise ValueError(f"Argument escapes workspace: {arg}")

        for part in candidate.relative_to(WORKSPACE_ROOT).parts:
            if part in BLOCKED_DIR_NAMES:
                raise PermissionError(f"Argument touches blocked directory: {part}")

        if _is_blocked_name(candidate.name):
            raise PermissionError(f"Argument touches blocked file: {candidate.name}")

        safe_args.append(arg)

    return safe_args


def _validate_exec_argv(argv: list[str]) -> list[str]:
    if not argv:
        raise ValueError("argv cannot be empty.")

    if len(argv) > 64:
        raise ValueError("argv has too many items.")

    safe: list[str] = []
    for item in argv:
        if not isinstance(item, str):
            raise ValueError("All argv items must be strings.")
        if item == "":
            raise ValueError("argv items cannot be empty.")
        if len(item) > 1000:
            raise ValueError("argv item is too long.")
        if "\x00" in item or "\n" in item or "\r" in item:
            raise ValueError("argv items cannot contain control characters.")
        safe.append(item)

    return safe


def _classify_exec_command(
    cwd: Path,
    argv: list[str],
) -> tuple[Literal["low", "medium", "high", "blocked"], str]:
    def pathish_arg_touches_blocked_location(arg: str) -> bool:
        if arg.startswith("-") or "://" in arg:
            return False

        path = Path(arg).expanduser()
        looks_pathish = path.is_absolute() or arg.startswith("~") or "/" in arg or ".." in path.parts

        if not looks_pathish:
            return _is_blocked_name(arg)

        if path.is_absolute():
            candidate = path.resolve(strict=False)
        else:
            candidate = (cwd / path).resolve(strict=False)

        if candidate != WORKSPACE_ROOT and not candidate.is_relative_to(WORKSPACE_ROOT):
            return True

        rel_parts = candidate.relative_to(WORKSPACE_ROOT).parts
        if any(part in BLOCKED_DIR_NAMES for part in rel_parts):
            return True

        return _is_blocked_name(candidate.name)

    executable = Path(argv[0]).name
    command_text = " ".join(argv)

    if executable in BLOCKED_EXECUTABLES:
        return "blocked", f"Executable is blocked: {executable}"

    if executable in {"bash", "sh", "zsh"} and "-c" in argv[1:]:
        return "blocked", "Shell -c execution is blocked in workspace_exec."

    if any(pathish_arg_touches_blocked_location(arg) for arg in argv[1:]):
        return "blocked", "Command argument touches a blocked or out-of-workspace path."

    if executable in APPROVAL_REQUIRED_EXECUTABLES:
        return "medium", f"Executable requires approval: {executable}"

    for pattern in APPROVAL_REQUIRED_PATTERNS:
        if command_text == pattern or command_text.startswith(pattern + " "):
            return "medium", f"Command pattern requires approval: {pattern}"

    if any("://" in arg for arg in argv):
        return "medium", "URL-like argument requires approval."

    return "low", "Command is allowed for automatic workspace execution."
