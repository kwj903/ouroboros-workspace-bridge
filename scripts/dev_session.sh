#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck source=scripts/session_env.sh
source "$(dirname "$0")/session_env.sh"

print_help() {
  cat <<'EOF'
Usage:
  scripts/dev_session.sh help
  scripts/dev_session.sh checklist
  scripts/dev_session.sh configure
  scripts/dev_session.sh doctor
  scripts/dev_session.sh review
  scripts/dev_session.sh start
  scripts/dev_session.sh status
  scripts/dev_session.sh start-service [mcp|ngrok]
  scripts/dev_session.sh stop-service [mcp|ngrok]
  scripts/dev_session.sh restart [mcp|ngrok]
  scripts/dev_session.sh restart-session
  scripts/dev_session.sh stop
  scripts/dev_session.sh logs [review|mcp|ngrok]

Commands:
  help       Show this help.
  checklist  Print the recommended local development session checklist.
  configure  Interactively create a private runtime session.env file.
  doctor     Check local tools and required environment variables.
  review     Run the local command bundle review server with its embedded watcher.
  start      Start review, MCP server, and ngrok in the background.
  status     Show supervisor-managed service status.
  start-service
             Start one supervisor-managed service. Supported: mcp, ngrok.
  stop-service
             Stop one supervisor-managed service. Supported: mcp, ngrok.
  restart    Restart a supervisor-managed service. Supported: mcp, ngrok.
  restart-session
             Restart the full local session through a detached helper.
  stop       Stop supervisor-managed services by pid file.
  logs       Tail a supervisor-managed service log.
EOF
}

print_checklist() {
  cat <<'EOF'
Workspace Terminal Bridge development session checklist

1. Check local prerequisites:
   scripts/dev_session.sh doctor

2. If MCP_ACCESS_TOKEN or NGROK_HOST is missing, create a private runtime env file:
   scripts/dev_session.sh configure

3. Start the full local session in the background:
   scripts/dev_session.sh start

4. Confirm review, MCP, and ngrok status:
   scripts/dev_session.sh status

5. Keep the review dashboard open:
   http://127.0.0.1:8790/pending

6. Use the management page for process status and limited restart controls:
   http://127.0.0.1:8790/servers?tab=processes

7. If server.py or MCP tool schemas change, restart MCP and Refresh the ChatGPT app:
   scripts/dev_session.sh restart mcp

8. If the ngrok tunnel needs to be reconnected, restart ngrok:
   scripts/dev_session.sh restart ngrok

9. Tail service logs when debugging:
   scripts/dev_session.sh logs [review|mcp|ngrok]

10. Stop the full local session when finished:
   scripts/dev_session.sh stop

Fallback/debug commands:
  - Review server only in foreground: scripts/dev_session.sh review
  - MCP server only: scripts/run_server.sh
  - ngrok only: scripts/run_ngrok.sh

ChatGPT app MCP URL format:
   https://<NGROK_HOST>/mcp?access_token=<TOKEN>

Notes:
  - Token values are intentionally not printed by this helper.
  - UI restart buttons are limited to MCP/ngrok. Full start/stop and review restart stay in the terminal.
  - If only the review UI, watcher, or README changes, MCP server restart and ChatGPT app Refresh are usually not needed.
EOF
}

doctor() {
  local exit_code=0

  load_session_env

  echo "Workspace Terminal Bridge doctor"
  echo

  if [[ -f "$SESSION_ENV" ]]; then
    local session_mode
    session_mode="$(stat -f "%Lp" "$SESSION_ENV" 2>/dev/null || stat -c "%a" "$SESSION_ENV" 2>/dev/null || echo unknown)"
    echo "[ok] session.env: found at $SESSION_ENV"
    if [[ "$session_mode" != "600" ]]; then
      echo "[warn] session.env permissions are $session_mode; recommended: chmod 600 $SESSION_ENV"
    fi
  else
    echo "[info] session.env: not found; run scripts/dev_session.sh configure if you want runtime env auto-loading."
  fi

  if command -v uv >/dev/null 2>&1; then
    echo "[ok] uv: found"
  else
    echo "[error] uv: missing"
    exit_code=1
  fi

  if command -v ngrok >/dev/null 2>&1; then
    echo "[ok] ngrok: found"
  else
    echo "[warn] ngrok: missing; scripts/run_ngrok.sh will fail until ngrok is installed."
  fi

  if command -v terminal-notifier >/dev/null 2>&1; then
    echo "[ok] terminal-notifier: found"
  else
    echo "[warn] terminal-notifier: missing; clickable macOS notifications require it."
    echo "       Install with: brew install terminal-notifier"
  fi

  if [[ -n "${MCP_ACCESS_TOKEN:-}" ]]; then
    echo "[ok] MCP_ACCESS_TOKEN: set"
  else
    echo "[warn] MCP_ACCESS_TOKEN: not set; scripts/run_server.sh may fail."
  fi

  if [[ -n "${NGROK_HOST:-}" || -n "${NGROK_BASE_URL:-}" ]]; then
    echo "[ok] NGROK_HOST/NGROK_BASE_URL: set"
  else
    echo "[warn] NGROK_HOST/NGROK_BASE_URL: not set; scripts/run_ngrok.sh will use its default host."
  fi

  echo
  echo "Supervisor services:"
  for service in review mcp ngrok; do
    print_service_status "$service"
  done

  return "$exit_code"
}

