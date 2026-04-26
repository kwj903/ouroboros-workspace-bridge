from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class WorkspaceInfo(BaseModel):
    root: str
    mode: str
    runtime_root: str
    tools: list[str]


class ListEntry(BaseModel):
    name: str
    path: str
    kind: str
    size_bytes: int | None = None


class ListResult(BaseModel):
    path: str
    entries: list[ListEntry]


class TreeResult(BaseModel):
    path: str
    entries: list[str]
    truncated: bool


class ReadFileResult(BaseModel):
    path: str
    content: str
    truncated: bool
    size_bytes: int
    sha256: str


class WriteFileResult(BaseModel):
    path: str
    action: str
    size_bytes: int
    sha256: str
    backup_id: str | None = None
    operation_id: str | None = None


class ReplaceTextResult(BaseModel):
    path: str
    replacements: int
    size_bytes: int
    sha256: str
    backup_id: str | None = None
    operation_id: str | None = None


class DeleteResult(BaseModel):
    original_path: str
    trash_id: str
    trash_path: str
    restored: bool = False
    operation_id: str | None = None


class RestoreResult(BaseModel):
    restored_path: str
    trash_id: str
    sha256: str | None = None
    operation_id: str | None = None


class CommandResult(BaseModel):
    cwd: str
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool


class WorkspaceExecResult(BaseModel):
    cwd: str
    command: list[str]
    risk: Literal["low", "medium", "high", "blocked"]
    approval_required: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    operation_id: str


class CommandBundleStep(BaseModel):
    name: str
    argv: list[str]
    timeout_seconds: int = 60


class CommandBundleAction(BaseModel):
    name: str
    type: Literal["command", "write_file", "append_file", "replace_text"] = "command"
    argv: list[str] | None = None
    timeout_seconds: int = 60
    path: str | None = None
    content: str | None = None
    content_ref: str | None = None
    old_text: str | None = None
    old_text_ref: str | None = None
    new_text: str | None = None
    new_text_ref: str | None = None
    overwrite: bool = False
    create_parent_dirs: bool = True
    replace_all: bool = False


class CommandBundleStageResult(BaseModel):
    bundle_id: str
    title: str
    cwd: str
    status: str
    risk: Literal["low", "medium", "high", "blocked"]
    approval_required: bool
    path: str
    review_hint: str
    command_count: int


class CommandBundleStatusResult(BaseModel):
    bundle_id: str
    title: str
    cwd: str
    status: str
    risk: str
    approval_required: bool
    command_count: int
    created_at: str
    updated_at: str
    result: dict[str, object] | None = None
    error: str | None = None


class CommandBundleListEntry(BaseModel):
    bundle_id: str
    title: str
    cwd: str
    status: str
    risk: str
    command_count: int
    updated_at: str


class CommandBundleListResult(BaseModel):
    entries: list[CommandBundleListEntry]
    count: int


class TextPayloadStageResult(BaseModel):
    payload_id: str
    chunk_index: int
    total_chunks: int
    chunk_chars: int
    total_chars: int
    complete: bool
    path: str


class GitCommitResult(BaseModel):
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool


class AuditLogResult(BaseModel):
    entries: list[dict[str, object]]
    count: int
    truncated: bool


class OperationStatusResult(BaseModel):
    operation_id: str
    status: str
    tool: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    failed_at: str | None = None
    args: dict[str, object] | None = None
    result: dict[str, object] | None = None
    error: str | None = None


class BackupEntry(BaseModel):
    backup_id: str
    original_path: str
    backup_path: str
    sha256: str | None = None
    created_at: str | None = None


class BackupListResult(BaseModel):
    entries: list[BackupEntry]
    count: int


class BackupRestoreResult(BaseModel):
    backup_id: str
    restored_path: str
    sha256: str
    backup_id_before_overwrite: str | None = None


class TrashEntry(BaseModel):
    trash_id: str
    original_path: str
    trash_path: str
    created_at: str | None = None
    exists: bool


class TrashListResult(BaseModel):
    entries: list[TrashEntry]
    count: int


class OperationListResult(BaseModel):
    entries: list[OperationStatusResult]
    count: int


class FileMatchEntry(BaseModel):
    path: str
    kind: str
    size_bytes: int | None = None


class FindFilesResult(BaseModel):
    path: str
    pattern: str
    entries: list[FileMatchEntry]
    count: int
    truncated: bool


class SearchTextMatch(BaseModel):
    path: str
    line_number: int
    line: str


class SearchTextResult(BaseModel):
    query: str
    path: str
    matches: list[SearchTextMatch]
    count: int
    truncated: bool


class ReadManyFileEntry(BaseModel):
    path: str
    content: str | None = None
    truncated: bool = False
    size_bytes: int | None = None
    sha256: str | None = None
    error: str | None = None


class ReadManyFilesResult(BaseModel):
    entries: list[ReadManyFileEntry]
    count: int
    truncated: bool


class ProjectSnapshotResult(BaseModel):
    path: str
    tree: list[str]
    key_files: list[str]
    git_status: str
    truncated: bool


class PatchFileEntry(BaseModel):
    path: str


class PatchPreviewResult(BaseModel):
    cwd: str
    files: list[PatchFileEntry]
    can_apply: bool
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool


class PatchApplyResult(BaseModel):
    cwd: str
    files: list[PatchFileEntry]
    exit_code: int
    stdout: str
    stderr: str
    backup_ids: dict[str, str | None]
    git_diff: str
    operation_id: str
    truncated: bool


class TaskStepEntry(BaseModel):
    ts: str
    kind: str
    message: str
    data: dict[str, object] | None = None


class TaskStatusResult(BaseModel):
    task_id: str
    title: str
    goal: str
    status: str
    created_at: str
    updated_at: str
    finished_at: str | None = None
    plan: list[str]
    steps: list[TaskStepEntry]
    metadata: dict[str, object]
    summary: str | None = None
    next_steps: list[str]


class TaskListEntry(BaseModel):
    task_id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    finished_at: str | None = None
    summary: str | None = None


class TaskListResult(BaseModel):
    entries: list[TaskListEntry]
    count: int
