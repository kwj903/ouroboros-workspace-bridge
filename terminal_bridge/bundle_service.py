from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from terminal_bridge import bundles as bundle_store
from terminal_bridge.mcp_tools.metadata_filters import metadata_matches_filters
from terminal_bridge.models import (
    CommandBundleListEntry,
    CommandBundleListResult,
    CommandBundleStageResult,
    CommandBundleStatusResult,
)
from terminal_bridge.storage import _now_iso, _read_json


AuditCallback = Callable[..., None]
CommandBundleDirs = Callable[[], list[Path]]
ReadJson = Callable[[Path], dict[str, object]]


def command_bundle_stage_result(
    path: Path,
    record: dict[str, object],
) -> CommandBundleStageResult:
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


def command_bundle_status_result(
    record: dict[str, object],
    bundle_id: str,
) -> CommandBundleStatusResult:
    steps = record.get("steps") if isinstance(record.get("steps"), list) else []
    metadata = bundle_store._normalize_command_bundle_metadata(record)
    return CommandBundleStatusResult(
        bundle_id=str(record.get("bundle_id", bundle_id)),
        title=str(record.get("title", "")),
        cwd=str(record.get("cwd", "")),
        status=str(record.get("status", "unknown")),
        risk=str(record.get("risk", "unknown")),
        approval_required=bool(record.get("approval_required", False)),
        command_count=len(steps),
        created_at=str(record.get("created_at", "")),
        updated_at=str(record.get("updated_at", "")),
        result=record.get("result") if isinstance(record.get("result"), dict) else None,
        error=record.get("error") if isinstance(record.get("error"), str) else None,
        metadata=metadata,
    )


@dataclass(frozen=True)
class BundleSubmission:
    result: CommandBundleStageResult
    created: bool


class BundleService:
    """Cohesive bundle orchestration over the canonical filesystem store."""

    def __init__(self, *, audit: AuditCallback | None = None) -> None:
        self._audit = audit

    def _audit_event(self, event: str, **data: object) -> None:
        if self._audit is not None:
            self._audit(event, **data)

    def stage(
        self,
        *,
        version: int,
        title: str,
        cwd: str,
        risk: str,
        steps: list[dict[str, object]],
        request_key: str,
        metadata: dict[str, object] | None,
        kind: str,
    ) -> BundleSubmission:
        existing = bundle_store._find_command_bundle_by_request_key(request_key)
        if existing is not None:
            path, record = existing
            self._audit_event(
                "dedupe_command_bundle",
                request_key=request_key,
                existing_bundle_id=str(record.get("bundle_id", path.stem)),
                kind=kind,
                requested_title=title,
            )
            return BundleSubmission(command_bundle_stage_result(path, record), created=False)

        bundle_id = bundle_store._new_command_bundle_id()
        now = _now_iso()
        record: dict[str, object] = {
            "version": version,
            "bundle_id": bundle_id,
            "title": title,
            "cwd": cwd,
            "status": "pending",
            "risk": risk,
            "approval_required": True,
            "created_at": now,
            "updated_at": now,
            "steps": steps,
            "metadata": bundle_store._merge_command_bundle_metadata(
                cwd,
                metadata,
                validate_workspace_mode=True,
            ),
            "result": None,
            "error": None,
            "request_key": request_key,
            "request_key_version": 1,
            "duplicate_of": None,
        }
        path = bundle_store._command_bundle_path(bundle_id, "pending")
        stored_path, stored_record, created = bundle_store._write_pending_command_bundle(
            path,
            record,
        )
        if not created:
            self._audit_event(
                "dedupe_command_bundle",
                request_key=request_key,
                existing_bundle_id=str(stored_record.get("bundle_id", stored_path.stem)),
                kind=kind,
                requested_title=title,
            )
        return BundleSubmission(
            command_bundle_stage_result(stored_path, stored_record),
            created=created,
        )

    def find(self, bundle_id: str) -> tuple[Path, dict[str, object]]:
        return bundle_store._find_command_bundle(bundle_id)

    def status(self, bundle_id: str) -> CommandBundleStatusResult:
        _path, record = self.find(bundle_id)
        return command_bundle_status_result(record, bundle_id)

    async def wait(
        self,
        bundle_id: str,
        *,
        timeout_seconds: int,
        poll_interval_seconds: float,
    ) -> CommandBundleStatusResult:
        deadline = time.monotonic() + timeout_seconds
        while True:
            result = self.status(bundle_id)
            if result.status not in bundle_store.ACTIVE_BUNDLE_STATUSES:
                return result
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return result
            await asyncio.sleep(min(poll_interval_seconds, remaining))

    def list(
        self,
        limit: int,
        *,
        task_id: str | None = None,
        client_id: str | None = None,
        session_id: str | None = None,
        project_id: str | None = None,
        command_bundle_dirs: CommandBundleDirs | None = None,
        read_json: ReadJson | None = None,
    ) -> CommandBundleListResult:
        entries: list[CommandBundleListEntry] = []
        filters = {
            "task_id": task_id,
            "client_id": client_id,
            "session_id": session_id,
            "project_id": project_id,
        }
        directories = command_bundle_dirs or bundle_store._command_bundle_dirs
        reader = read_json or _read_json

        for directory in directories():
            if not directory.exists():
                continue
            for path in directory.glob("cmd-*.json"):
                try:
                    record = reader(path)
                except Exception:
                    continue
                steps = record.get("steps") if isinstance(record.get("steps"), list) else []
                metadata = bundle_store._normalize_command_bundle_metadata(record)
                if not metadata_matches_filters(metadata, filters):
                    continue
                entries.append(
                    CommandBundleListEntry(
                        bundle_id=str(record.get("bundle_id", path.stem)),
                        title=str(record.get("title", "")),
                        cwd=str(record.get("cwd", "")),
                        status=directory.name,
                        risk=str(record.get("risk", "unknown")),
                        command_count=len(steps),
                        updated_at=str(record.get("updated_at", "")),
                        metadata=metadata,
                    )
                )

        entries.sort(key=lambda item: item.updated_at, reverse=True)
        return CommandBundleListResult(
            entries=entries[:limit],
            count=min(len(entries), limit),
        )

    def cancel(self, bundle_id: str) -> CommandBundleStatusResult:
        _path, record = self.find(bundle_id)
        if record.get("status") != "pending":
            raise ValueError(
                f"Only pending bundles can be cancelled. Current status: {record.get('status')}"
            )
        updated = bundle_store._move_command_bundle(
            bundle_id,
            "rejected",
            {
                "error": "Cancelled from ChatGPT.",
                "result": None,
            },
        )
        self._audit_event("cancel_command_bundle", bundle_id=bundle_id)
        return command_bundle_status_result(updated, bundle_id)
