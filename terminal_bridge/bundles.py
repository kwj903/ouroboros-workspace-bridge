from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from terminal_bridge.config import (
    COMMAND_BUNDLE_APPLIED_DIR,
    COMMAND_BUNDLE_FAILED_DIR,
    COMMAND_BUNDLE_PENDING_DIR,
    COMMAND_BUNDLE_REJECTED_DIR,
)
from terminal_bridge.storage import _now_iso, _read_json, _write_json


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
