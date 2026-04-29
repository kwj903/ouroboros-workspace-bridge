#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck source=scripts/session_env.sh
source "$(dirname "$0")/session_env.sh"
load_session_env

: "${NGROK_HOST:=}"
: "${NGROK_BASE_URL:=}"

if [[ -z "$NGROK_HOST" && -n "$NGROK_BASE_URL" ]]; then
  NGROK_HOST="${NGROK_BASE_URL#https://}"
  NGROK_HOST="${NGROK_HOST#http://}"
  NGROK_HOST="${NGROK_HOST%%/*}"
fi

uv run python scripts/smoke_check.py

if [[ -n "${MCP_ACCESS_TOKEN:-}" && -n "$NGROK_HOST" ]]; then
  if ! command -v npx >/dev/null 2>&1; then
    cat <<'EOF'

Remote MCP smoke skipped: npx not found on PATH.
Local checks passed; install Node.js/npm if you want MCP Inspector checks.
EOF
  else
    mcp_url="https://${NGROK_HOST}/mcp?access_token=${MCP_ACCESS_TOKEN}"
    uv run python scripts/smoke_check.py --mcp-url "$mcp_url"
  fi
else
  cat <<'EOF'

NGROK_HOST/NGROK_BASE_URL and MCP_ACCESS_TOKEN are required for remote MCP smoke check.
Skipping remote MCP smoke check.
EOF
fi

echo
git status --short --branch
