from __future__ import annotations

import os
from pathlib import Path


WORKSPACE_ROOT = (Path.home() / "workspace").resolve()
PROJECT_ROOT = Path(__file__).resolve().parent.parent

RUNTIME_ROOT = (Path.home() / ".mcp_terminal_bridge" / "my-terminal-tool").resolve()
AUDIT_LOG = RUNTIME_ROOT / "audit.jsonl"
BACKUP_DIR = RUNTIME_ROOT / "backups"
TRASH_DIR = RUNTIME_ROOT / "trash"
OPERATION_DIR = RUNTIME_ROOT / "operations"
TASK_DIR = RUNTIME_ROOT / "tasks"
TEXT_PAYLOAD_DIR = RUNTIME_ROOT / "text_payloads"
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
NGROK_HOST = os.getenv("NGROK_HOST", "iguana-dashing-tuna.ngrok-free.app")
MCP_ACCESS_TOKEN = os.getenv("MCP_ACCESS_TOKEN")
