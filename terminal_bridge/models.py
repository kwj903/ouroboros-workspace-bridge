from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "blocked"]
ValidationStatus = Literal["unknown", "pending", "passed", "failed"]
WorkspaceMode = Literal["direct", "task-workspace"]


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
    risk: RiskLevel
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
    bundle_id: str = Field(description="Identifier used to check or wait for this bundle.")
    title: str = Field(description="Human-readable purpose of the staged bundle.")
    cwd: str = Field(description="Workspace-relative directory where the bundle will run.")
    status: str = Field(description="Current bundle state after staging.")
    risk: RiskLevel = Field(description="Highest risk level assigned to the bundle.")
    approval_required: bool = Field(description="Whether local review approval is required before execution.")
    path: str = Field(description="Runtime record path for the staged bundle.")
    review_hint: str = Field(description="Short instruction for reviewing or following up on the bundle.")
    command_count: int = Field(description="Number of command or action steps in the bundle.")


class CommandBundleStatusResult(BaseModel):
    bundle_id: str = Field(description="Identifier of the bundle being reported.")
    title: str = Field(description="Human-readable purpose of the bundle.")
    cwd: str = Field(description="Workspace-relative directory where the bundle runs.")
    status: str = Field(description="Current bundle state; use it to decide whether to wait, review, or inspect failure.")
    risk: str = Field(description="Recorded bundle risk level; legacy records may contain broader values.")
    approval_required: bool = Field(description="Whether execution still depends on local review approval.")
    command_count: int = Field(description="Number of command or action steps in the bundle.")
    created_at: str = Field(description="Timestamp when the bundle was staged.")
    updated_at: str = Field(description="Timestamp of the latest bundle state change.")
    result: dict[str, object] | None = Field(default=None, description="Execution result when the bundle has completed.")
    error: str | None = Field(default=None, description="Failure message when the bundle did not complete successfully.")
    metadata: dict[str, object] = Field(
        default_factory=dict,
        description="Routing and workflow context attached to the bundle.",
    )


class CommandBundleListEntry(BaseModel):
    bundle_id: str = Field(description="Identifier used to inspect this bundle.")
    title: str = Field(description="Human-readable purpose of the bundle.")
    cwd: str = Field(description="Workspace-relative directory associated with the bundle.")
    status: str = Field(description="Current bundle state.")
    risk: str = Field(description="Recorded bundle risk level; legacy records may contain broader values.")
    command_count: int = Field(description="Number of command or action steps in the bundle.")
    updated_at: str = Field(description="Timestamp of the latest bundle state change.")
    metadata: dict[str, object] = Field(
        default_factory=dict,
        description="Routing and workflow context attached to the bundle.",
    )


class CommandBundleListResult(BaseModel):
    entries: list[CommandBundleListEntry] = Field(description="Bundles matching the requested filters.")
    count: int = Field(description="Number of returned bundle entries.")


class SafeTaskMergePreparationResult(BaseModel):
    task_id: str = Field(description="Task whose worktree was prepared for merge.")
    project_id: str = Field(description="Project that owns the task workspace.")
    source_cwd: str = Field(description="Source workspace directory that would receive the merge.")
    inspect_summary: dict[str, object] = Field(
        default_factory=dict,
        description="Summary of the task worktree inspection.",
    )
    preflight_result: dict[str, object] = Field(
        default_factory=dict,
        description="Merge preflight evidence used for the readiness decision.",
    )
    ready_to_merge: bool = Field(description="Whether preflight found the task safe to propose for merge.")
    conflict_risk: str = Field(description="Estimated merge conflict risk.")
    recommended_action: str = Field(description="Recommended next workflow action.")
    blockers: list[str] = Field(default_factory=list, description="Reasons the merge should not proceed yet.")
    merge_queue_status: str | None = Field(default=None, description="Current merge queue state, when available.")
    merge_queue_record: dict[str, object] | None = Field(
        default=None,
        description="Merge queue record created or inspected by this preparation.",
    )
    proposal_bundle_id: str | None = Field(default=None, description="Identifier of the staged merge proposal, if any.")
    proposal_status: str | None = Field(default=None, description="Current state of the staged merge proposal, if any.")
    proposal: dict[str, object] | None = Field(default=None, description="Staged merge proposal details, if any.")


