from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from terminal_bridge.config import WORKSPACE_ROOT
from terminal_bridge.merge_queue import task_validation_status
from terminal_bridge.models import CommandBundleStep
from terminal_bridge.task_workspaces import _normalize_project_id, _resolve_source_cwd


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


def _ensure_under(path: Path, root: Path, label: str) -> None:
    if path != root and not path.is_relative_to(root):
        raise ValueError(f"{label} escapes expected root: {path}")


def _normalize_argv(argv: object) -> list[str]:
    if not isinstance(argv, list):
        raise ValueError("validation command argv must be a list of strings.")
    normalized = [str(item) for item in argv]
    if not normalized or not normalized[0].strip():
        raise ValueError("validation command argv cannot be empty.")
    return normalized


def _source_git_root(
    record: dict[str, Any],
    *,
    source_path: Path,
    workspace_root: Path,
) -> Path:
    raw = str(record.get("source_git_root") or "").strip()
    if raw:
        source_git_root = Path(raw).expanduser().resolve(strict=False)
    else:
        source_git_root = Path(_git_stdout(["git", "-C", str(source_path), "rev-parse", "--show-toplevel"]))
        source_git_root = source_git_root.expanduser().resolve(strict=False)
    _ensure_under(source_git_root, workspace_root.expanduser().resolve(strict=False), "source_git_root")
    if not source_git_root.exists():
        raise FileNotFoundError(f"source_git_root does not exist: {source_git_root}")
    return source_git_root


def prepare_task_validation_command_proposal(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    argv: object,
    command_name: object | None = None,
    command_timeout_seconds: int = 60,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, Any]:
    source_cwd, source_path = _resolve_source_cwd(cwd, workspace_root=workspace_root)
    normalized_project_id = _normalize_project_id(project_id, source_cwd)
    record = task_validation_status(
        task_id,
        cwd=source_cwd,
        project_id=normalized_project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    if not record.get("exists"):
        raise FileNotFoundError("merge queue record not found.")
    if record.get("status") != "merged":
        raise ValueError(f"merge queue entry must be merged before proposing validation: status={record.get('status')}")

    source_git_root = _source_git_root(record, source_path=source_path, workspace_root=workspace_root)
    source_status = _git_stdout(["git", "-C", str(source_git_root), "status", "--short"])
    source_dirty = bool(source_status.strip())
    validation_blockers = ["source_dirty"] if source_dirty else []

    normalized_argv = _normalize_argv(argv)
    normalized_command_name = str(command_name or "").strip() or "Run source validation"
    title = f"Validate merged task: {record.get('task_id') or task_id}"
    step = CommandBundleStep(
        name=normalized_command_name,
        argv=normalized_argv,
        timeout_seconds=command_timeout_seconds,
    )
    metadata = {
        "task_id": str(record.get("task_id") or task_id),
        "project_id": str(record.get("project_id") or normalized_project_id),
        "workspace_mode": "direct",
        "source_cwd": source_cwd,
        "effective_cwd": source_cwd,
        "validation_command": normalized_argv,
        "validation_command_name": normalized_command_name,
        "merge_queue_status": str(record.get("status") or "unknown"),
        "source_dirty": source_dirty,
        "validation_blockers": validation_blockers,
        "validation_risk": "high" if validation_blockers else "normal",
    }
    return {
        "title": title,
        "cwd": source_cwd,
        "step": step,
        "metadata": metadata,
        "merge_queue_record": record,
    }
