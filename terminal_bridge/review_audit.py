from __future__ import annotations

import json
from collections import deque
from pathlib import Path


SENSITIVE_TEXT_MARKERS = (
    "access_token",
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
)


def _short_text(value: object, max_chars: int = 160) -> str:
    text = str(value or "").strip()
    if max_chars < 1:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def safe_audit_text(value: object, max_chars: int = 180) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if text == "":
        return None

    lowered = text.lower()
    if any(marker in lowered for marker in SENSITIVE_TEXT_MARKERS):
        return "[redacted]"

    return _short_text(text, max_chars=max_chars)


def summarize_audit_command(value: object) -> str | None:
    if isinstance(value, list):
        parts = [safe_audit_text(item, max_chars=80) or "" for item in value[:6]]
        if len(value) > 6:
            parts.append("...")
        summary = " ".join(part for part in parts if part)
        return summary or None

    return safe_audit_text(value, max_chars=180)


def sanitize_audit_event(record: dict[str, object]) -> dict[str, object]:
    return {
        "ts": safe_audit_text(record.get("ts")),
        "event": safe_audit_text(record.get("event")),
        "bundle_id": safe_audit_text(record.get("bundle_id")),
        "title": safe_audit_text(record.get("title")),
        "cwd": safe_audit_text(record.get("cwd")),
        "risk": safe_audit_text(record.get("risk")),
        "exit_code": record.get("exit_code") if type(record.get("exit_code")) is int else None,
        "truncated": record.get("truncated") if type(record.get("truncated")) is bool else None,
        "command": summarize_audit_command(record.get("command")),
    }


def recent_audit_events(audit_log: Path, limit: int = 20) -> list[dict[str, object]]:
    if limit < 1 or not audit_log.exists():
        return []

    lines: deque[str] = deque(maxlen=limit * 4)
    try:
        with audit_log.open("r", encoding="utf-8") as f:
            for line in f:
                lines.append(line)
    except OSError:
        return []

    events: list[dict[str, object]] = []
    for line in reversed(lines):
        if len(events) >= limit:
            break
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        events.append(sanitize_audit_event(record))

    return events


def audit_state(audit_log: Path, limit: int = 20) -> dict[str, object]:
    events = recent_audit_events(audit_log, limit)
    return {
        "count": len(events),
        "events": events,
    }
