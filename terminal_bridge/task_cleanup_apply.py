from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from terminal_bridge.config import RUNTIME_ROOT, WORKSPACE_ROOT
from terminal_bridge.merge_queue import list_merge_queue
from terminal_bridge.storage import _now_iso, _read_json, _write_json
from terminal_bridge.task_cleanup_preview import task_cleanup_preview
from terminal_bridge.task_workspaces import _normalize_project_id, _resolve_source_cwd, _task_workspace_root


def _run_git(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        check=True,
    )


def _git_stdout(argv: list[str]) -> str:
    return _run_git(argv).stdout.rstrip("\n")


def _git_failure_message(exc: subprocess.CalledProcessError) -> str:
    return (exc.stderr or exc.stdout or str(exc)).strip()


def _as_path(value: object) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return Path(text).expanduser().resolve(strict=False)


def _ensure_under(path: Path, root: Path, label: str) -> None:
    if path != root and not path.is_relative_to(root):
        raise ValueError(f"{label} escapes expected root: {path}")


def _matching_preview_entry(
    task_id: str,
    *,
    source_cwd: str,
    project_id: str,
    runtime_root: Path | None,
) -> dict[str, Any]:
    preview = task_cleanup_preview(project_id=project_id, runtime_root=runtime_root)
    for entry in preview.get("entries", []):
        if entry.get("task_id") == task_id and entry.get("source_cwd") == source_cwd:
            return entry
    raise FileNotFoundError("cleanup preview entry not found for task/source/project.")


def _matching_queue_record(
    task_id: str,
    *,
    source_cwd: str,
    project_id: str,
    runtime_root: Path | None,
) -> dict[str, Any] | None:
    for record in list_merge_queue(project_id=project_id, runtime_root=runtime_root):
        if record.get("task_id") == task_id and record.get("source_cwd") == source_cwd:
            return record
    return None


def _source_git_root_for_cleanup(
    entry: dict[str, Any],
    task_record: dict[str, Any],
    *,
    source_path: Path,
    workspace_root: Path,
) -> Path:
    raw = task_record.get("source_git_root") or entry.get("source_git_root")
    if raw:
        source_git_root = Path(str(raw)).expanduser().resolve(strict=False)
    else:
        source_git_root = Path(_git_stdout(["git", "-C", str(source_path), "rev-parse", "--show-toplevel"]))
        source_git_root = source_git_root.expanduser().resolve(strict=False)
    _ensure_under(source_git_root, workspace_root.expanduser().resolve(strict=False), "source_git_root")
    if not source_git_root.exists():
        raise FileNotFoundError(f"source_git_root does not exist: {source_git_root}")
    return source_git_root


def apply_task_cleanup(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, Any]:
    source_cwd, source_path = _resolve_source_cwd(cwd, workspace_root=workspace_root)
    normalized_project_id = _normalize_project_id(project_id, source_cwd)
    entry = _matching_preview_entry(
        task_id,
        source_cwd=source_cwd,
        project_id=normalized_project_id,
        runtime_root=runtime_root,
    )
    if not bool(entry.get("cleanup_ready")):
        blockers = entry.get("cleanup_blockers", [])
        action = entry.get("recommended_action")
        raise ValueError(f"task workspace is not ready for physical cleanup (blockers={blockers}, recommended_action={action})")

    task_root = _task_workspace_root(runtime_root)
    workspace_path = _as_path(entry.get("workspace_path"))
    record_path = _as_path(entry.get("record_path"))
    if workspace_path is None:
        raise ValueError("cleanup preview entry is missing workspace_path.")
    if record_path is None:
        raise ValueError("cleanup preview entry is missing record_path.")
    _ensure_under(workspace_path, task_root, "workspace_path")
    _ensure_under(record_path, task_root, "record_path")
    if not record_path.exists():
        raise FileNotFoundError("task workspace record not found.")
    if not workspace_path.exists():
        raise FileNotFoundError("task workspace path not found.")
    if not (workspace_path / ".git").exists():
        raise ValueError(f"workspace_path is not a git worktree: {workspace_path}")

    status_short = _git_stdout(["git", "-C", str(workspace_path), "status", "--short"])
    if status_short.strip():
        raise ValueError("task worktree is not clean; inspect or preserve it before cleanup.")

    task_record = _read_json(record_path)
    source_git_root = _source_git_root_for_cleanup(
        entry,
        task_record,
        source_path=source_path,
        workspace_root=workspace_root,
    )
    try:
        _run_git(["git", "-C", str(source_git_root), "worktree", "remove", str(workspace_path)])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git worktree remove failed: {_git_failure_message(exc)}") from exc

    if workspace_path.exists():
        raise RuntimeError("git worktree remove completed but workspace_path still exists.")

    now = _now_iso()
    task_record.update(
        {
            "status": "cleaned",
            "exists": False,
            "worktree_status": "removed",
            "cleanup_status": "cleaned",
            "cleanup_applied_at": now,
            "cleanup_workspace_path": str(workspace_path),
            "updated_at": now,
        }
    )
    _write_json(record_path, task_record)

    queue_record = _matching_queue_record(
        task_id,
        source_cwd=source_cwd,
        project_id=normalized_project_id,
        runtime_root=runtime_root,
    )
    if queue_record is not None:
        queue_record_path = _as_path(queue_record.get("record_path"))
        if queue_record_path is not None and queue_record_path.exists():
            queue_record.update(
                {
                    "cleanup_status": "cleaned",
                    "cleanup_applied_at": now,
                    "cleanup_workspace_path": str(workspace_path),
                    "updated_at": now,
                    "exists": True,
                }
            )
            _write_json(queue_record_path, queue_record)

    return {
        "task_id": task_id,
        "project_id": normalized_project_id,
        "source_cwd": source_cwd,
        "workspace_path": str(workspace_path),
        "record_path": str(record_path),
        "cleanup_status": "cleaned",
        "cleanup_applied_at": now,
        "worktree_removed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Physically clean up a ready archived task worktree after local approval.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--project-id", default=None)
    args = parser.parse_args()
    result = apply_task_cleanup(args.task_id, cwd=args.cwd, project_id=args.project_id)
    print(f"cleaned task worktree: {result['task_id']} -> {result.get('workspace_path')}")
    print(f"cleanup status: {result.get('cleanup_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
