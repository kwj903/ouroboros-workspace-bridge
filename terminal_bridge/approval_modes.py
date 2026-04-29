from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from terminal_bridge.config import BLOCKED_DIR_NAMES, BLOCKED_FILE_PATTERNS, COMMAND_BUNDLES_DIR


VALID_APPROVAL_MODES = {"normal", "safe-auto", "yolo"}
DEFAULT_APPROVAL_MODE = "normal"
APPROVAL_MODE_PATH = COMMAND_BUNDLES_DIR / "approval_mode.json"

_DANGEROUS_ARG_TOKENS = {
    "rm",
    "mv",
    "cp",
    "chmod",
    "chown",
    "install",
    "brew",
    "curl",
    "wget",
    "ssh",
    "scp",
}
_GIT_MUTATING_SUBCOMMANDS = {"add", "commit", "push"}
_SHELL_EXECUTABLES = {"bash", "sh", "zsh", "fish", "python", "python3", "node", "ruby", "perl"}
_SHELL_COMMAND_FLAGS = {"-c", "-lc", "-cl"}
_SENSITIVE_RUNTIME_PARTS = {".mcp_terminal_bridge"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_approval_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    if mode in VALID_APPROVAL_MODES:
        return mode
    return DEFAULT_APPROVAL_MODE


def load_approval_mode(path: Path = APPROVAL_MODE_PATH) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_APPROVAL_MODE

    if not isinstance(data, dict):
        return DEFAULT_APPROVAL_MODE

    return normalize_approval_mode(data.get("mode"))


def save_approval_mode(mode: str, path: Path = APPROVAL_MODE_PATH) -> dict[str, str]:
    normalized = normalize_approval_mode(mode)
    if normalized != mode:
        raise ValueError(f"Invalid approval mode: {mode}")

    record = {"mode": normalized, "updated_at": _now_iso()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def _steps(record: dict[str, object]) -> list[dict[str, Any]]:
    raw_steps = record.get("steps")
    if not isinstance(raw_steps, list):
        return []
    return [step for step in raw_steps if isinstance(step, dict)]


def _step_type(step: dict[str, Any]) -> str:
    raw_type = step.get("type", "command")
    return str(raw_type or "command")


def _string_items(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _looks_sensitive_path(value: str) -> bool:
    normalized = value.strip().strip("'\"").replace("\\", "/")
    if not normalized:
        return False

    parts = [part for part in normalized.split("/") if part and part not in {".", ".."}]
    if any(part in BLOCKED_DIR_NAMES or part in _SENSITIVE_RUNTIME_PARTS for part in parts):
        return True

    candidates = [normalized]
    if parts:
        candidates.append(parts[-1])

    for candidate in candidates:
        for pattern in BLOCKED_FILE_PATTERNS:
            if fnmatch.fnmatch(candidate, pattern):
                return True

    return False


def bundle_touches_sensitive_path(record: dict[str, object]) -> bool:
    for step in _steps(record):
        for key in ("path", "files", "argv"):
            for item in _string_items(step.get(key)):
                if _looks_sensitive_path(item):
                    return True
    return False


def _argv_has_dangerous_command(argv: list[str]) -> bool:
    lowered = [item.strip().lower() for item in argv if item.strip()]
    basenames = [Path(item).name for item in lowered]

    if basenames and basenames[0] in _SHELL_EXECUTABLES and any(item in _SHELL_COMMAND_FLAGS for item in lowered[1:]):
        return True

    if any(item in _DANGEROUS_ARG_TOKENS for item in basenames):
        return True

    if "git" in basenames and any(item in _GIT_MUTATING_SUBCOMMANDS for item in basenames):
        return True

    if "pip" in basenames and "install" in basenames:
        return True

    if "npm" in basenames and "install" in basenames:
        return True

    return False


def is_safe_auto_eligible(record: dict[str, object]) -> bool:
    if record.get("status") != "pending":
        return False
    if record.get("risk") != "low":
        return False
    if bundle_touches_sensitive_path(record):
        return False

    steps = _steps(record)
    if not steps:
        return False

    for step in steps:
        if _step_type(step) != "command":
            return False
        if step.get("risk") != "low":
            return False

        argv = step.get("argv")
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv) or not argv:
            return False
        if _argv_has_dangerous_command(argv):
            return False

    return True


def should_auto_approve(record: dict[str, object], mode: str) -> bool:
    normalized = normalize_approval_mode(mode)
    if normalized == "normal":
        return False
    if record.get("status") != "pending":
        return False
    if record.get("risk") == "blocked":
        return False
    if bundle_touches_sensitive_path(record):
        return False
    if normalized == "safe-auto":
        return is_safe_auto_eligible(record)
    if normalized == "yolo":
        return True
    return False