class TaskValidationRecordSuggestion(BaseModel):
    task_id: str
    cwd: str
    project_id: str | None = None
    validation_status: ValidationStatus = Field(description="Validation state inferred from the command result.")
    validation_commands: list[str] = Field(default_factory=list)
    validation_summary: str | None = None
    validated_by: str | None = None
    client_id: str | None = None
    session_id: str | None = None


class TaskValidationResultHintResult(BaseModel):
    task_id: str | None = Field(default=None, description="Task associated with the validation bundle, when known.")
    project_id: str | None = Field(default=None, description="Project associated with the validation bundle, when known.")
    source_cwd: str | None = Field(default=None, description="Source workspace directory associated with the task.")
    bundle_id: str | None = Field(default=None, description="Validation command bundle identifier.")
    bundle_status: str = Field(description="Current validation bundle state.")
    command_argv: list[str] = Field(default_factory=list, description="Validation command arguments that were executed.")
    command_summary: str | None = Field(default=None, description="Short summary of the validation command.")
    exit_code: int | None = Field(default=None, description="Validation command exit code, when available.")
    stdout_preview: str = Field(default="", description="Truncated preview of validation stdout.")
    stderr_preview: str = Field(default="", description="Truncated preview of validation stderr.")
    stdout_truncated: bool = Field(default=False, description="Whether the stdout preview omits content.")
    stderr_truncated: bool = Field(default=False, description="Whether the stderr preview omits content.")
    result_available: bool = Field(default=False, description="Whether a completed command result was available for inference.")
    inferred_status: Literal["passed", "failed", "unknown"] = Field(
        description="Validation status inferred from the available result.",
    )
    recommended_next_action: str = Field(description="Recommended next step for recording or rerunning validation.")
    suggested_record_input: TaskValidationRecordSuggestion = Field(
        description="Suggested input for recording the inferred validation result.",
    )


class TextPayloadStageResult(BaseModel):
    payload_id: str = Field(description="Identifier used to reference the staged text payload.")
    chunk_index: int = Field(description="Zero-based index of the chunk accepted by this call.")
    total_chunks: int = Field(description="Expected number of chunks in the complete payload.")
    chunk_chars: int = Field(description="Character count of the accepted chunk.")
    total_chars: int = Field(description="Character count currently stored for the payload.")
    complete: bool = Field(description="Whether all expected chunks are now staged.")
    path: str = Field(description="Runtime record path for the staged payload.")


class GitCommitResult(BaseModel):
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool


class TransportGitStatusSummary(BaseModel):
    cwd: str = Field(description="Workspace-relative git directory checked by the probe.")
    exit_code: int | None = Field(description="Git status exit code, or null when the check could not run.")
    branch: str = Field(description="Branch summary line returned by git status.")
    changed_line_count: int | None = Field(description="Number of changed-file lines, or null when unavailable.")
    stderr: str = Field(description="Compact git status error output, if any.")
    truncated: bool = Field(description="Whether git status error output was truncated.")


class TransportProbeResult(BaseModel):
    ok: bool = Field(description="Whether the request reached the MCP server.")
    server_time: str = Field(description="Server timestamp recorded for the probe.")
    pid: int = Field(description="Process identifier of the MCP server.")
    workspace_root: str = Field(description="Configured workspace root served by this MCP server.")
    runtime_root: str = Field(description="Runtime storage root used by this MCP server.")
    latest_tool_call_count: int = Field(description="Number of recent tool call records observed.")
    latest_bundle_count: int = Field(description="Number of command bundle records observed.")
    git_status: TransportGitStatusSummary | None = Field(
        description="Compact git status summary when requested.",
    )
    git_status_summary: TransportGitStatusSummary | None = Field(
        description="Compatibility alias containing the same compact git status summary.",
    )
    diagnosis: str = Field(description="Operational interpretation of the probe result.")


class RecoveryGitStatusResult(BaseModel):
    cwd: str = Field(description="Workspace-relative git directory checked during recovery.")
    command: list[str] = Field(description="Git status command used for recovery.")
    exit_code: int | None = Field(description="Git status exit code, or null when the check could not run.")
    stdout: str = Field(description="Git status output used to assess workspace state.")
    stderr: str = Field(description="Git status error output, if any.")
    truncated: bool = Field(description="Whether git status output was truncated.")


