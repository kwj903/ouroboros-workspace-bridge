from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "blocked"]


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
    status: str = Field(description="Current bundle state after staging; newly staged bundles are pending.")
    risk: RiskLevel = Field(description="Highest risk level assigned to the bundle.")
    approval_required: bool = Field(description="Whether local review approval is required before execution.")
    path: str = Field(description="Runtime record path for the staged bundle.")
    review_hint: str = Field(description="Short instruction for reviewing or following up on the bundle.")
    command_count: int = Field(description="Number of command or action steps in the bundle.")


class CommandBundleStatusResult(BaseModel):
    bundle_id: str = Field(description="Identifier of the bundle being reported.")
    title: str = Field(description="Human-readable purpose of the bundle.")
    cwd: str = Field(description="Workspace-relative directory where the bundle runs.")
    status: str = Field(
        description=(
            "Current bundle state: pending, running, applied, failed, interrupted, or rejected. "
            "Running is still in progress; interrupted requires explicit recovery review."
        )
    )
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
    status: str = Field(
        description=(
            "Current bundle state: pending, running, applied, failed, interrupted, or rejected."
        )
    )
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
    status: str = Field(
        description="Current or final command bundle state; interrupted entries require recovery review."
    )
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
    status: str = Field(
        description="Final bundle state recorded by the handoff, including interrupted recovery records."
    )
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