process_dir() {
  printf "%s/processes" "$RUNTIME_ROOT"
}

service_pid_file() {
  printf "%s/%s.pid" "$(process_dir)" "$1"
}

service_log_file() {
  printf "%s/%s.log" "$(process_dir)" "$1"
}

is_known_service() {
  case "$1" in
    review | mcp | ngrok)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_pid_alive() {
  local pid="$1"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

collect_descendant_pids() {
  local parent="$1"
  local child

  command -v pgrep >/dev/null 2>&1 || return 0

  while IFS= read -r child; do
    [[ -n "$child" ]] || continue
    printf "%s\n" "$child"
    collect_descendant_pids "$child"
  done < <(pgrep -P "$parent" 2>/dev/null || true)
}

managed_process_tree_pids() {
  local root_pid="$1"
  collect_descendant_pids "$root_pid"
  printf "%s\n" "$root_pid"
}

any_pid_alive() {
  local pid
  for pid in "$@"; do
    if is_pid_alive "$pid"; then
      return 0
    fi
  done
  return 1
}

python_launcher() {
  if [[ -x ".venv/bin/python" ]]; then
    printf "%s" ".venv/bin/python"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  command -v python
}

launch_background_service() {
  local log_file="$1"
  shift

  local launcher
  launcher="$(python_launcher)"

  "$launcher" - "$log_file" "$@" <<'PY'
import subprocess
import sys

log_path = sys.argv[1]
command = sys.argv[2:]

with open(log_path, "ab", buffering=0) as log:
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        close_fds=True,
        start_new_session=True,
    )

print(process.pid)
PY
}

read_service_pid() {
  local service="$1"
  local pid_file
  pid_file="$(service_pid_file "$service")"

  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi

  local pid
  pid="$(tr -d '[:space:]' < "$pid_file")"
  [[ -n "$pid" ]] || return 1
  printf "%s" "$pid"
}

cleanup_stale_pid() {
  local service="$1"
  local pid_file
  local pid
  pid_file="$(service_pid_file "$service")"

  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi

  pid="$(tr -d '[:space:]' < "$pid_file")"
  if ! is_pid_alive "$pid"; then
    rm -f "$pid_file"
  fi
}

service_port() {
  case "$1" in
    review)
      printf "%s" "${BUNDLE_REVIEW_PORT:-8790}"
      ;;
    mcp)
      printf "%s" "${MCP_PORT:-8787}"
      ;;
    *)
      return 1
      ;;
  esac
}

service_host() {
  case "$1" in
    review)
      printf "%s" "${BUNDLE_REVIEW_HOST:-127.0.0.1}"
      ;;
    mcp)
      printf "%s" "${MCP_HOST:-127.0.0.1}"
      ;;
    *)
      return 1
      ;;
  esac
}

tcp_reachable() {
  local host="$1"
  local port="$2"

  if [[ -z "$host" || -z "$port" ]]; then
    return 1
  fi

  (echo >"/dev/tcp/$host/$port") >/dev/null 2>&1
}

service_reachable() {
  local service="$1"
  local host
  local port

  case "$service" in
    review | mcp)
      host="$(service_host "$service")"
      port="$(service_port "$service")"
      tcp_reachable "$host" "$port"
      ;;
    *)
      return 1
      ;;
  esac
}

