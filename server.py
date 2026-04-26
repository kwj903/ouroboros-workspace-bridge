from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qs

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field


WORKSPACE_ROOT = (Path.home() / "workspace").resolve()
PROJECT_ROOT = Path(__file__).resolve().parent

RUNTIME_ROOT = (Path.home() / ".mcp_terminal_bridge" / "my-terminal-tool").resolve()
AUDIT_LOG = RUNTIME_ROOT / "audit.jsonl"
BACKUP_DIR = RUNTIME_ROOT / "backups"
TRASH_DIR = RUNTIME_ROOT / "trash"
OPERATION_DIR = RUNTIME_ROOT / "operations"
TASK_DIR = RUNTIME_ROOT / "tasks"

MAX_READ_CHARS = 20_000
MAX_WRITE_CHARS = 200_000
MAX_TREE_ENTRIES = 300
MAX_STDOUT_CHARS = 20_000
MAX_STDERR_CHARS = 8_000

BLOCKED_DIR_NAMES = {
    ".ssh",
    ".aws",
    ".gnupg",
    ".config",
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".mcp_trash",
}

BLOCKED_FILE_PATTERNS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_ed25519",
    ".git-credentials",
    "credentials",
    "credentials.json",
]

SAFE_ARG_FLAGS = {
    "-q",
    "-v",
    "-x",
    "-s",
    "--maxfail=1",
    "--tb=short",
    "--tb=long",
    "--disable-warnings",
    "--no-header",
    "--no-summary",
}

MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8787"))
NGROK_HOST = os.getenv("NGROK_HOST", "iguana-dashing-tuna.ngrok-free.app")
MCP_ACCESS_TOKEN = os.getenv("MCP_ACCESS_TOKEN")

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
        "soft deletion, restore, approved command profiles, and basic git operations. "
        "It never accepts arbitrary shell commands."
    ),
    stateless_http=True,
    json_response=True,
    host=MCP_HOST,
    port=MCP_PORT,
    transport_security=transport_security,
)


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_runtime_dirs() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    OPERATION_DIR.mkdir(parents=True, exist_ok=True)
    TASK_DIR.mkdir(parents=True, exist_ok=True)


