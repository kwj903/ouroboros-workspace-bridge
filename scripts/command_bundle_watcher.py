#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RUNTIME_ROOT = Path.home() / ".mcp_terminal_bridge" / "my-terminal-tool"
PENDING_DIR = RUNTIME_ROOT / "command_bundles" / "pending"

REVIEW_BASE_URL = os.environ.get("BUNDLE_REVIEW_BASE_URL", "http://127.0.0.1:8790")
POLL_SECONDS = float(os.environ.get("BUNDLE_WATCH_POLL_SECONDS", "1.5"))


def review_url(bundle_id: str) -> str:
    return f"{REVIEW_BASE_URL.rstrip('/')}/bundles/{bundle_id}"


def server_health_ok() -> bool:
    try:
        with urllib.request.urlopen(f"{REVIEW_BASE_URL.rstrip('/')}/health", timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


def open_url(url: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", url], check=False)
    else:
        import webbrowser

        webbrowser.open(url)


def load_bundle_id(path: Path) -> str | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return path.stem

    bundle_id = record.get("bundle_id")
    if isinstance(bundle_id, str) and bundle_id:
        return bundle_id

    return path.stem


def main() -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    opened: set[str] = set()

    print(f"승인 대기 명령 번들 감시 중: {PENDING_DIR}")
    print(f"승인 UI 주소: {REVIEW_BASE_URL}")
    print("종료하려면 Ctrl-C를 누르세요.")

    if not server_health_ok():
        print(
            "Warning: review server health check failed. "
            "Start it with: uv run python scripts/command_bundle_review_server.py",
            file=sys.stderr,
        )

    try:
        while True:
            for path in sorted(PENDING_DIR.glob("cmd-*.json")):
                bundle_id = load_bundle_id(path)
                if not bundle_id or bundle_id in opened:
                    continue

                url = review_url(bundle_id)
                print(f"승인 페이지 열기: {bundle_id}: {url}")
                open_url(url)
                opened.add(bundle_id)

            time.sleep(POLL_SECONDS)

    except KeyboardInterrupt:
        print("\n감시기를 종료합니다...")


if __name__ == "__main__":
    main()
