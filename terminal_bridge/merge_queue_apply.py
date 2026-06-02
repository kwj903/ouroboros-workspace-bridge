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
from terminal_bridge.merge_queue import read_merge_queue_entry
from terminal_bridge.storage import _now_iso, _read_json, _write_json


def _run_git(argv: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "shell": False,
        "check": True,
    }
    if input_text is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = input_text
    return subprocess.run(argv, **kwargs)


def _git_stdout(argv: list[str]) -> str:
    return _run_git(argv).stdout.rstrip("\n")


def _git_failure_message(exc: subprocess.CalledProcessError) -> str:
    return (exc.stderr or exc.stdout or str(exc)).strip()


def _ensure_under(path: Path, root: Path, label: str) -> None:
    if path != root and not path.is_relative_to(root):
        raise ValueError(f"{label} escapes expected root: {path}")


def apply_queued_task_worktree_merge(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, Any]:
    record = read_merge_queue_entry(
        task_id,
        cwd=cwd,
        project_id=project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    if record.get("status") != "queued" or not record.get("exists"):
        raise ValueError(f"merge queue entry is not queued: status={record.get('status')}")

    source_git_root = Path(str(record.get("source_git_root") or "")).expanduser().resolve(strict=False)
    workspace_path = Path(str(record.get("workspace_path") or "")).expanduser().resolve(strict=False)
    if not str(source_git_root):
        raise ValueError("merge queue record is missing source_git_root.")
    if not str(workspace_path):
        raise ValueError("merge queue record is missing workspace_path.")

    _ensure_under(source_git_root, workspace_root.expanduser().resolve(strict=False), "source_git_root")
    task_root = ((runtime_root or RUNTIME_ROOT).expanduser() / "task_workspaces").resolve(strict=False)
    _ensure_under(workspace_path, task_root, "workspace_path")

    if not (workspace_path / ".git").exists():
        raise ValueError(f"workspace_path is not a git worktree: {workspace_path}")

    expected_source_head = str(record.get("source_head_sha") or "").strip()
    if not expected_source_head:
        raise ValueError("merge queue record is missing source_head_sha.")
    current_source_head = _git_stdout(["git", "-C", str(source_git_root), "rev-parse", "HEAD"]).strip()
    if current_source_head != expected_source_head:
        raise ValueError("source HEAD changed since enqueue; rerun preflight and enqueue again.")

    source_status = _git_stdout(["git", "-C", str(source_git_root), "status", "--short"])
    if source_status.strip():
        raise ValueError("source workspace is not clean; commit/stash/revert source changes before merge apply.")

    base_sha = str(record.get("base_sha") or "").strip()
    if not base_sha:
        raise ValueError("merge queue record is missing base_sha.")
    diff_text = _run_git(["git", "-C", str(workspace_path), "diff", "--binary", base_sha, "--"]).stdout
    if not diff_text.strip():
        raise ValueError("task worktree has no diff to apply.")

    try:
        _run_git(["git", "-C", str(source_git_root), "apply", "--check", "--whitespace=nowarn", "-"], input_text=diff_text)
        _run_git(["git", "-C", str(source_git_root), "apply", "--whitespace=nowarn", "-"], input_text=diff_text)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git apply failed: {_git_failure_message(exc)}") from exc

    post_status = _git_stdout(["git", "-C", str(source_git_root), "status", "--short"])
    now = _now_iso()
    record_path = Path(str(record.get("record_path") or "")).expanduser().resolve(strict=False)
    if record_path.exists():
        stored = _read_json(record_path)
        stored.update(
            {
                "status": "merged",
                "exists": True,
                "merged_at": now,
                "updated_at": now,
                "applied_source_head_before": current_source_head,
                "source_status_after_apply": post_status,
            }
        )
        _write_json(record_path, stored)
        record = stored
    else:
        record.update(
            {
                "status": "merged",
                "exists": True,
                "merged_at": now,
                "updated_at": now,
                "applied_source_head_before": current_source_head,
                "source_status_after_apply": post_status,
            }
        )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a queued task worktree merge to the source project after local approval.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--project-id", default=None)
    args = parser.parse_args()
    result = apply_queued_task_worktree_merge(args.task_id, cwd=args.cwd, project_id=args.project_id)
    print(f"applied queued task merge: {result['task_id']} -> {result.get('source_cwd')}")
    print(f"queue status: {result.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