review_base_url() {
  printf "http://%s:%s" "${BUNDLE_REVIEW_HOST:-127.0.0.1}" "${BUNDLE_REVIEW_PORT:-8790}"
}

review_dashboard_url() {
  printf "%s/pending" "$(review_base_url)"
}

open_review_ui_once() {
  local base_url
  local url
  base_url="$(review_base_url)"
  url="$(review_dashboard_url)"

  echo "Opening review dashboard: $url"

  if [[ -x scripts/focus_review_url.py ]]; then
    uv run python scripts/focus_review_url.py "$url" "$base_url" >/dev/null 2>&1 || true
  elif [[ "$(uname -s)" == "Darwin" ]]; then
    open "$url" >/dev/null 2>&1 || true
  else
    python3 -m webbrowser "$url" >/dev/null 2>&1 || true
  fi
}

start_service() {
  local service="$1"
  local pid_file
  local log_file
  local pid
  local -a command

  is_known_service "$service" || {
    echo "[error] unknown service: $service"
    return 2
  }

  mkdir -p "$(process_dir)"
  chmod 700 "$RUNTIME_ROOT" "$(process_dir)" 2>/dev/null || true

  cleanup_stale_pid "$service"

  pid_file="$(service_pid_file "$service")"
  log_file="$(service_log_file "$service")"

  if pid="$(read_service_pid "$service" 2>/dev/null)" && is_pid_alive "$pid"; then
    echo "[reuse] $service pid=$pid log=$log_file"
    return 0
  fi

  if service_reachable "$service"; then
    echo "[warn] $service is reachable but not supervisor-managed; not starting duplicate. log=$log_file"
    return 0
  fi

  {
    echo
    echo "== $(date -u '+%Y-%m-%dT%H:%M:%SZ') starting $service =="
  } >> "$log_file"

  case "$service" in
    review)
      if [[ -x ".venv/bin/python" ]]; then
        command=(".venv/bin/python" "scripts/command_bundle_review_server.py")
      else
        command=("uv" "run" "python" "scripts/command_bundle_review_server.py")
      fi
      if [[ "${BUNDLE_WATCH_OPEN_MODE:-dashboard_once}" == "dashboard_once" ]]; then
        pid="$(BUNDLE_WATCH_OPEN_MODE=none launch_background_service "$log_file" "${command[@]}")"
      else
        pid="$(launch_background_service "$log_file" "${command[@]}")"
      fi
      ;;
    mcp)
      pid="$(launch_background_service "$log_file" scripts/run_server.sh)"
      ;;
    ngrok)
      pid="$(launch_background_service "$log_file" scripts/run_ngrok.sh)"
      ;;
  esac

  printf "%s\n" "$pid" > "$pid_file"
  echo "[start] $service pid=$pid log=$log_file"

  sleep 0.4
  if ! is_pid_alive "$pid"; then
    rm -f "$pid_file"
    echo "[warn] $service exited quickly; see log=$log_file"
  fi
}

stop_service() {
  local service="$1"
  local pid_file
  local pid
  local pids=()
  local tree_pid
  local stopped=0

  is_known_service "$service" || {
    echo "[error] unknown service: $service"
    return 2
  }

  pid_file="$(service_pid_file "$service")"

  if ! pid="$(read_service_pid "$service" 2>/dev/null)"; then
    echo "[stop] $service not managed"
    return 0
  fi

  if ! is_pid_alive "$pid"; then
    rm -f "$pid_file"
    echo "[stop] $service stale pid removed"
    return 0
  fi

  echo "[stop] $service pid=$pid"
  while IFS= read -r tree_pid; do
    [[ -n "$tree_pid" ]] || continue
    pids+=("$tree_pid")
  done < <(managed_process_tree_pids "$pid")

  if [[ "${#pids[@]}" -eq 0 ]]; then
    pids=("$pid")
  fi

  kill -TERM "-$pid" 2>/dev/null || kill -TERM "${pids[@]}" 2>/dev/null || true

  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if ! any_pid_alive "${pids[@]}"; then
      stopped=1
      break
    fi
    sleep 0.2
  done

  if [[ "$stopped" == "1" ]]; then
    rm -f "$pid_file"
    echo "[ok] $service stopped"
  else
    echo "[warn] $service still running after TERM; pid file kept: $pid_file"
  fi
}

