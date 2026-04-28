#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "[error] uv is required before installing Workspace Terminal Bridge."
  echo "        Install uv, then run this script again."
  exit 1
fi

uv sync

cat <<'EOF'

Workspace Terminal Bridge dependencies are installed.

Next:
  uv run woojae setup

This project is currently intended to run from a repository checkout with:
  uv run woojae ...
EOF
