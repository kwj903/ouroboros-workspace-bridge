from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from mcp.server.transport_security import TransportSecuritySettings

WORKSPACE_ROOT = (Path.home() / "workspace").resolve()

MAX_READ_CHARS = 20_000
MAX_TREE_ENTRIES = 300

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


MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8787"))
NGROK_HOST = os.getenv("NGROK_HOST", "iguana-dashing-tuna.ngrok-free.app")

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
        "Provides safe, read-only access to files under ~/workspace. "
        "This server rejects absolute paths, path traversal, secret-like files, "
        "and paths outside ~/workspace. It currently supports listing files, "
        "reading text files, git status, and git diff only."
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


class CommandResult(BaseModel):
    cwd: str
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool


def _safe_env() -> dict[str, str]:
    env = {
        "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        "HOME": str(WORKSPACE_ROOT / ".mcp_home"),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
    }
    return env


def _is_blocked_name(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in BLOCKED_FILE_PATTERNS)


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


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


@mcp.tool()
def workspace_info() -> WorkspaceInfo:
    """Return basic information about the configured ~/workspace root and enabled read-only tools."""
    return WorkspaceInfo(
        root=str(WORKSPACE_ROOT),
        mode="read_only_mvp",
        tools=[
            "workspace_list",
            "workspace_tree",
            "workspace_read_file",
            "workspace_git_status",
            "workspace_git_diff",
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
    """List files and directories under ~/workspace. This is read-only and blocks secret-like paths."""
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
    path: Annotated[
        str,
        Field(description="Relative directory path under ~/workspace. Use '.' for root."),
    ] = ".",
    max_depth: Annotated[
        int,
        Field(ge=1, le=5, description="Maximum tree depth. Allowed range: 1 to 5."),
    ] = 2,
    max_entries: Annotated[
        int,
        Field(ge=1, le=300, description="Maximum number of entries to return."),
    ] = 120,
) -> TreeResult:
    """Return a compact tree view under ~/workspace. This skips blocked directories and secret-like files."""
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
    path: Annotated[
        str,
        Field(
            description=(
                "Relative file path under ~/workspace. "
                "Absolute paths, '..', blocked directories, and secret-like files are rejected."
            )
        ),
    ],
    offset: Annotated[
        int,
        Field(ge=0, description="Starting character offset."),
    ] = 0,
    limit: Annotated[
        int,
        Field(ge=1, le=20_000, description="Maximum number of characters to return."),
    ] = 12_000,
) -> ReadFileResult:
    """Read a UTF-8 text file under ~/workspace. This blocks secret-like files and large unsafe reads."""
    target = _resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(f"File does not exist: {_relative(target)}")

    if not target.is_file():
        raise IsADirectoryError(f"Path is not a file: {_relative(target)}")

    raw = target.read_bytes()

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Only UTF-8 text files are supported in the MVP.") from exc

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


def _run_readonly_command(cwd: str, command: list[str], timeout_seconds: int = 15) -> CommandResult:
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

    stdout, out_truncated = _truncate(completed.stdout, 20_000)
    stderr, err_truncated = _truncate(completed.stderr, 8_000)

    return CommandResult(
        cwd=_relative(target),
        command=command,
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        truncated=out_truncated or err_truncated,
    )


@mcp.tool()
def workspace_git_status(
    cwd: Annotated[
        str,
        Field(description="Relative directory under ~/workspace that contains, or is inside, a git repository."),
    ] = ".",
) -> CommandResult:
    """Run read-only git status under ~/workspace. This does not accept arbitrary shell commands."""
    return _run_readonly_command(cwd=cwd, command=["git", "status", "--short", "--branch"])


@mcp.tool()
def workspace_git_diff(
    cwd: Annotated[
        str,
        Field(description="Relative directory under ~/workspace that contains, or is inside, a git repository."),
    ] = ".",
) -> CommandResult:
    """Run read-only git diff under ~/workspace. This does not accept arbitrary shell commands."""
    return _run_readonly_command(cwd=cwd, command=["git", "diff", "--no-ext-diff"])


if __name__ == "__main__":
    mcp.run(transport="streamable-http")