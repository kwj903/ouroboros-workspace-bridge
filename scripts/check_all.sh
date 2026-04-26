#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${NGROK_HOST:=}"
: "${NGROK_BASE_URL:=}"

if [[ -z "$NGROK_HOST" && -n "$NGROK_BASE_URL" ]]; then
  NGROK_HOST="${NGROK_BASE_URL#https://}"
  NGROK_HOST="${NGROK_HOST#http://}"
  NGROK_HOST="${NGROK_HOST%%/*}"
fi

: "${NGROK_HOST:=iguana-dashing-tuna.ngrok-free.app}"

uv run python scripts/smoke_check.py

if [[ -n "${MCP_ACCESS_TOKEN:-}" ]]; then
  mcp_url="https://${NGROK_HOST}/mcp?access_token=${MCP_ACCESS_TOKEN}"
  uv run python scripts/smoke_check.py --mcp-url "$mcp_url"
else
  cat <<'EOF'

MCP_ACCESS_TOKEN is not set; skipping remote MCP smoke check.
EOF
fi

echo
git status --short --branch