def _audit(event: str, **data: object) -> None:
    _ensure_runtime_dirs()
    record = {
        "ts": _now_iso(),
        "event": event,
        **data,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _model_to_dict(value: object) -> dict[str, object]:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {"value": value}


def _new_operation_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _normalize_operation_id(operation_id: str | None) -> str:
    if operation_id is None or operation_id.strip() == "":
        return _new_operation_id()

    normalized = operation_id.strip()

    if len(normalized) > 120:
        raise ValueError("operation_id is too long.")

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(ch not in allowed for ch in normalized):
        raise ValueError("operation_id can only contain letters, numbers, '-' and '_'.")

    return normalized


def _operation_path(operation_id: str) -> Path:
    return OPERATION_DIR / f"{operation_id}.json"


def _read_operation_record(operation_id: str) -> dict[str, object] | None:
    _ensure_runtime_dirs()
    path = _operation_path(operation_id)

    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def _write_operation_record(record: dict[str, object]) -> None:
    _ensure_runtime_dirs()
    operation_id = str(record["operation_id"])
    path = _operation_path(operation_id)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def _begin_operation(
    tool: str,
    args: dict[str, object],
    operation_id: str | None = None,
) -> tuple[str, dict[str, object] | None]:
    op_id = _normalize_operation_id(operation_id)
    existing = _read_operation_record(op_id)

    if existing is not None:
        status = existing.get("status")

        if status == "completed":
            _audit("operation_reused_completed", operation_id=op_id, tool=tool)
            return op_id, existing

        if status == "started":
            raise RuntimeError(f"Operation is already running: {op_id}")

        if status == "failed":
            raise RuntimeError(f"Operation already failed: {op_id}")

    record: dict[str, object] = {
        "operation_id": op_id,
        "tool": tool,
        "status": "started",
        "started_at": _now_iso(),
        "args": args,
    }

    _write_operation_record(record)
    _audit("operation_started", operation_id=op_id, tool=tool, args=args)

    return op_id, None


def _complete_operation(operation_id: str, result: object) -> None:
    record = _read_operation_record(operation_id) or {
        "operation_id": operation_id,
        "status": "started",
    }

    record["status"] = "completed"
    record["completed_at"] = _now_iso()
    record["result"] = _model_to_dict(result)

    _write_operation_record(record)
    _audit("operation_completed", operation_id=operation_id, result=record["result"])


def _fail_operation(operation_id: str, exc: BaseException) -> None:
    record = _read_operation_record(operation_id) or {
        "operation_id": operation_id,
        "status": "started",
    }

    record["status"] = "failed"
    record["failed_at"] = _now_iso()
    record["error"] = f"{type(exc).__name__}: {exc}"

    _write_operation_record(record)
    _audit("operation_failed", operation_id=operation_id, error=record["error"])


def _new_task_id() -> str:
    return f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _normalize_task_id(task_id: str) -> str:
    normalized = task_id.strip()

    if normalized == "":
        raise ValueError("task_id cannot be empty.")

    if len(normalized) > 160:
        raise ValueError("task_id is too long.")

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(ch not in allowed for ch in normalized):
        raise ValueError("task_id can only contain letters, numbers, '-' and '_'.")

    return normalized


def _task_path(task_id: str) -> Path:
    return TASK_DIR / f"{task_id}.json"


def _read_task_record(task_id: str) -> dict[str, object] | None:
    _ensure_runtime_dirs()
    path = _task_path(_normalize_task_id(task_id))

    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def _write_task_record(record: dict[str, object]) -> None:
    _ensure_runtime_dirs()
    task_id = _normalize_task_id(str(record["task_id"]))
    path = _task_path(task_id)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _safe_env() -> dict[str, str]:
    return {
        "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        "HOME": str(WORKSPACE_ROOT / ".mcp_home"),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
    }


def _is_blocked_name(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in BLOCKED_FILE_PATTERNS)


def _is_safe_visible_path(path: Path) -> bool:
    try:
        rel_parts = path.resolve(strict=False).relative_to(WORKSPACE_ROOT).parts
    except ValueError:
        return False

    if any(part in BLOCKED_DIR_NAMES for part in rel_parts):
        return False

    if path.name.startswith(".") or _is_blocked_name(path.name):
        return False

    return True


def _iter_visible_paths(root: Path, max_entries: int) -> tuple[list[Path], bool]:
    paths: list[Path] = []
    truncated = False

    def walk(current: Path) -> None:
        nonlocal truncated

        if truncated:
            return

        try:
            children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return

        for child in children:
            if not _is_safe_visible_path(child):
                continue

            paths.append(child)
            if len(paths) >= max_entries:
                truncated = True
                return

            if child.is_dir():
                walk(child)

    walk(root)
    return paths, truncated


def _ensure_workspace_root_exists() -> None:
    if not WORKSPACE_ROOT.exists() or not WORKSPACE_ROOT.is_dir():
        raise FileNotFoundError(f"Workspace root does not exist: {WORKSPACE_ROOT}")


def _resolve_workspace_path(path: str) -> Path:
    _ensure_workspace_root_exists()

    if not path or path.strip() == "":
        path = "."

    raw = Path(path).expanduser()

    if raw.is_absolute():
        raise ValueError("Absolute paths are not allowed. Use a path relative to ~/workspace.")

    candidate = (WORKSPACE_ROOT / raw).resolve(strict=False)

    if candidate != WORKSPACE_ROOT and not candidate.is_relative_to(WORKSPACE_ROOT):
        raise ValueError("Path escapes ~/workspace and is rejected.")

    relative_parts = candidate.relative_to(WORKSPACE_ROOT).parts

    for part in relative_parts:
        if part == "..":
            raise ValueError("Path traversal is not allowed.")
        if part in BLOCKED_DIR_NAMES:
            raise PermissionError(f"Blocked directory name: {part}")

    if _is_blocked_name(candidate.name):
        raise PermissionError(f"Blocked secret-like file name: {candidate.name}")

    return candidate


def _relative(path: Path) -> str:
    if path == WORKSPACE_ROOT:
        return "."
    return str(path.relative_to(WORKSPACE_ROOT))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _backup_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None

    _ensure_runtime_dirs()

    backup_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    rel = _relative(path)
    target = BACKUP_DIR / backup_id / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

    manifest = {
        "backup_id": backup_id,
        "original_path": rel,
        "backup_path": str(target),
        "sha256": _sha256_file(path),
        "created_at": _now_iso(),
    }

    manifest_path = BACKUP_DIR / backup_id / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return backup_id


def _validate_expected_sha256(path: Path, expected_sha256: str | None) -> None:
    if expected_sha256 is None:
        return
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Cannot check sha256 because file does not exist: {_relative(path)}")
    actual = _sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(
            f"sha256 mismatch for {_relative(path)}. expected={expected_sha256}, actual={actual}"
        )


def _validate_command_args(cwd: Path, args: list[str]) -> list[str]:
    safe_args: list[str] = []

    for arg in args:
        if not isinstance(arg, str):
            raise ValueError("All args must be strings.")

        if len(arg) > 200:
            raise ValueError(f"Argument too long: {arg[:40]}...")

        if "\x00" in arg or "\n" in arg or "\r" in arg:
            raise ValueError("Arguments cannot contain control characters.")

        if arg.startswith("-"):
            if arg not in SAFE_ARG_FLAGS:
                raise ValueError(f"Flag is not allowed in MVP: {arg}")
            safe_args.append(arg)
            continue

        if arg.startswith("~") or Path(arg).is_absolute() or ".." in Path(arg).parts:
            raise ValueError(f"Unsafe path argument: {arg}")

        if "://" in arg:
            raise ValueError(f"URL-like arguments are not allowed: {arg}")

        candidate = (cwd / arg).resolve(strict=False)
        if candidate != WORKSPACE_ROOT and not candidate.is_relative_to(WORKSPACE_ROOT):
            raise ValueError(f"Argument escapes workspace: {arg}")

        for part in candidate.relative_to(WORKSPACE_ROOT).parts:
            if part in BLOCKED_DIR_NAMES:
                raise PermissionError(f"Argument touches blocked directory: {part}")

        if _is_blocked_name(candidate.name):
            raise PermissionError(f"Argument touches blocked file: {candidate.name}")

        safe_args.append(arg)

    return safe_args


def _clean_patch_path(raw_path: str) -> str | None:
    value = raw_path.strip()

    if "\t" in value:
        value = value.split("\t", 1)[0]

    if value == "/dev/null":
        return None

    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]

    if value == "":
        return None

    path = Path(value)

    if path.is_absolute() or value.startswith("~") or ".." in path.parts:
        raise ValueError(f"Unsafe patch path: {raw_path}")

    if value.startswith(".git/") or "/.git/" in value:
        raise PermissionError(f"Patch path touches .git: {raw_path}")

    return value


