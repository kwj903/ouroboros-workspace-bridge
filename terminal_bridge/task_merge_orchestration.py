from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from terminal_bridge.config import WORKSPACE_ROOT
from terminal_bridge.merge_queue import enqueue_task_worktree_merge, read_merge_queue_entry
from terminal_bridge.task_workspaces import (
    _normalize_project_id,
    _resolve_source_cwd,
    inspect_task_worktree,
    merge_preflight_task_worktree,
)


ProposalCallback = Callable[[], object]


def _empty_result(
    *,
    task_id: str,
    project_id: str,
    source_cwd: str,
    blockers: list[str],
    recommended_action: str,
    conflict_risk: str = "unknown",
    inspect_summary: dict[str, object] | None = None,
    preflight_result: dict[str, object] | None = None,
    merge_queue_status: str | None = None,
    merge_queue_record: dict[str, object] | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "project_id": project_id,
        "source_cwd": source_cwd,
        "inspect_summary": inspect_summary or {},
        "preflight_result": preflight_result or {},
        "ready_to_merge": False,
        "conflict_risk": conflict_risk,
        "recommended_action": recommended_action,
        "blockers": blockers,
        "merge_queue_status": merge_queue_status,
        "merge_queue_record": merge_queue_record,
        "proposal_bundle_id": None,
        "proposal_status": None,
        "proposal": None,
    }


def _inspect_summary(inspection: Mapping[str, object]) -> dict[str, object]:
    return {
        "status": inspection.get("status"),
        "worktree_status": inspection.get("worktree_status"),
        "dirty": inspection.get("dirty"),
        "changed_file_count": inspection.get("changed_file_count"),
        "diff_stat": inspection.get("diff_stat"),
        "changed_files": inspection.get("changed_files", []),
    }


def _inspect_failure_blocker(exc: Exception) -> tuple[str, str]:
    message = str(exc)
    if "missing" in message or "record" in message:
        return "missing_task_workspace_record", "create_task_worktree_or_verify_task_id"
    return "inspect_task_worktree_failed", "inspect_task_worktree"


def _preflight_blockers(preflight: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    if not bool(preflight.get("dirty")) or int(preflight.get("changed_file_count") or 0) == 0:
        blockers.append("no_changes")
    if bool(preflight.get("source_dirty")):
        blockers.append("source_dirty")
    overlapping_files = preflight.get("overlapping_files")
    if isinstance(overlapping_files, list) and overlapping_files:
        blockers.append("overlapping_files")
    if bool(preflight.get("source_head_changed")):
        blockers.append("source_head_drift")
    if not bool(preflight.get("ready_to_merge")) and not blockers:
        action = str(preflight.get("recommended_action") or "merge_preflight_not_ready")
        blockers.append(action)
    return blockers


def _recommended_action(preflight: Mapping[str, object], blockers: list[str]) -> str:
    if "source_head_drift" in blockers:
        return "refresh_task_worktree_or_manual_review"
    return str(preflight.get("recommended_action") or "inspect_task_worktree")


def _proposal_to_dict(proposal: object) -> dict[str, object]:
    if isinstance(proposal, BaseModel):
        return proposal.model_dump()
    if isinstance(proposal, Mapping):
        return dict(proposal)
    raise TypeError("proposal callback must return a mapping or pydantic model.")


def prepare_safe_task_merge_and_wait(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    proposal_callback: ProposalCallback,
    timeout_seconds: int | None = None,
    poll_interval_seconds: float | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, Any]:
    """Inspect, preflight, queue, and stage a task merge proposal without applying source changes."""
    source_cwd, _source_path = _resolve_source_cwd(cwd, workspace_root=workspace_root)
    normalized_project_id = _normalize_project_id(project_id, source_cwd)
    task_id_text = str(task_id or "").strip()

    try:
        inspection = inspect_task_worktree(
            task_id_text,
            cwd=source_cwd,
            project_id=normalized_project_id,
            runtime_root=runtime_root,
            workspace_root=workspace_root,
        )
    except Exception as exc:
        blocker, action = _inspect_failure_blocker(exc)
        return _empty_result(
            task_id=task_id_text,
            project_id=normalized_project_id,
            source_cwd=source_cwd,
            blockers=[blocker],
            recommended_action=action,
        )

    inspect_summary = _inspect_summary(inspection)
    preflight = merge_preflight_task_worktree(
        task_id_text,
        cwd=source_cwd,
        project_id=normalized_project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    blockers = _preflight_blockers(preflight)
    recommended_action = _recommended_action(preflight, blockers)
    conflict_risk = str(preflight.get("conflict_risk") or "unknown")
    if blockers:
        return _empty_result(
            task_id=task_id_text,
            project_id=normalized_project_id,
            source_cwd=source_cwd,
            blockers=blockers,
            recommended_action=recommended_action,
            conflict_risk=conflict_risk,
            inspect_summary=inspect_summary,
            preflight_result=preflight,
        )

    queue_status = read_merge_queue_entry(
        task_id_text,
        cwd=source_cwd,
        project_id=normalized_project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    existing_status = str(queue_status.get("status") or "missing")
    if existing_status not in {"missing", "queued"}:
        return _empty_result(
            task_id=task_id_text,
            project_id=normalized_project_id,
            source_cwd=source_cwd,
            blockers=[f"merge_queue_{existing_status}"],
            recommended_action="inspect_existing_merge_queue_record",
            conflict_risk=conflict_risk,
            inspect_summary=inspect_summary,
            preflight_result=preflight,
            merge_queue_status=existing_status,
            merge_queue_record=queue_status,
        )

    queued = enqueue_task_worktree_merge(
        task_id_text,
        cwd=source_cwd,
        project_id=normalized_project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    queued_status = str(queued.get("status") or "unknown")
    if queued_status != "queued":
        return _empty_result(
            task_id=task_id_text,
            project_id=normalized_project_id,
            source_cwd=source_cwd,
            blockers=[f"merge_queue_{queued_status}"],
            recommended_action="inspect_existing_merge_queue_record",
            conflict_risk=conflict_risk,
            inspect_summary=inspect_summary,
            preflight_result=preflight,
            merge_queue_status=queued_status,
            merge_queue_record=queued,
        )

    proposal = _proposal_to_dict(proposal_callback())
    return {
        "task_id": task_id_text,
        "project_id": normalized_project_id,
        "source_cwd": source_cwd,
        "inspect_summary": inspect_summary,
        "preflight_result": preflight,
        "ready_to_merge": True,
        "conflict_risk": conflict_risk,
        "recommended_action": recommended_action,
        "blockers": [],
        "merge_queue_status": queued_status,
        "merge_queue_record": queued,
        "proposal_bundle_id": proposal.get("bundle_id"),
        "proposal_status": proposal.get("status"),
        "proposal": proposal,
    }
