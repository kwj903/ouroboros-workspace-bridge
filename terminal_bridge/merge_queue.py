from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from terminal_bridge.config import RUNTIME_ROOT, WORKSPACE_ROOT
from terminal_bridge.storage import _now_iso, _read_json, _write_json
from terminal_bridge.task_workspaces import merge_preflight_task_worktree


MERGE_QUEUE_DIR_NAME = "merge_queue"
MERGE_QUEUE_RECORD_NAME = "queue.json"


def _merge_queue_root(runtime_root: Path | None = None) -> Path:
    if runtime_root is None:
        return (RUNTIME_ROOT / MERGE_QUEUE_DIR_NAME).expanduser().resolve(strict=False)
    return (runtime_root.expanduser() / MERGE_QUEUE_DIR_NAME).resolve(strict=False)


def _queue_key(task_id: str, project_id: str, source_cwd: str) -> str:
    payload = json.dumps(
        {"project_id": project_id, "source_cwd": source_cwd, "task_id": task_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"{task_id}-{digest}"


def _queue_record_path(queue_key: str, *, runtime_root: Path | None = None) -> Path:
    root = _merge_queue_root(runtime_root)
    path = (root / queue_key / MERGE_QUEUE_RECORD_NAME).resolve(strict=False)
    if path.parent != root and not path.parent.is_relative_to(root):
        raise ValueError("merge queue path resolves outside merge queue root.")
    return path


def _missing_queue_record(
    *,
    task_id: str,
    project_id: str,
    source_cwd: str,
    queue_key: str,
    record_path: Path,
) -> dict[str, Any]:
    return {
        "queue_key": queue_key,
        "task_id": task_id,
        "project_id": project_id,
        "source_cwd": source_cwd,
        "status": "missing",
        "exists": False,
        "record_path": str(record_path),
        "created_at": "",
        "updated_at": "",
    }


def enqueue_task_worktree_merge(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, Any]:
    preflight = merge_preflight_task_worktree(
        task_id,
        cwd=cwd,
        project_id=project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    if not bool(preflight.get("ready_to_merge")):
        raise ValueError(
            "task worktree is not ready for merge queue "
            f"(recommended_action={preflight.get('recommended_action')}, conflict_risk={preflight.get('conflict_risk')})"
        )

    task_id_text = str(preflight["task_id"])
    project_id_text = str(preflight["project_id"])
    source_cwd_text = str(preflight["source_cwd"])
    queue_key = _queue_key(task_id_text, project_id_text, source_cwd_text)
    record_path = _queue_record_path(queue_key, runtime_root=runtime_root)

    existing: dict[str, Any] = {}
    if record_path.exists():
        existing = _read_json(record_path)

    now = _now_iso()
    record = {
        "queue_key": queue_key,
        "task_id": task_id_text,
        "project_id": project_id_text,
        "source_cwd": source_cwd_text,
        "workspace_path": preflight.get("workspace_path"),
        "source_git_root": preflight.get("source_git_root"),
        "worktree_branch": preflight.get("worktree_branch"),
        "base_ref": preflight.get("base_ref"),
        "base_sha": preflight.get("base_sha"),
        "source_head_sha": preflight.get("source_head_sha"),
        "source_head_changed": preflight.get("source_head_changed"),
        "source_dirty": preflight.get("source_dirty"),
        "changed_file_count": preflight.get("changed_file_count"),
        "changed_files": preflight.get("changed_files", []),
        "overlapping_files": preflight.get("overlapping_files", []),
        "conflict_risk": preflight.get("conflict_risk"),
        "recommended_action": preflight.get("recommended_action"),
        "status": str(existing.get("status") or "queued"),
        "exists": True,
        "record_path": str(record_path),
        "created_at": str(existing.get("created_at") or now),
        "updated_at": now,
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(record_path, record)
    return record


def read_merge_queue_entry(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, Any]:
    preflight = merge_preflight_task_worktree(
        task_id,
        cwd=cwd,
        project_id=project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    task_id_text = str(preflight["task_id"])
    project_id_text = str(preflight["project_id"])
    source_cwd_text = str(preflight["source_cwd"])
    queue_key = _queue_key(task_id_text, project_id_text, source_cwd_text)
    record_path = _queue_record_path(queue_key, runtime_root=runtime_root)
    if record_path.exists():
        record = _read_json(record_path)
        record["exists"] = True
        return record
    return _missing_queue_record(
        task_id=task_id_text,
        project_id=project_id_text,
        source_cwd=source_cwd_text,
        queue_key=queue_key,
        record_path=record_path,
    )


def list_merge_queue(
    *,
    project_id: str | None = None,
    runtime_root: Path | None = None,
) -> list[dict[str, Any]]:
    root = _merge_queue_root(runtime_root)
    normalized_project_id = project_id.strip() if isinstance(project_id, str) and project_id.strip() else None
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return rows
    for path in sorted(root.glob(f"*/{MERGE_QUEUE_RECORD_NAME}")):
        try:
            record = _read_json(path)
        except Exception:
            continue
        if normalized_project_id is not None and record.get("project_id") != normalized_project_id:
            continue
        record["exists"] = True
        rows.append(record)
    rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return rows
