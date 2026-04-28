#!/usr/bin/env bash

RUNTIME_ROOT="${MCP_TERMINAL_BRIDGE_RUNTIME_ROOT:-$HOME/.mcp_terminal_bridge/my-terminal-tool}"
SESSION_ENV="$RUNTIME_ROOT/session.env"

shell_quote() {
  printf "%q" "$1"
}

normalize_ngrok_host() {
  local value="$1"
  value="${value#https://}"
  value="${value#http://}"
  value="${value%%/*}"
  value="${value%%\?*}"
  value="${value%%#*}"
  printf "%s" "$value"
}

load_session_env() {
  if [[ ! -f "$SESSION_ENV" ]]; then
    return 0
  fi

  local had_mcp_access_token="${MCP_ACCESS_TOKEN+x}"
  local saved_mcp_access_token="${MCP_ACCESS_TOKEN-}"
  local had_ngrok_host="${NGROK_HOST+x}"
  local saved_ngrok_host="${NGROK_HOST-}"
  local had_ngrok_base_url="${NGROK_BASE_URL+x}"
  local saved_ngrok_base_url="${NGROK_BASE_URL-}"
  local had_mcp_host="${MCP_HOST+x}"
  local saved_mcp_host="${MCP_HOST-}"
  local had_mcp_port="${MCP_PORT+x}"
  local saved_mcp_port="${MCP_PORT-}"
  local had_workspace_root="${WORKSPACE_ROOT+x}"
  local saved_workspace_root="${WORKSPACE_ROOT-}"

  # shellcheck source=/dev/null
  source "$SESSION_ENV"

  if [[ -n "$had_mcp_access_token" ]]; then
    MCP_ACCESS_TOKEN="$saved_mcp_access_token"
    export MCP_ACCESS_TOKEN
  fi

  if [[ -n "$had_ngrok_host" ]]; then
    NGROK_HOST="$saved_ngrok_host"
    export NGROK_HOST
  elif [[ -n "$had_ngrok_base_url" ]]; then
    unset NGROK_HOST
  fi

  if [[ -n "$had_ngrok_base_url" ]]; then
    NGROK_BASE_URL="$saved_ngrok_base_url"
    export NGROK_BASE_URL
  fi

  if [[ -n "$had_mcp_host" ]]; then
    MCP_HOST="$saved_mcp_host"
    export MCP_HOST
  fi

  if [[ -n "$had_mcp_port" ]]; then
    MCP_PORT="$saved_mcp_port"
    export MCP_PORT
  fi

  if [[ -n "$had_workspace_root" ]]; then
    WORKSPACE_ROOT="$saved_workspace_root"
    export WORKSPACE_ROOT
  fi
}
