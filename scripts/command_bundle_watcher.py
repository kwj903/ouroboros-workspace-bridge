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
OPEN_MODE = os.environ.get("BUNDLE_WATCH_OPEN_MODE")
NOTIFY = os.environ.get("BUNDLE_WATCH_NOTIFY")
VALID_OPEN_MODES = {"dashboard_once", "bundle", "none"}


def parse_open_mode(value: str | None) -> str:
    mode = (value or "dashboard_once").strip().lower()
    if mode not in VALID_OPEN_MODES:
        return "dashboard_once"
    return mode


def parse_notify_flag(value: str | None) -> bool:
    normalized = (value if value is not None else "1").strip().lower()
    return normalized not in {"0", "false", "no", "off"}


def review_url(bundle_id: str) -> str:
    return f"{REVIEW_BASE_URL.rstrip('/')}/bundles/{bundle_id}"


def pending_url() -> str:
    return f"{REVIEW_BASE_URL.rstrip('/')}/pending"


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


def notify_pending_bundle(bundle_id: str) -> None:
    if sys.platform != "darwin":
        return

    message = f"승인 대기 번들: {bundle_id}"
    escaped_message = message.replace("\\", "\\\\").replace('"', '\\"')
    escaped_title = "Workspace Terminal Bridge".replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{escaped_message}" with title "{escaped_title}"'

    try:
        subprocess.run(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except Exception:
        pass


def load_bundle_id(path: Path) -> str | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return path.stem

    bundle_id = record.get("bundle_id")
    if isinstance(bundle_id, str) and bundle_id:
        return bundle_id

    return path.stem


def current_pending_bundle_ids() -> set[str]:
    ids: set[str] = set()
    for path in sorted(PENDING_DIR.glob("cmd-*.json")):
        bundle_id = load_bundle_id(path)
        if bundle_id:
            ids.add(bundle_id)
    return ids


def main() -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    open_mode = parse_open_mode(OPEN_MODE)
    notify_enabled = parse_notify_flag(NOTIFY)
    seen: set[str] = set() if open_mode == "bundle" else current_pending_bundle_ids()

    print(f"승인 대기 명령 번들 감시 중: {PENDING_DIR}")
    print(f"승인 UI 주소: {REVIEW_BASE_URL}")
    print(f"브라우저 열기 모드: {open_mode}")
    print(f"macOS 알림: {'켜짐' if notify_enabled else '꺼짐'}")
    print("종료하려면 Ctrl-C를 누르세요.")

    if not server_health_ok():
        print(
            "Warning: review server health check failed. "
            "Start it with: uv run python scripts/command_bundle_review_server.py",
            file=sys.stderr,
        )

    if open_mode == "dashboard_once":
        url = pending_url()
        print(f"승인 대기 대시보드 열기: {url}")
        open_url(url)

    try:
        while True:
            for path in sorted(PENDING_DIR.glob("cmd-*.json")):
                bundle_id = load_bundle_id(path)
                if not bundle_id or bundle_id in seen:
                    continue

                print(f"새 승인 대기 번들: {bundle_id}")
                if notify_enabled:
                    notify_pending_bundle(bundle_id)
                if open_mode == "bundle":
                    url = review_url(bundle_id)
                    print(f"승인 페이지 열기: {bundle_id}: {url}")
                    open_url(url)
                seen.add(bundle_id)

            time.sleep(POLL_SECONDS)

    except KeyboardInterrupt:
        print("\n감시기를 종료합니다...")


if __name__ == "__main__":
    main()
