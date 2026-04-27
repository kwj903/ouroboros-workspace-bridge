#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from terminal_bridge.review_notifications import (
    build_terminal_notifier_command,
    notification_url as _notification_url,
    open_url,
    parse_bool_env,
    parse_notification_target,
    parse_open_mode,
    pending_url as _pending_url,
    review_url as _review_url,
    send_notification,
)

RUNTIME_ROOT = Path.home() / ".mcp_terminal_bridge" / "my-terminal-tool"
PENDING_DIR = RUNTIME_ROOT / "command_bundles" / "pending"

REVIEW_BASE_URL = os.environ.get("BUNDLE_REVIEW_BASE_URL", "http://127.0.0.1:8790")
POLL_SECONDS = float(os.environ.get("BUNDLE_WATCH_POLL_SECONDS", "1.5"))
OPEN_MODE = os.environ.get("BUNDLE_WATCH_OPEN_MODE")
NOTIFY = os.environ.get("BUNDLE_WATCH_NOTIFY")
NOTIFICATION_TARGET = os.environ.get("BUNDLE_WATCH_NOTIFICATION_TARGET")
OSASCRIPT_FALLBACK = os.environ.get("BUNDLE_WATCH_OSASCRIPT_FALLBACK")


def parse_notify_flag(value: str | None) -> bool:
    return parse_bool_env(value, default=True)


def parse_osascript_fallback_flag(value: str | None) -> bool:
    return parse_bool_env(value, default=False)


def review_url(bundle_id: str) -> str:
    return _review_url(REVIEW_BASE_URL, bundle_id)


def pending_url() -> str:
    return _pending_url(REVIEW_BASE_URL)


def notification_url(bundle_id: str, target: str, base_url: str = REVIEW_BASE_URL) -> str:
    return _notification_url(base_url, bundle_id, target)


def terminal_notifier_command(bundle_id: str, target: str, base_url: str = REVIEW_BASE_URL) -> list[str]:
    return build_terminal_notifier_command(base_url, bundle_id, target)


def server_health_ok() -> bool:
    try:
        with urllib.request.urlopen(f"{REVIEW_BASE_URL.rstrip('/')}/health", timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


def notify_pending_bundle(bundle_id: str, target: str) -> None:
    send_notification(
        REVIEW_BASE_URL,
        bundle_id,
        target,
        enable_osascript_fallback=parse_osascript_fallback_flag(OSASCRIPT_FALLBACK),
    )


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
    notification_target = parse_notification_target(NOTIFICATION_TARGET)
    seen: set[str] = set() if open_mode == "bundle" else current_pending_bundle_ids()

    print(f"승인 대기 명령 번들 감시 중: {PENDING_DIR}")
    print(f"승인 UI 주소: {REVIEW_BASE_URL}")
    print(f"브라우저 열기 모드: {open_mode}")
    print(f"macOS 알림: {'켜짐' if notify_enabled else '꺼짐'}")
    print(f"알림 클릭 대상: {notification_target}")
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
                    notify_pending_bundle(bundle_id, notification_target)
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