print_service_status() {
  local service="$1"
  local pid_file
  local log_file
  local pid=""
  local state="no"
  local reachability=""

  pid_file="$(service_pid_file "$service")"
  log_file="$(service_log_file "$service")"

  if [[ -f "$pid_file" ]]; then
    pid="$(tr -d '[:space:]' < "$pid_file")"
    if is_pid_alive "$pid"; then
      state="yes"
    else
      state="stale"
    fi
  fi

  if [[ "$service" == "review" || "$service" == "mcp" ]]; then
    local host
    local port
    host="$(service_host "$service")"
    port="$(service_port "$service")"
    if tcp_reachable "$host" "$port"; then
      reachability=" reachable=yes ${host}:${port}"
    else
      reachability=" reachable=no ${host}:${port}"
    fi
  fi

  echo "$service pid=${pid:-none} alive=$state log=$log_file$reachability"
}

tail_service_log() {
  local service="${1:-}"
  local log_file

  if [[ -z "$service" ]]; then
    echo "Usage: scripts/dev_session.sh logs [review|mcp|ngrok]"
    echo
    for item in review mcp ngrok; do
      echo "$item: $(service_log_file "$item")"
    done
    return 2
  fi

  is_known_service "$service" || {
    echo "[error] unknown service: $service"
    return 2
  }

  log_file="$(service_log_file "$service")"
  if [[ ! -f "$log_file" ]]; then
    echo "[warn] log file does not exist yet: $log_file"
    return 0
  fi

  tail -n 80 -f "$log_file"
}

start_session() {
  load_session_env

  mkdir -p "$(process_dir)"
  chmod 700 "$RUNTIME_ROOT" "$(process_dir)" 2>/dev/null || true

  echo "Starting Workspace Terminal Bridge local session"
  echo "Process directory: $(process_dir)"
  echo

  start_service review
  start_service mcp
  start_service ngrok
  echo
  open_review_ui_once
  echo
  status_session
}

status_session() {
  load_session_env

  echo "Workspace Terminal Bridge service status"
  echo "Process directory: $(process_dir)"
  echo
  for service in review mcp ngrok; do
    print_service_status "$service"
  done
}

require_single_service() {
  local service="${1:-}"
  local action="$2"

  case "$service" in
    mcp | ngrok)
      return 0
      ;;
    "")
      echo "Usage: scripts/dev_session.sh $action [mcp|ngrok]" >&2
      return 2
      ;;
    review)
      echo "[error] review is intentionally not supported by scripts/dev_session.sh $action." >&2
      echo "        Use scripts/dev_session.sh start/stop from a terminal for the full session instead." >&2
      return 2
      ;;
    *)
      echo "[error] unknown or unsupported service for $action: $service" >&2
      echo "Usage: scripts/dev_session.sh $action [mcp|ngrok]" >&2
      return 2
      ;;
  esac
}

start_single_service() {
  local service="${1:-}"

  load_session_env
  require_single_service "$service" "start-service" || return "$?"

  echo "Starting Workspace Terminal Bridge service: $service"
  start_service "$service"
}

stop_single_service() {
  local service="${1:-}"

  load_session_env
  require_single_service "$service" "stop-service" || return "$?"

  echo "Stopping Workspace Terminal Bridge service: $service"
  stop_service "$service"
}

restart_service() {
  local service="${1:-}"

  load_session_env
  require_single_service "$service" "restart" || return "$?"

  echo "Restarting Workspace Terminal Bridge service: $service"
  stop_service "$service"
  start_service "$service"
}

restart_session() {
  load_session_env

  mkdir -p "$(process_dir)"
  chmod 700 "$RUNTIME_ROOT" "$(process_dir)" 2>/dev/null || true

  local log_file
  log_file="$(process_dir)/restart-session.log"

  echo "Restarting Workspace Terminal Bridge full local session"
  echo "Restart helper log: $log_file"
  echo "The current review UI may disconnect briefly."

  (
    sleep 0.8
    {
      echo
      echo "== $(date -u '+%Y-%m-%dT%H:%M:%SZ') restart-session =="
      scripts/dev_session.sh stop
      scripts/dev_session.sh start
    } >> "$log_file" 2>&1
  ) >/dev/null 2>&1 &

  echo "[ok] restart helper scheduled"
}

stop_session() {
  load_session_env

  echo "Stopping Workspace Terminal Bridge local session"
  for service in ngrok mcp review; do
    stop_service "$service"
  done
}

