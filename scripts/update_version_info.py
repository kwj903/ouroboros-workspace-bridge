#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from terminal_bridge.version import __version__


OUTPUT_PATH = PROJECT_ROOT / "docs" / "project" / "update-info.md"


def sanitize_git_text(value: str) -> str:
    sanitized = re.sub(r"access_token=[^\s)>\]]+", "access_token=<redacted>", value, flags=re.IGNORECASE)
    sanitized = re.sub(r"\bBearer\s+[^\s)>\]]+", "Bearer <redacted>", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\b(MCP_ACCESS_TOKEN|NGROK_AUTHTOKEN|NGROK_AUTH_TOKEN)=\S+", r"\1=<redacted>", sanitized)
    return sanitized


def git_lines(args: list[str], limit: int = 20) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return []

    if completed.returncode != 0:
        return []

    return [sanitize_git_text(line) for line in completed.stdout.splitlines()[:limit] if line.strip()]


def recent_commits(limit: int = 20) -> list[str]:
    return git_lines(["log", "--oneline", f"-{limit}"], limit=limit)


def render_update_info() -> str:
    commits = recent_commits()
    commit_lines = "\n".join(f"- {line}" for line in commits) if commits else "- unknown"

    return f"""# Update Info

Version: {__version__}

For live local version and git state, run:

```bash
uv run woojae version
```

## Recent Commits

Recent Commits is a generated snapshot. Run `uv run python scripts/update_version_info.py` before releases or documentation refreshes.

{commit_lines}

## How to Update Existing Installation

```bash
git pull origin main
uv sync
uv run woojae restart-session
uv run woojae status
```

After MCP tool or schema changes, refresh or reconnect the ChatGPT custom MCP connector.
"""


def normalize_for_check(text: str) -> str:
    normalized: list[str] = []
    in_recent_commits = False

    for line in text.splitlines():
        if line == "## Recent Commits":
            normalized.append(line)
            in_recent_commits = True
            continue

        if in_recent_commits:
            if line.startswith("## "):
                normalized.append("<recent-commits-snapshot>")
                normalized.append(line)
                in_recent_commits = False
            continue

        normalized.append(line)

    if in_recent_commits:
        normalized.append("<recent-commits-snapshot>")

    return "\n".join(normalized).strip() + "\n"


def check_update_info(path: Path = OUTPUT_PATH) -> int:
    if not path.exists():
        print(f"Missing update info file: {path}", file=sys.stderr)
        return 1

    current = path.read_text(encoding="utf-8")
    expected = render_update_info()
    if normalize_for_check(current) != normalize_for_check(expected):
        print(f"Update info is out of date: {path}", file=sys.stderr)
        print("Run: uv run python scripts/update_version_info.py", file=sys.stderr)
        return 1

    print(f"Update info is current: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate update metadata for Ouroboros Workspace Bridge.")
    parser.add_argument("--check", action="store_true", help="Check that docs/project/update-info.md is current.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)

    if args.check:
        return check_update_info(args.output)

    content = render_update_info()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
