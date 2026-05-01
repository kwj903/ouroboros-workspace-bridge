from __future__ import annotations

import shlex
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

VALID_OPEN_MODES = {"dashboard_once", "bundle", "none"}
VALID_NOTIFICATION_TARGETS = {"bundle", "pending"}
VALID_NOTIFICATION_CLICK_ACTIONS = {"focus", "open"}
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"", "0", "false", "no", "off"}

_terminal_notifier_warning_printed = False
_notification_warning_printed = False


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


def parse_notification_click_action(value: str | None) -> str:
    action = (value or "focus").strip().lower()
    if action not in VALID_NOTIFICATION_CLICK_ACTIONS:
        return "focus"
    return action


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


def focus_script_path() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts" / "focus_review_url.py"


def build_focus_execute_command(base_url: str, bundle_id: str, target: str) -> str:
    target_url = notification_url(base_url, bundle_id, target)
    clean_base_url = sanitize_base_url(base_url)
    parts = [
        sys.executable,
        str(focus_script_path()),
        target_url,
        clean_base_url,
    ]
    return " ".join(shlex.quote(part) for part in parts)


def build_terminal_notifier_command(
    base_url: str,
    bundle_id: str,
    target: str,
    click_action: str = "focus",
) -> list[str]:
    action = parse_notification_click_action(click_action)
    target_url = notification_url(base_url, bundle_id, target)
    action_args = (
        ["-execute", build_focus_execute_command(base_url, bundle_id, target)]
        if action == "focus"
        else ["-open", target_url]
    )

    return [
        "terminal-notifier",
        "-title",
        "Workspace Terminal Bridge",
        "-message",
        f"승인 대기 번들: {bundle_id}",
        *action_args,
        "-group",
        "workspace-terminal-bridge",
    ]


def osascript_notification_command(bundle_id: str) -> list[str]:
    message = f"승인 대기 번들: {bundle_id}"
    escaped_message = message.replace("\\", "\\\\").replace('"', '\\"')
    escaped_title = "Workspace Terminal Bridge".replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{escaped_message}" with title "{escaped_title}"'
    return ["osascript", "-e", script]


def build_notify_send_command(base_url: str, bundle_id: str, target: str) -> list[str]:
    target_url = notification_url(base_url, bundle_id, target)
    return [
        "notify-send",
        "Workspace Terminal Bridge",
        f"승인 대기 번들: {bundle_id}\n{target_url}",
    ]


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_powershell_notification_command(
    base_url: str,
    bundle_id: str,
    target: str,
    executable: str = "powershell",
) -> list[str]:
    target_url = notification_url(base_url, bundle_id, target)
    title = _powershell_quote("Workspace Terminal Bridge")
    message = _powershell_quote(f"승인 대기 번들: {bundle_id} {target_url}")
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "if (Get-Module -ListAvailable -Name BurntToast) { "
        f"Import-Module BurntToast; New-BurntToastNotification -Text {title}, {message}; exit 0 "
        "} "
        "exit 1"
    )
    return [
        executable,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]


def powershell_executable() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


def build_notification_command(
    base_url: str,
    bundle_id: str,
    target: str,
    *,
    click_action: str = "focus",
    enable_osascript_fallback: bool = False,
    platform: str | None = None,
) -> list[str] | None:
    current_platform = sys.platform if platform is None else platform

    if current_platform == "darwin":
        if shutil.which("terminal-notifier"):
            return build_terminal_notifier_command(base_url, bundle_id, target, click_action)
        if enable_osascript_fallback and shutil.which("osascript"):
            return osascript_notification_command(bundle_id)
        return None

    if current_platform.startswith("linux"):
        if shutil.which("notify-send"):
            return build_notify_send_command(base_url, bundle_id, target)
        return None

    if current_platform.startswith("win"):
        executable = powershell_executable()
        if executable:
            return build_powershell_notification_command(base_url, bundle_id, target, executable)
        return None

    return None


def build_open_url_command(url: str, *, platform: str | None = None) -> list[str] | None:
    current_platform = sys.platform if platform is None else platform
    if current_platform == "darwin":
        return ["open", url]
    if current_platform.startswith("linux") and shutil.which("xdg-open"):
        return ["xdg-open", url]
    return None


def open_url(url: str) -> None:
    try:
        if sys.platform.startswith("win") and hasattr(os, "startfile"):
            os.startfile(url)  # type: ignore[attr-defined]
            return

        command = build_open_url_command(url)
        if command is not None:
            subprocess.run(command, check=False)
            return

        webbrowser.open(url)
    except Exception:
        return None


def send_notification(
    base_url: str,
    bundle_id: str,
    target: str,
    *,
    click_action: str = "focus",
    enable_osascript_fallback: bool = False,
) -> bool:
    global _terminal_notifier_warning_printed, _notification_warning_printed

    command = build_notification_command(
        base_url,
        bundle_id,
        target,
        click_action=click_action,
        enable_osascript_fallback=enable_osascript_fallback,
    )
    if command is None:
        if sys.platform == "darwin" and not _terminal_notifier_warning_printed:
            print(
                "Clickable macOS notifications require terminal-notifier. "
                "Install with: brew install terminal-notifier, or enable osascript fallback.",
                file=sys.stderr,
            )
            _terminal_notifier_warning_printed = True
        elif sys.platform != "darwin" and not _notification_warning_printed:
            print(
                "Desktop notifications are unavailable on this platform or optional notification tools are missing.",
                file=sys.stderr,
            )
            _notification_warning_printed = True
        return False

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except Exception:
        return False

    return completed.returncode == 0
