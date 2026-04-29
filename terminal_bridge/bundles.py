from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from terminal_bridge.config import (
    COMMAND_BUNDLE_APPLIED_DIR,
    COMMAND_BUNDLE_FAILED_DIR,
    COMMAND_BUNDLE_PENDING_DIR,
    COMMAND_BUNDLE_REJECTED_DIR,
)
from terminal_bridge.storage import _now_iso, _read_json, _write_json
from terminal_bridge.handoffs import write_handoff_from_bundle


def _command_bundle_dirs() -> list[Path]:
    return [
        COMMAND_BUNDLE_PENDING_DIR,
        COMMAND_BUNDLE_APPLIED_DIR,
        COMMAND_BUNDLE_REJECTED_DIR,
        COMMAND_BUNDLE_FAILED_DIR,
    ]


def _new_command_bundle_id() -> str:
    return f"cmd-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _command_bundle_path(bundle_id: str, status: str = "pending") -> Path:
    if not bundle_id.startswith("cmd-"):
        raise ValueError("Invalid command bundle id.")

    mapping = {
        "pending": COMMAND_BUNDLE_PENDING_DIR,
        "applied": COMMAND_BUNDLE_APPLIED_DIR,
        "rejected": COMMAND_BUNDLE_REJECTED_DIR,
        "failed": COMMAND_BUNDLE_FAILED_DIR,
    }
    directory = mapping.get(status)
    if directory is None:
        raise ValueError(f"Unknown command bundle status: {status}")

    return directory / f"{bundle_id}.json"


def _find_command_bundle(bundle_id: str) -> tuple[Path, dict[str, object]]:
    for directory in _command_bundle_dirs():
        path = directory / f"{bundle_id}.json"
        if path.exists():
            return path, _read_json(path)
    raise FileNotFoundError(f"Command bundle not found: {bundle_id}")


def _write_command_bundle(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, record)


def _canonicalize_request_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonicalize_request_value(value.model_dump())

    if isinstance(value, dict):
        return {str(key): _canonicalize_request_value(item) for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))}

    if isinstance(value, list | tuple):
        return [_canonicalize_request_value(item) for item in value]

    if isinstance(value, Path):
        return str(value)

    return value


def _canonical_request_json(value: dict[str, object]) -> str:
    canonical = _canonicalize_request_value(value)
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _request_key(value: dict[str, object]) -> str:
    payload = _canonical_request_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _find_command_bundle_by_request_key(request_key: str) -> tuple[Path, dict[str, object]] | None:
    for directory in _command_bundle_dirs():
        if not directory.exists():
            continue
        for path in directory.glob("cmd-*.json"):
            try:
                record = _read_json(path)
            except Exception:
                continue
            if record.get("request_key") == request_key:
                return path, record
    return None


def _move_command_bundle(
    bundle_id: str,
    target_status: str,
    updates: dict[str, object] | None = None,
) -> dict[str, object]:
    source_path, record = _find_command_bundle(bundle_id)
    now = _now_iso()
    record["status"] = target_status
    record["updated_at"] = now

    if updates:
        record.update(updates)

    target_path = _command_bundle_path(bundle_id, target_status)
    _write_command_bundle(target_path, record)
    if target_status in {"applied", "failed", "rejected"}:
        write_handoff_from_bundle(record)

    if source_path != target_path and source_path.exists():
        source_path.unlink()

    return record


def _bundle_risk_rank(risk: str) -> int:
    order = {"low": 0, "medium": 1, "high": 2, "blocked": 3}
    return order.get(risk, 3)


def _combined_bundle_risk(
    risks: list[str],
) -> Literal["low", "medium", "high", "blocked"]:
    if not risks:
        return "low"
    worst = max(risks, key=_bundle_risk_rank)
    if worst not in {"low", "medium", "high", "blocked"}:
        return "blocked"
    return worst  # type: ignore[return-value]
