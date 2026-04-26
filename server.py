from __future__ import annotations

import contextlib
import fnmatch
import hmac
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qs

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

from terminal_bridge.backups import (
    _backup_file as _create_backup_file,
    _list_backup_entries,
    _restore_backup_payload,
    _sha256_file,
)
from terminal_bridge.browsing import (
    _is_safe_visible_path,
    _iter_visible_paths,
    _list_workspace,
    _read_workspace_file,
    _tree_workspace,
)
from terminal_bridge.bundles import (
    _bundle_risk_rank,
    _combined_bundle_risk,
    _command_bundle_dirs,
    _command_bundle_path,
    _find_command_bundle,
    _move_command_bundle,
    _new_command_bundle_id,
    _write_command_bundle,
)
from terminal_bridge.bundle_serialization import (
    _resolve_bundle_file_action_path,
    _serialize_action_steps,
    _serialize_command_steps,
)
from terminal_bridge.commands import (
    _classify_exec_command,
    _safe_env,
    _validate_command_args,
    _validate_exec_argv,
)
from terminal_bridge.config import (
    AUDIT_LOG,
    BACKUP_DIR,
    BLOCKED_DIR_NAMES,
    COMMAND_BUNDLE_APPLIED_DIR,
    COMMAND_BUNDLE_FAILED_DIR,
    COMMAND_BUNDLE_PENDING_DIR,
    COMMAND_BUNDLE_REJECTED_DIR,
    MAX_STDERR_CHARS,
    MAX_STDOUT_CHARS,
    MAX_WRITE_CHARS,
    MCP_ACCESS_TOKEN,
    MCP_EXPOSE_DIRECT_MUTATION_TOOLS,
    MCP_HOST,
    MCP_PORT,
    NGROK_HOST,
    OPERATION_DIR,
    PROJECT_ROOT,
    RUNTIME_ROOT,
    TASK_DIR,
    TEXT_PAYLOAD_CHUNK_MAX_CHARS,
    TEXT_PAYLOAD_DIR,
    TEXT_PAYLOAD_MAX_TOTAL_CHARS,
    TRASH_DIR,
    WORKSPACE_ROOT,
)
from terminal_bridge.models import (
    AuditLogResult,
    BackupEntry,
    BackupListResult,
    BackupRestoreResult,
    CommandBundleAction,
    CommandBundleListEntry,
    CommandBundleListResult,
    CommandBundleStageResult,
    CommandBundleStatusResult,
    CommandBundleStep,
    CommandResult,
    DeleteResult,
    FileMatchEntry,
    FindFilesResult,
    GitCommitResult,
    ListResult,
    OperationListResult,
    OperationStatusResult,
    PatchApplyResult,
    PatchFileEntry,
    PatchPreviewResult,
    ProjectSnapshotResult,
    ReadFileResult,
    ReadManyFileEntry,
    ReadManyFilesResult,
    ReplaceTextResult,
    RestoreResult,
    SearchTextMatch,
    SearchTextResult,
    TaskListEntry,
    TaskListResult,
    TaskStatusResult,
    TaskStepEntry,
    TextPayloadStageResult,
    TrashEntry,
    TrashListResult,
    TreeResult,
    WorkspaceExecResult,
    WorkspaceInfo,
    WriteFileResult,
)
from terminal_bridge.operations import (
    _begin_operation,
    _complete_operation,
    _fail_operation,
    _model_to_dict,
    _new_operation_id,
    _normalize_operation_id,
    _operation_path,
    _read_operation,
    _set_audit_callback as _set_operation_audit_callback,
    _write_operation_record,
)
from terminal_bridge.payloads import (
    _new_text_payload_id,
    _normalize_text_payload_id,
    _serialize_text_payload_field,
    _stage_text_payload_chunk,
    _text_payload_dir,
    _text_payload_manifest_path,
    _validate_text_payload_ref,
)
from terminal_bridge.patches import (
    _clean_patch_path,
    _extract_patch_paths,
    _resolve_patch_path,
    _run_git_apply_with_stdin,
    _validate_patch_paths,
)
from terminal_bridge.safety import (
    _is_blocked_name,
    _relative,
    _resolve_workspace_path,
    _validate_expected_sha256,
)
from terminal_bridge.storage import _now_iso, _read_json, _sha256_bytes, _write_json
from terminal_bridge.tasks import (
    _list_task_paths,
    _new_task_id,
    _normalize_task_id,
    _read_task,
    _task_path,
    _write_task,
)
from terminal_bridge.trash import (
    _list_trash_entries,
    _move_to_trash,
    _prepare_trash_restore,
    _restore_trash_payload,
)

transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
        NGROK_HOST,
        f"{NGROK_HOST}:*",
    ],
    allowed_origins=[
        "http://127.0.0.1:*",
        "http://localhost:*",
        f"https://{NGROK_HOST}",
        f"https://{NGROK_HOST}:*",
    ],
)

mcp = FastMCP(
    name="Workspace Terminal Bridge",
    instructions=(
        "Provides controlled development access under ~/workspace. "
        "This server rejects absolute paths, path traversal, secret-like files, "
        "and paths outside ~/workspace. It supports reading, safe file writes, "
        "soft deletion, restore, approved command profiles, basic git operations, "
        "and sandboxed argv-based command execution with risk classification."
    ),
    stateless_http=True,
    json_response=True,
    host=MCP_HOST,
    port=MCP_PORT,
    transport_security=transport_security,
)


def _direct_mutation_tool(**kwargs: object):
    if MCP_EXPOSE_DIRECT_MUTATION_TOOLS:
        return mcp.tool(**kwargs)

    def decorator(func):
        return func

    return decorator


def _ensure_runtime_dirs() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    OPERATION_DIR.mkdir(parents=True, exist_ok=True)
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_PENDING_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_APPLIED_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_BUNDLE_FAILED_DIR.mkdir(parents=True, exist_ok=True)


def _audit(event: str, **data: object) -> None:
    _ensure_runtime_dirs()
    record = {
        "ts": _now_iso(),
        "event": event,
        **data,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


_set_operation_audit_callback(_audit)


def _read_operation_record(operation_id: str) -> dict[str, object] | None:
    return _read_operation(operation_id)


def _read_task_record(task_id: str) -> dict[str, object] | None:
    try:
        return _read_task(task_id)
    except FileNotFoundError:
        return None


def _write_task_record(record: dict[str, object]) -> None:
    task_id = _normalize_task_id(str(record["task_id"]))
    _write_task(task_id, record)


def _task_result(record: dict[str, object]) -> TaskStatusResult:
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


def _extract_bearer_token(headers: dict[str, str]) -> str | None:
    authorization = headers.get("authorization")

    if not authorization:
        return None

    scheme, _, value = authorization.partition(" ")

    if scheme.lower() != "bearer" or not value:
        return None

    return value.strip()


def _extract_query_token(query_string: bytes) -> str | None:
    if not query_string:
        return None

    parsed = parse_qs(query_string.decode("utf-8", errors="replace"), keep_blank_values=False)
    values = parsed.get("access_token") or parsed.get("token")

    if not values:
        return None

    return values[0]


def _is_authorized_mcp_request(
    headers: dict[str, str],
    query_string: bytes,
    configured_token: str | None = MCP_ACCESS_TOKEN,
) -> bool:
    if configured_token is None or configured_token == "":
        return True

    candidates = [
        _extract_bearer_token(headers),
        _extract_query_token(query_string),
    ]

    return any(
        candidate is not None and hmac.compare_digest(candidate, configured_token)
        for candidate in candidates
    )


class AccessTokenMiddleware:
    def __init__(self, app: object, access_token: str | None) -> None:
        self.app = app
        self.access_token = access_token

    async def __call__(self, scope: dict[str, object], receive: object, send: object) -> None:
        if scope.get("type") != "http" or not self.access_token:
            await self.app(scope, receive, send)
            return

        raw_headers = scope.get("headers", [])
        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in raw_headers
            if isinstance(key, bytes) and isinstance(value, bytes)
        }

        query_string = scope.get("query_string", b"")
        if isinstance(query_string, str):
            query_string = query_string.encode("utf-8")

        if _is_authorized_mcp_request(headers, query_string, self.access_token):
            await self.app(scope, receive, send)
            return

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"error":"Unauthorized MCP request."}',
            }
        )


