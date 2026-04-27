from __future__ import annotations

import shutil
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

VALID_OPEN_MODES = {"dashboard_once", "bundle", "none"}
VALID_NOTIFICATION_TARGETS = {"bundle", "pending"}
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"", "0", "false", "no", "off"}

_terminal_notifier_warning_printed = False


def parse_bool_env(value: str | None, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def parse_open_mode(value: str | None) -> str:
    mode = (value or "dashboard_once").strip().lower()
    if mode not in VALID_OPEN_MODES:
        return "dashboard_once"
    return mode


def parse_notification_target(value: str | None) -> str:
    target = (value or "pending").strip().lower()
    if target not in VALID_NOTIFICATION_TARGETS:
        return "pending"
    return target


def sanitize_base_url(base_url: str) -> str:
    raw = (base_url or "http://127.0.0.1:8790").strip()
    parts = urlsplit(raw)
    if parts.scheme and parts.netloc:
        clean_path = parts.path.rstrip("/")
        return urlunsplit((parts.scheme, parts.netloc, clean_path, "", ""))

    return raw.split("?", 1)[0].split("#", 1)[0].rstrip("/")


def review_url(base_url: str, bundle_id: str) -> str:
    return f"{sanitize_base_url(base_url)}/bundles/{bundle_id}"


def pending_url(base_url: str) -> str:
    return f"{sanitize_base_url(base_url)}/pending"


def notification_url(base_url: str, bundle_id: str, target: str) -> str:
    normalized_target = parse_notification_target(target)
    if normalized_target == "pending":
        return pending_url(base_url)
    return review_url(base_url, bundle_id)


def build_terminal_notifier_command(base_url: str, bundle_id: str, target: str) -> list[str]:
    return [
        "terminal-notifier",
        "-title",
        "Workspace Terminal Bridge",
        "-message",
        f"승인 대기 번들: {bundle_id}",
        "-open",
        notification_url(base_url, bundle_id, target),
        "-group",
        "workspace-terminal-bridge",
    ]


def osascript_notification_command(bundle_id: str) -> list[str]:
    message = f"승인 대기 번들: {bundle_id}"
    escaped_message = message.replace("\\", "\\\\").replace('"', '\\"')
    escaped_title = "Workspace Terminal Bridge".replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{escaped_message}" with title "{escaped_title}"'
    return ["osascript", "-e", script]


def open_url(url: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", url], check=False)
    else:
        import webbrowser

        webbrowser.open(url)


def send_notification(
    base_url: str,
    bundle_id: str,
    target: str,
    *,
    enable_osascript_fallback: bool = False,
) -> bool:
    global _terminal_notifier_warning_printed

    if sys.platform != "darwin":
        return False

    if shutil.which("terminal-notifier"):
        command = build_terminal_notifier_command(base_url, bundle_id, target)
    elif enable_osascript_fallback:
        command = osascript_notification_command(bundle_id)
    else:
        if not _terminal_notifier_warning_printed:
            print(
                "Clickable macOS notifications require terminal-notifier. "
                "Install with: brew install terminal-notifier",
                file=sys.stderr,
            )
            _terminal_notifier_warning_printed = True
        return False

    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except Exception:
        return False

    return True