def _extract_patch_paths(patch: str) -> list[str]:
    paths: set[str] = set()

    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                for raw in (parts[2], parts[3]):
                    cleaned = _clean_patch_path(raw)
                    if cleaned is not None:
                        paths.add(cleaned)

        elif line.startswith("--- ") or line.startswith("+++ "):
            cleaned = _clean_patch_path(line[4:])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("rename from "):
            cleaned = _clean_patch_path(line[len("rename from ") :])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("rename to "):
            cleaned = _clean_patch_path(line[len("rename to ") :])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("copy from "):
            cleaned = _clean_patch_path(line[len("copy from ") :])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("copy to "):
            cleaned = _clean_patch_path(line[len("copy to ") :])
            if cleaned is not None:
                paths.add(cleaned)

    if not paths:
        raise ValueError("No patch file paths were found.")

    return sorted(paths)


def _resolve_patch_path(cwd: Path, patch_path: str) -> Path:
    cwd_rel = _relative(cwd)
    if cwd_rel == ".":
        combined = Path(patch_path)
    else:
        combined = Path(cwd_rel) / patch_path

    return _resolve_workspace_path(str(combined))


def _validate_patch_paths(cwd: Path, patch_paths: list[str]) -> None:
    for patch_path in patch_paths:
        target = _resolve_patch_path(cwd, patch_path)

        for part in target.relative_to(WORKSPACE_ROOT).parts:
            if part in BLOCKED_DIR_NAMES:
                raise PermissionError(f"Patch path touches blocked directory: {patch_path}")

        if _is_blocked_name(target.name):
            raise PermissionError(f"Patch path touches blocked file: {patch_path}")


