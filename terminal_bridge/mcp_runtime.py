from __future__ import annotations

import inspect
import json
from collections.abc import Callable

from terminal_bridge.config import (
    AUDIT_LOG,
    BACKUP_DIR,
    COMMAND_BUNDLE_APPLIED_DIR,
    COMMAND_BUNDLE_FAILED_DIR,
    COMMAND_BUNDLE_INTERRUPTED_DIR,
    COMMAND_BUNDLE_PENDING_DIR,
    COMMAND_BUNDLE_REJECTED_DIR,
    COMMAND_BUNDLE_RUNNING_DIR,
    HANDOFF_DIR,
    OPERATION_DIR,
    RUNTIME_ROOT,
    TEXT_PAYLOAD_DIR,
    TOOL_CALL_DIR,
    TRASH_DIR,
)
from terminal_bridge.models import ToolCallStatusResult
from terminal_bridge.operations import _set_audit_callback as _set_operation_audit_callback
from terminal_bridge.storage import _now_iso
from terminal_bridge.tool_calls import (
    write_completed as _write_tool_call_completed,
    write_failed as _write_tool_call_failed,
    write_started as _write_tool_call_started,
)


def _ensure_runtime_dirs() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    OPERATION_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    TOOL_CALL_DIR.mkdir(parents=True, exist_ok=True)
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_PENDING_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_RUNNING_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_APPLIED_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_FAILED_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_INTERRUPTED_DIR.mkdir(parents=True, exist_ok=True)


def _audit(event: str, **data: object) -> None:
    _ensure_runtime_dirs()
    record = {
        "ts": _now_iso(),
        "event": event,
        **data,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


_set_operation_audit_callback(_audit)


def _tool_call_status_result(record: dict[str, object]) -> ToolCallStatusResult:
    return ToolCallStatusResult(
        call_id=str(record.get("call_id", "")),
        tool_name=str(record.get("tool_name", "")),
        status=str(record.get("status", "unknown")),
        started_at=record.get("started_at") if isinstance(record.get("started_at"), str) else None,
        completed_at=record.get("completed_at") if isinstance(record.get("completed_at"), str) else None,
        failed_at=record.get("failed_at") if isinstance(record.get("failed_at"), str) else None,
        duration_ms=record.get("duration_ms") if isinstance(record.get("duration_ms"), int) else None,
        args_hash=record.get("args_hash") if isinstance(record.get("args_hash"), str) else None,
        args_summary=record.get("args_summary") if isinstance(record.get("args_summary"), dict) else None,
        result_summary=record.get("result_summary") if isinstance(record.get("result_summary"), dict) else None,
        error=record.get("error") if isinstance(record.get("error"), str) else None,
    )


def _record_tool_call(tool_name: str, args: dict[str, object], action: Callable[[], object]) -> object:
    call_id = _write_tool_call_started(tool_name, args)
    try:
        result = action()
    except Exception as exc:
        _write_tool_call_failed(call_id, exc)
        raise

    _write_tool_call_completed(call_id, result)
    return result

async def _record_tool_call_async(
    tool_name: str,
    args: dict[str, object],
    action: Callable[[], object],
) -> object:
    """Journal an async-capable tool call after its final result is available."""

    call_id = _write_tool_call_started(tool_name, args)
    try:
        pending_result = action()
        result = await pending_result if inspect.isawaitable(pending_result) else pending_result
    except BaseException as exc:
        _write_tool_call_failed(call_id, exc)
        raise

    _write_tool_call_completed(call_id, result)
    return result