class RecoveryCommandBundleEntry(BaseModel):
    bundle_id: str = Field(description="Identifier used to inspect the recovered command bundle.")
    title: str = Field(description="Human-readable purpose of the command bundle.")
    cwd: str = Field(description="Workspace-relative directory associated with the command bundle.")
    status: str = Field(description="Current or final command bundle state.")
    risk: str = Field(description="Recorded command bundle risk level.")
    command_count: int = Field(description="Number of command or action steps in the bundle.")
    updated_at: str = Field(description="Timestamp of the latest command bundle update.")
    error: str | None = Field(description="Command bundle failure message, if any.")


class RecoverySnapshotResult(BaseModel):
    git_status: RecoveryGitStatusResult = Field(description="Current git status used to assess recovery state.")
    latest_bundles: list[RecoveryCommandBundleEntry] = Field(
        description="Recent command bundle entries to inspect before retrying work.",
    )
    latest_audit_events: list[dict[str, object]] = Field(
        description="Recent safe audit event summaries; fields vary across legacy records.",
    )
    diagnosis: str = Field(description="Recommended interpretation and next recovery action.")


class IntentPreparationResult(BaseModel):
    ok: bool = Field(description="Whether the signed intent was prepared successfully.")
    intent_type: str = Field(description="Type of local review intent that was prepared.")
    risk: str = Field(description="Risk level assigned to the action that the intent can import.")
    summary: str = Field(description="Short description of the action awaiting local review.")
    local_review_url: str = Field(
        description="Signed local review URL containing a sensitive short-lived intent token; do not log or share it.",
        repr=False,
    )
    local_pending_url: str = Field(description="Local pending bundle UI URL for reviewing imported intents.")
    expires_at: str = Field(description="Timestamp after which the signed intent token is rejected.")
    diagnosis: str = Field(description="Recommended next action for importing and reviewing the intent.")


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


class ToolCallStatusResult(BaseModel):
    call_id: str = Field(description="Identifier of the recorded tool call.")
    tool_name: str = Field(description="Name of the tool that was called.")
    status: str = Field(description="Current or final tool call state.")
    started_at: str | None = Field(default=None, description="Timestamp when the tool call started.")
    completed_at: str | None = Field(default=None, description="Timestamp when the tool call completed successfully.")
    failed_at: str | None = Field(default=None, description="Timestamp when the tool call failed.")
    duration_ms: int | None = Field(default=None, description="Recorded tool call duration in milliseconds.")
    args_hash: str | None = Field(default=None, description="Hash used to identify the recorded arguments.")
    args_summary: dict[str, object] | None = Field(default=None, description="Redacted summary of the tool arguments.")
    result_summary: dict[str, object] | None = Field(default=None, description="Redacted summary of the tool result.")
    error: str | None = Field(default=None, description="Failure message when the tool call did not complete.")


class ToolCallListResult(BaseModel):
    entries: list[ToolCallStatusResult]
    count: int


class HandoffEntry(BaseModel):
    handoff_id: str = Field(description="Identifier of the handoff record.")
    bundle_id: str = Field(description="Command bundle associated with the handoff.")
    status: str = Field(description="Current or final bundle state recorded by the handoff.")
    ok: bool | None = Field(description="Whether the completed handoff succeeded, or null while unresolved.")
    risk: str = Field(description="Recorded risk level for the handoff.")
    title: str = Field(description="Human-readable purpose of the handoff.")
    cwd: str = Field(description="Workspace-relative directory associated with the handoff.")
    next: str = Field(description="Recommended next action for the receiving agent.")
    stdout_tail: str = Field(description="Tail of captured stdout for quick inspection.")
    stderr_tail: str = Field(description="Tail of captured stderr for quick inspection.")
    created_at: str = Field(description="Timestamp when the handoff was created.")
    updated_at: str = Field(description="Timestamp of the latest handoff update.")
    metadata: dict[str, object] = Field(
        default_factory=dict,
        description="Routing and workflow context attached to the handoff.",
    )


class HandoffListResult(BaseModel):
    entries: list[HandoffEntry]
    count: int


class FileMatchEntry(BaseModel):
    path: str
    kind: str
    size_bytes: int | None = None


