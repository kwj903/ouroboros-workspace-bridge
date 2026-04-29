from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from terminal_bridge.config import TOOL_CALL_DIR
from terminal_bridge.storage import _now_iso, _read_json, _write_json

MAX_SUMMARY_STRING_CHARS = 160
MAX_SUMMARY_LIST_ITEMS = 5
MAX_SUMMARY_DICT_ITEMS = 12

SENSITIVE_KEY_PARTS = {
    "access_token",
    "authorization",
    "bearer",
    "credential",
    "password",
    "secret",
    "token",
}

LARGE_CONTENT_KEYS = {
    "content",
    "new_text",
    "old_text",
    "patch",
    "text",
}


def _new_tool_call_id() -> str:
    return f"call-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _normalize_call_id(call_id: str) -> str:
    normalized = call_id.strip()

    if normalized == "":
        raise ValueError("call_id cannot be empty.")

    if len(normalized) > 160:
        raise ValueError("call_id is too long.")

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(ch not in allowed for ch in normalized):
        raise ValueError("call_id can only contain letters, numbers, '-' and '_'.")

    return normalized


def _tool_call_path(call_id: str) -> Path:
    return TOOL_CALL_DIR / f"{_normalize_call_id(call_id)}.json"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _is_large_content_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in LARGE_CONTENT_KEYS or ("content" in lowered and not lowered.endswith("_ref"))


def _redact_sensitive_text(value: str) -> str:
    redacted = re.sub(r"(?i)(access_token=)[^&\s]+", r"\1<redacted>", value)
    redacted = re.sub(r"(?i)(token=)[^&\s]+", r"\1<redacted>", redacted)
    redacted = re.sub(r"(?i)(Authorization:\s*Bearer\s+)\S+", r"\1<redacted>", redacted)
    redacted = re.sub(r"(?i)\bBearer\s+\S+", "Bearer <redacted>", redacted)
    return redacted


def _summarize_value(value: object, *, key: str | None = None, depth: int = 0) -> object:
    if key is not None and _is_sensitive_key(key):
        return "<redacted>"

    if key is not None and _is_large_content_key(key):
        if value is None:
            return None
        if isinstance(value, str):
            return {"type": "str", "chars": len(value), "omitted": True}
        return {"type": type(value).__name__, "omitted": True}

    if isinstance(value, BaseModel):
        value = value.model_dump()

    if value is None or isinstance(value, bool | int | float):
        return value

    if isinstance(value, str):
        value = _redact_sensitive_text(value)
        if len(value) <= MAX_SUMMARY_STRING_CHARS:
            return value
        return {"type": "str", "chars": len(value), "preview": value[:MAX_SUMMARY_STRING_CHARS]}

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, list | tuple):
        if depth >= 3:
            return {"type": type(value).__name__, "count": len(value)}
        return {
            "type": type(value).__name__,
            "count": len(value),
            "items": [_summarize_value(item, depth=depth + 1) for item in list(value)[:MAX_SUMMARY_LIST_ITEMS]],
        }

    if isinstance(value, dict):
        if depth >= 3:
            return {"type": "dict", "keys": sorted(str(item_key) for item_key in value.keys())[:MAX_SUMMARY_DICT_ITEMS]}
        summary: dict[str, object] = {}
        for item_key, item_value in list(value.items())[:MAX_SUMMARY_DICT_ITEMS]:
            str_key = str(item_key)
            summary[str_key] = _summarize_value(item_value, key=str_key, depth=depth + 1)
        if len(value) > MAX_SUMMARY_DICT_ITEMS:
            summary["_omitted_keys"] = len(value) - MAX_SUMMARY_DICT_ITEMS
        return summary

    return repr(value)[:MAX_SUMMARY_STRING_CHARS]


def summarize_args(args: dict[str, object]) -> dict[str, object]:
    return {key: _summarize_value(value, key=key) for key, value in args.items()}


def hash_args(args_summary: dict[str, object]) -> str:
    payload = json.dumps(args_summary, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def summarize_result(result: object) -> dict[str, object]:
    if isinstance(result, BaseModel):
        result = result.model_dump()

    if not isinstance(result, dict):
        return {"type": type(result).__name__}

    summary: dict[str, object] = {}
    for key in ("bundle_id", "status", "risk", "command_count", "error"):
        if key in result:
            summary[key] = result[key]
    return summary


def _duration_ms(started_at: object, ended_at: str) -> int | None:
    if not isinstance(started_at, str):
        return None

    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
    except ValueError:
        return None

    return max(0, int((end - start).total_seconds() * 1000))


def write_started(tool_name: str, args: dict[str, object]) -> str:
    TOOL_CALL_DIR.mkdir(parents=True, exist_ok=True)
    call_id = _new_tool_call_id()
    args_summary = summarize_args(args)
    record: dict[str, object] = {
        "call_id": call_id,
        "tool_name": tool_name,
        "status": "started",
        "started_at": _now_iso(),
        "completed_at": None,
        "failed_at": None,
        "duration_ms": None,
        "args_hash": hash_args(args_summary),
        "args_summary": args_summary,
        "result_summary": None,
        "error": None,
    }
    _write_json(_tool_call_path(call_id), record)
    return call_id


def write_completed(call_id: str, result: object) -> dict[str, object]:
    path = _tool_call_path(call_id)
    record = _read_json(path)
    completed_at = _now_iso()
    record["status"] = "completed"
    record["completed_at"] = completed_at
    record["failed_at"] = None
    record["duration_ms"] = _duration_ms(record.get("started_at"), completed_at)
    record["result_summary"] = summarize_result(result)
    record["error"] = None
    _write_json(path, record)
    return record


def write_failed(call_id: str, error: BaseException) -> dict[str, object]:
    path = _tool_call_path(call_id)
    record = _read_json(path)
    failed_at = _now_iso()
    record["status"] = "failed"
    record["completed_at"] = None
    record["failed_at"] = failed_at
    record["duration_ms"] = _duration_ms(record.get("started_at"), failed_at)
    record["result_summary"] = None
    record["error"] = f"{type(error).__name__}: {error}"[:MAX_SUMMARY_STRING_CHARS]
    _write_json(path, record)
    return record


def read_tool_call(call_id: str) -> dict[str, object]:
    TOOL_CALL_DIR.mkdir(parents=True, exist_ok=True)
    path = _tool_call_path(call_id)

    if not path.exists():
        raise FileNotFoundError(f"Tool call not found: {_normalize_call_id(call_id)}")

    try:
        return _read_json(path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Tool call record is malformed: {_normalize_call_id(call_id)}") from exc


def list_tool_calls(limit: int = 50) -> list[dict[str, object]]:
    TOOL_CALL_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []

    for path in sorted(TOOL_CALL_DIR.glob("call-*.json"), reverse=True):
        try:
            records.append(_read_json(path))
        except Exception:
            continue
        if len(records) >= limit:
            break

    return records
