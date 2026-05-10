from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from terminal_bridge.commands import _safe_env
from terminal_bridge.models import (
    AuditLogResult,
    BackupListResult,
    CommandResult,
    HandoffEntry,
    HandoffListResult,
    OperationListResult,
    OperationStatusResult,
    TaskListEntry,
    TaskListResult,
    TaskStatusResult,
    TaskStepEntry,
    ToolCallListResult,
    ToolCallStatusResult,
    TrashListResult,
)
from terminal_bridge.safety import _relative, _resolve_workspace_path
from terminal_bridge.storage import _now_iso


EnsureRuntimeDirs = Callable[[], None]
RunCommand = Callable[..., CommandResult]
CommandBundleDirs = Callable[[], list[Path]]
ReadJson = Callable[[Path], dict[str, object]]
ReadAuditLog = Callable[[int], AuditLogResult]
ListRecords = Callable[[int], list[dict[str, object]]]
NextRecord = Callable[[], dict[str, object] | None]
ReadRecord = Callable[[str], dict[str, object]]
StatusResult = Callable[[dict[str, object]], ToolCallStatusResult]
NormalizeId = Callable[[str], str]
ReadOptionalRecord = Callable[[str], dict[str, object] | None]
ListPaths = Callable[[], list[Path]]
ListEntries = Callable[[int], list[object]]


def read_audit_log(
    ensure_runtime_dirs: EnsureRuntimeDirs,
    audit_log: Path,
    limit: int = 50,
    event: str | None = None,
) -> AuditLogResult:
    ensure_runtime_dirs()

    if not audit_log.exists():
        return AuditLogResult(entries=[], count=0, truncated=False)

    lines = audit_log.read_text(encoding="utf-8").splitlines()
    entries: list[dict[str, object]] = []

    for line in reversed(lines):
        if not line.strip():
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event is not None and item.get("event") != event:
            continue

        entries.append(item)

        if len(entries) >= limit:
            break

    return AuditLogResult(
        entries=entries,
        count=len(entries),
        truncated=len(entries) >= limit,
    )


def transport_git_status_summary(cwd: str) -> dict[str, object]:
    try:
        target = _resolve_workspace_path(cwd)
        if not target.exists():
            raise FileNotFoundError(f"Directory does not exist: {_relative(target)}")
        if not target.is_dir():
            raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

        completed = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=str(target),
            env=_safe_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            shell=False,
            check=False,
        )
        stdout_lines = completed.stdout.splitlines()
        stderr = completed.stderr.strip()
        return {
            "cwd": _relative(target),
            "exit_code": completed.returncode,
            "branch": stdout_lines[0] if stdout_lines else "",
            "changed_line_count": max(0, len(stdout_lines) - 1),
            "stderr": stderr[:300],
            "truncated": len(stderr) > 300,
        }
    except Exception as exc:
        return {
            "cwd": cwd,
            "exit_code": None,
            "branch": "",
            "changed_line_count": None,
            "stderr": f"{type(exc).__name__}: {exc}"[:300],
            "truncated": False,
        }


def transport_probe(
    ensure_runtime_dirs: EnsureRuntimeDirs,
    list_tool_call_records: ListRecords,
    command_bundle_dirs: CommandBundleDirs,
    workspace_root: Path,
    runtime_root: Path,
    cwd: str,
    include_git_status: bool,
) -> dict[str, object]:
    ensure_runtime_dirs()
    latest_tool_call_count = len(list_tool_call_records(20))
    latest_bundle_count = sum(
        1
        for directory in command_bundle_dirs()
        if directory.exists()
        for _ in directory.glob("cmd-*.json")
    )
    git_status = transport_git_status_summary(cwd) if include_git_status else None

    return {
        "ok": True,
        "server_time": _now_iso(),
        "pid": os.getpid(),
        "workspace_root": str(workspace_root),
        "runtime_root": str(runtime_root),
        "latest_tool_call_count": latest_tool_call_count,
        "latest_bundle_count": latest_bundle_count,
        "git_status": git_status,
        "git_status_summary": git_status,
        "diagnosis": "Transport probe reached the MCP server.",
    }


