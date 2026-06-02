from __future__ import annotations

from pathlib import Path
from typing import Any

from terminal_bridge.merge_queue import list_merge_queue
from terminal_bridge.task_workspaces import list_task_workspaces


def _record_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("project_id") or ""),
        str(record.get("source_cwd") or "."),
        str(record.get("task_id") or ""),
    )


def _is_archived(record: dict[str, Any] | None) -> bool:
    return bool(record) and str(record.get("status") or "") == "archived"


def _optional_bool(record: dict[str, Any] | None, key: str) -> bool | None:
    if not record or record.get(key) is None:
        return None
    return bool(record.get(key))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _summary_entry(
    key: tuple[str, str, str],
    *,
    task_record: dict[str, Any] | None,
    queue_record: dict[str, Any] | None,
) -> dict[str, Any]:
    project_id, source_cwd, task_id = key
    anomaly_reasons: list[str] = []
    has_task = task_record is not None
    has_queue = queue_record is not None

    if has_queue and not has_task:
        anomaly_reasons.append("missing_task_workspace_record")
    if has_task and not task_id:
        anomaly_reasons.append("missing_task_id")

    task_status = str(task_record.get("status") or "missing") if task_record else "missing"
    queue_status = str(queue_record.get("status") or "") if queue_record else None
    archived = _is_archived(task_record) or _is_archived(queue_record)

    workspace_path = None
    if task_record and task_record.get("workspace_path") is not None:
        workspace_path = str(task_record.get("workspace_path"))
    elif queue_record and queue_record.get("workspace_path") is not None:
        workspace_path = str(queue_record.get("workspace_path"))

    worktree_branch = None
    if task_record and task_record.get("worktree_branch") is not None:
        worktree_branch = str(task_record.get("worktree_branch"))
    elif queue_record and queue_record.get("worktree_branch") is not None:
        worktree_branch = str(queue_record.get("worktree_branch"))

    changed_file_count = None
    if queue_record and queue_record.get("changed_file_count") is not None:
        try:
            changed_file_count = int(queue_record.get("changed_file_count"))
        except (TypeError, ValueError):
            anomaly_reasons.append("invalid_changed_file_count")

    source_head_changed = _optional_bool(queue_record, "source_head_changed")
    source_dirty = _optional_bool(queue_record, "source_dirty")
    overlapping_files = _string_list(queue_record.get("overlapping_files") if queue_record else [])
    conflict_risk = str(queue_record.get("conflict_risk")) if queue_record and queue_record.get("conflict_risk") is not None else None
    recommended_action = str(queue_record.get("recommended_action")) if queue_record and queue_record.get("recommended_action") is not None else None
    validation_status = str(queue_record.get("validation_status") or "unknown") if queue_record else "unknown"
    validation_commands = _string_list(queue_record.get("validation_commands") if queue_record else [])
    validation_summary = str(queue_record.get("validation_summary")) if queue_record and queue_record.get("validation_summary") is not None else None
    validated_at = str(queue_record.get("validated_at")) if queue_record and queue_record.get("validated_at") is not None else None
    validated_by = str(queue_record.get("validated_by")) if queue_record and queue_record.get("validated_by") is not None else None
    validation_client_id = str(queue_record.get("validation_client_id")) if queue_record and queue_record.get("validation_client_id") is not None else None
    validation_session_id = str(queue_record.get("validation_session_id")) if queue_record and queue_record.get("validation_session_id") is not None else None

    operator_attention_reasons: list[str] = []
    if conflict_risk == "high":
        operator_attention_reasons.append("high_risk")
    if source_dirty:
        operator_attention_reasons.append("source_dirty")
    if source_head_changed:
        operator_attention_reasons.append("source_head_changed")
    if overlapping_files:
        operator_attention_reasons.append("overlapping_files")
    if validation_status == "failed":
        operator_attention_reasons.append("validation_failed")
    operator_attention_reasons.extend(anomaly_reasons)

    return {
        "project_id": project_id,
        "source_cwd": source_cwd,
        "task_id": task_id,
        "task_workspace_status": task_status,
        "worktree_status": str(task_record.get("worktree_status")) if task_record and task_record.get("worktree_status") is not None else None,
        "worktree_branch": worktree_branch,
        "workspace_path": workspace_path,
        "merge_queue_status": queue_status,
        "conflict_risk": conflict_risk,
        "recommended_action": recommended_action,
        "changed_file_count": changed_file_count,
        "source_head_changed": source_head_changed,
        "source_dirty": source_dirty,
        "overlapping_files": overlapping_files,
        "operator_attention": bool(operator_attention_reasons),
        "operator_attention_reasons": operator_attention_reasons,
        "validation_status": validation_status,
        "validation_commands": validation_commands,
        "validation_summary": validation_summary,
        "validated_at": validated_at,
        "validated_by": validated_by,
        "validation_client_id": validation_client_id,
        "validation_session_id": validation_session_id,
        "archived": archived,
        "has_task_workspace_record": has_task,
        "has_merge_queue_record": has_queue,
        "anomaly": bool(anomaly_reasons),
        "anomaly_reasons": anomaly_reasons,
    }


def task_orchestration_summary(
    *,
    project_id: str | None = None,
    runtime_root: Path | None = None,
) -> dict[str, Any]:
    tasks = list_task_workspaces(project_id=project_id, runtime_root=runtime_root)
    queues = list_merge_queue(project_id=project_id, runtime_root=runtime_root)

    task_by_key = {_record_key(record): record for record in tasks}
    queue_by_key = {_record_key(record): record for record in queues}
    keys = sorted(set(task_by_key).union(queue_by_key), key=lambda item: (item[0], item[1], item[2]))

    entries = [
        _summary_entry(
            key,
            task_record=task_by_key.get(key),
            queue_record=queue_by_key.get(key),
        )
        for key in keys
    ]
    archived_count = sum(1 for entry in entries if bool(entry["archived"]))
    anomaly_count = sum(1 for entry in entries if bool(entry["anomaly"]))
    attention_count = sum(1 for entry in entries if bool(entry.get("operator_attention")))

    return {
        "project_id": project_id.strip() if isinstance(project_id, str) and project_id.strip() else None,
        "entries": entries,
        "count": len(entries),
        "active_count": len(entries) - archived_count,
        "archived_count": archived_count,
        "anomaly_count": anomaly_count,
        "attention_count": attention_count,
    }