class FindFilesResult(BaseModel):
    path: str = Field(description="Workspace-relative directory that was searched.")
    pattern: str = Field(description="File name pattern used for the search.")
    entries: list[FileMatchEntry] = Field(description="Files matching the requested pattern.")
    count: int = Field(description="Number of returned file matches.")
    truncated: bool = Field(description="Whether additional file matches were omitted.")


class SearchTextMatch(BaseModel):
    path: str
    line_number: int
    line: str


class SearchTextResult(BaseModel):
    query: str = Field(description="Text query used for the search.")
    path: str = Field(description="Workspace-relative path that was searched.")
    matches: list[SearchTextMatch] = Field(description="Matching lines returned by the search.")
    count: int = Field(description="Number of returned text matches.")
    truncated: bool = Field(description="Whether additional text matches were omitted.")


class ReadManyFileEntry(BaseModel):
    path: str = Field(description="Workspace-relative path requested for reading.")
    content: str | None = Field(default=None, description="File content when the read succeeded.")
    truncated: bool = Field(default=False, description="Whether returned content omits part of the file.")
    size_bytes: int | None = Field(default=None, description="Full file size in bytes, when available.")
    sha256: str | None = Field(default=None, description="SHA-256 digest of the full file, when available.")
    error: str | None = Field(default=None, description="Read failure message for this file, if any.")


class ReadManyFilesResult(BaseModel):
    entries: list[ReadManyFileEntry] = Field(description="Per-file read results in request order.")
    count: int = Field(description="Number of returned file read entries.")
    truncated: bool = Field(description="Whether any returned file content or the overall response was truncated.")


class ProjectSnapshotResult(BaseModel):
    path: str = Field(description="Workspace-relative project path summarized by the snapshot.")
    tree: list[str] = Field(description="Compact project tree entries.")
    key_files: list[str] = Field(description="Detected files that are useful for understanding the project.")
    git_status: str = Field(description="Current short git status for the project.")
    truncated: bool = Field(description="Whether the project tree omits additional entries.")


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
    task_id: str = Field(description="Identifier of the tracked task.")
    title: str = Field(description="Short task title.")
    goal: str = Field(description="Outcome the tracked task is intended to achieve.")
    status: str = Field(description="Current task lifecycle state.")
    created_at: str = Field(description="Timestamp when the task record was created.")
    updated_at: str = Field(description="Timestamp of the latest task update.")
    finished_at: str | None = Field(default=None, description="Timestamp when the task finished, if applicable.")
    plan: list[str] = Field(description="Current ordered task plan.")
    steps: list[TaskStepEntry] = Field(description="Recorded task progress events.")
    metadata: dict[str, object] = Field(description="Additional routing and workflow context for the task.")
    summary: str | None = Field(default=None, description="Completion or progress summary, when available.")
    next_steps: list[str] = Field(description="Recommended next actions for continuing the task.")


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


class TaskWorkspaceStatusResult(BaseModel):
    task_id: str = Field(description="Task associated with this workspace record.")
    project_id: str = Field(description="Project that owns the task workspace.")
    source_cwd: str = Field(description="Source workspace directory for the task.")
    source_git_root: str | None = Field(default=None, description="Source git root, when detected.")
    workspace_mode: str = Field(description="Workspace routing mode; legacy records may contain broader values.")
    workspace_key: str = Field(description="Stable key used to identify the task workspace.")
    workspace_path: str = Field(description="Filesystem path of the task workspace.")
    record_path: str = Field(description="Runtime record path for the task workspace.")
    worktree_branch: str | None = Field(default=None, description="Git branch used by the task worktree, if any.")
    worktree_status: str | None = Field(default=None, description="Current git worktree state, when available.")
    base_ref: str | None = Field(default=None, description="Git reference used as the task workspace base.")
    base_sha: str | None = Field(default=None, description="Commit SHA recorded as the task workspace base.")
    status: str = Field(description="Current task workspace lifecycle state.")
    exists: bool = Field(description="Whether the task workspace currently exists on disk.")
    created_at: str = Field(description="Timestamp when the task workspace record was created.")
    updated_at: str = Field(description="Timestamp of the latest task workspace update.")
    archived_at: str | None = Field(default=None, description="Timestamp when the task workspace was archived.")
    archive_reason: str | None = Field(default=None, description="Reason the task workspace was archived.")


class TaskWorkspaceListResult(BaseModel):
    entries: list[TaskWorkspaceStatusResult]
    count: int