def recover_last_activity(
    ensure_runtime_dirs: EnsureRuntimeDirs,
    run_command: RunCommand,
    command_bundle_dirs: CommandBundleDirs,
    read_json: ReadJson,
    read_audit_log: ReadAuditLog,
    cwd: str,
    bundle_limit: int,
    audit_limit: int,
) -> dict[str, object]:
    ensure_runtime_dirs()

    try:
        git_status = run_command(cwd, ["git", "status", "--short", "--branch"], timeout_seconds=30).model_dump()
    except Exception as exc:
        git_status = {
            "cwd": cwd,
            "command": ["git", "status", "--short", "--branch"],
            "exit_code": None,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
            "truncated": False,
        }

    bundle_entries: list[dict[str, object]] = []
    for directory in command_bundle_dirs():
        if not directory.exists():
            continue
        for bundle_path in directory.glob("cmd-*.json"):
            try:
                record = read_json(bundle_path)
            except Exception:
                continue
            steps = record.get("steps") if isinstance(record.get("steps"), list) else []
            bundle_entries.append(
                {
                    "bundle_id": str(record.get("bundle_id", bundle_path.stem)),
                    "title": str(record.get("title", "")),
                    "cwd": str(record.get("cwd", "")),
                    "status": str(record.get("status", directory.name)),
                    "risk": str(record.get("risk", "unknown")),
                    "command_count": len(steps),
                    "updated_at": str(record.get("updated_at", "")),
                    "error": record.get("error") if isinstance(record.get("error"), str) else None,
                }
            )

    bundle_entries.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    latest_bundles = bundle_entries[:bundle_limit]

    audit_entries: list[dict[str, object]] = []
    for item in read_audit_log(audit_limit).entries:
        safe_item: dict[str, object] = {}
        for key in (
            "ts",
            "event",
            "bundle_id",
            "operation_id",
            "cwd",
            "title",
            "risk",
            "intent_type",
            "nonce",
            "command_count",
            "path_count",
            "exit_code",
            "truncated",
        ):
            if key in item:
                safe_item[key] = item[key]
        audit_entries.append(safe_item)

    git_stdout = str(git_status.get("stdout", "")).strip()
    if not latest_bundles:
        diagnosis = "No command bundle records were found. If a mutation tool call appeared to hang, it may not have reached the MCP server."
    elif git_stdout and git_stdout != "## main...origin/main":
        diagnosis = "The worktree is not clean or the branch is ahead/behind. Inspect git_status and latest_bundles before retrying mutation tools."
    else:
        diagnosis = "Recent command bundle records and git status are available. Use latest_bundles to decide whether to retry, inspect status, or continue."

    return {
        "git_status": git_status,
        "latest_bundles": latest_bundles,
        "latest_audit_events": audit_entries,
        "diagnosis": diagnosis,
    }


def handoff_entry(record: dict[str, object]) -> HandoffEntry:
    return HandoffEntry(
        handoff_id=str(record.get("handoff_id", "")),
        bundle_id=str(record.get("bundle_id", "")),
        status=str(record.get("status", "unknown")),
        ok=record.get("ok") if isinstance(record.get("ok"), bool) else None,
        risk=str(record.get("risk", "unknown")),
        title=str(record.get("title", "")),
        cwd=str(record.get("cwd", "")),
        next=str(record.get("next", "inspect_logs")),
        stdout_tail=str(record.get("stdout_tail", "")),
        stderr_tail=str(record.get("stderr_tail", "")),
        created_at=str(record.get("created_at", "")),
        updated_at=str(record.get("updated_at", "")),
    )


def next_handoff(next_handoff_record: NextRecord) -> HandoffEntry | None:
    record = next_handoff_record()
    return handoff_entry(record) if record is not None else None


def list_handoffs(list_handoff_records: ListRecords, limit: int) -> HandoffListResult:
    entries = [handoff_entry(record) for record in list_handoff_records(limit)]
    return HandoffListResult(entries=entries, count=len(entries))


def list_tool_calls(
    list_tool_call_records: ListRecords,
    tool_call_status_result: StatusResult,
    limit: int,
) -> ToolCallListResult:
    records = list_tool_call_records(limit)
    entries = [tool_call_status_result(record) for record in records]
    return ToolCallListResult(entries=entries, count=len(entries))


def tool_call_status(
    read_tool_call_record: ReadRecord,
    tool_call_status_result: StatusResult,
    call_id: str,
) -> ToolCallStatusResult:
    return tool_call_status_result(read_tool_call_record(call_id))


def operation_status_from_record(
    operation_id: str,
    record: dict[str, object],
) -> OperationStatusResult:
    return OperationStatusResult(
        operation_id=operation_id,
        status=str(record.get("status", "unknown")),
        tool=record.get("tool") if isinstance(record.get("tool"), str) else None,
        started_at=record.get("started_at") if isinstance(record.get("started_at"), str) else None,
        completed_at=record.get("completed_at") if isinstance(record.get("completed_at"), str) else None,
        failed_at=record.get("failed_at") if isinstance(record.get("failed_at"), str) else None,
        args=record.get("args") if isinstance(record.get("args"), dict) else None,
        result=record.get("result") if isinstance(record.get("result"), dict) else None,
        error=record.get("error") if isinstance(record.get("error"), str) else None,
    )


