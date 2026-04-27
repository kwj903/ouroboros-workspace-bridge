#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

print_help() {
  cat <<'EOF'
Usage:
  scripts/dev_session.sh help
  scripts/dev_session.sh checklist
  scripts/dev_session.sh doctor
  scripts/dev_session.sh review

Commands:
  help       Show this help.
  checklist  Print the recommended local development session checklist.
  doctor     Check local tools and required environment variables.
  review     Run the local command bundle review server with its embedded watcher.
EOF
}

print_checklist() {
  cat <<'EOF'
Workspace Terminal Bridge development session checklist

1. Check local prerequisites:
   scripts/dev_session.sh doctor

2. Start the local approval UI:
   scripts/dev_session.sh review

3. Start the MCP server in another terminal:
   scripts/run_server.sh

4. Start ngrok in another terminal:
   scripts/run_ngrok.sh

5. Keep the review dashboard open:
   http://127.0.0.1:8790/pending

6. Configure the ChatGPT app MCP URL with this format:
   https://<NGROK_HOST>/mcp?access_token=<TOKEN>

Notes:
  - Token values are intentionally not printed by this helper.
  - If server.py or MCP tool schemas change, restart the MCP server and Refresh the ChatGPT app.
  - If only the review UI, watcher, or README changes, MCP server restart and ChatGPT app Refresh are usually not needed.
EOF
}

doctor() {
  local exit_code=0

  echo "Workspace Terminal Bridge doctor"
  echo

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

  return "$exit_code"
}

review() {
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
  doctor)
    doctor
    ;;
  review)
    review
    ;;
  *)
    print_help >&2
    exit 2
    ;;
esac