def _run_server() -> None:
    if not MCP_ACCESS_TOKEN:
        _run_server()
        return

    from starlette.applications import Starlette
    from starlette.routing import Mount
    import uvicorn

    protected_mcp_app = AccessTokenMiddleware(mcp.streamable_http_app(), MCP_ACCESS_TOKEN)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp.session_manager.run():
            yield

    app = Starlette(
        routes=[
            Mount("/", app=protected_mcp_app),
        ],
        lifespan=lifespan,
    )

    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)


def _ensure_workspace_root_exists() -> None:
    if not WORKSPACE_ROOT.exists() or not WORKSPACE_ROOT.is_dir():
        raise FileNotFoundError(f"Workspace root does not exist: {WORKSPACE_ROOT}")


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _backup_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None

    _ensure_runtime_dirs()
    return _create_backup_file(path)


def _run_workspace_exec(
    cwd: str,
    argv: list[str],
    timeout_seconds: int,
    operation_id: str | None = None,
) -> WorkspaceExecResult:
    safe_argv = _validate_exec_argv(argv)
    target = _resolve_workspace_path(cwd)

    if not target.exists():
        raise FileNotFoundError(f"Directory does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

    risk, reason = _classify_exec_command(target, safe_argv)
    op_id, previous = _begin_operation(
        "workspace_exec",
        {
            "cwd": cwd,
            "argv": safe_argv,
            "timeout_seconds": timeout_seconds,
            "risk": risk,
            "reason": reason,
        },
        operation_id,
    )

    if previous is not None and previous.get("status") == "completed":
        result = dict(previous.get("result") or {})
        result["operation_id"] = op_id
        return WorkspaceExecResult(**result)

    try:
        if risk == "blocked":
            result = WorkspaceExecResult(
                cwd=_relative(target),
                command=safe_argv,
                risk=risk,
                approval_required=False,
                operation_id=op_id,
                stderr=reason,
            )
            _complete_operation(op_id, result)
            return result

        if risk != "low":
            result = WorkspaceExecResult(
                cwd=_relative(target),
                command=safe_argv,
                risk=risk,
                approval_required=True,
                operation_id=op_id,
                stderr=reason,
            )
            _complete_operation(op_id, result)
            return result

        completed = subprocess.run(
            safe_argv,
            cwd=str(target),
            env=_safe_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )

        stdout, out_truncated = _truncate(completed.stdout, MAX_STDOUT_CHARS)
        stderr, err_truncated = _truncate(completed.stderr, MAX_STDERR_CHARS)

        result = WorkspaceExecResult(
            cwd=_relative(target),
            command=safe_argv,
            risk=risk,
            approval_required=False,
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            truncated=out_truncated or err_truncated,
            operation_id=op_id,
        )

        _audit(
            "workspace_exec",
            operation_id=op_id,
            cwd=result.cwd,
            command=safe_argv,
            risk=risk,
            exit_code=result.exit_code,
        )
        _complete_operation(op_id, result)
        return result

    except Exception as exc:
        _fail_operation(op_id, exc)
        raise



def _run_command(cwd: str, command: list[str], timeout_seconds: int = 30) -> CommandResult:
    target = _resolve_workspace_path(cwd)

    if not target.exists():
        raise FileNotFoundError(f"Directory does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

    completed = subprocess.run(
        command,
        cwd=str(target),
        env=_safe_env(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
        shell=False,
        check=False,
    )

    stdout, out_truncated = _truncate(completed.stdout, MAX_STDOUT_CHARS)
    stderr, err_truncated = _truncate(completed.stderr, MAX_STDERR_CHARS)

    result = CommandResult(
        cwd=_relative(target),
        command=command,
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        truncated=out_truncated or err_truncated,
    )

    _audit(
        "command",
        cwd=result.cwd,
        command=command,
        exit_code=result.exit_code,
        truncated=result.truncated,
    )

    return result


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_info() -> WorkspaceInfo:
    """Return basic information about the configured ~/workspace root and enabled tools."""
    tools = [
        "workspace_info",
        "workspace_list",
        "workspace_tree",
        "workspace_read_file",
        "workspace_find_files",
        "workspace_search_text",
        "workspace_read_many_files",
        "workspace_project_snapshot",
        "workspace_git_status",
        "workspace_git_diff",
        "workspace_preview_patch",
        "workspace_read_audit_log",
        "workspace_get_operation",
        "workspace_list_operations",
        "workspace_list_backups",
        "workspace_list_trash",
        "workspace_task_start",
        "workspace_task_status",
        "workspace_task_log_step",
        "workspace_task_update_plan",
        "workspace_task_finish",
        "workspace_list_tasks",
        "workspace_stage_text_payload",
        "workspace_stage_command_bundle",
        "workspace_stage_action_bundle",
        "workspace_stage_patch_bundle",
        "workspace_command_bundle_status",
        "workspace_list_command_bundles",
        "workspace_cancel_command_bundle",
    ]

    if MCP_EXPOSE_DIRECT_MUTATION_TOOLS:
        tools.extend(
            [
                "workspace_create_directory",
                "workspace_write_file",
                "workspace_append_file",
                "workspace_replace_text",
                "workspace_soft_delete",
                "workspace_move_to_trash",
                "workspace_restore_deleted",
                "workspace_restore_backup",
                "workspace_apply_patch",
                "workspace_git_add",
                "workspace_git_commit",
                "workspace_exec",
                "workspace_run_profile",
            ]
        )

    return WorkspaceInfo(
        root=str(WORKSPACE_ROOT),
        mode=(
            "development_mvp_with_direct_mutation_tools"
            if MCP_EXPOSE_DIRECT_MUTATION_TOOLS
            else "development_mvp_bundle_first"
        ),
        runtime_root=str(RUNTIME_ROOT),
        tools=tools,
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_list(
    path: Annotated[
        str,
        Field(
            description=(
                "Relative directory path under ~/workspace. "
                "Use '.' for the workspace root. Absolute paths and '..' are rejected."
            )
        ),
    ] = ".",
    include_hidden: Annotated[
        bool,
        Field(description="Whether to include hidden dotfiles, except blocked secret-like files."),
    ] = False,
) -> ListResult:
    """List files and directories under ~/workspace."""
    return _list_workspace(path, include_hidden)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_tree(
    path: Annotated[str, Field(description="Relative directory path under ~/workspace.")] = ".",
    max_depth: Annotated[int, Field(ge=1, le=5)] = 2,
    max_entries: Annotated[int, Field(ge=1, le=300)] = 120,
) -> TreeResult:
    """Return a compact tree view under ~/workspace."""
    return _tree_workspace(path, max_depth, max_entries)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_read_file(
    path: Annotated[str, Field(description="Relative file path under ~/workspace.")],
    offset: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int, Field(ge=1, le=20_000)] = 12_000,
) -> ReadFileResult:
    """Read a UTF-8 text file under ~/workspace."""
    return _read_workspace_file(path, offset, limit)


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_create_directory(
    path: Annotated[str, Field(description="Relative directory path under ~/workspace.")],
) -> WriteFileResult:
    """Create a directory under ~/workspace."""
    target = _resolve_workspace_path(path)
    target.mkdir(parents=True, exist_ok=True)

    _audit("create_directory", path=_relative(target))

    return WriteFileResult(
        path=_relative(target),
        action="created_directory",
        size_bytes=0,
        sha256="",
        backup_id=None,
    )


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_write_file(
    path: Annotated[str, Field(description="Relative file path under ~/workspace.")],
    content: Annotated[str, Field(description="UTF-8 text content to write.")],
    overwrite: Annotated[bool, Field(description="Whether to overwrite an existing file.")] = False,
    create_parent_dirs: Annotated[bool, Field(description="Whether to create missing parent directories.")] = True,
    expected_sha256: Annotated[str | None, Field(description="Optional current sha256 guard for overwrites.")] = None,
    operation_id: Annotated[str | None, Field(description="Optional idempotency key for retry-safe writes.")] = None,
) -> WriteFileResult:
    """Create or overwrite a UTF-8 text file under ~/workspace. Existing files are backed up before overwrite."""
    op_id, previous = _begin_operation(
        "workspace_write_file",
        {
            "path": path,
            "overwrite": overwrite,
            "create_parent_dirs": create_parent_dirs,
            "expected_sha256": expected_sha256,
            "content_length": len(content),
        },
        operation_id,
    )

    if previous is not None and previous.get("status") == "completed":
        result = dict(previous.get("result") or {})
        result["operation_id"] = op_id
        return WriteFileResult(**result)

    try:
        if len(content) > MAX_WRITE_CHARS:
            raise ValueError(f"Content too large. Max characters: {MAX_WRITE_CHARS}")

        target = _resolve_workspace_path(path)

        if target.exists() and not overwrite:
            raise FileExistsError(f"File already exists. Set overwrite=true to replace: {_relative(target)}")

        if target.exists() and not target.is_file():
            raise IsADirectoryError(f"Path exists and is not a file: {_relative(target)}")

        _validate_expected_sha256(target, expected_sha256)

        if create_parent_dirs:
            target.parent.mkdir(parents=True, exist_ok=True)

        backup_id = _backup_file(target)
        data = content.encode("utf-8")
        target.write_bytes(data)

        result = WriteFileResult(
            path=_relative(target),
            action="overwritten" if backup_id else "created",
            size_bytes=len(data),
            sha256=_sha256_bytes(data),
            backup_id=backup_id,
            operation_id=op_id,
        )

        _audit(
            "write_file",
            operation_id=op_id,
            path=result.path,
            action=result.action,
            size_bytes=result.size_bytes,
            sha256=result.sha256,
            backup_id=backup_id,
        )
        _complete_operation(op_id, result)

        return result

    except Exception as exc:
        _fail_operation(op_id, exc)
        raise


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_append_file(
    path: Annotated[str, Field(description="Relative file path under ~/workspace.")],
    content: Annotated[str, Field(description="UTF-8 text content to append.")],
    create_if_missing: Annotated[bool, Field(description="Create the file if it does not exist.")] = True,
) -> WriteFileResult:
    """Append UTF-8 text to a file under ~/workspace. Existing files are backed up before append."""
    if len(content) > MAX_WRITE_CHARS:
        raise ValueError(f"Content too large. Max characters: {MAX_WRITE_CHARS}")

    target = _resolve_workspace_path(path)

    if not target.exists() and not create_if_missing:
        raise FileNotFoundError(f"File does not exist: {_relative(target)}")

    if target.exists() and not target.is_file():
        raise IsADirectoryError(f"Path exists and is not a file: {_relative(target)}")

    target.parent.mkdir(parents=True, exist_ok=True)

    backup_id = _backup_file(target)
    with target.open("a", encoding="utf-8") as f:
        f.write(content)

    raw = target.read_bytes()

    result = WriteFileResult(
        path=_relative(target),
        action="appended",
        size_bytes=len(raw),
        sha256=_sha256_bytes(raw),
        backup_id=backup_id,
    )

    _audit(
        "append_file",
        path=result.path,
        size_bytes=result.size_bytes,
        sha256=result.sha256,
        backup_id=backup_id,
    )

    return result


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_replace_text(
    path: Annotated[str, Field(description="Relative UTF-8 file path under ~/workspace.")],
    old_text: Annotated[str, Field(description="Exact text to find.")],
    new_text: Annotated[str, Field(description="Replacement text.")],
    replace_all: Annotated[bool, Field(description="Replace all occurrences instead of only the first.")] = False,
    expected_sha256: Annotated[str | None, Field(description="Optional current sha256 guard.")] = None,
    operation_id: Annotated[str | None, Field(description="Optional idempotency key for retry-safe replacements.")] = None,
) -> ReplaceTextResult:
    """Replace exact text in a UTF-8 file under ~/workspace. The file is backed up before modification."""
    op_id, previous = _begin_operation(
        "workspace_replace_text",
        {
            "path": path,
            "replace_all": replace_all,
            "expected_sha256": expected_sha256,
            "old_text_length": len(old_text),
            "new_text_length": len(new_text),
        },
        operation_id,
    )

    if previous is not None and previous.get("status") == "completed":
        result = dict(previous.get("result") or {})
        result["operation_id"] = op_id
        return ReplaceTextResult(**result)

    try:
        target = _resolve_workspace_path(path)

        if not target.exists():
            raise FileNotFoundError(f"File does not exist: {_relative(target)}")

        if not target.is_file():
            raise IsADirectoryError(f"Path is not a file: {_relative(target)}")

        if old_text == "":
            raise ValueError("old_text cannot be empty.")

        _validate_expected_sha256(target, expected_sha256)

        raw = target.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Only UTF-8 text files are supported.") from exc

        count = text.count(old_text)
        if count == 0:
            raise ValueError("old_text was not found.")

        if replace_all:
            updated = text.replace(old_text, new_text)
            replacements = count
        else:
            updated = text.replace(old_text, new_text, 1)
            replacements = 1

        if len(updated) > MAX_WRITE_CHARS:
            raise ValueError(f"Updated content too large. Max characters: {MAX_WRITE_CHARS}")

        backup_id = _backup_file(target)
        data = updated.encode("utf-8")
        target.write_bytes(data)

        result = ReplaceTextResult(
            path=_relative(target),
            replacements=replacements,
            size_bytes=len(data),
            sha256=_sha256_bytes(data),
            backup_id=backup_id,
            operation_id=op_id,
        )

        _audit(
            "replace_text",
            operation_id=op_id,
            path=result.path,
            replacements=replacements,
            size_bytes=result.size_bytes,
            sha256=result.sha256,
            backup_id=backup_id,
        )
        _complete_operation(op_id, result)

        return result

    except Exception as exc:
        _fail_operation(op_id, exc)
        raise


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_soft_delete(
    path: Annotated[str, Field(description="Relative file or directory path under ~/workspace.")],
    operation_id: Annotated[str | None, Field(description="Optional idempotency key for retry-safe trash moves.")] = None,
) -> DeleteResult:
    """Move a file or directory to the MCP trash instead of permanently deleting it."""
    op_id, previous = _begin_operation(
        "workspace_soft_delete",
        {
            "path": path,
        },
        operation_id,
    )

    if previous is not None and previous.get("status") == "completed":
        result = dict(previous.get("result") or {})
        result["operation_id"] = op_id
        return DeleteResult(**result)

    try:
        target = _resolve_workspace_path(path)

        if not target.exists():
            raise FileNotFoundError(f"Path does not exist: {_relative(target)}")

        if target == WORKSPACE_ROOT:
            raise PermissionError("Cannot delete workspace root.")

        _ensure_runtime_dirs()

        result = _move_to_trash(target, op_id)

        _audit(
            "soft_delete",
            operation_id=op_id,
            original_path=result.original_path,
            trash_id=result.trash_id,
        )
        _complete_operation(op_id, result)

        return result

    except Exception as exc:
        _fail_operation(op_id, exc)
        raise


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_restore_deleted(
    trash_id: Annotated[str, Field(description="trash_id returned from workspace_soft_delete.")],
    overwrite: Annotated[bool, Field(description="Whether to overwrite if the original path exists.")] = False,
) -> RestoreResult:
    """Restore a soft-deleted file or directory from MCP trash."""
    original, trash_path, backup_id, overwrote_original = _prepare_trash_restore(trash_id, overwrite)

    if overwrote_original:
        _audit("restore_overwrite_backup", path=_relative(original), backup_id=backup_id)

    result = _restore_trash_payload(trash_id, original, trash_path)

    _audit("restore_deleted", restored_path=result.restored_path, trash_id=trash_id)

    return result


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_read_audit_log(
    limit: Annotated[int, Field(ge=1, le=200, description="Maximum audit entries to return.")] = 50,
    event: Annotated[str | None, Field(description="Optional event name filter.")] = None,
) -> AuditLogResult:
    """Read recent MCP audit log entries. Useful for checking whether a tool call actually ran."""
    _ensure_runtime_dirs()

    if not AUDIT_LOG.exists():
        return AuditLogResult(entries=[], count=0, truncated=False)

    lines = AUDIT_LOG.read_text(encoding="utf-8").splitlines()
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_get_operation(
    operation_id: Annotated[str, Field(description="Operation id returned by write/delete/replace tools.")],
) -> OperationStatusResult:
    """Return a recorded operation status by operation_id."""
    op_id = _normalize_operation_id(operation_id)
    record = _read_operation_record(op_id)

    if record is None:
        raise FileNotFoundError(f"Operation not found: {op_id}")

    return OperationStatusResult(
        operation_id=op_id,
        status=str(record.get("status", "unknown")),
        tool=record.get("tool") if isinstance(record.get("tool"), str) else None,
        started_at=record.get("started_at") if isinstance(record.get("started_at"), str) else None,
        completed_at=record.get("completed_at") if isinstance(record.get("completed_at"), str) else None,
        failed_at=record.get("failed_at") if isinstance(record.get("failed_at"), str) else None,
        args=record.get("args") if isinstance(record.get("args"), dict) else None,
        result=record.get("result") if isinstance(record.get("result"), dict) else None,
        error=record.get("error") if isinstance(record.get("error"), str) else None,
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_list_operations(
    limit: Annotated[int, Field(ge=1, le=200, description="Maximum operations to return.")] = 50,
) -> OperationListResult:
    """List recent recorded operations, newest first."""
    _ensure_runtime_dirs()

    entries: list[OperationStatusResult] = []

    for operation_path in sorted(OPERATION_DIR.glob("*.json"), reverse=True):
        try:
            record = json.loads(operation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        op_id = str(record.get("operation_id", operation_path.stem))
        entries.append(
            OperationStatusResult(
                operation_id=op_id,
                status=str(record.get("status", "unknown")),
                tool=record.get("tool") if isinstance(record.get("tool"), str) else None,
                started_at=record.get("started_at") if isinstance(record.get("started_at"), str) else None,
                completed_at=record.get("completed_at") if isinstance(record.get("completed_at"), str) else None,
                failed_at=record.get("failed_at") if isinstance(record.get("failed_at"), str) else None,
                args=record.get("args") if isinstance(record.get("args"), dict) else None,
                result=record.get("result") if isinstance(record.get("result"), dict) else None,
                error=record.get("error") if isinstance(record.get("error"), str) else None,
            )
        )

        if len(entries) >= limit:
            break

    return OperationListResult(entries=entries, count=len(entries))


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_list_backups(
    limit: Annotated[int, Field(ge=1, le=200, description="Maximum backups to return.")] = 50,
) -> BackupListResult:
    """List recent file backups created before overwrite/append/replace/restore operations."""
    _ensure_runtime_dirs()

    entries = _list_backup_entries(limit)
    return BackupListResult(entries=entries, count=len(entries))


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_restore_backup(
    backup_id: Annotated[str, Field(description="backup_id returned by workspace_list_backups or write operations.")],
    overwrite: Annotated[bool, Field(description="Whether to overwrite the current original path.")] = False,
    operation_id: Annotated[str | None, Field(description="Optional idempotency key for retry-safe backup restore.")] = None,
) -> BackupRestoreResult:
    """Restore a file from a backup created by this MCP server."""
    op_id, previous = _begin_operation(
        "workspace_restore_backup",
        {
            "backup_id": backup_id,
            "overwrite": overwrite,
        },
        operation_id,
    )

    if previous is not None and previous.get("status") == "completed":
        return BackupRestoreResult(**dict(previous.get("result") or {}))

    try:
        result = _restore_backup_payload(backup_id, overwrite)

        _audit(
            "restore_backup",
            operation_id=op_id,
            backup_id=backup_id,
            restored_path=result.restored_path,
            backup_id_before_overwrite=result.backup_id_before_overwrite,
        )
        _complete_operation(op_id, result)

        return result

    except Exception as exc:
        _fail_operation(op_id, exc)
        raise


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_list_trash(
    limit: Annotated[int, Field(ge=1, le=200, description="Maximum trash entries to return.")] = 50,
) -> TrashListResult:
    """List recent soft-deleted files and directories in MCP trash."""
    _ensure_runtime_dirs()

    entries = _list_trash_entries(limit)
    return TrashListResult(entries=entries, count=len(entries))


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_move_to_trash(
    path: Annotated[str, Field(description="Relative file or directory path under ~/workspace.")],
    operation_id: Annotated[str | None, Field(description="Optional idempotency key for retry-safe trash moves.")] = None,
) -> DeleteResult:
    """Alias for workspace_soft_delete. Moves a file or directory to reversible MCP trash."""
    return workspace_soft_delete(path=path, operation_id=operation_id)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_find_files(
    path: Annotated[str, Field(description="Relative directory path under ~/workspace.")] = ".",
    pattern: Annotated[str, Field(description="fnmatch pattern such as '*.py' or '*server*'.")] = "*",
    include_files: Annotated[bool, Field(description="Whether to include files.")] = True,
    include_directories: Annotated[bool, Field(description="Whether to include directories.")] = False,
    max_entries: Annotated[int, Field(ge=1, le=300, description="Maximum matching entries to return.")] = 100,
) -> FindFilesResult:
    """Find files or directories under ~/workspace using a safe fnmatch pattern."""
    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {_relative(target)}")

    if pattern.strip() == "":
        raise ValueError("pattern cannot be empty.")

    scan_limit = min(max(max_entries * 20, 500), 3000)
    paths, scan_truncated = _iter_visible_paths(target, scan_limit)

    entries: list[FileMatchEntry] = []
    truncated = scan_truncated

    for item in paths:
        rel = _relative(item)
        kind = "directory" if item.is_dir() else "file" if item.is_file() else "other"

        if kind == "file" and not include_files:
            continue
        if kind == "directory" and not include_directories:
            continue

        if not (fnmatch.fnmatch(item.name, pattern) or fnmatch.fnmatch(rel, pattern)):
            continue

        size_bytes: int | None = None
        if item.is_file():
            try:
                size_bytes = item.stat().st_size
            except OSError:
                size_bytes = None

        entries.append(FileMatchEntry(path=rel, kind=kind, size_bytes=size_bytes))

        if len(entries) >= max_entries:
            truncated = True
            break

    return FindFilesResult(
        path=_relative(target),
        pattern=pattern,
        entries=entries,
        count=len(entries),
        truncated=truncated,
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_search_text(
    query: Annotated[str, Field(description="Plain text query to search for. Regex is not used.")],
    path: Annotated[str, Field(description="Relative directory path under ~/workspace.")] = ".",
    file_glob: Annotated[str, Field(description="File glob such as '*.py' or '*'.")] = "*",
    case_sensitive: Annotated[bool, Field(description="Whether matching is case-sensitive.")] = False,
    max_matches: Annotated[int, Field(ge=1, le=300, description="Maximum matches to return.")] = 100,
    max_file_bytes: Annotated[int, Field(ge=1, le=1_000_000, description="Maximum bytes per file to scan.")] = 500_000,
) -> SearchTextResult:
    """Search text files under ~/workspace for a plain text query."""
    if query == "":
        raise ValueError("query cannot be empty.")

    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {_relative(target)}")

    needle = query if case_sensitive else query.lower()
    paths, scan_truncated = _iter_visible_paths(target, 5000)

    matches: list[SearchTextMatch] = []
    truncated = scan_truncated

    for item in paths:
        if not item.is_file():
            continue

        rel = _relative(item)

        if not (fnmatch.fnmatch(item.name, file_glob) or fnmatch.fnmatch(rel, file_glob)):
            continue

        try:
            if item.stat().st_size > max_file_bytes:
                continue
        except OSError:
            continue

        try:
            text = item.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError:
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            haystack = line if case_sensitive else line.lower()
            if needle not in haystack:
                continue

            display_line = line
            if len(display_line) > 500:
                display_line = display_line[:500] + "..."

            matches.append(
                SearchTextMatch(
                    path=rel,
                    line_number=line_number,
                    line=display_line,
                )
            )

            if len(matches) >= max_matches:
                truncated = True
                return SearchTextResult(
                    query=query,
                    path=_relative(target),
                    matches=matches,
                    count=len(matches),
                    truncated=truncated,
                )

    return SearchTextResult(
        query=query,
        path=_relative(target),
        matches=matches,
        count=len(matches),
        truncated=truncated,
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_read_many_files(
    paths: Annotated[list[str], Field(description="Relative file paths under ~/workspace.")],
    limit_per_file: Annotated[int, Field(ge=1, le=20_000, description="Maximum characters per file.")] = 8_000,
    total_limit: Annotated[int, Field(ge=1, le=80_000, description="Maximum total characters to return.")] = 40_000,
) -> ReadManyFilesResult:
    """Read multiple UTF-8 text files under ~/workspace with per-file and total limits."""
    if not paths:
        raise ValueError("paths cannot be empty.")

    entries: list[ReadManyFileEntry] = []
    remaining = total_limit
    truncated = False

    for raw_path in paths:
        if remaining <= 0:
            truncated = True
            entries.append(
                ReadManyFileEntry(
                    path=raw_path,
                    error="Total output limit reached before reading this file.",
                    truncated=True,
                )
            )
            continue

        try:
            target = _resolve_workspace_path(raw_path)

            if not target.exists():
                raise FileNotFoundError(f"File does not exist: {_relative(target)}")

            if not target.is_file():
                raise IsADirectoryError(f"Path is not a file: {_relative(target)}")

            raw = target.read_bytes()
            text = raw.decode("utf-8")

            local_limit = min(limit_per_file, remaining)
            content, file_truncated = _truncate(text, local_limit)
            remaining -= len(content)
            truncated = truncated or file_truncated or len(content) < len(text)

            entries.append(
                ReadManyFileEntry(
                    path=_relative(target),
                    content=content,
                    truncated=file_truncated,
                    size_bytes=len(raw),
                    sha256=_sha256_bytes(raw),
                )
            )

        except Exception as exc:
            entries.append(
                ReadManyFileEntry(
                    path=raw_path,
                    error=f"{type(exc).__name__}: {exc}",
                    truncated=False,
                )
            )

    return ReadManyFilesResult(entries=entries, count=len(entries), truncated=truncated)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_project_snapshot(
    path: Annotated[str, Field(description="Relative project directory under ~/workspace.")] = ".",
    max_depth: Annotated[int, Field(ge=1, le=5, description="Tree depth.")] = 2,
    max_entries: Annotated[int, Field(ge=1, le=300, description="Tree entries.")] = 120,
) -> ProjectSnapshotResult:
    """Return a compact project snapshot: tree, key files, and git status."""
    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {_relative(target)}")

    tree_result = workspace_tree(path=_relative(target), max_depth=max_depth, max_entries=max_entries)

    key_names = [
        "README.md",
        "pyproject.toml",
        "uv.lock",
        "package.json",
        "go.mod",
        "Cargo.toml",
        "requirements.txt",
        "Makefile",
        "Dockerfile",
        ".python-version",
    ]

    key_files: list[str] = []
    for name in key_names:
        candidate = target / name
        if candidate.exists() and candidate.is_file() and _is_safe_visible_path(candidate):
            key_files.append(_relative(candidate))

    git_status_result = _run_command(
        cwd=_relative(target),
        command=["git", "status", "--short", "--branch"],
        timeout_seconds=15,
    )

    git_status = git_status_result.stdout
    if git_status_result.stderr:
        git_status = (git_status + "\n" + git_status_result.stderr).strip()

    return ProjectSnapshotResult(
        path=_relative(target),
        tree=tree_result.entries,
        key_files=key_files,
        git_status=git_status,
        truncated=tree_result.truncated or git_status_result.truncated,
    )


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_task_start(
    title: Annotated[str, Field(min_length=1, max_length=120, description="Short task title.")],
    goal: Annotated[str, Field(min_length=1, max_length=2_000, description="Task goal or user request summary.")],
    plan: Annotated[list[str], Field(description="Initial ordered plan steps.")] = [],
    metadata: Annotated[dict[str, object] | None, Field(description="Optional task metadata.")] = None,
    task_id: Annotated[str | None, Field(description="Optional explicit task id. Generated if omitted.")] = None,
) -> TaskStatusResult:
    """Start a Codex-style local work task record for planning, steps, verification, and handoff."""
    new_task_id = _normalize_task_id(task_id) if task_id else _new_task_id()

    if _task_path(new_task_id).exists():
        raise FileExistsError(f"Task already exists: {new_task_id}")

    now = _now_iso()
    record: dict[str, object] = {
        "task_id": new_task_id,
        "title": title,
        "goal": goal,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "finished_at": None,
        "plan": [str(item) for item in plan],
        "steps": [],
        "metadata": metadata or {},
        "summary": None,
        "next_steps": [],
    }

    _write_task(new_task_id, record)
    _audit("task_started", task_id=new_task_id, title=title)
    return _task_result(record)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_task_status(
    task_id: Annotated[str, Field(description="Task id returned by workspace_task_start.")],
) -> TaskStatusResult:
    """Return a task record by task_id."""
    normalized = _normalize_task_id(task_id)
    record = _read_task(normalized)

    return _task_result(record)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_task_log_step(
    task_id: Annotated[str, Field(description="Task id returned by workspace_task_start.")],
    message: Annotated[str, Field(min_length=1, max_length=2_000, description="Step message to append.")],
    kind: Annotated[
        Literal["note", "read", "write", "test", "decision", "todo", "error"],
        Field(description="Step kind."),
    ] = "note",
    data: Annotated[dict[str, object] | None, Field(description="Optional structured data for this step.")] = None,
) -> TaskStatusResult:
    """Append a step to a task record and return the updated task."""
    normalized = _normalize_task_id(task_id)
    record = _read_task(normalized)

    if record.get("status") not in {"active", "paused"}:
        raise ValueError(f"Cannot log step to non-active task: {record.get('status')}")

    steps = record.get("steps") if isinstance(record.get("steps"), list) else []
    steps.append(
        {
            "ts": _now_iso(),
            "kind": kind,
            "message": message,
            "data": data,
        }
    )

    record["steps"] = steps
    record["updated_at"] = _now_iso()

    _write_task(normalized, record)
    _audit("task_step_logged", task_id=normalized, kind=kind, message=message)
    return _task_result(record)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_task_update_plan(
    task_id: Annotated[str, Field(description="Task id returned by workspace_task_start.")],
    plan: Annotated[list[str], Field(description="Replacement ordered plan steps.")],
) -> TaskStatusResult:
    """Replace the plan for an active task."""
    normalized = _normalize_task_id(task_id)
    record = _read_task(normalized)

    if record.get("status") not in {"active", "paused"}:
        raise ValueError(f"Cannot update plan for non-active task: {record.get('status')}")

    record["plan"] = [str(item) for item in plan]
    record["updated_at"] = _now_iso()

    _write_task(normalized, record)
    _audit("task_plan_updated", task_id=normalized, plan=record["plan"])
    return _task_result(record)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_task_finish(
    task_id: Annotated[str, Field(description="Task id returned by workspace_task_start.")],
    status: Annotated[
        Literal["completed", "paused", "cancelled"],
        Field(description="Final or paused task status."),
    ] = "completed",
    summary: Annotated[str, Field(max_length=4_000, description="Task summary.")] = "",
    next_steps: Annotated[list[str], Field(description="Follow-up steps, if any.")] = [],
) -> TaskStatusResult:
    """Finish, pause, or cancel a task record."""
    normalized = _normalize_task_id(task_id)
    record = _read_task(normalized)

    now = _now_iso()
    record["status"] = status
    record["updated_at"] = now
    record["finished_at"] = now if status in {"completed", "cancelled"} else None
    record["summary"] = summary
    record["next_steps"] = [str(item) for item in next_steps]

    _write_task(normalized, record)
    _audit("task_finished", task_id=normalized, status=status, summary=summary)
    return _task_result(record)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_list_tasks(
    limit: Annotated[int, Field(ge=1, le=200, description="Maximum tasks to return.")] = 50,
) -> TaskListResult:
    """List recent task records, newest first."""
    _ensure_runtime_dirs()

    entries: list[TaskListEntry] = []

    for task_path in _list_task_paths():
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_preview_patch(
    patch: Annotated[str, Field(description="Unified diff patch text to validate with git apply --check.")],
    cwd: Annotated[str, Field(description="Relative git repository directory under ~/workspace.")] = ".",
    timeout_seconds: Annotated[int, Field(ge=1, le=60)] = 15,
) -> PatchPreviewResult:
    """Validate a unified diff patch without applying it."""
    if patch.strip() == "":
        raise ValueError("patch cannot be empty.")

    if len(patch) > MAX_WRITE_CHARS:
        raise ValueError(f"Patch too large. Max characters: {MAX_WRITE_CHARS}")

    target = _resolve_workspace_path(cwd)

    if not target.exists() or not target.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

    patch_paths = _extract_patch_paths(patch)
    _validate_patch_paths(target, patch_paths)

    check = _run_git_apply_with_stdin(
        cwd=target,
        args=["--check"],
        patch=patch,
        timeout_seconds=timeout_seconds,
    )

    return PatchPreviewResult(
        cwd=_relative(target),
        files=[PatchFileEntry(path=item) for item in patch_paths],
        can_apply=check.exit_code == 0,
        exit_code=check.exit_code,
        stdout=check.stdout,
        stderr=check.stderr,
        truncated=check.truncated,
    )


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_apply_patch(
    patch: Annotated[str, Field(description="Unified diff patch text to apply with git apply.")],
    cwd: Annotated[str, Field(description="Relative git repository directory under ~/workspace.")] = ".",
    operation_id: Annotated[str | None, Field(description="Optional idempotency key for retry-safe patch application.")] = None,
    timeout_seconds: Annotated[int, Field(ge=1, le=120)] = 30,
    return_diff: Annotated[bool, Field(description="Whether to include git diff in the tool result. Keep false for large changes.")] = False,
    diff_max_chars: Annotated[int, Field(ge=1, le=20_000, description="Maximum diff characters to return when return_diff is true.")] = 4_000,
) -> PatchApplyResult:
    """Apply a unified diff patch under ~/workspace after git apply --check. Existing files are backed up first."""
    op_id, previous = _begin_operation(
        "workspace_apply_patch",
        {
            "cwd": cwd,
            "patch_length": len(patch),
            "patch_sha256": _sha256_bytes(patch.encode("utf-8")),
            "return_diff": return_diff,
            "diff_max_chars": diff_max_chars,
        },
        operation_id,
    )

    if previous is not None and previous.get("status") == "completed":
        result = dict(previous.get("result") or {})
        result["operation_id"] = op_id
        return PatchApplyResult(**result)

    try:
        if patch.strip() == "":
            raise ValueError("patch cannot be empty.")

        if len(patch) > MAX_WRITE_CHARS:
            raise ValueError(f"Patch too large. Max characters: {MAX_WRITE_CHARS}")

        target = _resolve_workspace_path(cwd)

        if not target.exists() or not target.is_dir():
            raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

        patch_paths = _extract_patch_paths(patch)
        _validate_patch_paths(target, patch_paths)

        check = _run_git_apply_with_stdin(
            cwd=target,
            args=["--check"],
            patch=patch,
            timeout_seconds=timeout_seconds,
        )

        if check.exit_code != 0:
            raise RuntimeError(f"git apply --check failed: {check.stderr or check.stdout}")

        backup_ids: dict[str, str | None] = {}
        for patch_path in patch_paths:
            workspace_path = _resolve_patch_path(target, patch_path)
            if workspace_path.exists() and workspace_path.is_file():
                backup_ids[patch_path] = _backup_file(workspace_path)
            else:
                backup_ids[patch_path] = None

        applied = _run_git_apply_with_stdin(
            cwd=target,
            args=[],
            patch=patch,
            timeout_seconds=timeout_seconds,
        )

        if applied.exit_code != 0:
            raise RuntimeError(f"git apply failed: {applied.stderr or applied.stdout}")

        diff_result = _run_command(
            cwd=_relative(target),
            command=["git", "diff", "--no-ext-diff"],
            timeout_seconds=15,
        )

        git_diff = ""
        diff_truncated = diff_result.truncated

        if return_diff:
            git_diff, limit_truncated = _truncate(diff_result.stdout, diff_max_chars)
            diff_truncated = diff_truncated or limit_truncated
        else:
            diff_truncated = diff_truncated or bool(diff_result.stdout)

        result = PatchApplyResult(
            cwd=_relative(target),
            files=[PatchFileEntry(path=item) for item in patch_paths],
            exit_code=applied.exit_code,
            stdout=applied.stdout,
            stderr=applied.stderr,
            backup_ids=backup_ids,
            git_diff=git_diff,
            operation_id=op_id,
            truncated=applied.truncated or diff_truncated,
        )

        _audit(
            "apply_patch",
            operation_id=op_id,
            cwd=result.cwd,
            files=patch_paths,
            backup_ids=backup_ids,
            patch_sha256=_sha256_bytes(patch.encode("utf-8")),
        )
        _complete_operation(op_id, result)

        return result

    except Exception as exc:
        _fail_operation(op_id, exc)
        raise


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_git_status(
    cwd: Annotated[
        str,
        Field(description="Relative directory under ~/workspace that contains, or is inside, a git repository."),
    ] = ".",
) -> CommandResult:
    """Run git status under ~/workspace."""
    return _run_command(cwd=cwd, command=["git", "status", "--short", "--branch"], timeout_seconds=15)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_git_diff(
    cwd: Annotated[
        str,
        Field(description="Relative directory under ~/workspace that contains, or is inside, a git repository."),
    ] = ".",
) -> CommandResult:
    """Run git diff under ~/workspace."""
    return _run_command(cwd=cwd, command=["git", "diff", "--no-ext-diff"], timeout_seconds=15)



@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_exec(
    cwd: Annotated[str, Field(description="Relative working directory under ~/workspace.")],
    argv: Annotated[
        list[str],
        Field(description="Command argv to run with shell=False. The first item is the executable."),
    ],
    timeout_seconds: Annotated[int, Field(ge=1, le=300)] = 60,
    operation_id: Annotated[
        str | None,
        Field(description="Optional idempotency key for retry-safe command execution."),
    ] = None,
) -> WorkspaceExecResult:
    """Run a sandboxed argv-based command under ~/workspace after risk classification.

    Low-risk commands run immediately. Medium/high-risk commands return
    approval_required=true for a future local approval UI. Blocked commands are never executed.
    """
    return _run_workspace_exec(
        cwd=cwd,
        argv=argv,
        timeout_seconds=timeout_seconds,
        operation_id=operation_id,
    )





@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_text_payload(
    text: Annotated[
        str,
        Field(
            max_length=TEXT_PAYLOAD_CHUNK_MAX_CHARS,
            description="One UTF-8 text payload chunk. Store large content in chunks, then reference it from action bundles.",
        ),
    ],
    payload_id: Annotated[
        str | None,
        Field(description="Optional payload id. Omit for the first chunk to create a new id."),
    ] = None,
    chunk_index: Annotated[int, Field(ge=0, le=1000)] = 0,
    total_chunks: Annotated[int, Field(ge=1, le=1000)] = 1,
) -> TextPayloadStageResult:
    """Stage a text payload chunk in the MCP runtime directory.

    This does not modify project files. Action bundles can later reference the
    completed payload via content_ref, old_text_ref, or new_text_ref.
    """
    _ensure_runtime_dirs()
    normalized_id = _new_text_payload_id() if payload_id is None or payload_id.strip() == "" else _normalize_text_payload_id(payload_id)

    result = _stage_text_payload_chunk(
        payload_id=normalized_id,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        text=text,
    )

    _audit(
        "stage_text_payload",
        payload_id=result.payload_id,
        chunk_index=result.chunk_index,
        total_chunks=result.total_chunks,
        chunk_chars=result.chunk_chars,
        total_chars=result.total_chars,
        complete=result.complete,
    )

    return result


def _read_staged_text_payload(payload_ref: str) -> tuple[str, dict[str, object]]:
    ref_info = _validate_text_payload_ref(payload_ref)
    payload_id = str(ref_info["payload_id"])
    total_chunks = int(ref_info["total_chunks"])

    chunks: list[str] = []
    for idx in range(total_chunks):
        chunks.append((_text_payload_dir(payload_id) / f"chunk_{idx:06d}.txt").read_text(encoding="utf-8"))

    return "".join(chunks), ref_info


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_patch_bundle(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative git repository directory under ~/workspace.")],
    patch: Annotated[str | None, Field(description="Unified diff patch text. Prefer patch_ref for large patches.")] = None,
    patch_ref: Annotated[str | None, Field(description="Text payload id containing unified diff patch text.")] = None,
) -> CommandBundleStageResult:
    """Stage a unified diff patch for local approval without modifying project files."""
    if patch is not None and patch_ref is not None:
        raise ValueError("patch and patch_ref cannot both be set.")

    if patch is None and patch_ref is None:
        raise ValueError("patch or patch_ref is required.")

    target = _resolve_workspace_path(cwd)

    if not target.exists():
        raise FileNotFoundError(f"Directory does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

    step_source: dict[str, object]
    if patch_ref is not None:
        patch_text, ref_info = _read_staged_text_payload(patch_ref)
        step_source = {
            "patch_ref": str(ref_info["payload_id"]),
            "patch_chars": int(ref_info["total_chars"]),
            "patch_chunks": int(ref_info["total_chunks"]),
        }
    else:
        assert patch is not None
        patch_text = patch
        step_source = {
            "patch": patch_text,
            "patch_chars": len(patch_text),
        }

    if patch_text.strip() == "":
        raise ValueError("patch cannot be empty.")

    if len(patch_text) > MAX_WRITE_CHARS:
        raise ValueError(f"Patch too large. Max characters: {MAX_WRITE_CHARS}")

    patch_paths = _extract_patch_paths(patch_text)
    _validate_patch_paths(target, patch_paths)

    bundle_id = _new_command_bundle_id()
    now = _now_iso()
    patch_sha256 = _sha256_bytes(patch_text.encode("utf-8"))
    serialized_steps = [
        {
            "type": "apply_patch",
            "name": title,
            "cwd": _relative(target),
            **step_source,
            "patch_sha256": patch_sha256,
            "files": patch_paths,
            "risk": "medium",
            "reason": "Patch apply requires local approval.",
        }
    ]

    record: dict[str, object] = {
        "version": 3,
        "bundle_id": bundle_id,
        "title": title,
        "cwd": _relative(target),
        "status": "pending",
        "risk": "medium",
        "approval_required": True,
        "created_at": now,
        "updated_at": now,
        "steps": serialized_steps,
        "result": None,
        "error": None,
    }

    bundle_path = _command_bundle_path(bundle_id, "pending")
    _write_command_bundle(bundle_path, record)
    _audit(
        "stage_patch_bundle",
        bundle_id=bundle_id,
        cwd=_relative(target),
        title=title,
        patch_sha256=patch_sha256,
        files=patch_paths,
    )

    return CommandBundleStageResult(
        bundle_id=bundle_id,
        title=title,
        cwd=_relative(target),
        status="pending",
        risk="medium",
        approval_required=True,
        path=str(bundle_path),
        review_hint=f"uv run python scripts/command_bundle_runner.py preview {bundle_id}",
        command_count=len(serialized_steps),
    )


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_action_bundle(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative working directory under ~/workspace.")],
    actions: Annotated[list[CommandBundleAction], Field(min_length=1, max_length=30)],
) -> CommandBundleStageResult:
    """Stage file and command actions for local approval.

    Supported action types are command, write_file, append_file, and replace_text.
    Project files are not modified until the local review UI approves and applies
    the staged bundle.
    """
    target = _resolve_workspace_path(cwd)

    if not target.exists():
        raise FileNotFoundError(f"Directory does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

    bundle_id = _new_command_bundle_id()
    serialized_steps, risk, _ = _serialize_action_steps(target, actions)
    now = _now_iso()

    record: dict[str, object] = {
        "version": 2,
        "bundle_id": bundle_id,
        "title": title,
        "cwd": _relative(target),
        "status": "pending",
        "risk": risk,
        "approval_required": True,
        "created_at": now,
        "updated_at": now,
        "steps": serialized_steps,
        "result": None,
        "error": None,
    }

    bundle_path = _command_bundle_path(bundle_id, "pending")
    _write_command_bundle(bundle_path, record)
    _audit(
        "stage_action_bundle",
        bundle_id=bundle_id,
        cwd=_relative(target),
        title=title,
        risk=risk,
        action_count=len(serialized_steps),
    )

    return CommandBundleStageResult(
        bundle_id=bundle_id,
        title=title,
        cwd=_relative(target),
        status="pending",
        risk=risk,
        approval_required=True,
        path=str(bundle_path),
        review_hint=f"uv run python scripts/command_bundle_runner.py preview {bundle_id}",
        command_count=len(serialized_steps),
    )



@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_command_bundle(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative working directory under ~/workspace.")],
    steps: Annotated[list[CommandBundleStep], Field(min_length=1, max_length=20)],
) -> CommandBundleStageResult:
    """Stage a command bundle for local approval instead of executing it in ChatGPT.

    This does not modify project files. It writes a pending command bundle under
    the MCP runtime directory. A local runner can preview/apply/reject it.
    """
    target = _resolve_workspace_path(cwd)

    if not target.exists():
        raise FileNotFoundError(f"Directory does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

    bundle_id = _new_command_bundle_id()
    serialized_steps, risk, _ = _serialize_command_steps(target, steps)
    now = _now_iso()

    record: dict[str, object] = {
        "version": 1,
        "bundle_id": bundle_id,
        "title": title,
        "cwd": _relative(target),
        "status": "pending",
        "risk": risk,
        "approval_required": True,
        "created_at": now,
        "updated_at": now,
        "steps": serialized_steps,
        "result": None,
        "error": None,
    }

    bundle_path = _command_bundle_path(bundle_id, "pending")
    _write_command_bundle(bundle_path, record)
    _audit(
        "stage_command_bundle",
        bundle_id=bundle_id,
        cwd=_relative(target),
        title=title,
        risk=risk,
        command_count=len(serialized_steps),
    )

    return CommandBundleStageResult(
        bundle_id=bundle_id,
        title=title,
        cwd=_relative(target),
        status="pending",
        risk=risk,
        approval_required=True,
        path=str(bundle_path),
        review_hint=f"uv run python scripts/command_bundle_runner.py preview {bundle_id}",
        command_count=len(serialized_steps),
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_command_bundle_status(
    bundle_id: Annotated[str, Field(description="Command bundle id returned by workspace_stage_command_bundle.")],
) -> CommandBundleStatusResult:
    """Return status and result for a staged command bundle."""
    _, record = _find_command_bundle(bundle_id)
    steps = record.get("steps") if isinstance(record.get("steps"), list) else []

    return CommandBundleStatusResult(
        bundle_id=str(record.get("bundle_id", bundle_id)),
        title=str(record.get("title", "")),
        cwd=str(record.get("cwd", "")),
        status=str(record.get("status", "unknown")),
        risk=str(record.get("risk", "unknown")),
        approval_required=bool(record.get("approval_required", False)),
        command_count=len(steps),
        created_at=str(record.get("created_at", "")),
        updated_at=str(record.get("updated_at", "")),
        result=record.get("result") if isinstance(record.get("result"), dict) else None,
        error=record.get("error") if isinstance(record.get("error"), str) else None,
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_list_command_bundles(
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> CommandBundleListResult:
    """List recent command bundles across pending/applied/rejected/failed states."""
    entries: list[CommandBundleListEntry] = []

    for directory in _command_bundle_dirs():
        if not directory.exists():
            continue

        for path in directory.glob("cmd-*.json"):
            try:
                record = _read_json(path)
            except Exception:
                continue

            steps = record.get("steps") if isinstance(record.get("steps"), list) else []
            entries.append(
                CommandBundleListEntry(
                    bundle_id=str(record.get("bundle_id", path.stem)),
                    title=str(record.get("title", "")),
                    cwd=str(record.get("cwd", "")),
                    status=str(record.get("status", directory.name)),
                    risk=str(record.get("risk", "unknown")),
                    command_count=len(steps),
                    updated_at=str(record.get("updated_at", "")),
                )
            )

    entries.sort(key=lambda item: item.updated_at, reverse=True)
    return CommandBundleListResult(entries=entries[:limit], count=min(len(entries), limit))


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_cancel_command_bundle(
    bundle_id: Annotated[str, Field(description="Pending command bundle id to reject.")],
) -> CommandBundleStatusResult:
    """Reject a pending command bundle without executing it."""
    _, record = _find_command_bundle(bundle_id)

    if record.get("status") != "pending":
        raise ValueError(f"Only pending bundles can be cancelled. Current status: {record.get('status')}")

    updated = _move_command_bundle(
        bundle_id,
        "rejected",
        {
            "error": "Cancelled from ChatGPT.",
            "result": None,
        },
    )
    _audit("cancel_command_bundle", bundle_id=bundle_id)

    steps = updated.get("steps") if isinstance(updated.get("steps"), list) else []
    return CommandBundleStatusResult(
        bundle_id=str(updated.get("bundle_id", bundle_id)),
        title=str(updated.get("title", "")),
        cwd=str(updated.get("cwd", "")),
        status=str(updated.get("status", "rejected")),
        risk=str(updated.get("risk", "unknown")),
        approval_required=bool(updated.get("approval_required", False)),
        command_count=len(steps),
        created_at=str(updated.get("created_at", "")),
        updated_at=str(updated.get("updated_at", "")),
        result=updated.get("result") if isinstance(updated.get("result"), dict) else None,
        error=updated.get("error") if isinstance(updated.get("error"), str) else None,
    )



@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_run_profile(
    profile: Annotated[
        Literal[
            "git_status",
            "git_diff",
            "uv_pytest",
            "uv_ruff_check",
            "uv_mypy",
            "go_test",
            "npm_test",
            "npm_lint",
        ],
        Field(description="Approved command profile. Arbitrary shell commands are not accepted."),
    ],
    cwd: Annotated[str, Field(description="Relative directory under ~/workspace.")],
    args: Annotated[list[str], Field(description="Additional safe args for the selected profile.")] = [],
    timeout_seconds: Annotated[int, Field(ge=1, le=180)] = 60,
) -> CommandResult:
    """Run an approved command profile under ~/workspace. This does not accept arbitrary shell commands."""
    target = _resolve_workspace_path(cwd)
    if not target.exists() or not target.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

    safe_args = _validate_command_args(target, args)

    profile_commands: dict[str, list[str]] = {
        "git_status": ["git", "status", "--short", "--branch"],
        "git_diff": ["git", "diff", "--no-ext-diff"],
        "uv_pytest": ["uv", "run", "pytest"],
        "uv_ruff_check": ["uv", "run", "ruff", "check", "."],
        "uv_mypy": ["uv", "run", "mypy", "."],
        "go_test": ["go", "test", "./..."],
        "npm_test": ["npm", "test", "--"],
        "npm_lint": ["npm", "run", "lint", "--"],
    }

    command = profile_commands[profile] + safe_args
    return _run_command(cwd=cwd, command=command, timeout_seconds=timeout_seconds)


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_git_add(
    cwd: Annotated[str, Field(description="Relative git repository directory under ~/workspace.")],
    paths: Annotated[list[str], Field(description="Relative paths to stage. Use ['.'] to stage all allowed files.")],
) -> CommandResult:
    """Stage files with git add under ~/workspace. Paths are validated and secret-like files are blocked."""
    target = _resolve_workspace_path(cwd)

    if not target.exists() or not target.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

    if not paths:
        raise ValueError("paths cannot be empty.")

    safe_paths: list[str] = []

    for path in paths:
        if path == ".":
            safe_paths.append(".")
            continue

        if path.startswith("-"):
            raise ValueError("git add paths cannot be flags.")

        resolved = _resolve_workspace_path(str(Path(cwd) / path))
        if not resolved.exists():
            raise FileNotFoundError(f"Path does not exist: {_relative(resolved)}")

        safe_paths.append(path)

    return _run_command(
        cwd=cwd,
        command=["git", "add", "--"] + safe_paths,
        timeout_seconds=30,
    )


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_git_commit(
    cwd: Annotated[str, Field(description="Relative git repository directory under ~/workspace.")],
    message: Annotated[str, Field(min_length=1, max_length=200, description="Commit message.")],
) -> GitCommitResult:
    """Create a git commit for already staged changes under ~/workspace."""
    if "\n" in message or "\r" in message:
        raise ValueError("Commit message must be a single line in this MVP.")

    result = _run_command(
        cwd=cwd,
        command=["git", "commit", "-m", message],
        timeout_seconds=30,
    )

    _audit(
        "git_commit",
        cwd=result.cwd,
        message=message,
        exit_code=result.exit_code,
    )

    return GitCommitResult(
        cwd=result.cwd,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        truncated=result.truncated,
    )


if __name__ == "__main__":
    _ensure_runtime_dirs()
    _run_server()
