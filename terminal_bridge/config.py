from __future__ import annotations

import os
import shlex
from pathlib import Path


DEFAULT_RUNTIME_ROOT = (Path.home() / ".mcp_terminal_bridge" / "my-terminal-tool").resolve()


def _runtime_root() -> Path:
    return Path(os.getenv("MCP_TERMINAL_BRIDGE_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT))).expanduser().resolve()


def _session_env_value(name: str) -> str | None:
    session_env = _runtime_root() / "session.env"
    if not session_env.exists():
        return None

    try:
        lines = session_env.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    prefixes = (f"export {name}=", f"{name}=")
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(prefixes):
            continue

        assignment = stripped.removeprefix("export ")
        try:
            parts = shlex.split(assignment, comments=False, posix=True)
        except ValueError:
            continue
        if not parts or not parts[0].startswith(f"{name}="):
            continue
        return parts[0].split("=", 1)[1]

    return None


def _workspace_root_value() -> str:
    return os.getenv("WORKSPACE_ROOT") or _session_env_value("WORKSPACE_ROOT") or str(Path.home() / "workspace")


def _resolve_workspace_root() -> Path:
    root = Path(_workspace_root_value()).expanduser().resolve(strict=False)
    dangerous_roots = {
        Path("/").resolve(strict=False),
        Path("/System").resolve(strict=False),
        Path("/Library").resolve(strict=False),
        Path("/private").resolve(strict=False),
        Path("/etc").resolve(strict=False),
        Path("/usr").resolve(strict=False),
        Path("/bin").resolve(strict=False),
        Path("/sbin").resolve(strict=False),
    }
    if root in dangerous_roots:
        raise ValueError(f"Unsafe WORKSPACE_ROOT is not allowed: {root}")
    return root


def _normalize_ngrok_host(value: str) -> str:
    host = value.strip()
    host = host.removeprefix("https://").removeprefix("http://")
    host = host.split("/", 1)[0]
    host = host.split("?", 1)[0]
    host = host.split("#", 1)[0]
    return host


WORKSPACE_ROOT = _resolve_workspace_root()
PROJECT_ROOT = Path(__file__).resolve().parent.parent

RUNTIME_ROOT = _runtime_root()
AUDIT_LOG = RUNTIME_ROOT / "audit.jsonl"
BACKUP_DIR = RUNTIME_ROOT / "backups"
TRASH_DIR = RUNTIME_ROOT / "trash"
OPERATION_DIR = RUNTIME_ROOT / "operations"
TASK_DIR = RUNTIME_ROOT / "tasks"
TEXT_PAYLOAD_DIR = RUNTIME_ROOT / "text_payloads"
TOOL_CALL_DIR = RUNTIME_ROOT / "tool_calls"
HANDOFF_DIR = RUNTIME_ROOT / "handoffs"
COMMAND_BUNDLES_DIR = RUNTIME_ROOT / "command_bundles"
COMMAND_BUNDLE_PENDING_DIR = COMMAND_BUNDLES_DIR / "pending"
COMMAND_BUNDLE_APPLIED_DIR = COMMAND_BUNDLES_DIR / "applied"
COMMAND_BUNDLE_REJECTED_DIR = COMMAND_BUNDLES_DIR / "rejected"
COMMAND_BUNDLE_FAILED_DIR = COMMAND_BUNDLES_DIR / "failed"

MAX_READ_CHARS = 20_000
MAX_WRITE_CHARS = 200_000
MAX_TREE_ENTRIES = 300
MAX_STDOUT_CHARS = 20_000
MAX_STDERR_CHARS = 8_000
TEXT_PAYLOAD_CHUNK_MAX_CHARS = 32_000
TEXT_PAYLOAD_MAX_TOTAL_CHARS = 1_000_000

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

BLOCKED_EXECUTABLES = {
    "sudo",
    "su",
    "ssh",
    "scp",
    "sftp",
    "rsync",
    "launchctl",
    "osascript",
    "diskutil",
    "dd",
    "mkfs",
    "killall",
    "pkill",
}

APPROVAL_REQUIRED_EXECUTABLES = {
    "bash",
    "sh",
    "zsh",
    "curl",
    "wget",
    "pip",
    "pip3",
    "npm",
    "pnpm",
    "yarn",
}

APPROVAL_REQUIRED_PATTERNS = {
    "rm",
    "chmod",
    "chown",
    "git clean",
    "git reset",
    "git push",
    "git checkout",
    "git switch",
    "uv add",
    "uv sync",
    "uv pip",
    "npm install",
    "npm add",
}


MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8787"))
NGROK_HOST = _normalize_ngrok_host(os.getenv("NGROK_HOST") or os.getenv("NGROK_BASE_URL", ""))
MCP_ACCESS_TOKEN = os.getenv("MCP_ACCESS_TOKEN")
MCP_EXPOSE_DIRECT_MUTATION_TOOLS = os.getenv("MCP_EXPOSE_DIRECT_MUTATION_TOOLS") == "1"
