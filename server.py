from __future__ import annotations

import contextlib
import html
import hmac
import json
import os
import secrets
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
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
    _request_key,
    _write_command_bundle,
)
from terminal_bridge.bundle_serialization import (
    _resolve_bundle_file_action_path,
    _serialize_action_steps,
    _serialize_command_steps,
    _serialize_commit_steps,
)
from terminal_bridge.commands import (
    _classify_exec_command,
    _safe_env,
    _validate_command_args,
    _validate_exec_argv,
)
from terminal_bridge.config import (
    AUDIT_LOG,
    BLOCKED_DIR_NAMES,
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
    TEXT_PAYLOAD_CHUNK_MAX_CHARS,
    TEXT_PAYLOAD_MAX_TOTAL_CHARS,
    WORKSPACE_ROOT,
)
from terminal_bridge.models import (
    AuditLogResult,
    BackupListResult,
    BackupRestoreResult,
    CommandBundleAction,
    CommandBundleListResult,
    CommandBundleStageResult,
    CommandBundleStatusResult,
    CommandBundleStep,
    CommandResult,
    DeleteResult,
    FindFilesResult,
    GitCommitResult,
    HandoffEntry,
    HandoffListResult,
    ListResult,
    OperationListResult,
    OperationStatusResult,
    PatchApplyResult,
    PatchFileEntry,
    PatchPreviewResult,
    ProjectSnapshotResult,
    ReadFileResult,
    ReadManyFilesResult,
    ReplaceTextResult,
    RestoreResult,
    SearchTextResult,
    TaskListResult,
    TaskStatusResult,
    TextPayloadStageResult,
    ToolCallListResult,
    ToolCallStatusResult,
    TrashEntry,
    TrashListResult,
    TreeResult,
    WorkspaceExecResult,
    WorkspaceInfo,
    WriteFileResult,
)
from terminal_bridge.handoffs import list_handoffs as _list_handoff_records
from terminal_bridge.handoffs import next_handoff as _next_handoff_record
from terminal_bridge.mcp_tools.readonly import (
    find_files as _readonly_find_files,
    project_snapshot as _readonly_project_snapshot,
    read_many_files as _readonly_read_many_files,
    search_text as _readonly_search_text,
)
from terminal_bridge.mcp_tools.proposals import (
    action_proposal_and_wait as _proposal_action_and_wait,
    command_proposal_and_wait as _proposal_command_and_wait,
    command_proposal_step as _proposal_command_step,
    commit_proposal_and_wait as _proposal_commit_and_wait,
    file_replace_proposal_action as _proposal_file_replace_action,
    file_write_proposal_action as _proposal_file_write_action,
    git_push_proposal as _proposal_git_push,
    patch_proposal_and_wait as _proposal_patch_and_wait,
    validate_git_remote_or_branch as _proposal_validate_git_remote_or_branch,
)
from terminal_bridge.mcp_tools.bundles import (
    cancel_command_bundle as _bundle_cancel_command_bundle,
    command_bundle_status as _bundle_command_bundle_status,
    list_command_bundles as _bundle_list_command_bundles,
    stage_action_bundle_and_wait as _bundle_stage_action_bundle_and_wait,
    stage_command_bundle_and_wait as _bundle_stage_command_bundle_and_wait,
    stage_commit_bundle_and_wait as _bundle_stage_commit_bundle_and_wait,
    stage_patch_bundle_and_wait as _bundle_stage_patch_bundle_and_wait,
    wait_command_bundle_status as _bundle_wait_command_bundle_status,
)
from terminal_bridge.mcp_tools.status import (
    get_operation as _status_get_operation,
    git_diff as _status_git_diff,
    git_status as _status_git_status,
    handoff_entry as _status_handoff_entry,
    list_backups as _status_list_backups,
    list_handoffs as _status_list_handoffs,
    list_operations as _status_list_operations,
    list_tasks as _status_list_tasks,
    list_tool_calls as _status_list_tool_calls,
    list_trash as _status_list_trash,
    next_handoff as _status_next_handoff,
    read_audit_log as _status_read_audit_log,
    recover_last_activity as _status_recover_last_activity,
    task_result as _status_task_result,
    task_status as _status_task_status,
    tool_call_status as _status_tool_call_status,
    transport_git_status_summary as _status_transport_git_status_summary,
    transport_probe as _status_transport_probe,
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
from terminal_bridge.tool_calls import list_tool_calls as _list_tool_call_records
from terminal_bridge.tool_calls import read_tool_call as _read_tool_call_record
from terminal_bridge.trash import (
    _list_trash_entries,
    _move_to_trash,
    _prepare_trash_restore,
    _restore_trash_payload,
)
from terminal_bridge.mcp_runtime import (
    _audit,
    _command_bundle_stage_result,
    _dedupe_command_bundle,
    _ensure_runtime_dirs,
    _record_tool_call,
    _tool_call_status_result,
)
from terminal_bridge.mcp_intents import (
    local_browser_host as _intent_local_browser_host,
    local_pending_url as _intent_local_pending_url,
    local_review_url as _intent_local_review_url,
    sign_intent_payload as _sign_intent_payload_with_secret,
    validate_intent_token as _validate_intent_token_with_secret,
)

allowed_hosts = [
    "127.0.0.1:*",
    "localhost:*",
    "[::1]:*",
]
allowed_origins = [
    "http://127.0.0.1:*",
    "http://localhost:*",
]
if NGROK_HOST:
    allowed_hosts.extend([NGROK_HOST, f"{NGROK_HOST}:*"])
    allowed_origins.extend([f"https://{NGROK_HOST}", f"https://{NGROK_HOST}:*"])

transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=allowed_hosts,
    allowed_origins=allowed_origins,
)