logs_session() {
  load_session_env
  tail_service_log "${1:-}"
}

configure() {
  load_session_env

  mkdir -p "$RUNTIME_ROOT"
  chmod 700 "$RUNTIME_ROOT" 2>/dev/null || true

  local token="${MCP_ACCESS_TOKEN:-}"
  local token_input=""
  local ngrok_host="${NGROK_HOST:-${NGROK_BASE_URL:-}}"
  local ngrok_input=""
  local mcp_host="${MCP_HOST:-127.0.0.1}"
  local mcp_port="${MCP_PORT:-8787}"

  echo "Workspace Terminal Bridge session env configure"
  echo "Target: $SESSION_ENV"
  echo

  if [[ -n "$token" ]]; then
    read -r -s -p "MCP_ACCESS_TOKEN is already set. Press Enter to keep it, or type a new value: " token_input
    echo
    if [[ -n "$token_input" ]]; then
      token="$token_input"
    fi
  else
    read -r -s -p "MCP_ACCESS_TOKEN: " token
    echo
    if [[ -z "$token" ]]; then
      echo "[error] MCP_ACCESS_TOKEN is required."
      return 1
    fi
  fi

  ngrok_host="$(normalize_ngrok_host "$ngrok_host")"
  if [[ -n "$ngrok_host" ]]; then
    read -r -p "NGROK_HOST [$ngrok_host]: " ngrok_input
    if [[ -n "$ngrok_input" ]]; then
      ngrok_host="$(normalize_ngrok_host "$ngrok_input")"
    fi
  else
    read -r -p "NGROK_HOST, for example your-domain.ngrok-free.app: " ngrok_host
    ngrok_host="$(normalize_ngrok_host "$ngrok_host")"
    if [[ -z "$ngrok_host" ]]; then
      echo "[error] NGROK_HOST is required."
      return 1
    fi
  fi

  umask 077
  {
    echo "# Generated by scripts/dev_session.sh configure"
    echo "# Stored outside the git repository. Do not commit token values."
    echo "export MCP_ACCESS_TOKEN=$(shell_quote "$token")"
    echo "export NGROK_HOST=$(shell_quote "$ngrok_host")"
    echo "export MCP_HOST=$(shell_quote "$mcp_host")"
    echo "export MCP_PORT=$(shell_quote "$mcp_port")"
  } > "$SESSION_ENV"
  chmod 600 "$SESSION_ENV"

  echo
  echo "Saved private session environment: $SESSION_ENV"
  echo "MCP_ACCESS_TOKEN: set"
  echo "NGROK_HOST: $ngrok_host"
  echo
  echo "The helper scripts auto-load this file. To use it in your current shell too, run:"
  echo "  source $SESSION_ENV"
}

review() {
  load_session_env

  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:8790 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[error] Port 8790 is already in use."
    echo "Stop the existing review server first:"
    echo "  lsof -tiTCP:8790 -sTCP:LISTEN | xargs kill"
    echo "Then run:"
    echo "  scripts/dev_session.sh review"
    return 1
  fi

  echo "Starting command bundle review server with embedded watcher..."
  echo "Embedded watcher: ${BUNDLE_REVIEW_EMBEDDED_WATCHER:-1}"
  echo "Review dashboard: http://127.0.0.1:8790/pending"
  echo "Disable embedded watcher: BUNDLE_REVIEW_EMBEDDED_WATCHER=0 scripts/dev_session.sh review"
  echo "Standalone watcher fallback: uv run python scripts/command_bundle_watcher.py"
  echo "Press Ctrl-C to stop the review server."
  echo

  exec uv run python scripts/command_bundle_review_server.py
}

cmd="${1:-help}"

case "$cmd" in
  help)
    print_help
    ;;
  checklist)
    print_checklist
    ;;
  configure)
    configure
    ;;
  doctor)
    doctor
    ;;
  review)
    review
    ;;
  start)
    start_session
    ;;
  status)
    status_session
    ;;
  start-service)
    start_single_service "${2:-}"
    ;;
  stop-service)
    stop_single_service "${2:-}"
    ;;
  restart)
    restart_service "${2:-}"
    ;;
  restart-session)
    restart_session
    ;;
  stop)
    stop_session
    ;;
  logs)
    logs_session "${2:-}"
    ;;
  *)
    print_help >&2
    exit 2
    ;;
esac