def _run_git_apply_with_stdin(
    cwd: Path,
    args: list[str],
    patch: str,
    timeout_seconds: int,
) -> CommandResult:
    completed = subprocess.run(
        ["git", "apply", *args],
        input=patch,
        cwd=str(cwd),
        env=_safe_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
        shell=False,
        check=False,
    )

    stdout, out_truncated = _truncate(completed.stdout, MAX_STDOUT_CHARS)
    stderr, err_truncated = _truncate(completed.stderr, MAX_STDERR_CHARS)

    return CommandResult(
        cwd=_relative(cwd),
        command=["git", "apply", *args],
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        truncated=out_truncated or err_truncated,
    )


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


@mcp.tool()
def workspace_info() -> WorkspaceInfo:
    """Return basic information about the configured ~/workspace root and enabled tools."""
    return WorkspaceInfo(
        root=str(WORKSPACE_ROOT),
        mode="development_mvp_with_write_and_safe_commands",
        runtime_root=str(RUNTIME_ROOT),
        tools=[
            "workspace_list",
            "workspace_tree",
            "workspace_read_file",
            "workspace_create_directory",
            "workspace_write_file",
            "workspace_append_file",
            "workspace_replace_text",
            "workspace_soft_delete",
            "workspace_restore_deleted",
            "workspace_git_status",
            "workspace_git_diff",
            "workspace_run_profile",
            "workspace_git_add",
            "workspace_git_commit",
            "workspace_read_audit_log",
            "workspace_get_operation",
            "workspace_list_backups",
            "workspace_restore_backup",
            "workspace_list_trash",
            "workspace_move_to_trash",
            "workspace_list_operations",
            "workspace_find_files",
            "workspace_search_text",
            "workspace_read_many_files",
            "workspace_project_snapshot",
            "workspace_preview_patch",
            "workspace_apply_patch",
            "workspace_task_start",
            "workspace_task_status",
            "workspace_task_log_step",
            "workspace_task_update_plan",
            "workspace_task_finish",
            "workspace_list_tasks",
        ],
    )


@mcp.tool()
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
    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {_relative(target)}")

    entries: list[ListEntry] = []

    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if not include_hidden and child.name.startswith("."):
            continue
        if child.name in BLOCKED_DIR_NAMES or _is_blocked_name(child.name):
            continue

        kind = "directory" if child.is_dir() else "file" if child.is_file() else "other"

        size_bytes: int | None = None
        if child.is_file():
            try:
                size_bytes = child.stat().st_size
            except OSError:
                size_bytes = None

        entries.append(
            ListEntry(
                name=child.name,
                path=_relative(child),
                kind=kind,
                size_bytes=size_bytes,
            )
        )

    return ListResult(path=_relative(target), entries=entries)