mcp = FastMCP(
    name="Workspace Terminal Bridge",
    instructions=(
        "Provides controlled development access under the configured WORKSPACE_ROOT. "
        "This server rejects absolute paths, path traversal, secret-like files, "
        "and paths outside WORKSPACE_ROOT. It supports reading, safe file writes, "
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


def _internal_tool(**_kwargs: object):
    def decorator(func):
        return func

    return decorator


INTENT_TOKEN_TTL_SECONDS = 15 * 60
INTENT_SECRET_FILE = RUNTIME_ROOT / "intent_hmac_secret"
INTENT_IMPORT_DIR = RUNTIME_ROOT / "intent_imports"


def _intent_secret() -> bytes:
    _ensure_runtime_dirs()
    if INTENT_SECRET_FILE.exists():
        return INTENT_SECRET_FILE.read_bytes()

    secret = secrets.token_bytes(32)
    INTENT_SECRET_FILE.write_bytes(secret)
    try:
        INTENT_SECRET_FILE.chmod(0o600)
    except OSError:
        pass
    return secret


def _sign_intent_payload(payload: dict[str, object]) -> str:
    return _sign_intent_payload_with_secret(payload, _intent_secret())


def _validate_intent_token(token: str, *, now: datetime | None = None) -> dict[str, object]:
    return _validate_intent_token_with_secret(token, _intent_secret(), now=now)


def _local_browser_host(host: str) -> str:
    return _intent_local_browser_host(host)


def _local_review_url(token: str) -> str:
    host = os.getenv("BUNDLE_REVIEW_HOST", "127.0.0.1")
    port = int(os.getenv("BUNDLE_REVIEW_PORT", "8790"))
    return _intent_local_review_url(token, host, port)


def _local_pending_url(bundle_id: str | None = None) -> str:
    host = os.getenv("BUNDLE_REVIEW_HOST", "127.0.0.1")
    port = int(os.getenv("BUNDLE_REVIEW_PORT", "8790"))
    return _intent_local_pending_url(host, port, bundle_id)


def _prepare_intent(intent_type: str, cwd: str, params: dict[str, object], risk: str, summary: str) -> dict[str, object]:
    target = _resolve_workspace_path(cwd)
    if not target.exists():
        raise FileNotFoundError(f"Directory does not exist: {_relative(target)}")
    if not target.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

    created = datetime.now(timezone.utc)
    expires = created + timedelta(seconds=INTENT_TOKEN_TTL_SECONDS)
    payload: dict[str, object] = {
        "intent_type": intent_type,
        "cwd": _relative(target),
        "params": params,
        "created_at": created.isoformat(),
        "expires_at": expires.isoformat(),
        "nonce": secrets.token_hex(12),
    }
    token = _sign_intent_payload(payload)
    return {
        "ok": True,
        "intent_type": intent_type,
        "risk": risk,
        "summary": summary,
        "local_review_url": _local_review_url(token),
        "local_pending_url": _local_pending_url(),
        "expires_at": payload["expires_at"],
        "diagnosis": "Open the local URL to import this intent into the pending bundle UI.",
    }


def _intent_command_step_for_check(check: str) -> CommandBundleStep:
    mapping = {
        "git_status": CommandBundleStep(name="Git status", argv=["git", "status", "--short", "--branch"], timeout_seconds=30),
        "py_compile": CommandBundleStep(
            name="Python compile check",
            argv=["bash", "-lc", "uv run python -m py_compile server.py terminal_bridge/*.py"],
            timeout_seconds=120,
        ),
        "unit_tests": CommandBundleStep(
            name="Unit tests",
            argv=["uv", "run", "python", "-m", "unittest", "discover", "-s", "tests"],
            timeout_seconds=120,
        ),
        "check_all": CommandBundleStep(name="Full local check", argv=["bash", "scripts/check_all.sh"], timeout_seconds=240),
    }
    try:
        return mapping[check]
    except KeyError as exc:
        raise ValueError(f"Unknown check intent: {check}") from exc


def _intent_command_step_for_dev_session(action: str) -> CommandBundleStep:
    mapping = {
        "status": CommandBundleStep(name="Dev session status", argv=["bash", "scripts/dev_session.sh", "status"], timeout_seconds=30),
        "doctor": CommandBundleStep(name="Dev session doctor", argv=["bash", "scripts/dev_session.sh", "doctor"], timeout_seconds=60),
        "restart_mcp": CommandBundleStep(name="Restart MCP service", argv=["bash", "scripts/dev_session.sh", "restart", "mcp"], timeout_seconds=60),
        "restart_session": CommandBundleStep(name="Restart full dev session", argv=["bash", "scripts/dev_session.sh", "restart-session"], timeout_seconds=60),
    }
    try:
        return mapping[action]
    except KeyError as exc:
        raise ValueError(f"Unknown dev session intent: {action}") from exc


def _intent_changed_paths(cwd: str, include_untracked: bool) -> list[str]:
    target = _resolve_workspace_path(cwd)
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(target),
        env=_safe_env(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
        shell=False,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git status failed: {completed.stderr or completed.stdout}")

    paths: list[str] = []
    for line in completed.stdout.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if status == "??" and not include_untracked:
            continue
        paths.append(path)

    return paths


def _intent_preview(payload: dict[str, object]) -> dict[str, object]:
    intent_type = str(payload.get("intent_type", ""))
    cwd = str(payload.get("cwd", "."))
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    if intent_type == "check":
        check = str(params.get("check", ""))
        step = _intent_command_step_for_check(check)
        return {"intent_type": intent_type, "cwd": cwd, "summary": f"Prepare check bundle: {check}", "steps": [step.model_dump()]}
    if intent_type == "dev_session":
        action = str(params.get("action", ""))
        step = _intent_command_step_for_dev_session(action)
        return {"intent_type": intent_type, "cwd": cwd, "summary": f"Prepare dev session bundle: {action}", "steps": [step.model_dump()]}
    if intent_type == "commit_current_changes":
        include_untracked = bool(params.get("include_untracked", False))
        paths = _intent_changed_paths(cwd, include_untracked)
        return {
            "intent_type": intent_type,
            "cwd": cwd,
            "summary": f"Prepare commit bundle: {params.get('message', '')}",
            "paths": paths,
            "include_untracked": include_untracked,
        }
    raise ValueError(f"Unknown intent_type: {intent_type}")


def _approve_intent(payload: dict[str, object]) -> CommandBundleStageResult:
    intent_type = str(payload.get("intent_type", ""))
    cwd = str(payload.get("cwd", "."))
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    if intent_type == "check":
        check = str(params.get("check", ""))
        step = _intent_command_step_for_check(check)
        return workspace_stage_command_bundle(title=f"Check: {check} ({_intent_nonce(payload)[:8]})", cwd=cwd, steps=[step])
    if intent_type == "dev_session":
        action = str(params.get("action", ""))
        step = _intent_command_step_for_dev_session(action)
        return workspace_stage_command_bundle(title=f"Dev session: {action} ({_intent_nonce(payload)[:8]})", cwd=cwd, steps=[step])
    if intent_type == "commit_current_changes":
        include_untracked = bool(params.get("include_untracked", False))
        paths = _intent_changed_paths(cwd, include_untracked)
        if not paths:
            raise ValueError("No changes to commit.")
        return workspace_stage_commit_bundle(cwd=cwd, paths=paths, message=str(params.get("message", "")), precheck_commands=None)
    raise ValueError(f"Unknown intent_type: {intent_type}")


def _intent_nonce(payload: dict[str, object]) -> str:
    nonce = str(payload.get("nonce", ""))
    if not nonce or any(ch not in "0123456789abcdef" for ch in nonce.lower()):
        raise ValueError("Intent token is missing a valid nonce.")
    return nonce


def _intent_import_path(payload: dict[str, object]) -> Path:
    return INTENT_IMPORT_DIR / f"{_intent_nonce(payload)}.json"


def _intent_result_from_import(record: dict[str, object]) -> CommandBundleStageResult | None:
    bundle_id = record.get("bundle_id")
    if not isinstance(bundle_id, str):
        return None
    try:
        path, bundle_record = _find_command_bundle(bundle_id)
    except FileNotFoundError:
        return None
    return _command_bundle_stage_result(path, bundle_record)


def _import_intent(payload: dict[str, object]) -> CommandBundleStageResult:
    import_path = _intent_import_path(payload)
    if import_path.exists():
        try:
            imported = _intent_result_from_import(_read_json(import_path))
        except Exception:
            imported = None
        if imported is not None:
            return imported

    result = _approve_intent(payload)
    record = {
        "nonce": _intent_nonce(payload),
        "intent_type": str(payload.get("intent_type", "")),
        "cwd": str(payload.get("cwd", ".")),
        "bundle_id": result.bundle_id,
        "imported_at": _now_iso(),
    }
    INTENT_IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(import_path, record)
    _audit(
        "intent_imported",
        intent_type=record["intent_type"],
        nonce=record["nonce"],
        bundle_id=result.bundle_id,
        cwd=record["cwd"],
        risk=result.risk,
    )
    return result


def _intent_response(
    cwd: str,
    intent_type: str,
    params: dict[str, object],
    risk: str,
    summary: str,
) -> dict[str, object]:
    return _prepare_intent(intent_type, cwd, params, risk, summary)


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
    return _status_task_result(record)


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


def _intent_preview_html(token: str, payload: dict[str, object], preview: dict[str, object]) -> str:
    escaped_token = html.escape(token, quote=True)
    title = html.escape(str(preview.get("summary", "Intent preview")))
    body = html.escape(json.dumps(preview, ensure_ascii=False, indent=2))
    expires_at = html.escape(str(payload.get("expires_at", "")))
    import_url = f"/review-intent?token={escaped_token}"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Intent review</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 32px; max-width: 920px; }}
    pre {{ background: #f6f8fa; padding: 16px; overflow: auto; }}
    button {{ padding: 8px 12px; }}
  </style>
</head>
<body>
  <h1>Intent review</h1>
  <p>{title}</p>
  <p>Expires: <code>{expires_at}</code></p>
  <pre>{body}</pre>
  <p><a href="{import_url}">Import into pending bundle UI</a></p>
</body>
</html>"""


def _intent_approved_html(result: CommandBundleStageResult) -> str:
    summary = {
        "bundle_id": result.bundle_id,
        "status": result.status,
        "risk": result.risk,
        "command_count": result.command_count,
        "next_tool": "workspace_wait_command_bundle_status",
    }
    body = html.escape(json.dumps(summary, ensure_ascii=False, indent=2))
    bundle_id = html.escape(result.bundle_id)
    pending_url = html.escape(_local_pending_url(result.bundle_id), quote=True)
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Intent approved</title></head>
<body>
  <h1>Command bundle imported</h1>
  <p>Bundle: <code>{bundle_id}</code></p>
  <p>Status: <code>{html.escape(result.status)}</code></p>
  <p><a href="{pending_url}">Open pending bundle UI</a></p>
  <p>Next tool: <code>workspace_wait_command_bundle_status</code></p>
  <p>Copyable JSON summary:</p>
  <pre>{body}</pre>
</body>
</html>"""


async def _review_intent_endpoint(request: object):
    from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse

    token = str(request.query_params.get("token", ""))  # type: ignore[attr-defined]
    try:
        payload = _validate_intent_token(token)
        result = _import_intent(payload)
        pending_url = _local_pending_url(result.bundle_id)
    except Exception as exc:
        return PlainTextResponse(f"Intent import failed: {type(exc).__name__}: {exc}", status_code=400)
    if pending_url:
        return RedirectResponse(pending_url, status_code=303)
    return HTMLResponse(_intent_approved_html(result))


async def _preview_intent_endpoint(request: object):
    from starlette.responses import HTMLResponse, PlainTextResponse

    token = str(request.query_params.get("token", ""))  # type: ignore[attr-defined]
    try:
        payload = _validate_intent_token(token)
        preview = _intent_preview(payload)
    except Exception as exc:
        return PlainTextResponse(f"Invalid intent: {type(exc).__name__}: {exc}", status_code=400)
    return HTMLResponse(_intent_preview_html(token, payload, preview))


async def _approve_intent_endpoint(request: object):
    from starlette.responses import HTMLResponse, PlainTextResponse

    token = str(request.query_params.get("token", ""))  # type: ignore[attr-defined]
    try:
        payload = _validate_intent_token(token)
        result = _import_intent(payload)
    except Exception as exc:
        return PlainTextResponse(f"Intent approval failed: {type(exc).__name__}: {exc}", status_code=400)
    return HTMLResponse(_intent_approved_html(result))


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
        raise SystemExit(
            "MCP_ACCESS_TOKEN is required. Run `woojae setup` or "
            "`scripts/dev_session.sh configure` before starting the MCP server."
        )

    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    import uvicorn

    protected_mcp_app = AccessTokenMiddleware(mcp.streamable_http_app(), MCP_ACCESS_TOKEN)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp.session_manager.run():
            yield

    app = Starlette(
        routes=[
            Route("/review-intent", _review_intent_endpoint, methods=["GET"]),
            Route("/review-intent/preview", _preview_intent_endpoint, methods=["GET"]),
            Route("/review-intent/approve", _approve_intent_endpoint, methods=["POST"]),
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


DEFAULT_PUBLIC_MCP_TOOLS: tuple[str, ...] = (
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
    "workspace_transport_probe",
    "workspace_prepare_check_intent",
    "workspace_prepare_commit_current_changes_intent",
    "workspace_prepare_dev_session_intent",
    "workspace_read_audit_log",
    "workspace_recover_last_activity",
    "workspace_next_handoff",
    "workspace_list_handoffs",
    "workspace_list_tool_calls",
    "workspace_tool_call_status",
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
    "workspace_propose_command_and_wait",
    "workspace_propose_file_write_and_wait",
    "workspace_propose_file_replace_and_wait",
    "workspace_propose_patch_and_wait",
    "workspace_propose_git_commit_and_wait",
    "workspace_propose_git_push_and_wait",
    "workspace_command_bundle_status",
    "workspace_wait_command_bundle_status",
    "workspace_list_command_bundles",
    "workspace_cancel_command_bundle",
)

DIRECT_MUTATION_MCP_TOOLS: tuple[str, ...] = (
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
)


def _workspace_info_tools() -> list[str]:
    tools = list(DEFAULT_PUBLIC_MCP_TOOLS)

    if MCP_EXPOSE_DIRECT_MUTATION_TOOLS:
        tools.extend(DIRECT_MUTATION_MCP_TOOLS)

    return tools


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_info() -> WorkspaceInfo:
    """Return basic information about the configured WORKSPACE_ROOT and enabled tools."""
    return WorkspaceInfo(
        root=str(WORKSPACE_ROOT),
        mode=(
            "development_mvp_with_direct_mutation_tools"
            if MCP_EXPOSE_DIRECT_MUTATION_TOOLS
            else "development_mvp_bundle_first"
        ),
        runtime_root=str(RUNTIME_ROOT),
        tools=_workspace_info_tools(),
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
                "Relative directory path under the configured WORKSPACE_ROOT. "
                "Use '.' for the workspace root. Absolute paths and '..' are rejected."
            )
        ),
    ] = ".",
    include_hidden: Annotated[
        bool,
        Field(description="Whether to include hidden dotfiles, except blocked secret-like files."),
    ] = False,
) -> ListResult:
    """List files and directories under the configured WORKSPACE_ROOT."""
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
    path: Annotated[str, Field(description="Relative directory path under the configured WORKSPACE_ROOT.")] = ".",
    max_depth: Annotated[int, Field(ge=1, le=5)] = 2,
    max_entries: Annotated[int, Field(ge=1, le=300)] = 120,
) -> TreeResult:
    """Return a compact tree view under the configured WORKSPACE_ROOT."""
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
    path: Annotated[str, Field(description="Relative file path under the configured WORKSPACE_ROOT.")],
    offset: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int, Field(ge=1, le=160_000)] = 40_000,
) -> ReadFileResult:
    """Read a UTF-8 text file under the configured WORKSPACE_ROOT."""
    return _read_workspace_file(path, offset, limit)


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_create_directory(
    path: Annotated[str, Field(description="Relative directory path under the configured WORKSPACE_ROOT.")],
) -> WriteFileResult:
    """Create a directory under the configured WORKSPACE_ROOT."""
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
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_write_file(
    path: Annotated[str, Field(description="Relative file path under the configured WORKSPACE_ROOT.")],
    content: Annotated[str, Field(description="UTF-8 text content to write.")],
    overwrite: Annotated[bool, Field(description="Whether to overwrite an existing file.")] = False,
    create_parent_dirs: Annotated[bool, Field(description="Whether to create missing parent directories.")] = True,
    expected_sha256: Annotated[str | None, Field(description="Optional current sha256 guard for overwrites.")] = None,
    operation_id: Annotated[str | None, Field(description="Optional idempotency key for retry-safe writes.")] = None,
) -> WriteFileResult:
    """Create or overwrite a UTF-8 text file under the configured WORKSPACE_ROOT. Existing files are backed up before overwrite."""
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
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_append_file(
    path: Annotated[str, Field(description="Relative file path under the configured WORKSPACE_ROOT.")],
    content: Annotated[str, Field(description="UTF-8 text content to append.")],
    create_if_missing: Annotated[bool, Field(description="Create the file if it does not exist.")] = True,
) -> WriteFileResult:
    """Append UTF-8 text to a file under the configured WORKSPACE_ROOT. Existing files are backed up before append."""
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
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_replace_text(
    path: Annotated[str, Field(description="Relative UTF-8 file path under the configured WORKSPACE_ROOT.")],
    old_text: Annotated[str, Field(description="Exact text to find.")],
    new_text: Annotated[str, Field(description="Replacement text.")],
    replace_all: Annotated[bool, Field(description="Replace all occurrences instead of only the first.")] = False,
    expected_sha256: Annotated[str | None, Field(description="Optional current sha256 guard.")] = None,
    operation_id: Annotated[str | None, Field(description="Optional idempotency key for retry-safe replacements.")] = None,
) -> ReplaceTextResult:
    """Replace exact text in a UTF-8 file under the configured WORKSPACE_ROOT. The file is backed up before modification."""
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
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_soft_delete(
    path: Annotated[str, Field(description="Relative file or directory path under the configured WORKSPACE_ROOT.")],
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
        "readOnlyHint": True,
        "destructiveHint": False,
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
    return _status_read_audit_log(_ensure_runtime_dirs, AUDIT_LOG, limit, event)


def _transport_git_status_summary(cwd: str) -> dict[str, object]:
    return _status_transport_git_status_summary(cwd)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_transport_probe(
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")] = ".",
    include_git_status: Annotated[bool, Field(description="Whether to include a compact git status summary.")] = True,
) -> dict[str, object]:
    """Quickly confirm that the MCP request reached this server."""
    return _record_tool_call(
        "workspace_transport_probe",
        {"cwd": cwd, "include_git_status": include_git_status},
        lambda: _workspace_transport_probe_impl(cwd, include_git_status),
    )


def _workspace_transport_probe_impl(cwd: str, include_git_status: bool) -> dict[str, object]:
    return _status_transport_probe(
        _ensure_runtime_dirs,
        _list_tool_call_records,
        _command_bundle_dirs,
        WORKSPACE_ROOT,
        RUNTIME_ROOT,
        cwd,
        include_git_status,
    )


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_prepare_check_intent(
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
    check: Annotated[Literal["git_status", "py_compile", "unit_tests", "check_all"], Field(description="Check bundle to prepare.")],
) -> dict[str, object]:
    """Prepare a signed local review URL for a check command bundle without creating it."""
    return _record_tool_call(
        "workspace_prepare_check_intent",
        {"cwd": cwd, "check": check},
        lambda: _intent_response(cwd, "check", {"check": check}, "low", f"Prepare check bundle: {check}"),
    )


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_prepare_commit_current_changes_intent(
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
    message: Annotated[str, Field(min_length=1, max_length=200, description="Single-line commit message.")],
    include_untracked: Annotated[bool, Field(description="Whether approval should include untracked files.")] = False,
) -> dict[str, object]:
    """Prepare a signed local review URL for committing current changes without creating a bundle."""
    return _record_tool_call(
        "workspace_prepare_commit_current_changes_intent",
        {"cwd": cwd, "message": message, "include_untracked": include_untracked},
        lambda: _intent_response(
            cwd,
            "commit_current_changes",
            {"message": message, "include_untracked": include_untracked},
            "medium",
            "Prepare commit bundle for current changes.",
        ),
    )


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_prepare_dev_session_intent(
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
    action: Annotated[Literal["status", "doctor", "restart_mcp", "restart_session"], Field(description="Dev session action to prepare.")],
) -> dict[str, object]:
    """Prepare a signed local review URL for a dev-session command bundle without creating it."""
    risk = "low" if action in {"status", "doctor"} else "medium"
    return _record_tool_call(
        "workspace_prepare_dev_session_intent",
        {"cwd": cwd, "action": action},
        lambda: _intent_response(cwd, "dev_session", {"action": action}, risk, f"Prepare dev session bundle: {action}"),
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_recover_last_activity(
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")] = ".",
    bundle_limit: Annotated[int, Field(ge=1, le=20, description="Maximum recent command bundles to summarize.")] = 5,
    audit_limit: Annotated[int, Field(ge=1, le=50, description="Maximum recent audit events to summarize.")] = 10,
) -> dict[str, object]:
    """Return a compact recovery snapshot after an interrupted ChatGPT tool call."""
    return _record_tool_call(
        "workspace_recover_last_activity",
        {"cwd": cwd, "bundle_limit": bundle_limit, "audit_limit": audit_limit},
        lambda: _workspace_recover_last_activity_impl(cwd, bundle_limit, audit_limit),
    )


def _workspace_recover_last_activity_impl(cwd: str, bundle_limit: int, audit_limit: int) -> dict[str, object]:
    return _status_recover_last_activity(
        _ensure_runtime_dirs,
        _run_command,
        _command_bundle_dirs,
        _read_json,
        lambda limit: workspace_read_audit_log(limit=limit),
        cwd,
        bundle_limit,
        audit_limit,
    )


def _handoff_entry(record: dict[str, object]) -> HandoffEntry:
    return _status_handoff_entry(record)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_next_handoff() -> HandoffEntry | None:
    """Return the latest local bundle handoff, if one exists."""
    return _status_next_handoff(_next_handoff_record)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_list_handoffs(
    limit: Annotated[int, Field(ge=1, le=100, description="Maximum handoff records to return.")] = 20,
) -> HandoffListResult:
    """List recent local bundle handoffs, newest first."""
    return _status_list_handoffs(_list_handoff_records, limit)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_list_tool_calls(
    limit: Annotated[int, Field(ge=1, le=200, description="Maximum tool call records to return.")] = 50,
) -> ToolCallListResult:
    """List recent instrumented MCP tool calls, newest first."""
    return _status_list_tool_calls(_list_tool_call_records, _tool_call_status_result, limit)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_tool_call_status(
    call_id: Annotated[str, Field(description="Tool call id returned by workspace_list_tool_calls.")],
) -> ToolCallStatusResult:
    """Return one instrumented MCP tool call record."""
    return _status_tool_call_status(_read_tool_call_record, _tool_call_status_result, call_id)


@_internal_tool(
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
    return _status_get_operation(_normalize_operation_id, _read_operation_record, operation_id)


@_internal_tool(
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
    return _status_list_operations(_ensure_runtime_dirs, OPERATION_DIR, limit)


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
    return _status_list_backups(_ensure_runtime_dirs, _list_backup_entries, limit)


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
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


@_internal_tool(
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
    return _status_list_trash(_ensure_runtime_dirs, _list_trash_entries, limit)


@_direct_mutation_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_move_to_trash(
    path: Annotated[str, Field(description="Relative file or directory path under the configured WORKSPACE_ROOT.")],
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
    path: Annotated[str, Field(description="Relative directory path under the configured WORKSPACE_ROOT.")] = ".",
    pattern: Annotated[str, Field(description="fnmatch pattern such as '*.py' or '*server*'.")] = "*",
    include_files: Annotated[bool, Field(description="Whether to include files.")] = True,
    include_directories: Annotated[bool, Field(description="Whether to include directories.")] = False,
    max_entries: Annotated[int, Field(ge=1, le=300, description="Maximum matching entries to return.")] = 100,
) -> FindFilesResult:
    """Find files or directories under the configured WORKSPACE_ROOT using a safe fnmatch pattern."""
    return _readonly_find_files(
        path=path,
        pattern=pattern,
        include_files=include_files,
        include_directories=include_directories,
        max_entries=max_entries,
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
    path: Annotated[str, Field(description="Relative directory path under the configured WORKSPACE_ROOT.")] = ".",
    file_glob: Annotated[str, Field(description="File glob such as '*.py' or '*'.")] = "*",
    case_sensitive: Annotated[bool, Field(description="Whether matching is case-sensitive.")] = False,
    max_matches: Annotated[int, Field(ge=1, le=300, description="Maximum matches to return.")] = 100,
    max_file_bytes: Annotated[int, Field(ge=1, le=1_000_000, description="Maximum bytes per file to scan.")] = 500_000,
) -> SearchTextResult:
    """Search text files under the configured WORKSPACE_ROOT for a plain text query."""
    return _readonly_search_text(
        query=query,
        path=path,
        file_glob=file_glob,
        case_sensitive=case_sensitive,
        max_matches=max_matches,
        max_file_bytes=max_file_bytes,
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
    paths: Annotated[list[str], Field(description="Relative file paths under the configured WORKSPACE_ROOT.")],
    limit_per_file: Annotated[int, Field(ge=1, le=80_000, description="Maximum characters per file.")] = 20_000,
    total_limit: Annotated[int, Field(ge=1, le=320_000, description="Maximum total characters to return.")] = 100_000,
) -> ReadManyFilesResult:
    """Read multiple UTF-8 text files under the configured WORKSPACE_ROOT with per-file and total limits."""
    return _readonly_read_many_files(
        paths=paths,
        limit_per_file=limit_per_file,
        total_limit=total_limit,
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_project_snapshot(
    path: Annotated[str, Field(description="Relative project directory under the configured WORKSPACE_ROOT.")] = ".",
    max_depth: Annotated[int, Field(ge=1, le=5, description="Tree depth.")] = 2,
    max_entries: Annotated[int, Field(ge=1, le=300, description="Tree entries.")] = 120,
) -> ProjectSnapshotResult:
    """Return a compact project snapshot: tree, key files, and git status."""
    return _readonly_project_snapshot(
        run_command=_run_command,
        path=path,
        max_depth=max_depth,
        max_entries=max_entries,
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
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
    return _status_task_status(_normalize_task_id, _read_task, task_id)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
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
        "readOnlyHint": True,
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
        "readOnlyHint": True,
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
    return _status_list_tasks(_ensure_runtime_dirs, _list_task_paths, limit)


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
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")] = ".",
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
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_apply_patch(
    patch: Annotated[str, Field(description="Unified diff patch text to apply with git apply.")],
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")] = ".",
    operation_id: Annotated[str | None, Field(description="Optional idempotency key for retry-safe patch application.")] = None,
    timeout_seconds: Annotated[int, Field(ge=1, le=120)] = 30,
    return_diff: Annotated[bool, Field(description="Whether to include git diff in the tool result. Keep false for large changes.")] = False,
    diff_max_chars: Annotated[int, Field(ge=1, le=20_000, description="Maximum diff characters to return when return_diff is true.")] = 4_000,
) -> PatchApplyResult:
    """Apply a unified diff patch under the configured WORKSPACE_ROOT after git apply --check. Existing files are backed up first."""
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
        Field(description="Relative directory under the configured WORKSPACE_ROOT that contains, or is inside, a git repository."),
    ] = ".",
) -> CommandResult:
    """Run git status under the configured WORKSPACE_ROOT."""
    return _status_git_status(_run_command, cwd)


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
        Field(description="Relative directory under the configured WORKSPACE_ROOT that contains, or is inside, a git repository."),
    ] = ".",
) -> CommandResult:
    """Run git diff under the configured WORKSPACE_ROOT."""
    return _status_git_diff(_run_command, cwd)



@_direct_mutation_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_exec(
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
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
    """Run a sandboxed argv-based command under the configured WORKSPACE_ROOT after risk classification.

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
        "readOnlyHint": True,
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


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_patch_bundle(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
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

    relative_cwd = _relative(target)
    patch_sha256 = _sha256_bytes(patch_text.encode("utf-8"))
    request_key = _request_key(
        {
            "kind": "patch_bundle",
            "title": title,
            "cwd": relative_cwd,
            "patch_sha256": patch_sha256,
            "patch_paths": patch_paths,
        }
    )
    deduped = _dedupe_command_bundle(request_key, kind="patch_bundle", title=title)
    if deduped is not None:
        return deduped

    bundle_id = _new_command_bundle_id()
    now = _now_iso()
    serialized_steps = [
        {
            "type": "apply_patch",
            "name": title,
            "cwd": relative_cwd,
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
        "cwd": relative_cwd,
        "status": "pending",
        "risk": "medium",
        "approval_required": True,
        "created_at": now,
        "updated_at": now,
        "steps": serialized_steps,
        "result": None,
        "error": None,
        "request_key": request_key,
        "request_key_version": 1,
        "duplicate_of": None,
    }

    bundle_path = _command_bundle_path(bundle_id, "pending")
    _write_command_bundle(bundle_path, record)
    _audit(
        "stage_patch_bundle",
        bundle_id=bundle_id,
        cwd=relative_cwd,
        title=title,
        patch_sha256=patch_sha256,
        files=patch_paths,
        request_key=request_key,
    )

    return CommandBundleStageResult(
        bundle_id=bundle_id,
        title=title,
        cwd=relative_cwd,
        status="pending",
        risk="medium",
        approval_required=True,
        path=str(bundle_path),
        review_hint=f"uv run python scripts/command_bundle_runner.py preview {bundle_id}",
        command_count=len(serialized_steps),
    )


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_action_bundle(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
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

    serialized_steps, risk, _ = _serialize_action_steps(target, actions)
    relative_cwd = _relative(target)
    request_key = _request_key(
        {
            "kind": "action_bundle",
            "title": title,
            "cwd": relative_cwd,
            "actions": actions,
            "steps": serialized_steps,
        }
    )
    deduped = _dedupe_command_bundle(request_key, kind="action_bundle", title=title)
    if deduped is not None:
        return deduped

    bundle_id = _new_command_bundle_id()
    now = _now_iso()

    record: dict[str, object] = {
        "version": 2,
        "bundle_id": bundle_id,
        "title": title,
        "cwd": relative_cwd,
        "status": "pending",
        "risk": risk,
        "approval_required": True,
        "created_at": now,
        "updated_at": now,
        "steps": serialized_steps,
        "result": None,
        "error": None,
        "request_key": request_key,
        "request_key_version": 1,
        "duplicate_of": None,
    }

    bundle_path = _command_bundle_path(bundle_id, "pending")
    _write_command_bundle(bundle_path, record)
    _audit(
        "stage_action_bundle",
        bundle_id=bundle_id,
        cwd=relative_cwd,
        title=title,
        risk=risk,
        action_count=len(serialized_steps),
        request_key=request_key,
    )

    return CommandBundleStageResult(
        bundle_id=bundle_id,
        title=title,
        cwd=relative_cwd,
        status="pending",
        risk=risk,
        approval_required=True,
        path=str(bundle_path),
        review_hint=f"uv run python scripts/command_bundle_runner.py preview {bundle_id}",
        command_count=len(serialized_steps),
    )


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_commit_bundle(
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
    paths: Annotated[
        list[str],
        Field(min_length=1, max_length=100, description="Relative paths to stage and commit. Use ['.'] with care."),
    ],
    message: Annotated[str, Field(min_length=1, max_length=200, description="Single-line commit message.")],
    precheck_commands: Annotated[
        list[CommandBundleStep] | None,
        Field(description="Optional low-risk commands to run before git add/commit."),
    ] = None,
) -> CommandBundleStageResult:
    """Stage a git add/commit workflow for local approval without executing it in ChatGPT."""
    target = _resolve_workspace_path(cwd)

    if not target.exists():
        raise FileNotFoundError(f"Directory does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {_relative(target)}")

    serialized_steps, risk, safe_paths, commit_message = _serialize_commit_steps(
        target,
        paths,
        message,
        precheck_commands,
    )
    relative_cwd = _relative(target)
    request_key = _request_key(
        {
            "kind": "commit_bundle",
            "cwd": relative_cwd,
            "paths": safe_paths,
            "message": commit_message,
            "precheck_commands": precheck_commands,
        }
    )
    deduped = _dedupe_command_bundle(request_key, kind="commit_bundle", title=f"Commit: {commit_message[:120]}")
    if deduped is not None:
        return deduped

    bundle_id = _new_command_bundle_id()
    now = _now_iso()
    title = f"Commit: {commit_message[:120]}"

    record: dict[str, object] = {
        "version": 4,
        "bundle_id": bundle_id,
        "title": title,
        "cwd": relative_cwd,
        "status": "pending",
        "risk": risk,
        "approval_required": True,
        "created_at": now,
        "updated_at": now,
        "steps": serialized_steps,
        "result": None,
        "error": None,
        "request_key": request_key,
        "request_key_version": 1,
        "duplicate_of": None,
    }

    bundle_path = _command_bundle_path(bundle_id, "pending")
    _write_command_bundle(bundle_path, record)
    _audit(
        "stage_commit_bundle",
        bundle_id=bundle_id,
        cwd=relative_cwd,
        risk=risk,
        path_count=len(safe_paths),
        command_count=len(serialized_steps),
        request_key=request_key,
    )

    return CommandBundleStageResult(
        bundle_id=bundle_id,
        title=title,
        cwd=relative_cwd,
        status="pending",
        risk=risk,
        approval_required=True,
        path=str(bundle_path),
        review_hint=f"uv run python scripts/command_bundle_runner.py preview {bundle_id}",
        command_count=len(serialized_steps),
    )


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_command_bundle(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
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

    serialized_steps, risk, _ = _serialize_command_steps(target, steps)
    relative_cwd = _relative(target)
    request_key = _request_key(
        {
            "kind": "command_bundle",
            "title": title,
            "cwd": relative_cwd,
            "steps": serialized_steps,
        }
    )
    deduped = _dedupe_command_bundle(request_key, kind="command_bundle", title=title)
    if deduped is not None:
        return deduped

    bundle_id = _new_command_bundle_id()
    now = _now_iso()

    record: dict[str, object] = {
        "version": 1,
        "bundle_id": bundle_id,
        "title": title,
        "cwd": relative_cwd,
        "status": "pending",
        "risk": risk,
        "approval_required": True,
        "created_at": now,
        "updated_at": now,
        "steps": serialized_steps,
        "result": None,
        "error": None,
        "request_key": request_key,
        "request_key_version": 1,
        "duplicate_of": None,
    }

    bundle_path = _command_bundle_path(bundle_id, "pending")
    _write_command_bundle(bundle_path, record)
    _audit(
        "stage_command_bundle",
        bundle_id=bundle_id,
        cwd=relative_cwd,
        title=title,
        risk=risk,
        command_count=len(serialized_steps),
        request_key=request_key,
    )

    return CommandBundleStageResult(
        bundle_id=bundle_id,
        title=title,
        cwd=relative_cwd,
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
    return _record_tool_call(
        "workspace_command_bundle_status",
        {"bundle_id": bundle_id},
        lambda: _workspace_command_bundle_status_impl(bundle_id),
    )


def _workspace_command_bundle_status_impl(bundle_id: str) -> CommandBundleStatusResult:
    return _bundle_command_bundle_status(_find_command_bundle, bundle_id)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def workspace_wait_command_bundle_status(
    bundle_id: Annotated[str, Field(description="Command bundle id returned by workspace_stage_command_bundle.")],
    timeout_seconds: Annotated[int, Field(ge=1, le=45, description="Maximum seconds to wait for pending status to change.")] = 30,
    poll_interval_seconds: Annotated[float, Field(ge=0.2, le=5.0, description="Seconds between status checks.")] = 1.0,
) -> CommandBundleStatusResult:
    """Wait briefly for a pending command bundle to be approved, rejected, applied, or failed.

    This tool is read-only. It never approves, rejects, or executes bundles. It only polls
    the existing bundle status so ChatGPT can continue promptly after a local approval.
    """
    return _record_tool_call(
        "workspace_wait_command_bundle_status",
        {
            "bundle_id": bundle_id,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        },
        lambda: _workspace_wait_command_bundle_status_impl(bundle_id, timeout_seconds, poll_interval_seconds),
    )


def _workspace_wait_command_bundle_status_impl(
    bundle_id: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> CommandBundleStatusResult:
    return _bundle_wait_command_bundle_status(
        _find_command_bundle,
        bundle_id,
        timeout_seconds,
        poll_interval_seconds,
    )


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_submit_command_bundle(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
    steps: Annotated[list[CommandBundleStep], Field(min_length=1, max_length=20)],
) -> CommandBundleStageResult:
    """Submit a command bundle for local approval and return immediately."""
    return _record_tool_call(
        "workspace_submit_command_bundle",
        {"title": title, "cwd": cwd, "steps": steps},
        lambda: _workspace_submit_command_bundle_impl(title, cwd, steps),
    )


def _workspace_submit_command_bundle_impl(
    title: str,
    cwd: str,
    steps: list[CommandBundleStep],
) -> CommandBundleStageResult:
    return workspace_stage_command_bundle(title=title, cwd=cwd, steps=steps)


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_submit_patch_bundle(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
    patch: Annotated[str | None, Field(description="Unified diff patch text. Prefer patch_ref for large patches.")] = None,
    patch_ref: Annotated[str | None, Field(description="Text payload id containing unified diff patch text.")] = None,
) -> CommandBundleStageResult:
    """Submit a patch bundle for local approval and return immediately."""
    return _record_tool_call(
        "workspace_submit_patch_bundle",
        {"title": title, "cwd": cwd, "patch": patch, "patch_ref": patch_ref},
        lambda: _workspace_submit_patch_bundle_impl(title, cwd, patch, patch_ref),
    )


def _workspace_submit_patch_bundle_impl(
    title: str,
    cwd: str,
    patch: str | None,
    patch_ref: str | None,
) -> CommandBundleStageResult:
    return workspace_stage_patch_bundle(title=title, cwd=cwd, patch=patch, patch_ref=patch_ref)


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_submit_action_bundle(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
    actions: Annotated[list[CommandBundleAction], Field(min_length=1, max_length=30)],
) -> CommandBundleStageResult:
    """Submit an action bundle for local approval and return immediately."""
    return _record_tool_call(
        "workspace_submit_action_bundle",
        {"title": title, "cwd": cwd, "actions": actions},
        lambda: _workspace_submit_action_bundle_impl(title, cwd, actions),
    )


def _workspace_submit_action_bundle_impl(
    title: str,
    cwd: str,
    actions: list[CommandBundleAction],
) -> CommandBundleStageResult:
    return workspace_stage_action_bundle(title=title, cwd=cwd, actions=actions)


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_submit_commit_bundle(
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
    paths: Annotated[
        list[str],
        Field(min_length=1, max_length=100, description="Relative paths to stage and commit. Use ['.'] with care."),
    ],
    message: Annotated[str, Field(min_length=1, max_length=200, description="Single-line commit message.")],
) -> CommandBundleStageResult:
    """Submit a git add/commit bundle for local approval and return immediately."""
    return _record_tool_call(
        "workspace_submit_commit_bundle",
        {"cwd": cwd, "paths": paths, "message": message},
        lambda: _workspace_submit_commit_bundle_impl(cwd, paths, message),
    )


def _workspace_submit_commit_bundle_impl(
    cwd: str,
    paths: list[str],
    message: str,
) -> CommandBundleStageResult:
    return workspace_stage_commit_bundle(
        cwd=cwd,
        paths=paths,
        message=message,
        precheck_commands=None,
    )


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_command_bundle_and_wait(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
    steps: Annotated[
        list[CommandBundleStep],
        Field(
            min_length=1,
            max_length=1,
            description=(
                "Exactly one approval proposal command step. Use repeated calls for multiple checks or commands. "
                "Do not batch install, test, and git commands in one call. This stages a proposal in the local "
                "/pending review UI and does not directly execute commands."
            ),
        ),
    ],
    timeout_seconds: Annotated[int, Field(ge=1, le=45, description="Maximum seconds to wait for pending status to change.")] = 30,
    poll_interval_seconds: Annotated[float, Field(ge=0.2, le=5.0, description="Seconds between status checks.")] = 1.0,
) -> CommandBundleStatusResult:
    """Stage exactly one command proposal, then briefly wait for local review UI approval.

    This tool does not directly execute commands. It writes one pending proposal for
    local user review. Commands run only after the user approves the proposal in the
    local /pending browser UI.
    """
    return _record_tool_call(
        "workspace_stage_command_bundle_and_wait",
        {
            "title": title,
            "cwd": cwd,
            "steps": steps,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        },
        lambda: _workspace_stage_command_bundle_and_wait_impl(
            title,
            cwd,
            steps,
            timeout_seconds,
            poll_interval_seconds,
        ),
    )


def _workspace_stage_command_bundle_and_wait_impl(
    title: str,
    cwd: str,
    steps: list[CommandBundleStep],
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> CommandBundleStatusResult:
    return _bundle_stage_command_bundle_and_wait(
        _workspace_submit_command_bundle_impl,
        _workspace_wait_command_bundle_status_impl,
        title,
        cwd,
        steps,
        timeout_seconds,
        poll_interval_seconds,
    )


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_patch_bundle_and_wait(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
    patch: Annotated[
        str | None,
        Field(
            description=(
                "Unified diff patch text. Prefer patch_ref for large patches. This stages a patch proposal in the "
                "local /pending review UI and does not directly modify project files. Avoid large patches or "
                "many-file changes when possible; split them into smaller patch proposals or action micro edits."
            )
        ),
    ] = None,
    patch_ref: Annotated[str | None, Field(description="Text payload id containing unified diff patch text.")] = None,
    timeout_seconds: Annotated[int, Field(ge=1, le=45, description="Maximum seconds to wait for pending status to change.")] = 30,
    poll_interval_seconds: Annotated[float, Field(ge=0.2, le=5.0, description="Seconds between status checks.")] = 1.0,
) -> CommandBundleStatusResult:
    """Stage a patch proposal, then briefly wait for local review UI approval.

    This tool does not directly modify project files. It writes a pending patch
    proposal for local user review in the local /pending browser UI. Avoid large
    patches or many-file changes when possible; split them into smaller patch
    proposals or action micro edits.
    """
    return _record_tool_call(
        "workspace_stage_patch_bundle_and_wait",
        {
            "title": title,
            "cwd": cwd,
            "patch": patch,
            "patch_ref": patch_ref,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        },
        lambda: _workspace_stage_patch_bundle_and_wait_impl(
            title,
            cwd,
            patch,
            patch_ref,
            timeout_seconds,
            poll_interval_seconds,
        ),
    )


def _workspace_stage_patch_bundle_and_wait_impl(
    title: str,
    cwd: str,
    patch: str | None,
    patch_ref: str | None,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> CommandBundleStatusResult:
    return _bundle_stage_patch_bundle_and_wait(
        _workspace_submit_patch_bundle_impl,
        _workspace_wait_command_bundle_status_impl,
        title,
        cwd,
        patch,
        patch_ref,
        timeout_seconds,
        poll_interval_seconds,
    )


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_action_bundle_and_wait(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
    actions: Annotated[
        list[CommandBundleAction],
        Field(
            min_length=1,
            max_length=1,
            description=(
                "Exactly one approval proposal action. Use repeated calls for multi-step edits. Do not batch "
                "multiple file writes, replacements, or commands. This stages a proposal in the local /pending "
                "review UI and does not directly modify project files."
            ),
        ),
    ],
    timeout_seconds: Annotated[int, Field(ge=1, le=45, description="Maximum seconds to wait for pending status to change.")] = 30,
    poll_interval_seconds: Annotated[float, Field(ge=0.2, le=5.0, description="Seconds between status checks.")] = 1.0,
) -> CommandBundleStatusResult:
    """Stage exactly one action proposal, then briefly wait for local review UI approval.

    This tool does not directly modify project files. It writes one pending proposal
    for local user review. Project files are changed only after the user approves
    the proposal in the local /pending browser UI.
    """
    return _record_tool_call(
        "workspace_stage_action_bundle_and_wait",
        {
            "title": title,
            "cwd": cwd,
            "actions": actions,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        },
        lambda: _workspace_stage_action_bundle_and_wait_impl(
            title,
            cwd,
            actions,
            timeout_seconds,
            poll_interval_seconds,
        ),
    )


def _workspace_stage_action_bundle_and_wait_impl(
    title: str,
    cwd: str,
    actions: list[CommandBundleAction],
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> CommandBundleStatusResult:
    return _bundle_stage_action_bundle_and_wait(
        _workspace_submit_action_bundle_impl,
        _workspace_wait_command_bundle_status_impl,
        title,
        cwd,
        actions,
        timeout_seconds,
        poll_interval_seconds,
    )


@_internal_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_stage_commit_bundle_and_wait(
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
    paths: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=100,
            description=(
                "Relative paths to stage and commit. This stages a commit proposal in the local /pending review UI "
                "and does not directly run git add or git commit. Use ['.'] only after reviewing git status and diff."
            ),
        ),
    ],
    message: Annotated[str, Field(min_length=1, max_length=200, description="Single-line commit message.")],
    timeout_seconds: Annotated[int, Field(ge=1, le=45, description="Maximum seconds to wait for pending status to change.")] = 30,
    poll_interval_seconds: Annotated[float, Field(ge=0.2, le=5.0, description="Seconds between status checks.")] = 1.0,
) -> CommandBundleStatusResult:
    """Stage a commit proposal, then briefly wait for local review UI approval.

    This tool does not directly run git add or git commit. It writes a pending
    commit proposal for local user review in the local /pending browser UI. The
    actual git add/commit runs only after the user approves it. Use ['.'] only
    after reviewing git status and diff.
    """
    return _record_tool_call(
        "workspace_stage_commit_bundle_and_wait",
        {
            "cwd": cwd,
            "paths": paths,
            "message": message,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        },
        lambda: _workspace_stage_commit_bundle_and_wait_impl(
            cwd,
            paths,
            message,
            timeout_seconds,
            poll_interval_seconds,
        ),
    )


def _workspace_stage_commit_bundle_and_wait_impl(
    cwd: str,
    paths: list[str],
    message: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> CommandBundleStatusResult:
    return _bundle_stage_commit_bundle_and_wait(
        _workspace_submit_commit_bundle_impl,
        _workspace_wait_command_bundle_status_impl,
        cwd,
        paths,
        message,
        timeout_seconds,
        poll_interval_seconds,
    )


def _validate_git_remote_or_branch(value: str, label: str) -> str:
    return _proposal_validate_git_remote_or_branch(value, label)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_propose_command_and_wait(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
    argv: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=40,
            description=(
                "Exactly one argv-based command proposal. This only creates a local pending bundle. "
                "It does not run until approved at http://127.0.0.1:8790/pending."
            ),
        ),
    ],
    command_name: Annotated[
        str | None,
        Field(description="Optional display name for the command step. Defaults to title."),
    ] = None,
    command_timeout_seconds: Annotated[int, Field(ge=1, le=300)] = 60,
    timeout_seconds: Annotated[int, Field(ge=1, le=45, description="Maximum seconds to wait for pending status to change.")] = 30,
    poll_interval_seconds: Annotated[float, Field(ge=0.2, le=5.0, description="Seconds between status checks.")] = 1.0,
) -> CommandBundleStatusResult:
    """Create exactly one command proposal in the local pending UI and briefly wait.

    This tool only creates a local pending proposal. It never executes the command
    in ChatGPT. The command runs only after the user approves the bundle at
    http://127.0.0.1:8790/pending.
    """
    step = _proposal_command_step(title, argv, command_name, command_timeout_seconds)
    return _record_tool_call(
        "workspace_propose_command_and_wait",
        {
            "title": title,
            "cwd": cwd,
            "argv": argv,
            "command_name": command_name,
            "command_timeout_seconds": command_timeout_seconds,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        },
        lambda: _proposal_command_and_wait(
            _workspace_stage_command_bundle_and_wait_impl,
            title,
            cwd,
            step,
            timeout_seconds,
            poll_interval_seconds,
        ),
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_propose_file_write_and_wait(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
    path: Annotated[str, Field(description="Relative file path to create or overwrite under cwd.")],
    content: Annotated[
        str,
        Field(
            max_length=MAX_WRITE_CHARS,
            description=(
                "UTF-8 text content. This only creates a local pending bundle. "
                "It does not write until approved at http://127.0.0.1:8790/pending."
            ),
        ),
    ],
    overwrite: Annotated[bool, Field(description="Whether the proposal may overwrite an existing file.")] = False,
    create_parent_dirs: Annotated[bool, Field(description="Whether the proposal may create missing parent directories.")] = True,
    timeout_seconds: Annotated[int, Field(ge=1, le=45, description="Maximum seconds to wait for pending status to change.")] = 30,
    poll_interval_seconds: Annotated[float, Field(ge=0.2, le=5.0, description="Seconds between status checks.")] = 1.0,
) -> CommandBundleStatusResult:
    """Create exactly one file-write proposal in the local pending UI and briefly wait.

    This tool only creates a local pending proposal. It never writes files in
    ChatGPT. Files change only after the user approves the bundle at
    http://127.0.0.1:8790/pending.
    """
    action = _proposal_file_write_action(
        title,
        path,
        content,
        overwrite,
        create_parent_dirs,
    )
    return _record_tool_call(
        "workspace_propose_file_write_and_wait",
        {
            "title": title,
            "cwd": cwd,
            "path": path,
            "content": content,
            "overwrite": overwrite,
            "create_parent_dirs": create_parent_dirs,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        },
        lambda: _proposal_action_and_wait(
            _workspace_stage_action_bundle_and_wait_impl,
            title,
            cwd,
            action,
            timeout_seconds,
            poll_interval_seconds,
        ),
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_propose_file_replace_and_wait(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative working directory under the configured WORKSPACE_ROOT.")],
    path: Annotated[str, Field(description="Relative UTF-8 file path under cwd.")],
    old_text: Annotated[str, Field(min_length=1, description="Exact text to find.")],
    new_text: Annotated[
        str,
        Field(
            max_length=MAX_WRITE_CHARS,
            description=(
                "Replacement text. This only creates a local pending bundle. "
                "It does not edit until approved at http://127.0.0.1:8790/pending."
            ),
        ),
    ],
    replace_all: Annotated[bool, Field(description="Replace all occurrences instead of only the first.")] = False,
    timeout_seconds: Annotated[int, Field(ge=1, le=45, description="Maximum seconds to wait for pending status to change.")] = 30,
    poll_interval_seconds: Annotated[float, Field(ge=0.2, le=5.0, description="Seconds between status checks.")] = 1.0,
) -> CommandBundleStatusResult:
    """Create exactly one file replacement proposal in the local pending UI and briefly wait.

    This tool only creates a local pending proposal. It never edits files in
    ChatGPT. Files change only after the user approves the bundle at
    http://127.0.0.1:8790/pending.
    """
    action = _proposal_file_replace_action(
        title,
        path,
        old_text,
        new_text,
        replace_all,
    )
    return _record_tool_call(
        "workspace_propose_file_replace_and_wait",
        {
            "title": title,
            "cwd": cwd,
            "path": path,
            "old_text": old_text,
            "new_text": new_text,
            "replace_all": replace_all,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        },
        lambda: _proposal_action_and_wait(
            _workspace_stage_action_bundle_and_wait_impl,
            title,
            cwd,
            action,
            timeout_seconds,
            poll_interval_seconds,
        ),
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_propose_patch_and_wait(
    title: Annotated[str, Field(min_length=1, max_length=160)],
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
    patch: Annotated[str | None, Field(description="Unified diff patch text. Prefer smaller patches or file-specific wrappers.")] = None,
    patch_ref: Annotated[str | None, Field(description="Text payload id containing unified diff patch text.")] = None,
    timeout_seconds: Annotated[int, Field(ge=1, le=45, description="Maximum seconds to wait for pending status to change.")] = 30,
    poll_interval_seconds: Annotated[float, Field(ge=0.2, le=5.0, description="Seconds between status checks.")] = 1.0,
) -> CommandBundleStatusResult:
    """Create one patch proposal in the local pending UI and briefly wait.

    This tool only creates a local pending proposal. It never applies patches in
    ChatGPT. The patch applies only after the user approves the bundle at
    http://127.0.0.1:8790/pending.
    """
    return _record_tool_call(
        "workspace_propose_patch_and_wait",
        {
            "title": title,
            "cwd": cwd,
            "patch": patch,
            "patch_ref": patch_ref,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        },
        lambda: _proposal_patch_and_wait(
            _workspace_stage_patch_bundle_and_wait_impl,
            title,
            cwd,
            patch,
            patch_ref,
            timeout_seconds,
            poll_interval_seconds,
        ),
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_propose_git_commit_and_wait(
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
    paths: Annotated[list[str], Field(min_length=1, max_length=100, description="Relative paths to stage and commit.")],
    message: Annotated[str, Field(min_length=1, max_length=200, description="Single-line commit message.")],
    timeout_seconds: Annotated[int, Field(ge=1, le=45, description="Maximum seconds to wait for pending status to change.")] = 30,
    poll_interval_seconds: Annotated[float, Field(ge=0.2, le=5.0, description="Seconds between status checks.")] = 1.0,
) -> CommandBundleStatusResult:
    """Create one git commit proposal in the local pending UI and briefly wait.

    This tool only creates a local pending proposal. It never runs git add or git
    commit in ChatGPT. Git runs only after the user approves the bundle at
    http://127.0.0.1:8790/pending.
    """
    return _record_tool_call(
        "workspace_propose_git_commit_and_wait",
        {
            "cwd": cwd,
            "paths": paths,
            "message": message,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        },
        lambda: _proposal_commit_and_wait(
            _workspace_stage_commit_bundle_and_wait_impl,
            cwd,
            paths,
            message,
            timeout_seconds,
            poll_interval_seconds,
        ),
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_propose_git_push_and_wait(
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
    remote: Annotated[str, Field(min_length=1, max_length=80, description="Git remote name, usually origin.")] = "origin",
    branch: Annotated[str, Field(min_length=1, max_length=120, description="Git branch name, usually main.")] = "main",
    timeout_seconds: Annotated[int, Field(ge=1, le=45, description="Maximum seconds to wait for pending status to change.")] = 30,
    poll_interval_seconds: Annotated[float, Field(ge=0.2, le=5.0, description="Seconds between status checks.")] = 1.0,
) -> CommandBundleStatusResult:
    """Create one git push proposal in the local pending UI and briefly wait.

    This tool only creates a local pending proposal. It never pushes in ChatGPT.
    Git push runs only after the user approves the bundle at
    http://127.0.0.1:8790/pending.
    """
    safe_remote, safe_branch, title, step = _proposal_git_push(remote, branch)
    return _record_tool_call(
        "workspace_propose_git_push_and_wait",
        {
            "cwd": cwd,
            "remote": safe_remote,
            "branch": safe_branch,
            "timeout_seconds": timeout_seconds,
            "poll_interval_seconds": poll_interval_seconds,
        },
        lambda: _proposal_command_and_wait(
            _workspace_stage_command_bundle_and_wait_impl,
            title,
            cwd,
            step,
            timeout_seconds,
            poll_interval_seconds,
        ),
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
    return _bundle_list_command_bundles(_command_bundle_dirs, _read_json, limit)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_cancel_command_bundle(
    bundle_id: Annotated[str, Field(description="Pending command bundle id to reject.")],
) -> CommandBundleStatusResult:
    """Reject a pending command bundle without executing it."""
    return _bundle_cancel_command_bundle(
        _find_command_bundle,
        _move_command_bundle,
        _audit,
        bundle_id,
    )



@_direct_mutation_tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
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
    cwd: Annotated[str, Field(description="Relative directory under the configured WORKSPACE_ROOT.")],
    args: Annotated[list[str], Field(description="Additional safe args for the selected profile.")] = [],
    timeout_seconds: Annotated[int, Field(ge=1, le=180)] = 60,
) -> CommandResult:
    """Run an approved command profile under the configured WORKSPACE_ROOT. This does not accept arbitrary shell commands."""
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
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_git_add(
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
    paths: Annotated[list[str], Field(description="Relative paths to stage. Use ['.'] to stage all allowed files.")],
) -> CommandResult:
    """Stage files with git add under the configured WORKSPACE_ROOT. Paths are validated and secret-like files are blocked."""
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
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def workspace_git_commit(
    cwd: Annotated[str, Field(description="Relative git repository directory under the configured WORKSPACE_ROOT.")],
    message: Annotated[str, Field(min_length=1, max_length=200, description="Commit message.")],
) -> GitCommitResult:
    """Create a git commit for already staged changes under the configured WORKSPACE_ROOT."""
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