class TaskWorktreeChangedFile(BaseModel):
    status: str
    path: str
    old_path: str | None = None


class TaskWorktreeInspectionResult(TaskWorkspaceStatusResult):
    dirty: bool = Field(description="Whether the task worktree has uncommitted changes.")
    changed_file_count: int = Field(description="Number of changed files detected in the task worktree.")
    git_status_short: str = Field(description="Short git status for the task worktree.")
    diff_stat: str = Field(description="Git diff statistics for the task worktree.")
    diff_name_status: str = Field(description="Git diff name-status output for the task worktree.")
    changed_files: list[TaskWorktreeChangedFile] = Field(description="Changed files detected in the task worktree.")


class TaskWorktreeMergePreflightResult(TaskWorktreeInspectionResult):
    source_head_sha: str = Field(description="Current source workspace HEAD commit SHA.")
    source_head_changed: bool = Field(description="Whether source HEAD moved since the task workspace was created.")
    source_dirty: bool = Field(description="Whether the source workspace has uncommitted changes.")
    source_git_status_short: str = Field(description="Short git status for the source workspace.")
    source_diff_name_status: str = Field(description="Git diff name-status output for the source workspace.")
    source_changed_files: list[TaskWorktreeChangedFile] = Field(description="Changed files detected in the source workspace.")
    overlapping_files: list[str] = Field(description="Files changed in both source and task workspaces.")
    ready_to_merge: bool = Field(description="Whether current preflight evidence permits a merge proposal.")
    conflict_risk: str = Field(description="Estimated conflict risk for merging the task worktree.")
    recommended_action: str = Field(description="Recommended next merge workflow action.")


class MergeQueueEntryResult(BaseModel):
    queue_key: str = Field(description="Stable key identifying this merge queue entry.")
    task_id: str = Field(description="Task waiting in the merge queue.")
    project_id: str = Field(description="Project that owns the queued task.")
    source_cwd: str = Field(description="Source workspace directory that would receive the merge.")
    workspace_path: str | None = Field(default=None, description="Task workspace path, when available.")
    source_git_root: str | None = Field(default=None, description="Source git root, when detected.")
    worktree_branch: str | None = Field(default=None, description="Git branch used by the task worktree.")
    base_ref: str | None = Field(default=None, description="Git reference used as the task worktree base.")
    base_sha: str | None = Field(default=None, description="Commit SHA recorded as the task worktree base.")
    source_head_sha: str | None = Field(default=None, description="Source HEAD commit observed during preflight.")
    source_head_changed: bool | None = Field(default=None, description="Whether source HEAD moved since task creation.")
    source_dirty: bool | None = Field(default=None, description="Whether the source workspace has uncommitted changes.")
    changed_file_count: int | None = Field(default=None, description="Number of changed files in the task worktree.")
    changed_files: list[TaskWorktreeChangedFile] = Field(
        default_factory=list,
        description="Changed files recorded for the task worktree.",
    )
    overlapping_files: list[str] = Field(
        default_factory=list,
        description="Files changed in both source and task workspaces.",
    )
    conflict_risk: str | None = Field(default=None, description="Estimated merge conflict risk.")
    recommended_action: str | None = Field(default=None, description="Recommended next merge workflow action.")
    validation_status: str = Field(
        default="unknown",
        description="Recorded task validation state; legacy records may contain broader values.",
    )
    validation_commands: list[str] = Field(
        default_factory=list,
        description="Commands recorded as validation evidence.",
    )
    validation_summary: str | None = Field(default=None, description="Summary of the recorded validation result.")
    validated_at: str | None = Field(default=None, description="Timestamp when validation was recorded.")
    validated_by: str | None = Field(default=None, description="Actor that recorded validation.")
    validation_client_id: str | None = Field(default=None, description="Client identifier associated with validation.")
    validation_session_id: str | None = Field(default=None, description="Session identifier associated with validation.")
    status: str = Field(description="Current merge queue lifecycle state.")
    exists: bool = Field(description="Whether the merge queue record currently exists.")
    record_path: str = Field(description="Runtime record path for the merge queue entry.")
    created_at: str = Field(description="Timestamp when the merge queue entry was created.")
    updated_at: str = Field(description="Timestamp of the latest merge queue update.")
    archived_at: str | None = Field(default=None, description="Timestamp when the merge queue entry was archived.")
    archive_reason: str | None = Field(default=None, description="Reason the merge queue entry was archived.")


