#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${MCP_HOST:=127.0.0.1}"
: "${MCP_PORT:=8787}"
: "${NGROK_HOST:=iguana-dashing-tuna.ngrok-free.app}"

if [[ -z "${MCP_ACCESS_TOKEN:-}" ]]; then
  cat >&2 <<'EOF'
MCP_ACCESS_TOKEN is not set.

Source your private env file before running this script.
The token value is intentionally not printed.
EOF
  exit 1
fi

export MCP_HOST MCP_PORT NGROK_HOST
uv run python server.py
