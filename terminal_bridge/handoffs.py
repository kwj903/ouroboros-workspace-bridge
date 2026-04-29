from __future__ import annotations

import json
import re
from pathlib import Path

from terminal_bridge.config import HANDOFF_DIR
from terminal_bridge.storage import _now_iso, _read_json, _write_json


SENSITIVE_TEXT_PATTERNS = (
    (r"(?i)(access_token=)[^&\s\"'<>]+", r"\1[redacted]"),
    (r"(?i)(token=)[^&\s\"'<>]+", r"\1[redacted]"),
    (r"(?i)(Authorization:\s*Bearer\s+)\S+", r"\1[redacted]"),
    (r"(?i)Bearer\s+[^\s\"'<>]+", "Bearer [redacted]"),
)


def _handoff_path(handoff_id: str) -> Path:
    if not handoff_id.startswith("handoff-") or "/" in handoff_id or "\\" in handoff_id:
        raise ValueError("Invalid handoff id.")
    return HANDOFF_DIR / f"{handoff_id}.json"


def _mask_sensitive_text(value: object) -> str:
    text = str(value or "")
    for pattern, replacement in SENSITIVE_TEXT_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


def _compact_tail(value: object, max_chars: int = 1000) -> str:
    text = _mask_sensitive_text(value)
    if len(text) <= max_chars:
        return text
    return text[-max_chars:].lstrip()


def _bundle_result_tails(record: dict[str, object], max_chars: int = 1000) -> tuple[str, str]:
    result = record.get("result")
    if not isinstance(result, dict):
        return "", ""

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    steps = result.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            if step.get("stdout"):
                stdout_parts.append(str(step.get("stdout")))
            if step.get("stderr"):
                stderr_parts.append(str(step.get("stderr")))

    return _compact_tail("\n".join(stdout_parts), max_chars), _compact_tail("\n".join(stderr_parts), max_chars)


def _next_for_status(status: str, error: object) -> str:
    if status == "applied" and not error:
        return "continue"
    if status == "failed":
        return "fix_failure"
    return "inspect_logs"


def handoff_from_bundle_record(record: dict[str, object]) -> dict[str, object]:
    bundle_id = str(record.get("bundle_id", ""))
    if not bundle_id:
        raise ValueError("bundle record is missing bundle_id.")

    status = str(record.get("status", "unknown"))
    if status not in {"applied", "failed", "rejected"}:
        raise ValueError(f"handoff requires a final bundle status, got: {status}")

    error = record.get("error")
    stdout_tail, stderr_tail = _bundle_result_tails(record)
    existing: dict[str, object] = {}
    handoff_id = f"handoff-{bundle_id}"
    path = _handoff_path(handoff_id)
    if path.exists():
        try:
            existing = _read_json(path)
        except Exception:
            existing = {}

    now = _now_iso()
    created_at = str(existing.get("created_at", now))
    ok: bool | None = True if status == "applied" and not error else False

    return {
        "handoff_id": handoff_id,
        "bundle_id": bundle_id,
        "status": status,
        "ok": ok,
        "risk": str(record.get("risk", "unknown")),
        "title": str(record.get("title", "")),
        "cwd": str(record.get("cwd", "")),
        "next": _next_for_status(status, error),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail or _compact_tail(error),
        "created_at": created_at,
        "updated_at": now,
    }


def write_handoff_from_bundle(record: dict[str, object]) -> dict[str, object]:
    handoff = handoff_from_bundle_record(record)
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(_handoff_path(str(handoff["handoff_id"])), handoff)
    return handoff


def read_handoff(handoff_id: str) -> dict[str, object] | None:
    path = _handoff_path(handoff_id)
    if not path.exists():
        return None
    try:
        record = _read_json(path)
    except Exception:
        return None
    return _compact_handoff_record(record)


def _compact_handoff_record(record: dict[str, object]) -> dict[str, object]:
    return {
        "handoff_id": str(record.get("handoff_id", "")),
        "bundle_id": str(record.get("bundle_id", "")),
        "status": str(record.get("status", "unknown")),
        "ok": record.get("ok") if isinstance(record.get("ok"), bool) else None,
        "risk": str(record.get("risk", "unknown")),
        "title": str(record.get("title", "")),
        "cwd": str(record.get("cwd", "")),
        "next": str(record.get("next", "inspect_logs")),
        "stdout_tail": _compact_tail(record.get("stdout_tail")),
        "stderr_tail": _compact_tail(record.get("stderr_tail")),
        "created_at": str(record.get("created_at", "")),
        "updated_at": str(record.get("updated_at", "")),
    }


def list_handoffs(limit: int = 20) -> list[dict[str, object]]:
    if limit < 1 or not HANDOFF_DIR.exists():
        return []

    records: list[dict[str, object]] = []
    for path in HANDOFF_DIR.glob("handoff-*.json"):
        try:
            record = _read_json(path)
        except Exception:
            continue
        records.append(_compact_handoff_record(record))

    records.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return records[:limit]


def next_handoff() -> dict[str, object] | None:
    records = list_handoffs(1)
    return records[0] if records else None


def handoff_json(record: dict[str, object]) -> str:
    return json.dumps(_compact_handoff_record(record), ensure_ascii=False, indent=2, sort_keys=True)
