#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

uv run python scripts/smoke_check.py

echo
uv run python scripts/smoke_check.py --remote-only

echo
git status --short --branch
