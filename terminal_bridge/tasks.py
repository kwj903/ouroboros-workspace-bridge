from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from terminal_bridge.config import TASK_DIR
from terminal_bridge.storage import _read_json, _write_json


def _new_task_id() -> str:
    return f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _normalize_task_id(task_id: str) -> str:
    normalized = task_id.strip()

    if normalized == "":
        raise ValueError("task_id cannot be empty.")

    if len(normalized) > 160:
        raise ValueError("task_id is too long.")

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(ch not in allowed for ch in normalized):
        raise ValueError("task_id can only contain letters, numbers, '-' and '_'.")

    return normalized


def _task_path(task_id: str) -> Path:
    return TASK_DIR / f"{task_id}.json"


def _write_task(task_id: str, record: dict[str, object]) -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    path = _task_path(_normalize_task_id(task_id))
    _write_json(path, record)


def _read_task(task_id: str) -> dict[str, object]:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_task_id(task_id)
    path = _task_path(normalized)

    if not path.exists():
        raise FileNotFoundError(f"Task not found: {normalized}")

    return _read_json(path)


def _list_task_paths() -> list[Path]:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(TASK_DIR.glob("*.json"), reverse=True)