@mcp.tool()
def workspace_tree(
    path: Annotated[str, Field(description="Relative directory path under ~/workspace.")] = ".",
    max_depth: Annotated[int, Field(ge=1, le=5)] = 2,
    max_entries: Annotated[int, Field(ge=1, le=300)] = 120,
) -> TreeResult:
    """Return a compact tree view under ~/workspace."""
    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {_relative(target)}")

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {_relative(target)}")

    max_entries = min(max_entries, MAX_TREE_ENTRIES)
    lines: list[str] = []
    truncated = False

    def walk(current: Path, depth: int, prefix: str = "") -> None:
        nonlocal truncated

        if truncated or depth > max_depth:
            return

        try:
            children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as exc:
            lines.append(f"{prefix}[error: {exc}]")
            return

        visible_children = [
            child
            for child in children
            if child.name not in BLOCKED_DIR_NAMES
            and not _is_blocked_name(child.name)
            and not child.name.startswith(".")
        ]

        for index, child in enumerate(visible_children):
            if len(lines) >= max_entries:
                truncated = True
                return

            connector = "└── " if index == len(visible_children) - 1 else "├── "
            suffix = "/" if child.is_dir() else ""
            lines.append(f"{prefix}{connector}{child.name}{suffix}")

            if child.is_dir():
                extension = "    " if index == len(visible_children) - 1 else "│   "
                walk(child, depth + 1, prefix + extension)

    lines.append(f"{_relative(target)}/")
    walk(target, 1)

    return TreeResult(path=_relative(target), entries=lines, truncated=truncated)


@mcp.tool()
def workspace_read_file(
    path: Annotated[str, Field(description="Relative file path under ~/workspace.")],
    offset: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int, Field(ge=1, le=20_000)] = 12_000,
) -> ReadFileResult:
    """Read a UTF-8 text file under ~/workspace."""
    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"File does not exist: {_relative(target)}")

    if not target.is_file():
        raise IsADirectoryError(f"Path is not a file: {_relative(target)}")

    raw = target.read_bytes()

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Only UTF-8 text files are supported.") from exc

    limit = min(limit, MAX_READ_CHARS)
    sliced = text[offset : offset + limit]
    truncated = offset + limit < len(text)

    return ReadFileResult(
        path=_relative(target),
        content=sliced,
        truncated=truncated,
        size_bytes=len(raw),
        sha256=_sha256_bytes(raw),
    )


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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

        trash_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        rel = _relative(target)
        trash_target = TRASH_DIR / trash_id / rel
        trash_target.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(target), str(trash_target))

        manifest = {
            "trash_id": trash_id,
            "original_path": rel,
            "trash_path": str(trash_target),
            "created_at": _now_iso(),
            "operation_id": op_id,
        }

        manifest_path = TRASH_DIR / trash_id / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        result = DeleteResult(
            original_path=rel,
            trash_id=trash_id,
            trash_path=str(trash_target),
            operation_id=op_id,
        )

        _audit("soft_delete", operation_id=op_id, original_path=rel, trash_id=trash_id)
        _complete_operation(op_id, result)

        return result

    except Exception as exc:
        _fail_operation(op_id, exc)
        raise


