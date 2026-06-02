from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from terminal_bridge.merge_queue import list_merge_queue
from terminal_bridge.task_workspaces import _task_workspace_root, list_task_workspaces


READY_QUEUE_STATUSES = {"merged", "archived"}


def _record_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("project_id") or ""),
        str(record.get("source_cwd") or "."),
        str(record.get("task_id") or ""),
    )


def _as_path(value: object) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return Path(text).expanduser().resolve(strict=False)


def _is_under(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _is_git_worktree(path: Path) -> bool:
    return path.is_dir() and (path / ".git").exists()


def _git_status_short(path: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), "status", "--short"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        check=True,
    )
    return completed.stdout.rstrip("\n")


def _cleanup_risk(cleanup_ready: bool, blockers: list[str]) -> str:
    if cleanup_ready:
        return "low"
    high_risk_blockers = {
        "workspace_path_outside_runtime",
        "record_path_outside_runtime",
        "workspace_not_git_worktree",
        "git_status_failed",
        "worktree_dirty",
        "validation_failed",
    }
    if high_risk_blockers.intersection(blockers):
        return "high"
    return "medium"


def _recommended_action(cleanup_ready: bool, blockers: list[str]) -> str:
    if cleanup_ready:
        return "ready_for_physical_cleanup_review"
    if "workspace_path_outside_runtime" in blockers or "record_path_outside_runtime" in blockers:
        return "inspect_runtime_record"
    if "worktree_dirty" in blockers:
        return "inspect_or_preserve_worktree"
    if "validation_failed" in blockers:
        return "resolve_failed_validation_before_cleanup"
    if "validation_not_passed" in blockers:
        return "record_passed_validation_before_cleanup"
    if "task_workspace_not_archived" in blockers or "merge_queue_not_merged_or_archived" in blockers:
        return "finish_merge_archive_validation_lifecycle"
    if "missing_task_workspace_record" in blockers or "missing_merge_queue_record" in blockers:
        return "inspect_runtime_records"
    return "inspect_cleanup_blockers"


def _preview_entry(
    key: tuple[str, str, str],
    *,
    task_record: dict[str, Any] | None,
    queue_record: dict[str, Any] | None,
    task_root: Path,
) -> dict[str, Any]:
    project_id, source_cwd, task_id = key
    has_task = task_record is not None
    has_queue = queue_record is not None
    blockers: list[str] = []
    worktree_dirty: bool | None = None

    workspace_status = str(task_record.get("status") or "missing") if task_record else "missing"
    queue_status = str(queue_record.get("status") or "") if queue_record else None
    validation_status = str(queue_record.get("validation_status") or "unknown") if queue_record else "unknown"

    workspace_path = None
    if task_record and task_record.get("workspace_path") is not None:
        workspace_path = str(task_record.get("workspace_path"))
    elif queue_record and queue_record.get("workspace_path") is not None:
        workspace_path = str(queue_record.get("workspace_path"))

    record_path = None
    if task_record and task_record.get("record_path") is not None:
        record_path = str(task_record.get("record_path"))
    elif queue_record and queue_record.get("record_path") is not None:
        record_path = str(queue_record.get("record_path"))

    if not has_task:
        blockers.append("missing_task_workspace_record")
    elif workspace_status != "archived":
        blockers.append("task_workspace_not_archived")

    if not has_queue:
        blockers.append("missing_merge_queue_record")
    elif queue_status not in READY_QUEUE_STATUSES:
        blockers.append("merge_queue_not_merged_or_archived")

    if validation_status == "failed":
        blockers.append("validation_failed")
    elif validation_status != "passed":
        blockers.append("validation_not_passed")

    if task_record:
        record_path_obj = _as_path(task_record.get("record_path"))
        if record_path_obj is None:
            blockers.append("record_path_missing")
        elif not _is_under(record_path_obj, task_root):
            blockers.append("record_path_outside_runtime")
        elif not record_path_obj.exists():
            blockers.append("record_path_missing")

        workspace_path_obj = _as_path(task_record.get("workspace_path"))
        if workspace_path_obj is None:
            blockers.append("workspace_path_missing")
        elif not _is_under(workspace_path_obj, task_root):
            blockers.append("workspace_path_outside_runtime")
        elif not workspace_path_obj.exists():
            blockers.append("workspace_path_missing")
        elif not workspace_path_obj.is_dir():
            blockers.append("workspace_path_not_directory")
        elif not _is_git_worktree(workspace_path_obj):
            blockers.append("workspace_not_git_worktree")
        else:
            try:
                status_short = _git_status_short(workspace_path_obj)
            except subprocess.CalledProcessError:
                blockers.append("git_status_failed")
            else:
                worktree_dirty = bool(status_short.strip())
                if worktree_dirty:
                    blockers.append("worktree_dirty")

    cleanup_ready = not blockers
    risk = _cleanup_risk(cleanup_ready, blockers)
    action = _recommended_action(cleanup_ready, blockers)

    return {
        "task_id": task_id,
        "project_id": project_id,
        "source_cwd": source_cwd,
        "workspace_path": workspace_path,
        "record_path": record_path,
        "queue_status": queue_status,
        "workspace_status": workspace_status,
        "validation_status": validation_status,
        "cleanup_ready": cleanup_ready,
        "cleanup_risk": risk,
        "cleanup_blockers": blockers,
        "recommended_action": action,
        "worktree_dirty": worktree_dirty,
        "has_task_workspace_record": has_task,
        "has_merge_queue_record": has_queue,
    }


def task_cleanup_preview(
    *,
    project_id: str | None = None,
    runtime_root: Path | None = None,
) -> dict[str, Any]:
    tasks = list_task_workspaces(project_id=project_id, runtime_root=runtime_root)
    queues = list_merge_queue(project_id=project_id, runtime_root=runtime_root)
    task_root = _task_workspace_root(runtime_root)

    task_by_key = {_record_key(record): record for record in tasks}
    queue_by_key = {_record_key(record): record for record in queues}
    keys = sorted(set(task_by_key).union(queue_by_key), key=lambda item: (item[0], item[1], item[2]))
    entries = [
        _preview_entry(
            key,
            task_record=task_by_key.get(key),
            queue_record=queue_by_key.get(key),
            task_root=task_root,
        )
        for key in keys
    ]
    ready_count = sum(1 for entry in entries if bool(entry["cleanup_ready"]))
    return {
        "project_id": project_id.strip() if isinstance(project_id, str) and project_id.strip() else None,
        "entries": entries,
        "count": len(entries),
        "ready_count": ready_count,
        "blocked_count": len(entries) - ready_count,
    }
