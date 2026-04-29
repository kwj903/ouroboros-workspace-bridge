from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from terminal_bridge.bundles import _find_command_bundle_by_request_key
from terminal_bridge.config import (
    AUDIT_LOG,
    BACKUP_DIR,
    COMMAND_BUNDLE_APPLIED_DIR,
    COMMAND_BUNDLE_FAILED_DIR,
    COMMAND_BUNDLE_PENDING_DIR,
    COMMAND_BUNDLE_REJECTED_DIR,
    HANDOFF_DIR,
    OPERATION_DIR,
    RUNTIME_ROOT,
    TASK_DIR,
    TEXT_PAYLOAD_DIR,
    TOOL_CALL_DIR,
    TRASH_DIR,
)
from terminal_bridge.models import CommandBundleStageResult, ToolCallStatusResult
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
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    TOOL_CALL_DIR.mkdir(parents=True, exist_ok=True)
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_PENDING_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_APPLIED_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_FAILED_DIR.mkdir(parents=True, exist_ok=True)


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


def _command_bundle_stage_result(path: Path, record: dict[str, object]) -> CommandBundleStageResult:
    bundle_id = str(record.get("bundle_id", path.stem))
    steps = record.get("steps") if isinstance(record.get("steps"), list) else []
    return CommandBundleStageResult(
        bundle_id=bundle_id,
        title=str(record.get("title", "")),
        cwd=str(record.get("cwd", "")),
        status=str(record.get("status", "unknown")),
        risk=str(record.get("risk", "unknown")),
        approval_required=bool(record.get("approval_required", False)),
        path=str(path),
        review_hint=f"uv run python scripts/command_bundle_runner.py preview {bundle_id}",
        command_count=len(steps),
    )


def _dedupe_command_bundle(request_key: str, *, kind: str, title: str | None = None) -> CommandBundleStageResult | None:
    existing = _find_command_bundle_by_request_key(request_key)
    if existing is None:
        return None

    path, record = existing
    _audit(
        "dedupe_command_bundle",
        request_key=request_key,
        existing_bundle_id=str(record.get("bundle_id", path.stem)),
        kind=kind,
        requested_title=title,
    )
    return _command_bundle_stage_result(path, record)