class MergeQueueListResult(BaseModel):
    entries: list[MergeQueueEntryResult]
    count: int


class TaskOrchestrationSummaryEntry(BaseModel):
    project_id: str
    source_cwd: str
    task_id: str
    task_workspace_status: str = Field(description="Current task workspace lifecycle state.")
    worktree_status: str | None = Field(default=None, description="Current git worktree state, when available.")
    worktree_branch: str | None = None
    workspace_path: str | None = None
    merge_queue_status: str | None = Field(default=None, description="Current merge queue state, when available.")
    conflict_risk: str | None = Field(default=None, description="Estimated merge conflict risk.")
    recommended_action: str | None = Field(default=None, description="Recommended next orchestration action.")
    changed_file_count: int | None = Field(default=None, description="Number of changed files in the task worktree.")
    source_head_changed: bool | None = Field(default=None, description="Whether source HEAD moved since task creation.")
    source_dirty: bool | None = Field(default=None, description="Whether the source workspace has uncommitted changes.")
    overlapping_files: list[str] = Field(
        default_factory=list,
        description="Files changed in both source and task workspaces.",
    )
    operator_attention: bool = Field(default=False, description="Whether this entry needs operator attention.")
    operator_attention_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons operator attention is required.",
    )
    validation_status: str = Field(
        default="unknown",
        description="Recorded validation state; legacy records may contain broader values.",
    )
    validation_commands: list[str] = []
    validation_summary: str | None = None
    validated_at: str | None = None
    validated_by: str | None = None
    validation_client_id: str | None = None
    validation_session_id: str | None = None
    archived: bool = Field(description="Whether the task workspace or merge queue record is archived.")
    has_task_workspace_record: bool
    has_merge_queue_record: bool
    anomaly: bool = Field(description="Whether inconsistent orchestration state was detected.")
    anomaly_reasons: list[str] = Field(default_factory=list, description="Reasons the entry is marked anomalous.")


class TaskOrchestrationSummaryResult(BaseModel):
    project_id: str | None = Field(default=None, description="Project filter applied to the summary, if any.")
    entries: list[TaskOrchestrationSummaryEntry] = Field(description="Task orchestration entries matching the request.")
    count: int = Field(description="Number of returned orchestration entries.")
    active_count: int = Field(description="Number of non-archived orchestration entries.")
    archived_count: int = Field(description="Number of archived orchestration entries.")
    anomaly_count: int = Field(description="Number of entries with inconsistent state.")
    attention_count: int = Field(default=0, description="Number of entries requiring operator attention.")


class TaskCleanupPreviewEntry(BaseModel):
    task_id: str
    project_id: str
    source_cwd: str
    workspace_path: str | None = None
    record_path: str | None = None
    queue_status: str | None = Field(default=None, description="Current merge queue state, when available.")
    workspace_status: str = Field(description="Current task workspace lifecycle state.")
    validation_status: str = Field(
        default="unknown",
        description="Recorded validation state; legacy records may contain broader values.",
    )
    cleanup_ready: bool = Field(description="Whether cleanup can proceed without known blockers.")
    cleanup_risk: str = Field(description="Estimated risk of cleaning up this task workspace.")
    cleanup_blockers: list[str] = Field(default_factory=list, description="Reasons cleanup should not proceed yet.")
    recommended_action: str = Field(description="Recommended next cleanup workflow action.")
    worktree_dirty: bool | None = Field(default=None, description="Whether the task worktree has uncommitted changes.")
    has_task_workspace_record: bool = Field(description="Whether a task workspace record exists.")
    has_merge_queue_record: bool = Field(description="Whether a merge queue record exists.")


class TaskCleanupPreviewResult(BaseModel):
    project_id: str | None = Field(default=None, description="Project filter applied to the cleanup preview, if any.")
    entries: list[TaskCleanupPreviewEntry] = Field(description="Per-task cleanup readiness entries.")
    count: int = Field(description="Number of returned cleanup preview entries.")
    ready_count: int = Field(description="Number of entries currently ready for cleanup.")
    blocked_count: int = Field(description="Number of entries currently blocked from cleanup.")
