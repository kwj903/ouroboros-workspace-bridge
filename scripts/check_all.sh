#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck source=scripts/session_env.sh
source "$(dirname "$0")/session_env.sh"
load_session_env

: "${PUBLIC_ACCESS_MODE:=ngrok}"
: "${PUBLIC_MCP_URL:=}"
: "${NGROK_HOST:=}"
: "${NGROK_BASE_URL:=}"

uv run python scripts/smoke_check.py

mcp_url="$(
  uv run python - <<'PY'
import os

from terminal_bridge.public_access import (
    PublicAccessConfigError,
    public_mcp_base_url,
    tokenized_mcp_url,
)

try:
    base_url = public_mcp_base_url(
        mode=os.getenv("PUBLIC_ACCESS_MODE", "ngrok"),
        ngrok_host=os.getenv("NGROK_HOST") or os.getenv("NGROK_BASE_URL", ""),
        external_mcp_url=os.getenv("PUBLIC_MCP_URL", ""),
    )
    token = os.getenv("MCP_ACCESS_TOKEN", "")
    if base_url and token:
        print(tokenized_mcp_url(base_url, token))
except PublicAccessConfigError:
    pass
PY
)"

if [[ -n "$mcp_url" ]]; then
  if ! command -v npx >/dev/null 2>&1; then
    cat <<'EOF'

Remote MCP smoke skipped: npx not found on PATH.
Local checks passed; install Node.js/npm if you want MCP Inspector checks.
EOF
  else
    uv run python scripts/smoke_check.py --mcp-url "$mcp_url"
  fi
else
  cat <<'EOF'

A fixed public MCP endpoint and MCP_ACCESS_TOKEN are required for remote MCP smoke check.
Configure NGROK_HOST/NGROK_BASE_URL in ngrok mode or PUBLIC_MCP_URL in external mode.
Skipping remote MCP smoke check.
EOF
fi

echo
git status --short --branch