@mcp.tool()
def workspace_restore_deleted(
    trash_id: Annotated[str, Field(description="trash_id returned from workspace_soft_delete.")],
    overwrite: Annotated[bool, Field(description="Whether to overwrite if the original path exists.")] = False,
) -> RestoreResult:
    """Restore a soft-deleted file or directory from MCP trash."""
    manifest_path = TRASH_DIR / trash_id / "manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Trash manifest not found: {trash_id}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original = _resolve_workspace_path(manifest["original_path"])
    trash_path = Path(manifest["trash_path"])

    if not trash_path.exists():
        raise FileNotFoundError(f"Trash payload not found: {trash_id}")

    if original.exists() and not overwrite:
        raise FileExistsError(f"Original path already exists: {_relative(original)}")

    if original.exists() and overwrite:
        backup_id = _backup_file(original)
        if original.is_dir():
            shutil.rmtree(original)
        else:
            original.unlink()
        _audit("restore_overwrite_backup", path=_relative(original), backup_id=backup_id)

    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(trash_path), str(original))

    sha = _sha256_file(original) if original.is_file() else None

    _audit("restore_deleted", restored_path=_relative(original), trash_id=trash_id)

    return RestoreResult(
        restored_path=_relative(original),
        trash_id=trash_id,
        sha256=sha,
    )


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
def workspace_list_backups(
    limit: Annotated[int, Field(ge=1, le=200, description="Maximum backups to return.")] = 50,
) -> BackupListResult:
    """List recent file backups created before overwrite/append/replace/restore operations."""
    _ensure_runtime_dirs()

    entries: list[BackupEntry] = []

    for manifest_path in sorted(BACKUP_DIR.glob("*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        entries.append(
            BackupEntry(
                backup_id=str(manifest.get("backup_id", manifest_path.parent.name)),
                original_path=str(manifest.get("original_path", "")),
                backup_path=str(manifest.get("backup_path", "")),
                sha256=manifest.get("sha256") if isinstance(manifest.get("sha256"), str) else None,
                created_at=manifest.get("created_at") if isinstance(manifest.get("created_at"), str) else None,
            )
        )

        if len(entries) >= limit:
            break

    return BackupListResult(entries=entries, count=len(entries))


@mcp.tool()
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
        manifest_path = BACKUP_DIR / backup_id / "manifest.json"

        if not manifest_path.exists():
            raise FileNotFoundError(f"Backup manifest not found: {backup_id}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        original = _resolve_workspace_path(str(manifest["original_path"]))
        backup_path = Path(str(manifest["backup_path"]))

        if not backup_path.exists() or not backup_path.is_file():
            raise FileNotFoundError(f"Backup payload not found: {backup_id}")

        if original.exists() and not overwrite:
            raise FileExistsError(f"Original path already exists. Set overwrite=true: {_relative(original)}")

        backup_id_before_overwrite = None
        if original.exists() and overwrite:
            backup_id_before_overwrite = _backup_file(original)

        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, original)

        result = BackupRestoreResult(
            backup_id=backup_id,
            restored_path=_relative(original),
            sha256=_sha256_file(original),
            backup_id_before_overwrite=backup_id_before_overwrite,
        )

        _audit(
            "restore_backup",
            operation_id=op_id,
            backup_id=backup_id,
            restored_path=result.restored_path,
            backup_id_before_overwrite=backup_id_before_overwrite,
        )
        _complete_operation(op_id, result)

        return result

    except Exception as exc:
        _fail_operation(op_id, exc)
        raise


@mcp.tool()
def workspace_list_trash(
    limit: Annotated[int, Field(ge=1, le=200, description="Maximum trash entries to return.")] = 50,
) -> TrashListResult:
    """List recent soft-deleted files and directories in MCP trash."""
    _ensure_runtime_dirs()

    entries: list[TrashEntry] = []

    for manifest_path in sorted(TRASH_DIR.glob("*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        trash_path = Path(str(manifest.get("trash_path", "")))

        entries.append(
            TrashEntry(
                trash_id=str(manifest.get("trash_id", manifest_path.parent.name)),
                original_path=str(manifest.get("original_path", "")),
                trash_path=str(trash_path),
                created_at=manifest.get("created_at") if isinstance(manifest.get("created_at"), str) else None,
                exists=trash_path.exists(),
            )
        )

        if len(entries) >= limit:
            break

    return TrashListResult(entries=entries, count=len(entries))


@mcp.tool()
def workspace_move_to_trash(
    path: Annotated[str, Field(description="Relative file or directory path under ~/workspace.")],
    operation_id: Annotated[str | None, Field(description="Optional idempotency key for retry-safe trash moves.")] = None,
) -> DeleteResult:
    """Alias for workspace_soft_delete. Moves a file or directory to reversible MCP trash."""
    return workspace_soft_delete(path=path, operation_id=operation_id)


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
def workspace_task_start(
    title: Annotated[str, Field(min_length=1, max_length=120, description="Short task title.")],
    goal: Annotated[str, Field(min_length=1, max_length=2_000, description="Task goal or user request summary.")],
    plan: Annotated[list[str], Field(description="Initial ordered plan steps.")] = [],
    metadata: Annotated[dict[str, object] | None, Field(description="Optional task metadata.")] = None,
    task_id: Annotated[str | None, Field(description="Optional explicit task id. Generated if omitted.")] = None,
) -> TaskStatusResult:
    """Start a Codex-style local work task record for planning, steps, verification, and handoff."""
    new_task_id = _normalize_task_id(task_id) if task_id else _new_task_id()

    if _read_task_record(new_task_id) is not None:
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

    _write_task_record(record)
    _audit("task_started", task_id=new_task_id, title=title)
    return _task_result(record)


@mcp.tool()
def workspace_task_status(
    task_id: Annotated[str, Field(description="Task id returned by workspace_task_start.")],
) -> TaskStatusResult:
    """Return a task record by task_id."""
    normalized = _normalize_task_id(task_id)
    record = _read_task_record(normalized)

    if record is None:
        raise FileNotFoundError(f"Task not found: {normalized}")

    return _task_result(record)


@mcp.tool()
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
    record = _read_task_record(normalized)

    if record is None:
        raise FileNotFoundError(f"Task not found: {normalized}")

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

    _write_task_record(record)
    _audit("task_step_logged", task_id=normalized, kind=kind, message=message)
    return _task_result(record)


@mcp.tool()
def workspace_task_update_plan(
    task_id: Annotated[str, Field(description="Task id returned by workspace_task_start.")],
    plan: Annotated[list[str], Field(description="Replacement ordered plan steps.")],
) -> TaskStatusResult:
    """Replace the plan for an active task."""
    normalized = _normalize_task_id(task_id)
    record = _read_task_record(normalized)

    if record is None:
        raise FileNotFoundError(f"Task not found: {normalized}")

    if record.get("status") not in {"active", "paused"}:
        raise ValueError(f"Cannot update plan for non-active task: {record.get('status')}")

    record["plan"] = [str(item) for item in plan]
    record["updated_at"] = _now_iso()

    _write_task_record(record)
    _audit("task_plan_updated", task_id=normalized, plan=record["plan"])
    return _task_result(record)


@mcp.tool()
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
    record = _read_task_record(normalized)

    if record is None:
        raise FileNotFoundError(f"Task not found: {normalized}")

    now = _now_iso()
    record["status"] = status
    record["updated_at"] = now
    record["finished_at"] = now if status in {"completed", "cancelled"} else None
    record["summary"] = summary
    record["next_steps"] = [str(item) for item in next_steps]

    _write_task_record(record)
    _audit("task_finished", task_id=normalized, status=status, summary=summary)
    return _task_result(record)


@mcp.tool()
def workspace_list_tasks(
    limit: Annotated[int, Field(ge=1, le=200, description="Maximum tasks to return.")] = 50,
) -> TaskListResult:
    """List recent task records, newest first."""
    _ensure_runtime_dirs()

    entries: list[TaskListEntry] = []

    for task_path in sorted(TASK_DIR.glob("*.json"), reverse=True):
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
def workspace_git_status(
    cwd: Annotated[
        str,
        Field(description="Relative directory under ~/workspace that contains, or is inside, a git repository."),
    ] = ".",
) -> CommandResult:
    """Run git status under ~/workspace."""
    return _run_command(cwd=cwd, command=["git", "status", "--short", "--branch"], timeout_seconds=15)


@mcp.tool()
def workspace_git_diff(
    cwd: Annotated[
        str,
        Field(description="Relative directory under ~/workspace that contains, or is inside, a git repository."),
    ] = ".",
) -> CommandResult:
    """Run git diff under ~/workspace."""
    return _run_command(cwd=cwd, command=["git", "diff", "--no-ext-diff"], timeout_seconds=15)


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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