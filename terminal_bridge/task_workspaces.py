from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from terminal_bridge.bundles import _default_command_bundle_metadata, _normalize_command_bundle_metadata
from terminal_bridge.config import TASK_WORKSPACES_DIR, WORKSPACE_ROOT
from terminal_bridge.storage import _now_iso, _read_json, _write_json
from terminal_bridge.tasks import _normalize_task_id


TASK_WORKSPACE_MODE = "task-workspace"
TASK_WORKSPACE_RECORD_NAME = "workspace.json"
TASK_WORKSPACE_REPO_DIR_NAME = "repo"
GitRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class TaskWorkspaceResolution:
    workspace_mode: str
    status: str
    reason: str
    exists: bool
    task_id: str | None = None
    project_id: str | None = None
    source_cwd: str | None = None
    workspace_key: str | None = None
    workspace_path: str | None = None
    record_path: str | None = None
    record: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object | None]:
        return {
            "workspace_mode": self.workspace_mode,
            "status": self.status,
            "reason": self.reason,
            "exists": self.exists,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "source_cwd": self.source_cwd,
            "workspace_key": self.workspace_key,
            "workspace_path": self.workspace_path,
            "record_path": self.record_path,
            "record": self.record,
        }


def _task_workspace_root(runtime_root: Path | None = None) -> Path:
    if runtime_root is None:
        return TASK_WORKSPACES_DIR.expanduser().resolve(strict=False)
    return (runtime_root.expanduser() / "task_workspaces").resolve(strict=False)


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


def _normalize_project_id(project_id: object | None, source_cwd: str) -> str:
    if project_id is None:
        return str(_default_command_bundle_metadata(source_cwd)["project_id"])
    if not isinstance(project_id, str):
        raise ValueError("project_id must be a string when provided.")

    normalized = project_id.strip()
    if not normalized:
        return str(_default_command_bundle_metadata(source_cwd)["project_id"])
    if len(normalized) > 256:
        raise ValueError("project_id is too long.")
    if "/" in normalized or "\\" in normalized or "\x00" in normalized:
        raise ValueError("project_id cannot contain path separators.")
    return normalized


def _resolve_source_cwd(cwd: object, *, workspace_root: Path = WORKSPACE_ROOT) -> tuple[str, Path]:
    root = workspace_root.expanduser().resolve(strict=False)
    raw_text = "." if cwd is None else str(cwd).strip() or "."
    raw = Path(raw_text).expanduser()
    if raw.is_absolute():
        raise ValueError("source_cwd must be a relative path under WORKSPACE_ROOT.")

    candidate = (root / raw).resolve(strict=False)
    if candidate != root and not candidate.is_relative_to(root):
        raise ValueError("source_cwd escapes WORKSPACE_ROOT.")

    relative = "." if candidate == root else str(candidate.relative_to(root))
    return relative, candidate