def get_operation(
    normalize_operation_id: NormalizeId,
    read_operation_record: ReadOptionalRecord,
    operation_id: str,
) -> OperationStatusResult:
    op_id = normalize_operation_id(operation_id)
    record = read_operation_record(op_id)

    if record is None:
        raise FileNotFoundError(f"Operation not found: {op_id}")

    return operation_status_from_record(op_id, record)


def list_operations(
    ensure_runtime_dirs: EnsureRuntimeDirs,
    operation_dir: Path,
    limit: int,
) -> OperationListResult:
    ensure_runtime_dirs()

    entries: list[OperationStatusResult] = []

    for operation_path in sorted(operation_dir.glob("*.json"), reverse=True):
        try:
            record = json.loads(operation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        op_id = str(record.get("operation_id", operation_path.stem))
        entries.append(operation_status_from_record(op_id, record))

        if len(entries) >= limit:
            break

    return OperationListResult(entries=entries, count=len(entries))


def list_backups(
    ensure_runtime_dirs: EnsureRuntimeDirs,
    list_backup_entries: ListEntries,
    limit: int,
) -> BackupListResult:
    ensure_runtime_dirs()

    entries = list_backup_entries(limit)
    return BackupListResult(entries=entries, count=len(entries))


def list_trash(
    ensure_runtime_dirs: EnsureRuntimeDirs,
    list_trash_entries: ListEntries,
    limit: int,
) -> TrashListResult:
    ensure_runtime_dirs()

    entries = list_trash_entries(limit)
    return TrashListResult(entries=entries, count=len(entries))


def task_result(record: dict[str, object]) -> TaskStatusResult:
    raw_steps = record.get("steps")
    steps: list[TaskStepEntry] = []

    if isinstance(raw_steps, list):
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                continue

            steps.append(
                TaskStepEntry(
                    ts=str(raw_step.get("ts", "")),
                    kind=str(raw_step.get("kind", "note")),
                    message=str(raw_step.get("message", "")),
                    data=raw_step.get("data") if isinstance(raw_step.get("data"), dict) else None,
                )
            )

    raw_plan = record.get("plan")
    plan = [str(item) for item in raw_plan] if isinstance(raw_plan, list) else []

    raw_next_steps = record.get("next_steps")
    next_steps = [str(item) for item in raw_next_steps] if isinstance(raw_next_steps, list) else []

    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}

    return TaskStatusResult(
        task_id=str(record.get("task_id", "")),
        title=str(record.get("title", "")),
        goal=str(record.get("goal", "")),
        status=str(record.get("status", "unknown")),
        created_at=str(record.get("created_at", "")),
        updated_at=str(record.get("updated_at", "")),
        finished_at=record.get("finished_at") if isinstance(record.get("finished_at"), str) else None,
        plan=plan,
        steps=steps,
        metadata=metadata,
        summary=record.get("summary") if isinstance(record.get("summary"), str) else None,
        next_steps=next_steps,
    )


def task_status(
    normalize_task_id: NormalizeId,
    read_task: ReadRecord,
    task_id: str,
) -> TaskStatusResult:
    normalized = normalize_task_id(task_id)
    record = read_task(normalized)

    return task_result(record)


def list_tasks(
    ensure_runtime_dirs: EnsureRuntimeDirs,
    list_task_paths: ListPaths,
    limit: int,
) -> TaskListResult:
    ensure_runtime_dirs()

    entries: list[TaskListEntry] = []

    for task_path in list_task_paths():
        try:
            record = json.loads(task_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        entries.append(
            TaskListEntry(
                task_id=str(record.get("task_id", task_path.stem)),
                title=str(record.get("title", "")),
                status=str(record.get("status", "unknown")),
                created_at=str(record.get("created_at", "")),
                updated_at=str(record.get("updated_at", "")),
                finished_at=record.get("finished_at") if isinstance(record.get("finished_at"), str) else None,
                summary=record.get("summary") if isinstance(record.get("summary"), str) else None,
            )
        )

        if len(entries) >= limit:
            break

    return TaskListResult(entries=entries, count=len(entries))


def git_status(run_command: RunCommand, cwd: str) -> CommandResult:
    return run_command(cwd=cwd, command=["git", "status", "--short", "--branch"], timeout_seconds=15)


def git_diff(run_command: RunCommand, cwd: str) -> CommandResult:
    return run_command(cwd=cwd, command=["git", "diff", "--no-ext-diff"], timeout_seconds=15)
