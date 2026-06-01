from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from terminal_bridge.config import BLOCKED_DIR_NAMES, BLOCKED_FILE_PATTERNS, COMMAND_BUNDLES_DIR


VALID_APPROVAL_MODES = {"normal", "safe-auto", "yolo"}
DEFAULT_APPROVAL_MODE = "normal"
APPROVAL_MODE_PATH = COMMAND_BUNDLES_DIR / "approval_mode.json"
APPROVAL_SCOPE_DIR = COMMAND_BUNDLES_DIR.parent / "approval_modes"
VALID_APPROVAL_SCOPES = {"global", "project", "client", "task"}
_SCOPED_APPROVAL_DIRS = {
    "project": "projects",
    "client": "clients",
    "task": "tasks",
}
_SCOPE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,191}$")

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


@dataclass(frozen=True)
class ApprovalModeResolution:
    mode: str
    scope_type: str
    scope_id: str | None = None
    path: str | None = None
    reason: str = "global_default"

    @property
    def source_label(self) -> str:
        if self.scope_id:
            return f"mode={self.mode} scope={self.scope_type}:{self.scope_id}"
        return f"mode={self.mode} scope={self.scope_type}"


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


def _normalize_scope_id(scope_id: object) -> str:
    normalized = str(scope_id or "").strip()
    if not normalized or normalized in {".", ".."}:
        raise ValueError("scope_id cannot be empty or relative path syntax.")
    if "/" in normalized or "\\" in normalized:
        raise ValueError("scope_id cannot contain path separators.")
    if not _SCOPE_ID_RE.fullmatch(normalized):
        raise ValueError("scope_id contains unsupported characters.")
    return normalized


def scoped_approval_mode_path(
    scope_type: str,
    scope_id: object | None = None,
    *,
    scope_root: Path = APPROVAL_SCOPE_DIR,
    global_path: Path = APPROVAL_MODE_PATH,
) -> Path:
    normalized_scope = str(scope_type or "").strip().lower()
    if normalized_scope == "global":
        return global_path
    if normalized_scope not in _SCOPED_APPROVAL_DIRS:
        raise ValueError(f"Unsupported approval mode scope: {scope_type}")

    normalized_id = _normalize_scope_id(scope_id)
    root = scope_root.expanduser().resolve(strict=False)
    path = (root / _SCOPED_APPROVAL_DIRS[normalized_scope] / f"{normalized_id}.json").resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("scope_id resolves outside approval mode scope root.") from exc
    return path


def _load_optional_approval_mode(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    raw_mode = data.get("mode")
    mode = normalize_approval_mode(raw_mode)
    if mode != str(raw_mode or "").strip().lower():
        return None
    return mode


def load_scoped_approval_mode(
    scope_type: str,
    scope_id: object | None = None,
    *,
    scope_root: Path = APPROVAL_SCOPE_DIR,
    global_path: Path = APPROVAL_MODE_PATH,
) -> str | None:
    if str(scope_type or "").strip().lower() == "global":
        return load_approval_mode(global_path)
    path = scoped_approval_mode_path(scope_type, scope_id, scope_root=scope_root, global_path=global_path)
    return _load_optional_approval_mode(path)


def save_scoped_approval_mode(
    scope_type: str,
    mode: str,
    scope_id: object | None = None,
    *,
    scope_root: Path = APPROVAL_SCOPE_DIR,
    global_path: Path = APPROVAL_MODE_PATH,
) -> dict[str, str]:
    normalized_scope = str(scope_type or "").strip().lower()
    if normalized_scope == "global":
        return save_approval_mode(mode, global_path)

    normalized = normalize_approval_mode(mode)
    if normalized != mode:
        raise ValueError(f"Invalid approval mode: {mode}")

    path = scoped_approval_mode_path(normalized_scope, scope_id, scope_root=scope_root, global_path=global_path)
    record = {
        "mode": normalized,
        "scope_type": normalized_scope,
        "scope_id": _normalize_scope_id(scope_id),
        "updated_at": _now_iso(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def list_scoped_approval_modes(*, scope_root: Path = APPROVAL_SCOPE_DIR) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    root = scope_root.expanduser().resolve(strict=False)
    for scope_type, dirname in _SCOPED_APPROVAL_DIRS.items():
        scope_dir = root / dirname
        if not scope_dir.exists():
            continue
        for path in sorted(scope_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            mode = _load_optional_approval_mode(path)
            if mode is None:
                continue
            scope_id = str(data.get("scope_id") or path.stem).strip()
            try:
                normalized_id = _normalize_scope_id(scope_id)
            except ValueError:
                continue
            rows.append(
                {
                    "scope_type": scope_type,
                    "scope_id": normalized_id,
                    "mode": mode,
                    "updated_at": str(data.get("updated_at") or ""),
                    "path": str(path),
                }
            )
    return rows


def delete_scoped_approval_mode(
    scope_type: str,
    scope_id: object | None = None,
    *,
    scope_root: Path = APPROVAL_SCOPE_DIR,
) -> bool:
    path = scoped_approval_mode_path(scope_type, scope_id, scope_root=scope_root)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def _metadata_from_bundle_or_metadata(value: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    raw_metadata = value.get("metadata")
    if isinstance(raw_metadata, dict):
        return raw_metadata
    return value


def _metadata_text(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _approval_scope_candidates(metadata: dict[str, object]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    task_id = _metadata_text(metadata, "task_id")
    if task_id is not None:
        candidates.append(("task", task_id))

    client_id = _metadata_text(metadata, "client_id")
    if client_id is not None and client_id != "default":
        candidates.append(("client", client_id))

    project_id = _metadata_text(metadata, "project_id")
    if project_id is not None:
        candidates.append(("project", project_id))

    return candidates


def load_effective_approval_mode(
    bundle_or_metadata: dict[str, object] | None,
    *,
    scope_root: Path = APPROVAL_SCOPE_DIR,
    global_path: Path = APPROVAL_MODE_PATH,
) -> ApprovalModeResolution:
    metadata = _metadata_from_bundle_or_metadata(bundle_or_metadata)
    for scope_type, scope_id in _approval_scope_candidates(metadata):
        try:
            path = scoped_approval_mode_path(scope_type, scope_id, scope_root=scope_root, global_path=global_path)
        except ValueError:
            continue

        mode = _load_optional_approval_mode(path)
        if mode is not None:
            return ApprovalModeResolution(
                mode=mode,
                scope_type=scope_type,
                scope_id=scope_id,
                path=str(path),
                reason="scoped",
            )

    global_exists = global_path.exists()
    return ApprovalModeResolution(
        mode=load_approval_mode(global_path),
        scope_type="global",
        scope_id=None,
        path=str(global_path) if global_exists else None,
        reason="global" if global_exists else "global_default",
    )


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
