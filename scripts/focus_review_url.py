#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from terminal_bridge.review_notifications import sanitize_base_url

BROWSERS = (
    "Brave Browser",
    "Google Chrome",
    "Safari",
    "Microsoft Edge",
)


def sanitize_target_url(value: str) -> str:
    raw = (value or "http://127.0.0.1:8790/pending").strip()
    parts = urlsplit(raw)
    if parts.scheme and parts.netloc:
        path = parts.path or "/"
        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    return raw.split("?", 1)[0].split("#", 1)[0]


def origin_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme and parts.netloc:
        return urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    return sanitize_base_url(value)


def fallback_open(target_url: str) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["open", target_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            webbrowser.open(target_url)
    except Exception:
        pass


def chrome_family_script(browser_name: str, target_url: str, base_url: str) -> str:
    browser = json.dumps(browser_name)
    target = json.dumps(target_url)
    base = json.dumps(base_url)
    return f"""
set browserName to {browser}
set targetURL to {target}
set baseURL to {base}

tell application "System Events"
  if not (exists process browserName) then return "not_running"
end tell

tell application {browser}
  repeat with w in windows
    set tabIndex to 0
    repeat with t in tabs of w
      set tabIndex to tabIndex + 1
      if (URL of t as text) starts with baseURL then
        set active tab index of w to tabIndex
        set index of w to 1
        set URL of t to targetURL
        activate
        return "focused"
      end if
    end repeat
  end repeat
end tell

return "not_found"
"""


def safari_script(target_url: str, base_url: str) -> str:
    target = json.dumps(target_url)
    base = json.dumps(base_url)
    return f"""
set targetURL to {target}
set baseURL to {base}

tell application "System Events"
  if not (exists process "Safari") then return "not_running"
end tell

tell application "Safari"
  repeat with w in windows
    repeat with t in tabs of w
      if (URL of t as text) starts with baseURL then
        set current tab of w to t
        set index of w to 1
        set URL of t to targetURL
        activate
        return "focused"
      end if
    end repeat
  end repeat
end tell

return "not_found"
"""


def run_osascript(script: str) -> str:
    completed = subprocess.run(
        ["osascript", "-e", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=3,
        check=False,
    )
    return completed.stdout.strip()


def focus_existing_tab(target_url: str, base_url: str) -> bool:
    if sys.platform != "darwin":
        return False

    for browser_name in BROWSERS:
        script = (
            safari_script(target_url, base_url)
            if browser_name == "Safari"
            else chrome_family_script(browser_name, target_url, base_url)
        )
        try:
            if run_osascript(script) == "focused":
                return True
        except Exception:
            continue

    return False


def main(argv: list[str]) -> int:
    target_url = sanitize_target_url(argv[1]) if len(argv) > 1 else "http://127.0.0.1:8790/pending"
    base_url = sanitize_base_url(argv[2]) if len(argv) > 2 else origin_url(target_url)

    if not focus_existing_tab(target_url, base_url):
        fallback_open(target_url)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
