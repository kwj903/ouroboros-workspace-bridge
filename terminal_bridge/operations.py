from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from terminal_bridge.config import OPERATION_DIR
from terminal_bridge.storage import _now_iso, _read_json

_audit_callback: Callable[..., None] | None = None


def _set_audit_callback(callback: Callable[..., None] | None) -> None:
    global _audit_callback
    _audit_callback = callback


def _emit_audit(event: str, **data: object) -> None:
    if _audit_callback is not None:
        _audit_callback(event, **data)


def _model_to_dict(value: object) -> dict[str, object]:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {"value": value}


def _new_operation_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _normalize_operation_id(operation_id: str | None) -> str:
    if operation_id is None or operation_id.strip() == "":
        return _new_operation_id()

    normalized = operation_id.strip()

    if len(normalized) > 120:
        raise ValueError("operation_id is too long.")

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(ch not in allowed for ch in normalized):
        raise ValueError("operation_id can only contain letters, numbers, '-' and '_'.")

    return normalized


def _operation_path(operation_id: str) -> Path:
    return OPERATION_DIR / f"{operation_id}.json"


def _read_operation(operation_id: str) -> dict[str, object] | None:
    OPERATION_DIR.mkdir(parents=True, exist_ok=True)
    path = _operation_path(operation_id)

    if not path.exists():
        return None

    return _read_json(path)


def _write_operation_record(record: dict[str, object]) -> None:
    OPERATION_DIR.mkdir(parents=True, exist_ok=True)
    operation_id = str(record["operation_id"])
    path = _operation_path(operation_id)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def _begin_operation(
    tool: str,
    args: dict[str, object],
    operation_id: str | None = None,
) -> tuple[str, dict[str, object] | None]:
    op_id = _normalize_operation_id(operation_id)
    existing = _read_operation(op_id)

    if existing is not None:
        status = existing.get("status")

        if status == "completed":
            _emit_audit("operation_reused_completed", operation_id=op_id, tool=tool)
            return op_id, existing

        if status in {"started", "running"}:
            raise RuntimeError(f"Operation is already running: {op_id}")

        if status == "failed":
            raise RuntimeError(f"Operation already failed: {op_id}")

    record: dict[str, object] = {
        "operation_id": op_id,
        "tool": tool,
        "status": "started",
        "started_at": _now_iso(),
        "args": args,
    }

    _write_operation_record(record)
    _emit_audit("operation_started", operation_id=op_id, tool=tool, args=args)

    return op_id, None


def _complete_operation(operation_id: str, result: object) -> None:
    record = _read_operation(operation_id) or {
        "operation_id": operation_id,
        "status": "started",
    }

    record["status"] = "completed"
    record["completed_at"] = _now_iso()
    record["result"] = _model_to_dict(result)

    _write_operation_record(record)
    _emit_audit("operation_completed", operation_id=operation_id, result=record["result"])


def _fail_operation(operation_id: str, exc: BaseException) -> None:
    record = _read_operation(operation_id) or {
        "operation_id": operation_id,
        "status": "started",
    }

    record["status"] = "failed"
    record["failed_at"] = _now_iso()
    record["error"] = f"{type(exc).__name__}: {exc}"

    _write_operation_record(record)
    _emit_audit("operation_failed", operation_id=operation_id, error=record["error"])
