#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${MCP_PORT:=8787}"
: "${NGROK_HOST:=}"
: "${NGROK_BASE_URL:=}"

if [[ -z "$NGROK_HOST" && -n "$NGROK_BASE_URL" ]]; then
  NGROK_HOST="${NGROK_BASE_URL#https://}"
  NGROK_HOST="${NGROK_HOST#http://}"
  NGROK_HOST="${NGROK_HOST%%/*}"
fi

: "${NGROK_HOST:=iguana-dashing-tuna.ngrok-free.app}"

export MCP_PORT NGROK_HOST
exec ngrok http --url="$NGROK_HOST" "$MCP_PORT"
