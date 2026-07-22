from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Literal

from terminal_bridge.config import (
    APPROVAL_REQUIRED_EXECUTABLES,
    APPROVAL_REQUIRED_PATTERNS,
    BLOCKED_DIR_NAMES,
    BLOCKED_EXECUTABLES,
    MAX_EXEC_ARG_CHARS,
    MAX_EXEC_ARGV_ITEMS,
    MAX_EXEC_ARGV_TOTAL_CHARS,
    PROJECT_ROOT,
    SAFE_ARG_FLAGS,
    WORKSPACE_ROOT,
)
from terminal_bridge.safety import _is_blocked_name


def _fallback_command_path(project_root: Path = PROJECT_ROOT) -> str:
    entries: list[str] = []
    if os.name == "nt":
        entries.append(str(project_root / ".venv" / "Scripts"))
    else:
        entries.extend(
            [
                str(project_root / ".venv" / "bin"),
                str(Path.home() / ".local" / "bin"),
                str(Path.home() / ".local" / "share" / "mise" / "shims"),
                str(Path.home() / ".local" / "share" / "mise" / "installs" / "python" / "3.12" / "bin"),
                "/usr/local/bin",
                "/opt/homebrew/bin",
                "/usr/bin",
                "/bin",
                "/usr/sbin",
                "/sbin",
            ]
        )
    entries.extend(item for item in os.defpath.split(os.pathsep) if item)
    return os.pathsep.join(dict.fromkeys(entries))


def _safe_home_directory() -> str:
    for key in ("HOME", "USERPROFILE"):
        value = os.environ.get(key)
        if value:
            return value
    home_drive = os.environ.get("HOMEDRIVE", "")
    home_path = os.environ.get("HOMEPATH", "")
    if home_drive and home_path:
        return f"{home_drive}{home_path}"
    try:
        return str(Path.home())
    except RuntimeError:
        return str(PROJECT_ROOT)


def _safe_env() -> dict[str, str]:
    """Return a minimal cross-platform child-process environment.

    Secret-bearing variables are intentionally not forwarded. The current PATH
    is preserved when available; otherwise an OS-specific virtualenv and system
    fallback is used. Windows process-launch variables are forwarded because
    PowerShell, cmd.exe, and executable extension lookup rely on them.
    """
    safe_env = {
        "PATH": os.environ.get("PATH") or _fallback_command_path(),
        "HOME": _safe_home_directory(),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
    }

    passthrough_keys = (
        "USER",
        "LOGNAME",
        "SHELL",
        "TERM",
        "SYSTEMROOT",
        "WINDIR",
        "SYSTEMDRIVE",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
    )
    for key in passthrough_keys:
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

        # Keep workspace-relative development paths lexical. CI virtualenv
        # entries such as `.venv/bin/python` may be symlinks outside the repo,
        # but the user supplied path itself still stays under WORKSPACE_ROOT.
        candidate = (cwd / arg).absolute()
        if candidate != WORKSPACE_ROOT and not candidate.is_relative_to(WORKSPACE_ROOT):
            raise ValueError(f"Argument escapes workspace: {arg}")

        for part in candidate.relative_to(WORKSPACE_ROOT).parts:
            if part in BLOCKED_DIR_NAMES:
                raise PermissionError(f"Argument touches blocked directory: {part}")

        if _is_blocked_name(candidate.name):
            raise PermissionError(f"Argument touches blocked file: {candidate.name}")

        safe_args.append(arg)

    return safe_args


def _shell_command_body_index(argv: list[str]) -> int | None:
    if not argv:
        return None

    executable = Path(argv[0]).name
    if executable not in {"bash", "sh", "zsh"} or len(argv) < 3:
        return None

    for index, item in enumerate(argv[1:-1], 1):
        if item in {"-c", "-lc"}:
            return len(argv) - 1

    return None


def _validate_exec_argv(argv: list[str]) -> list[str]:
    if not argv:
        raise ValueError("argv cannot be empty.")

    if len(argv) > MAX_EXEC_ARGV_ITEMS:
        raise ValueError("argv has too many items.")

    shell_body_index = _shell_command_body_index(argv)
    total_chars = 0
    safe: list[str] = []
    for index, item in enumerate(argv):
        if not isinstance(item, str):
            raise ValueError("All argv items must be strings.")
        if item == "":
            raise ValueError("argv items cannot be empty.")
        if len(item) > MAX_EXEC_ARG_CHARS:
            raise ValueError(f"argv item is too long. Max characters: {MAX_EXEC_ARG_CHARS}")
        total_chars += len(item)
        if total_chars > MAX_EXEC_ARGV_TOTAL_CHARS:
            raise ValueError(f"argv is too large. Max total characters: {MAX_EXEC_ARGV_TOTAL_CHARS}")
        if "\x00" in item:
            raise ValueError("argv items cannot contain control characters.")
        if index != shell_body_index and ("\n" in item or "\r" in item):
            raise ValueError("argv items cannot contain newlines except shell command bodies.")
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

        if ".." in path.parts:
            return True

        if path.is_absolute():
            candidate = path.resolve(strict=False)
        else:
            candidate = (cwd / path).absolute()

        if candidate != WORKSPACE_ROOT and not candidate.is_relative_to(WORKSPACE_ROOT):
            return True

        rel_parts = candidate.relative_to(WORKSPACE_ROOT).parts
        if any(part in BLOCKED_DIR_NAMES for part in rel_parts):
            return True

        return _is_blocked_name(candidate.name)

    def shell_body_touches_blocked_location(body: str) -> bool:
        try:
            tokens = shlex.split(body, comments=False, posix=True)
        except ValueError:
            return False

        return any(pathish_arg_touches_blocked_location(token) for token in tokens)

    executable = Path(argv[0]).name
    command_text = " ".join(argv)

    if executable in BLOCKED_EXECUTABLES:
        return "blocked", f"Executable is blocked: {executable}"

    shell_body_index = _shell_command_body_index(argv)
    if shell_body_index is not None and shell_body_touches_blocked_location(argv[shell_body_index]):
        return "blocked", "Shell command body touches a blocked or out-of-workspace path."

    path_args = [arg for index, arg in enumerate(argv[1:], 1) if index != shell_body_index]
    if any(pathish_arg_touches_blocked_location(arg) for arg in path_args):
        return "blocked", "Command argument touches a blocked or out-of-workspace path."

    if executable in APPROVAL_REQUIRED_EXECUTABLES:
        return "medium", f"Executable requires approval: {executable}"

    for pattern in APPROVAL_REQUIRED_PATTERNS:
        if command_text == pattern or command_text.startswith(pattern + " "):
            return "medium", f"Command pattern requires approval: {pattern}"

    if any("://" in arg for arg in argv):
        return "medium", "URL-like argument requires approval."

    return "low", "Command is allowed for automatic workspace execution."
