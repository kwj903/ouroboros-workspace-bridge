#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck source=scripts/session_env.sh
source "$(dirname "$0")/session_env.sh"
load_session_env

: "${MCP_PORT:=8787}"
: "${NGROK_HOST:=}"
: "${NGROK_BASE_URL:=}"

if [[ -z "$NGROK_HOST" && -n "$NGROK_BASE_URL" ]]; then
  NGROK_HOST="${NGROK_BASE_URL#https://}"
  NGROK_HOST="${NGROK_HOST#http://}"
  NGROK_HOST="${NGROK_HOST%%/*}"
fi

export MCP_PORT NGROK_HOST

if [[ -n "$NGROK_HOST" ]]; then
  exec ngrok http --url="$NGROK_HOST" "$MCP_PORT"
fi

cat <<'EOF'
NGROK_HOST is not set. Starting ngrok in temporary URL mode.
Use `woojae setup` or `scripts/dev_session.sh configure` to save a fixed domain later.
EOF
exec ngrok http "$MCP_PORT"