def _workspace_key(task_id: str, project_id: str, source_cwd: str) -> str:
    payload = json.dumps(
        {
            "project_id": project_id,
            "source_cwd": source_cwd,
            "task_id": task_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"{task_id}-{digest}"


def _task_workspace_paths(
    task_id: object,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, object]:
    normalized_task_id = _normalize_task_id(str(task_id or ""))
    source_cwd, source_path = _resolve_source_cwd(cwd, workspace_root=workspace_root)
    normalized_project_id = _normalize_project_id(project_id, source_cwd)
    key = _workspace_key(normalized_task_id, normalized_project_id, source_cwd)
    root = _task_workspace_root(runtime_root)
    workspace_dir = (root / key).resolve(strict=False)
    workspace_path = (workspace_dir / TASK_WORKSPACE_REPO_DIR_NAME).resolve(strict=False)
    record_path = (workspace_dir / TASK_WORKSPACE_RECORD_NAME).resolve(strict=False)

    for path in (workspace_dir, workspace_path, record_path):
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("task workspace path resolves outside task workspace root.") from exc

    return {
        "task_id": normalized_task_id,
        "project_id": normalized_project_id,
        "source_cwd": source_cwd,
        "source_path": source_path,
        "workspace_key": key,
        "workspace_dir": workspace_dir,
        "workspace_path": workspace_path,
        "record_path": record_path,
    }


def _record_with_current_status(record: dict[str, object]) -> dict[str, object]:
    refreshed = dict(record)
    raw_workspace_path = str(refreshed.get("workspace_path") or "").strip()
    workspace_path = Path(raw_workspace_path) if raw_workspace_path else None
    exists = bool(workspace_path) and workspace_path.exists()
    if refreshed.get("status") != "archived":
        if workspace_path is not None and _is_git_worktree_path(workspace_path):
            refreshed["status"] = "worktree"
            refreshed["worktree_status"] = "ready"
        elif refreshed.get("status") == "worktree":
            refreshed["status"] = "missing"
            refreshed["worktree_status"] = "missing"
        else:
            refreshed["status"] = "created" if exists else "missing"
    refreshed["exists"] = exists
    return refreshed


def _is_git_worktree_path(path: Path) -> bool:
    return path.is_dir() and (path / ".git").exists()


def _git_stdout(git_runner: GitRunner, argv: list[str]) -> str:
    completed = git_runner(argv)
    return completed.stdout.strip()


def _git_inspection_stdout(git_runner: GitRunner, workspace_path: Path, args: list[str]) -> str:
    argv = ["git", "-C", str(workspace_path), *args]
    try:
        completed = git_runner(argv)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}") from exc
    return completed.stdout.rstrip("\n")


def _source_git_info(
    source_path: Path,
    *,
    workspace_root: Path,
    git_runner: GitRunner,
) -> dict[str, str]:
    try:
        source_git_root = Path(
            _git_stdout(git_runner, ["git", "-C", str(source_path), "rev-parse", "--show-toplevel"])
        ).expanduser().resolve(strict=False)
    except subprocess.CalledProcessError as exc:
        raise ValueError("source_cwd is not a git repository.") from exc

    root = workspace_root.expanduser().resolve(strict=False)
    if source_git_root != root and not source_git_root.is_relative_to(root):
        raise ValueError("source git root escapes WORKSPACE_ROOT.")

    try:
        base_ref = _git_stdout(git_runner, ["git", "-C", str(source_git_root), "rev-parse", "--abbrev-ref", "HEAD"])
        base_sha = _git_stdout(git_runner, ["git", "-C", str(source_git_root), "rev-parse", "HEAD"])
    except subprocess.CalledProcessError as exc:
        raise ValueError("source git repository does not have a valid HEAD.") from exc

    return {
        "source_git_root": str(source_git_root),
        "base_ref": base_ref or "HEAD",
        "base_sha": base_sha,
    }


def _target_has_unknown_files(path: Path) -> bool:
    if not path.exists():
        return False
    if _is_git_worktree_path(path):
        return False
    return any(path.iterdir())


def _task_workspace_not_ready_message(status: str) -> str:
    return (
        "task workspace worktree is not ready "
        f"(status={status}); run workspace_create_task_worktree before inspecting this task worktree."
    )


def _validate_task_worktree_record(
    raw_record: dict[str, object],
    *,
    runtime_root: Path | None = None,
) -> tuple[dict[str, object], Path]:
    record = _record_with_current_status(raw_record)
    workspace_path_text = str(raw_record.get("workspace_path") or "").strip()
    if not workspace_path_text:
        raise ValueError(_task_workspace_not_ready_message(str(record.get("status") or "missing")))

    workspace_path = Path(workspace_path_text).expanduser().resolve(strict=False)
    task_root = _task_workspace_root(runtime_root)
    if workspace_path != task_root and not workspace_path.is_relative_to(task_root):
        raise ValueError(f"workspace_path escapes task workspace root: {workspace_path}")

    raw_status = str(raw_record.get("status") or "")
    status = str(record.get("status") or "missing")
    worktree_status = str(record.get("worktree_status") or "")

    if raw_status == "worktree" and workspace_path.exists() and not _is_git_worktree_path(workspace_path):
        raise ValueError(f"workspace_path is not a git worktree: {workspace_path}")

    if status != "worktree" or worktree_status != "ready":
        raise ValueError(_task_workspace_not_ready_message(status))

    if not _is_git_worktree_path(workspace_path):
        raise ValueError(f"workspace_path is not a git worktree: {workspace_path}")

    return record, workspace_path


def _parse_diff_name_status(diff_name_status: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for line in diff_name_status.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if len(parts) >= 3 and status[:1] in {"R", "C"}:
            old_path = parts[1]
            path = parts[2]
            item = {"status": status, "path": path, "old_path": old_path}
        elif len(parts) >= 2:
            path = parts[-1]
            item = {"status": status, "path": path}
        else:
            continue
        if path not in seen:
            seen.add(path)
            rows.append(item)

    return rows


def _parse_status_short_extra_paths(status_short: str, seen_paths: set[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in status_short.splitlines():
        if len(line) < 4:
            continue
        status = line[:2].strip() or line[:2]
        path_text = line[3:]
        old_path: str | None = None
        if " -> " in path_text:
            old_path, path_text = path_text.split(" -> ", 1)
        if path_text in seen_paths:
            continue
        seen_paths.add(path_text)
        item = {"status": status, "path": path_text}
        if old_path:
            item["old_path"] = old_path
        rows.append(item)
    return rows


def _missing_record(fields: dict[str, object]) -> dict[str, object]:
    return {
        "task_id": fields["task_id"],
        "project_id": fields["project_id"],
        "source_cwd": fields["source_cwd"],
        "workspace_mode": TASK_WORKSPACE_MODE,
        "workspace_key": fields["workspace_key"],
        "workspace_path": str(fields["workspace_path"]),
        "record_path": str(fields["record_path"]),
        "worktree_branch": f"task/{fields['workspace_key']}",
        "status": "missing",
        "exists": False,
        "created_at": "",
        "updated_at": "",
    }


def prepare_task_workspace(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, object]:
    fields = _task_workspace_paths(
        task_id,
        cwd=cwd,
        project_id=project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    source_path = fields["source_path"]
    if not isinstance(source_path, Path) or not source_path.exists() or not source_path.is_dir():
        raise NotADirectoryError(f"source_cwd does not exist or is not a directory: {fields['source_cwd']}")

    record_path = fields["record_path"]
    existing: dict[str, object] = {}
    if isinstance(record_path, Path) and record_path.exists():
        existing = _read_json(record_path)

    now = _now_iso()
    workspace_path = fields["workspace_path"]
    if not isinstance(workspace_path, Path):
        raise ValueError("Invalid task workspace path.")
    workspace_path.mkdir(parents=True, exist_ok=True)

    record = {
        "task_id": fields["task_id"],
        "project_id": fields["project_id"],
        "source_cwd": fields["source_cwd"],
        "workspace_mode": TASK_WORKSPACE_MODE,
        "workspace_key": fields["workspace_key"],
        "workspace_path": str(workspace_path),
        "record_path": str(record_path),
        "worktree_branch": str(existing.get("worktree_branch") or f"task/{fields['workspace_key']}"),
        "status": "created",
        "exists": True,
        "created_at": str(existing.get("created_at") or now),
        "updated_at": now,
    }
    if not isinstance(record_path, Path):
        raise ValueError("Invalid task workspace record path.")
    _write_json(record_path, record)
    return _record_with_current_status(record)


def create_task_worktree(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
    git_runner: GitRunner = _run_git,
) -> dict[str, object]:
    fields = _task_workspace_paths(
        task_id,
        cwd=cwd,
        project_id=project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    source_path = fields["source_path"]
    if not isinstance(source_path, Path) or not source_path.exists() or not source_path.is_dir():
        raise NotADirectoryError(f"source_cwd does not exist or is not a directory: {fields['source_cwd']}")

    git_info = _source_git_info(
        source_path,
        workspace_root=workspace_root,
        git_runner=git_runner,
    )

    record_path = fields["record_path"]
    existing: dict[str, object] = {}
    if isinstance(record_path, Path) and record_path.exists():
        existing = _read_json(record_path)

    workspace_path = fields["workspace_path"]
    if not isinstance(workspace_path, Path):
        raise ValueError("Invalid task workspace path.")
    if _target_has_unknown_files(workspace_path):
        raise ValueError("task workspace target path is not empty; refusing to overwrite unknown files.")

    branch = str(existing.get("worktree_branch") or f"task/{fields['workspace_key']}")
    now = _now_iso()

    if not _is_git_worktree_path(workspace_path):
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            git_runner(
                [
                    "git",
                    "-C",
                    str(git_info["source_git_root"]),
                    "worktree",
                    "add",
                    "-b",
                    branch,
                    str(workspace_path),
                    str(git_info["base_sha"]),
                ]
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise RuntimeError(f"git worktree add failed: {detail}") from exc

    record = {
        "task_id": fields["task_id"],
        "project_id": fields["project_id"],
        "source_cwd": fields["source_cwd"],
        "source_git_root": git_info["source_git_root"],
        "workspace_mode": TASK_WORKSPACE_MODE,
        "workspace_key": fields["workspace_key"],
        "workspace_path": str(workspace_path),
        "record_path": str(record_path),
        "worktree_branch": branch,
        "worktree_status": "ready",
        "base_ref": str(existing.get("base_ref") or git_info["base_ref"]),
        "base_sha": str(existing.get("base_sha") or git_info["base_sha"]),
        "status": "worktree",
        "exists": True,
        "created_at": str(existing.get("created_at") or now),
        "updated_at": now,
    }
    if not isinstance(record_path, Path):
        raise ValueError("Invalid task workspace record path.")
    _write_json(record_path, record)
    return record


def inspect_task_worktree(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
    git_runner: GitRunner = _run_git,
) -> dict[str, object]:
    fields = _task_workspace_paths(
        task_id,
        cwd=cwd,
        project_id=project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    record_path = fields["record_path"]
    if not isinstance(record_path, Path) or not record_path.exists():
        raise ValueError(_task_workspace_not_ready_message("missing"))

    raw_record = _read_json(record_path)
    record, workspace_path = _validate_task_worktree_record(raw_record, runtime_root=runtime_root)

    git_status_short = _git_inspection_stdout(git_runner, workspace_path, ["status", "--short"])
    base_sha = str(record.get("base_sha") or "").strip()
    diff_ref = base_sha or "HEAD"
    diff_stat = _git_inspection_stdout(git_runner, workspace_path, ["diff", "--stat", diff_ref, "--"])
    diff_name_status = _git_inspection_stdout(git_runner, workspace_path, ["diff", "--name-status", diff_ref, "--"])

    changed_files = _parse_diff_name_status(diff_name_status)
    seen_paths = {item["path"] for item in changed_files}
    changed_files.extend(_parse_status_short_extra_paths(git_status_short, seen_paths))

    return {
        **record,
        "dirty": bool(git_status_short.strip() or diff_name_status.strip()),
        "changed_file_count": len(changed_files),
        "git_status_short": git_status_short,
        "diff_stat": diff_stat,
        "diff_name_status": diff_name_status,
        "changed_files": changed_files,
    }


def merge_preflight_task_worktree(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
    git_runner: GitRunner = _run_git,
) -> dict[str, object]:
    inspection = inspect_task_worktree(
        task_id,
        cwd=cwd,
        project_id=project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
        git_runner=git_runner,
    )

    source_git_root_text = str(inspection.get("source_git_root") or "").strip()
    if not source_git_root_text:
        raise ValueError("task workspace record is missing source_git_root.")
    source_git_root = Path(source_git_root_text).expanduser().resolve(strict=False)
    root = workspace_root.expanduser().resolve(strict=False)
    if source_git_root != root and not source_git_root.is_relative_to(root):
        raise ValueError(f"source_git_root escapes WORKSPACE_ROOT: {source_git_root}")

    base_sha = str(inspection.get("base_sha") or "").strip()
    if not base_sha:
        raise ValueError("task workspace record is missing base_sha.")

    source_head_sha = _git_inspection_stdout(git_runner, source_git_root, ["rev-parse", "HEAD"]).strip()
    source_git_status_short = _git_inspection_stdout(git_runner, source_git_root, ["status", "--short"])
    source_head_changed = source_head_sha != base_sha
    if source_head_changed:
        source_diff_name_status = _git_inspection_stdout(
            git_runner,
            source_git_root,
            ["diff", "--name-status", base_sha, source_head_sha, "--"],
        )
    else:
        source_diff_name_status = ""

    source_changed_files = _parse_diff_name_status(source_diff_name_status)
    source_seen = {item["path"] for item in source_changed_files}
    source_changed_files.extend(_parse_status_short_extra_paths(source_git_status_short, source_seen))

    task_changed_paths = {str(item.get("path") or "") for item in inspection.get("changed_files", []) if item.get("path")}
    source_changed_paths = {str(item.get("path") or "") for item in source_changed_files if item.get("path")}
    overlapping_files = sorted(task_changed_paths.intersection(source_changed_paths))

    task_dirty = bool(inspection.get("dirty"))
    source_dirty = bool(source_git_status_short.strip())
    if not task_dirty:
        conflict_risk = "none"
        ready_to_merge = False
        recommended_action = "no_changes"
    elif source_dirty:
        conflict_risk = "high"
        ready_to_merge = False
        recommended_action = "clean_source_before_merge"
    elif overlapping_files:
        conflict_risk = "high"
        ready_to_merge = False
        recommended_action = "manual_conflict_review"
    elif source_head_changed:
        conflict_risk = "medium"
        ready_to_merge = True
        recommended_action = "merge_queue_with_source_head_check"
    else:
        conflict_risk = "low"
        ready_to_merge = True
        recommended_action = "merge_queue"

    return {
        **inspection,
        "source_head_sha": source_head_sha,
        "source_head_changed": source_head_changed,
        "source_dirty": source_dirty,
        "source_git_status_short": source_git_status_short,
        "source_diff_name_status": source_diff_name_status,
        "source_changed_files": source_changed_files,
        "overlapping_files": overlapping_files,
        "ready_to_merge": ready_to_merge,
        "conflict_risk": conflict_risk,
        "recommended_action": recommended_action,
    }


def read_task_workspace(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, object]:
    fields = _task_workspace_paths(
        task_id,
        cwd=cwd,
        project_id=project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    record_path = fields["record_path"]
    if isinstance(record_path, Path) and record_path.exists():
        return _record_with_current_status(_read_json(record_path))
    return _missing_record(fields)


def list_task_workspaces(
    *,
    project_id: str | None = None,
    runtime_root: Path | None = None,
) -> list[dict[str, object]]:
    root = _task_workspace_root(runtime_root)
    normalized_project_id = project_id.strip() if isinstance(project_id, str) and project_id.strip() else None
    if normalized_project_id is not None:
        _normalize_project_id(normalized_project_id, ".")

    rows: list[dict[str, object]] = []
    if not root.exists():
        return rows

    for path in sorted(root.glob(f"*/{TASK_WORKSPACE_RECORD_NAME}")):
        try:
            record = _record_with_current_status(_read_json(path))
        except Exception:
            continue
        if normalized_project_id is not None and record.get("project_id") != normalized_project_id:
            continue
        rows.append(record)

    rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return rows


def archive_task_workspace(
    task_id: str,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, object]:
    record = read_task_workspace(
        task_id,
        cwd=cwd,
        project_id=project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    if not record.get("created_at"):
        raise FileNotFoundError(f"Task workspace not found: {task_id}")
    record["status"] = "archived"
    record["updated_at"] = _now_iso()
    _write_json(Path(str(record["record_path"])), record)
    return _record_with_current_status(record)


def resolve_task_workspace_for_bundle(
    record: dict[str, object] | None,
    *,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> TaskWorkspaceResolution:
    normalized_record = record if isinstance(record, dict) else {"cwd": "."}
    metadata = _normalize_command_bundle_metadata(normalized_record)
    workspace_mode = str(metadata.get("workspace_mode") or "direct").strip() or "direct"
    if workspace_mode != TASK_WORKSPACE_MODE:
        return TaskWorkspaceResolution(
            workspace_mode=workspace_mode,
            status="skipped",
            reason="direct-mode",
            exists=False,
            task_id=metadata.get("task_id") if isinstance(metadata.get("task_id"), str) else None,
            project_id=metadata.get("project_id") if isinstance(metadata.get("project_id"), str) else None,
            source_cwd=metadata.get("source_cwd") if isinstance(metadata.get("source_cwd"), str) else None,
        )

    task_id = metadata.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("workspace_mode='task-workspace' requires task_id.")

    source_cwd = metadata.get("source_cwd") if isinstance(metadata.get("source_cwd"), str) else normalized_record.get("cwd", ".")
    project_id = metadata.get("project_id") if isinstance(metadata.get("project_id"), str) else None
    workspace_record = read_task_workspace(
        task_id,
        cwd=source_cwd,
        project_id=project_id,
        runtime_root=runtime_root,
        workspace_root=workspace_root,
    )
    status = str(workspace_record.get("status") or "missing")
    exists = bool(workspace_record.get("exists"))
    return TaskWorkspaceResolution(
        workspace_mode=TASK_WORKSPACE_MODE,
        status=status,
        reason="found" if exists else "missing",
        exists=exists,
        task_id=str(workspace_record.get("task_id") or task_id),
        project_id=str(workspace_record.get("project_id") or project_id or ""),
        source_cwd=str(workspace_record.get("source_cwd") or source_cwd or "."),
        workspace_key=str(workspace_record.get("workspace_key") or ""),
        workspace_path=str(workspace_record.get("workspace_path") or ""),
        record_path=str(workspace_record.get("record_path") or ""),
        record=workspace_record if exists else None,
    )
