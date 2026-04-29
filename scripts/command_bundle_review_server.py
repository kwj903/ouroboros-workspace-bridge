#!/usr/bin/env python3
from __future__ import annotations

import html
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from terminal_bridge.review_notifications import (
    open_url,
    parse_bool_env,
    parse_notification_click_action,
    parse_notification_target,
    parse_open_mode,
    pending_url as notification_pending_url,
    review_url as notification_review_url,
    send_notification,
)
from terminal_bridge import bundle_watcher
from terminal_bridge.approval_modes import (
    VALID_APPROVAL_MODES,
    load_approval_mode,
    normalize_approval_mode,
    save_approval_mode,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNNER = PROJECT_ROOT / "scripts" / "command_bundle_runner.py"

DEFAULT_RUNTIME_ROOT = Path.home() / ".mcp_terminal_bridge" / "my-terminal-tool"
RUNTIME_ROOT = Path(os.environ.get("MCP_TERMINAL_BRIDGE_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT))).expanduser()
COMMAND_BUNDLES_DIR = RUNTIME_ROOT / "command_bundles"
AUDIT_LOG = RUNTIME_ROOT / "audit.jsonl"
PENDING_DIR = COMMAND_BUNDLES_DIR / "pending"
APPLIED_DIR = COMMAND_BUNDLES_DIR / "applied"
REJECTED_DIR = COMMAND_BUNDLES_DIR / "rejected"
FAILED_DIR = COMMAND_BUNDLES_DIR / "failed"
SUPERVISOR_SERVICES = ("review", "mcp", "ngrok")
SUPERVISOR_RESTARTABLE_SERVICES = {"mcp", "ngrok"}
SUPERVISOR_SERVICE_ACTIONS = {"start", "stop", "restart"}

HOST = os.environ.get("BUNDLE_REVIEW_HOST", "127.0.0.1")
PORT = int(os.environ.get("BUNDLE_REVIEW_PORT", "8790"))
EVENT_POLL_SECONDS = 0.5
EVENT_TIMEOUT_SECONDS = 25.0
VALID_STATUS_FILTERS = {"all", "pending", "applied", "failed", "rejected"}
VALID_SERVER_TABS = {"overview", "services", "processes", "connection", "environment", "tools", "diagnostics"}
SERVER_TAB_LABELS = {
    "overview": "개요",
    "services": "서버",
    "processes": "프로세스",
    "connection": "연결",
    "environment": "환경",
    "tools": "로컬 도구",
    "diagnostics": "진단",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def bundle_dirs() -> list[Path]:
    return [PENDING_DIR, APPLIED_DIR, REJECTED_DIR, FAILED_DIR]


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_bundle(bundle_id: str) -> tuple[Path, dict[str, object]]:
    for directory in bundle_dirs():
        path = directory / f"{bundle_id}.json"
        if path.exists():
            return path, read_json(path)
    raise FileNotFoundError(f"Bundle not found: {bundle_id}")


def normalize_status_filter(value: str | None) -> str:
    status = (value or "all").strip().lower()
    if status not in VALID_STATUS_FILTERS:
        return "all"
    return status


def normalize_server_tab(value: str | None) -> str:
    tab = (value or "overview").strip().lower()
    if tab not in VALID_SERVER_TABS:
        return "overview"
    return tab


def list_bundles(status_filter: str = "all") -> list[dict[str, object]]:
    status_filter = normalize_status_filter(status_filter)
    rows: list[dict[str, object]] = []

    for directory in bundle_dirs():
        directory_status = directory.name
        if status_filter != "all" and directory_status != status_filter:
            continue

        if not directory.exists():
            continue

        for path in directory.glob("cmd-*.json"):
            try:
                record = read_json(path)
            except Exception:
                continue
            record["_file"] = str(path)
            record["_directory_status"] = directory_status
            rows.append(record)

    rows.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return rows


def pending_bundles() -> list[dict[str, object]]:
    return list_bundles("pending")


def latest_pending_bundle_id() -> str | None:
    rows = pending_bundles()
    if not rows:
        return None
    bundle_id = rows[0].get("bundle_id")
    return str(bundle_id) if bundle_id else None


def command_bundle_revision() -> str:
    parts: list[str] = []

    for directory in bundle_dirs():
        if not directory.exists():
            continue

        for path in sorted(directory.glob("cmd-*.json")):
            status = directory.name
            bundle_id = path.stem
            updated_at = ""
            try:
                record = read_json(path)
                status = str(record.get("status", status))
                bundle_id = str(record.get("bundle_id", bundle_id))
                updated_at = str(record.get("updated_at", ""))
            except Exception:
                updated_at = ""

            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                mtime_ns = 0

            parts.append(f"{status}\t{path.name}\t{bundle_id}\t{updated_at}\t{mtime_ns}")

    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def command_bundle_state() -> dict[str, object]:
    pending = pending_bundles()
    return {
        "revision": command_bundle_revision(),
        "pending_count": len(pending),
        "latest_pending_bundle_id": str(pending[0].get("bundle_id", "")) if pending else None,
    }


def load_bundle_id(path: Path) -> str | None:
    return bundle_watcher.load_bundle_id(path)


def current_pending_bundle_ids() -> set[str]:
    return bundle_watcher.current_pending_bundle_ids(PENDING_DIR)


def bundle_status_counts() -> dict[str, int]:
    counts = {
        "pending": 0,
        "applied": 0,
        "failed": 0,
        "rejected": 0,
        "all": 0,
    }

    for record in list_bundles("all"):
        status = str(record.get("status", record.get("_directory_status", "unknown")))
        if status in counts and status != "all":
            counts[status] += 1
        counts["all"] += 1

    return counts


def latest_bundle_id(status: str) -> str | None:
    rows = list_bundles(status)
    if not rows:
        return None
    bundle_id = rows[0].get("bundle_id")
    return str(bundle_id) if bundle_id else None


def latest_updated_at() -> str | None:
    rows = list_bundles("all")
    if not rows:
        return None
    updated_at = rows[0].get("updated_at")
    return str(updated_at) if updated_at else None


def step_result_status(step: dict[str, object]) -> str:
    if "exit_code" not in step or step.get("exit_code") is None:
        return "unknown"
    return "success" if step.get("exit_code") == 0 else "failed"


def short_error(value: object, max_chars: int = 160) -> str:
    text = str(value or "").strip()
    if max_chars < 1:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def mask_sensitive_text(value: object) -> str:
    text = str(value or "")
    for secret in (os.environ.get("MCP_ACCESS_TOKEN", ""), os.environ.get("NGROK_AUTHTOKEN", "")):
        if secret:
            text = text.replace(secret, "[redacted]")

    replacements = (
        (r"access_token=([^\s&\"'<>]+)", "access_token=[redacted]"),
        (r"Authorization:\s*Bearer\s+([^\s\"'<>]+)", "Authorization: Bearer [redacted]"),
        (r"Bearer\s+([^\s\"'<>]+)", "Bearer [redacted]"),
        (r"(MCP_ACCESS_TOKEN=)([^\s\"'<>]+)", r"\1[redacted]"),
        (r"(NGROK_AUTHTOKEN=)([^\s\"'<>]+)", r"\1[redacted]"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


def summarize_bundle_result(record: dict[str, object]) -> dict[str, object]:
    steps = record.get("steps")
    result = record.get("result")
    result_steps: list[dict[str, object]] = []

    if isinstance(result, dict) and isinstance(result.get("steps"), list):
        result_steps = [step for step in result["steps"] if isinstance(step, dict)]

    failed_step_count = sum(1 for step in result_steps if step_result_status(step) == "failed")

    return {
        "command_count": len(steps) if isinstance(steps, list) else 0,
        "result_step_count": len(result_steps),
        "failed_step_count": failed_step_count,
        "error_summary": short_error(record.get("error")),
    }


def compact_tail(value: object, max_chars: int = 800) -> str:
    text = mask_sensitive_text(value)
    if len(text) <= max_chars:
        return text
    return text[-max_chars:].lstrip()


def bundle_result_tails(record: dict[str, object], max_chars: int = 800) -> tuple[str, str]:
    result = record.get("result")
    if not isinstance(result, dict):
        return "", ""

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    steps = result.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            stdout = step.get("stdout")
            stderr = step.get("stderr")
            if stdout:
                stdout_parts.append(str(stdout))
            if stderr:
                stderr_parts.append(str(stderr))

    return compact_tail("\n".join(stdout_parts), max_chars), compact_tail("\n".join(stderr_parts), max_chars)


def copy_for_chatgpt_summary(record: dict[str, object]) -> dict[str, object]:
    status = str(record.get("status", "unknown"))
    error = record.get("error")
    stdout_tail, stderr_tail = bundle_result_tails(record)

    ok: bool | None
    next_step: str
    if status == "applied" and not error:
        ok = True
        next_step = "continue"
    elif status == "failed":
        ok = False
        next_step = "fix_failure"
    elif status == "rejected":
        ok = False
        next_step = "inspect_logs"
    else:
        ok = None
        next_step = "continue"

    return {
        "bundle_id": str(record.get("bundle_id", "")),
        "status": status,
        "ok": ok,
        "risk": str(record.get("risk", "unknown")),
        "title": str(record.get("title", "")),
        "next": next_step,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail or compact_tail(error),
    }


def history_state() -> dict[str, object]:
    return {
        "counts": bundle_status_counts(),
        "latest_failed_bundle_id": latest_bundle_id("failed"),
        "latest_updated_at": latest_updated_at(),
    }


SENSITIVE_TEXT_MARKERS = (
    "access_token",
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
)


def safe_audit_text(value: object, max_chars: int = 180) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if text == "":
        return None

    lowered = text.lower()
    if any(marker in lowered for marker in SENSITIVE_TEXT_MARKERS):
        return "[redacted]"

    return short_error(text, max_chars=max_chars)


def summarize_audit_command(value: object) -> str | None:
    if isinstance(value, list):
        parts = [safe_audit_text(item, max_chars=80) or "" for item in value[:6]]
        if len(value) > 6:
            parts.append("...")
        summary = " ".join(part for part in parts if part)
        return summary or None

    return safe_audit_text(value, max_chars=180)


def sanitize_audit_event(record: dict[str, object]) -> dict[str, object]:
    return {
        "ts": safe_audit_text(record.get("ts")),
        "event": safe_audit_text(record.get("event")),
        "bundle_id": safe_audit_text(record.get("bundle_id")),
        "title": safe_audit_text(record.get("title")),
        "cwd": safe_audit_text(record.get("cwd")),
        "risk": safe_audit_text(record.get("risk")),
        "exit_code": record.get("exit_code") if type(record.get("exit_code")) is int else None,
        "truncated": record.get("truncated") if type(record.get("truncated")) is bool else None,
        "command": summarize_audit_command(record.get("command")),
    }


def recent_audit_events(limit: int = 20) -> list[dict[str, object]]:
    if limit < 1 or not AUDIT_LOG.exists():
        return []

    lines: deque[str] = deque(maxlen=limit * 4)
    try:
        with AUDIT_LOG.open("r", encoding="utf-8") as f:
            for line in f:
                lines.append(line)
    except OSError:
        return []

    events: list[dict[str, object]] = []
    for line in reversed(lines):
        if len(events) >= limit:
            break
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        events.append(sanitize_audit_event(record))

    return events


def audit_state() -> dict[str, object]:
    events = recent_audit_events(20)
    return {
        "count": len(events),
        "events": events,
    }


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def env_status(name: str) -> str:
    return "set" if os.environ.get(name) else "missing"


def env_any_status(names: list[str]) -> str:
    return "set" if any(os.environ.get(name) for name in names) else "missing"


def env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


def review_base_url() -> str:
    return os.environ.get("BUNDLE_REVIEW_BASE_URL", f"http://{HOST}:{PORT}")


def embedded_watcher_config() -> dict[str, object]:
    return {
        "enabled": parse_bool_env(os.environ.get("BUNDLE_REVIEW_EMBEDDED_WATCHER"), default=True),
        "poll_seconds": env_float("BUNDLE_WATCH_POLL_SECONDS", 1.5),
        "open_mode": parse_open_mode(os.environ.get("BUNDLE_WATCH_OPEN_MODE")),
        "notify_enabled": parse_bool_env(os.environ.get("BUNDLE_WATCH_NOTIFY"), default=True),
        "notification_target": parse_notification_target(os.environ.get("BUNDLE_WATCH_NOTIFICATION_TARGET")),
        "notification_click_action": parse_notification_click_action(
            os.environ.get("BUNDLE_WATCH_NOTIFICATION_CLICK_ACTION")
        ),
        "osascript_fallback": parse_bool_env(
            os.environ.get("BUNDLE_WATCH_OSASCRIPT_FALLBACK"),
            default=False,
        ),
        "base_url": review_base_url(),
    }


def normalize_ngrok_host(value: str) -> str:
    host = value.strip()
    host = host.removeprefix("https://").removeprefix("http://")
    host = host.split("/", 1)[0]
    host = host.split("?", 1)[0]
    host = host.split("#", 1)[0]
    return host


def public_mcp_endpoint_hint() -> str | None:
    raw_host = os.environ.get("NGROK_HOST") or os.environ.get("NGROK_BASE_URL")
    if not raw_host:
        return None

    host = normalize_ngrok_host(raw_host)
    if host == "":
        return None

    return f"https://{host}/mcp"


def tcp_port_reachable(host: str, port: int, timeout_seconds: float = 0.5) -> bool:
    if port < 1 or port > 65535:
        return False

    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def supervisor_process_dir() -> Path:
    return RUNTIME_ROOT / "processes"


def supervisor_pid_file(service: str) -> Path:
    return supervisor_process_dir() / f"{service}.pid"


def supervisor_log_file(service: str) -> Path:
    return supervisor_process_dir() / f"{service}.log"


def read_supervisor_pid(path: Path) -> int | None:
    try:
        raw_pid = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if not raw_pid.isdigit():
        return None

    try:
        return int(raw_pid)
    except ValueError:
        return None


def pid_is_alive(pid: int | None) -> bool:
    if pid is None or pid < 1:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def supervisor_service_endpoint(service: str) -> tuple[str | None, int | None]:
    if service == "review":
        return os.environ.get("BUNDLE_REVIEW_HOST", HOST), env_int("BUNDLE_REVIEW_PORT", PORT)
    if service == "mcp":
        return os.environ.get("MCP_HOST", "127.0.0.1"), env_int("MCP_PORT", 8787)
    return None, None


def supervisor_service_state(service: str) -> dict[str, object]:
    pid_file = supervisor_pid_file(service)
    log_file = supervisor_log_file(service)
    pid_file_exists = pid_file.exists()
    pid = read_supervisor_pid(pid_file) if pid_file_exists else None
    alive = pid_is_alive(pid)
    state = "yes" if alive else "stale" if pid_file_exists else "no"
    host, port = supervisor_service_endpoint(service)
    reachable: bool | None
    if host is not None and port is not None:
        reachable = tcp_port_reachable(host, port, timeout_seconds=0.2)
    else:
        reachable = None

    return {
        "name": service,
        "pid": pid,
        "alive": alive,
        "state": state,
        "managed": alive,
        "managed_state": state,
        "reachable": reachable,
        "host": host,
        "port": port,
        "pid_file": str(pid_file),
        "log_file": str(log_file),
    }


def supervisor_state() -> dict[str, object]:
    process_dir = supervisor_process_dir()
    return {
        "runtime_root": str(RUNTIME_ROOT),
        "process_dir": str(process_dir),
        "services": [supervisor_service_state(service) for service in SUPERVISOR_SERVICES],
    }


def server_state() -> dict[str, object]:
    mcp_host = os.environ.get("MCP_HOST", "127.0.0.1")
    mcp_port = env_int("MCP_PORT", 8787)
    review_host = os.environ.get("BUNDLE_REVIEW_HOST", HOST)
    review_port = env_int("BUNDLE_REVIEW_PORT", PORT)
    public_endpoint = public_mcp_endpoint_hint()
    watcher_config = embedded_watcher_config()

    return {
        "review_server": {
            "status": "running",
            "url": f"http://{review_host}:{review_port}/pending",
            "pid": os.getpid(),
        },
        "review_dashboard": {
            "pending_url": "/pending",
            "history_url": "/bundles?status=all",
        },
        "tools": {
            "uv": command_exists("uv"),
            "ngrok": command_exists("ngrok"),
            "terminal_notifier": command_exists("terminal-notifier"),
        },
        "environment": {
            "mcp_access_token": env_status("MCP_ACCESS_TOKEN"),
            "ngrok_host": env_any_status(["NGROK_HOST", "NGROK_BASE_URL"]),
            "mcp_host": mcp_host,
            "mcp_port": mcp_port,
            "bundle_review_host": review_host,
            "bundle_review_port": review_port,
        },
        "mcp_server": {
            "reachable": tcp_port_reachable(mcp_host, mcp_port),
            "url": f"http://{mcp_host}:{mcp_port}/mcp",
        },
        "ngrok": {
            "installed": command_exists("ngrok"),
            "configured": env_any_status(["NGROK_HOST", "NGROK_BASE_URL"]),
            "public_mcp_endpoint_hint": public_endpoint,
        },
        "embedded_watcher": {
            "enabled": watcher_config["enabled"],
            "open_mode": watcher_config["open_mode"],
            "notify_enabled": watcher_config["notify_enabled"],
            "notification_target": watcher_config["notification_target"],
            "notification_click_action": watcher_config["notification_click_action"],
            "poll_seconds": watcher_config["poll_seconds"],
        },
        "supervisor": supervisor_state(),
    }


def embedded_watcher_loop(
    stop_event: threading.Event,
    seen_pending_bundle_ids: set[str],
    config: dict[str, object],
) -> None:
    base_url = str(config.get("base_url", review_base_url()))
    open_mode = str(config.get("open_mode", "dashboard_once"))
    notify_enabled = bool(config.get("notify_enabled", True))
    notification_target = str(config.get("notification_target", "pending"))
    notification_click_action = str(config.get("notification_click_action", "focus"))
    poll_seconds = float(config.get("poll_seconds", 1.5))
    osascript_fallback = bool(config.get("osascript_fallback", False))

    def notify_bundle(bundle_id: str) -> None:
        send_notification(
            base_url,
            bundle_id,
            notification_target,
            click_action=notification_click_action,
            enable_osascript_fallback=osascript_fallback,
        )

    def open_bundle(bundle_id: str) -> None:
        url = notification_review_url(base_url, bundle_id)
        print(f"[review-ui] 승인 페이지 열기: {bundle_id}: {url}")
        open_url(url)

    bundle_watcher.watch_pending_bundles(
        pending_dir=PENDING_DIR,
        runner=RUNNER,
        project_root=PROJECT_ROOT,
        seen_bundle_ids=seen_pending_bundle_ids,
        poll_seconds=poll_seconds,
        notify_enabled=notify_enabled,
        notify_bundle=notify_bundle,
        open_mode=open_mode,
        open_bundle=open_bundle,
        stop_event=stop_event,
        log_prefix="[review-ui] ",
    )


def start_embedded_watcher() -> tuple[threading.Event | None, threading.Thread | None]:
    config = embedded_watcher_config()
    if not bool(config["enabled"]):
        print("[review-ui] Embedded watcher disabled.")
        return None, None

    base_url = str(config["base_url"])
    open_mode = str(config["open_mode"])

    if open_mode == "dashboard_once":
        url = notification_pending_url(base_url)
        print(f"[review-ui] 승인 대기 대시보드 열기: {url}")
        open_url(url)

    seen_pending_bundle_ids = current_pending_bundle_ids()
    stop_event = threading.Event()
    thread = threading.Thread(
        target=embedded_watcher_loop,
        args=(stop_event, seen_pending_bundle_ids, config),
        name="command-bundle-embedded-watcher",
        daemon=True,
    )
    thread.start()

    print("[review-ui] Embedded watcher enabled.")
    print(f"[review-ui] 브라우저 열기 모드: {open_mode}")
    print(f"[review-ui] macOS 알림: {'켜짐' if config['notify_enabled'] else '꺼짐'}")
    print(f"[review-ui] 알림 클릭 대상: {config['notification_target']}")
    print(f"[review-ui] 알림 클릭 동작: {config['notification_click_action']}")
    return stop_event, thread


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def status_label(value: object) -> str:
    mapping = {
        "pending": "승인 대기",
        "applied": "적용 완료",
        "failed": "실패",
        "rejected": "거절됨",
        "unknown": "알 수 없음",
    }
    return mapping.get(str(value), str(value))


def risk_label(value: object) -> str:
    mapping = {
        "low": "낮음",
        "medium": "주의 필요",
        "high": "높음",
        "blocked": "차단됨",
        "unknown": "알 수 없음",
    }
    return mapping.get(str(value), str(value))


def bool_label(value: object) -> str:
    return "예" if bool(value) else "아니오"


def status_filter_links_html(current: str) -> str:
    current = normalize_status_filter(current)
    labels = {
        "all": "전체",
        "pending": "승인 대기",
        "applied": "적용 완료",
        "failed": "실패",
        "rejected": "거절됨",
    }
    links: list[str] = []
    for status in ("all", "pending", "applied", "failed", "rejected"):
        label = labels[status]
        if status == current:
            links.append(
                f'<span class="subnav-link is-active" aria-current="page">{escape(label)}</span>'
            )
        else:
            links.append(
                f'<a class="subnav-link" href="/bundles?status={escape(status)}">{escape(label)}</a>'
            )
    return '<div class="subnav"><span class="meta-label">필터</span>' + "".join(links) + "</div>"


def primary_nav_html(active: str) -> str:
    items = (
        ("pending", "/pending", "승인"),
        ("history", "/history", "이력/결과"),
        ("servers", "/servers", "관리"),
    )
    links: list[str] = []
    for key, href, label in items:
        classes = ["nav-link"]
        aria = ""
        if key == active:
            classes.append("is-active")
            aria = ' aria-current="page"'
        links.append(
            f'<a class="{" ".join(classes)}" href="{escape(href)}"{aria}>{escape(label)}</a>'
        )
    return '<nav class="nav">' + "".join(links) + "</nav>"


def management_nav_html(current_tab: str) -> str:
    current_tab = normalize_server_tab(current_tab)
    links: list[str] = []
    for tab in ("overview", "services", "processes", "connection", "environment", "tools", "diagnostics"):
        classes = ["side-link"]
        aria = ""
        if tab == current_tab:
            classes.append("is-active")
            aria = ' aria-current="page"'
        links.append(
            f'<a class="{" ".join(classes)}" href="/servers?tab={escape(tab)}"{aria}>'
            f"{escape(SERVER_TAB_LABELS[tab])}</a>"
        )
    return '<div class="side-nav">' + "".join(links) + "</div>"


def status_badge(label: str, tone: str) -> str:
    allowed_tones = {"ok", "warn", "danger", "neutral"}
    safe_tone = tone if tone in allowed_tones else "neutral"
    return f'<span class="badge {escape(safe_tone)}">{escape(label)}</span>'


def status_chip(label: str, tone: str) -> str:
    return status_badge(label, tone)


def approval_mode_label(mode: str) -> str:
    return {
        "normal": "Normal",
        "safe-auto": "Safe Auto",
        "yolo": "YOLO",
    }.get(normalize_approval_mode(mode), "Normal")


def approval_mode_banner_html(mode: str) -> str:
    current = normalize_approval_mode(mode)
    if current == "safe-auto":
        return (
            '<div class="banner info">'
            "Safe Auto mode is ON. Low-risk command-only check bundles may be auto-approved."
            "</div>"
        )
    if current == "yolo":
        return (
            '<div class="banner warning">'
            "YOLO mode is ON. Pending bundles may be auto-approved except blocked-risk bundles."
            "</div>"
        )
    return ""


def approval_mode_card_html(current_mode: str | None = None) -> str:
    current = normalize_approval_mode(current_mode or load_approval_mode())
    choices = [
        (
            "normal",
            "Normal",
            "수동 승인만 사용합니다. Pending bundle은 기존처럼 직접 승인해야 합니다.",
            "neutral",
        ),
        (
            "safe-auto",
            "Safe Auto",
            "보수적으로 low-risk command-only 확인 bundle만 자동 승인합니다.",
            "ok",
        ),
        (
            "yolo",
            "YOLO",
            "blocked risk를 제외한 pending bundle을 자동 승인할 수 있습니다. 명시 확인이 필요합니다.",
            "danger",
        ),
    ]
    items: list[str] = []
    for mode, label, description, tone in choices:
        selected = mode == current
        warning_class = " warning" if mode == "yolo" else ""
        selected_class = " selected" if selected else ""
        button_class = "reject" if mode == "yolo" else "secondary"
        button_text = "현재 모드" if selected else ("확인 후 켜기" if mode == "yolo" else "선택")
        items.append(
            f"""
            <div class="mode-option{selected_class}{warning_class}">
              <div>
                <div class="mode-title">
                  <span>{escape(label)}</span>
                  {status_badge("active", tone) if selected else ""}
                </div>
                <p class="meta">{escape(description)}</p>
              </div>
              <form method="post" action="/settings/approval-mode">
                <input type="hidden" name="mode" value="{escape(mode)}">
                <button class="{button_class}" type="submit">{escape(button_text)}</button>
              </form>
            </div>
            """
        )

    return f"""
    <div class="card">
      <h2>Approval mode</h2>
      <p class="meta">현재 모드: <strong>{escape(approval_mode_label(current))}</strong></p>
      <div class="mode-grid">
        {''.join(items)}
      </div>
    </div>
    """


def approval_mode_confirm_html() -> str:
    return """
    <p><a href="/pending">← 승인 대기로 돌아가기</a></p>
    <div class="card">
      <h2>YOLO mode 확인</h2>
      <p class="meta">
        YOLO mode는 blocked risk를 제외한 pending bundle을 자동 승인할 수 있습니다.
        이 모드는 기본값이 아니며, 신뢰할 수 있는 짧은 작업 중에만 사용하세요.
      </p>
      <form method="post" action="/settings/approval-mode">
        <input type="hidden" name="mode" value="yolo">
        <label for="confirm-yolo"><strong>계속하려면 YOLO를 입력하세요.</strong></label><br>
        <input id="confirm-yolo" name="confirm" autocomplete="off" style="margin-top: 10px; padding: 10px; width: min(260px, 100%);">
        <div class="button-row">
          <button class="reject" type="submit">YOLO mode 켜기</button>
          <a class="nav-link" href="/pending">취소</a>
        </div>
      </form>
    </div>
    """


def bool_chip(value: object, true_label: str = "예", false_label: str = "아니오") -> str:
    return status_chip(true_label if bool(value) else false_label, "ok" if bool(value) else "warn")


def set_missing_chip(value: object) -> str:
    return status_chip("set" if value == "set" else "missing", "ok" if value == "set" else "warn")


def kv_row_html(
    label: str,
    value: object,
    *,
    code_value: bool = False,
    value_is_html: bool = False,
) -> str:
    if value_is_html:
        content = str(value)
    elif code_value:
        content = f"<code>{escape(value)}</code>"
    else:
        content = escape(value)

    return (
        '<div class="kv-row">'
        f'<div class="kv-label">{escape(label)}</div>'
        f'<div class="kv-value">{content}</div>'
        "</div>"
    )


def audit_event_summary_html(event: dict[str, object]) -> str:
    parts: list[str] = []

    for key, label in (
        ("bundle_id", "bundle"),
        ("title", "title"),
        ("cwd", "cwd"),
        ("command", "command"),
        ("risk", "risk"),
        ("exit_code", "exit"),
        ("truncated", "truncated"),
    ):
        value = event.get(key)
        if value is None or value == "":
            continue
        parts.append(f"<span><strong>{escape(label)}:</strong> {escape(value)}</span>")

    return " · ".join(parts) if parts else '<span class="meta">요약 없음</span>'


def recent_audit_events_html(limit: int = 10) -> str:
    events = recent_audit_events(limit)
    if not events:
        return '<p class="meta">최근 audit event가 없습니다.</p>'

    rows = []
    for event in events:
        rows.append(
            "<tr>"
            f"<td><code>{escape(event.get('ts') or '')}</code></td>"
            f"<td>{escape(event.get('event') or '')}</td>"
            f"<td>{audit_event_summary_html(event)}</td>"
            "</tr>"
        )

    return (
        '<div class="table-wrap">'
        '<table class="data-table">'
        "<thead><tr><th>시간</th><th>이벤트</th><th>요약</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
    )


def state_tone(state: object) -> str:
    if state in {"yes", True}:
        return "ok"
    if state == "stale":
        return "warn"
    if state is False:
        return "warn"
    return "neutral"


def reachable_badge(value: object) -> str:
    if value is True:
        return status_badge("yes", "ok")
    if value is False:
        return status_badge("no", "warn")
    return status_badge("not checked", "neutral")


def process_path_cell_html(value: object) -> str:
    path = str(value or "")
    if path == "":
        return "<code>none</code>"

    label = Path(path).name or path
    return f'<code title="{escape(path)}">{escape(label)}</code>'


def supervisor_control_html(service: str, state: str) -> str:
    if service not in SUPERVISOR_RESTARTABLE_SERVICES:
        return '<span class="meta">terminal only</span>'

    safe_service = escape(service)
    actions = (("stop", "Stop"), ("restart", "Restart")) if state == "yes" else (("start", "Start"),)
    buttons = []
    for action, label in actions:
        buttons.append(
            f'<form class="inline" method="post" action="/servers/processes/{action}/{safe_service}">'
            f'<button class="secondary" type="submit">{label}</button>'
            '</form>'
        )
    return '<div class="service-controls">' + "".join(buttons) + '</div>'


def supervisor_processes_html(state: dict[str, object]) -> str:
    services = state.get("services")
    if not isinstance(services, list):
        services = []

    rows: list[str] = []
    for item in services:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        pid = item.get("pid")
        pid_label = str(pid) if pid is not None else "none"
        alive_state = str(item.get("state", "no"))
        managed_state = str(item.get("managed_state", alive_state))
        host = item.get("host")
        port = item.get("port")
        endpoint = f"{host}:{port}" if host and port else "not checked"
        rows.append(
            "<tr>"
            f"<td><strong>{escape(name)}</strong></td>"
            f"<td><code>{escape(pid_label)}</code></td>"
            f"<td>{status_badge(alive_state, state_tone(alive_state))}</td>"
            f"<td>{status_badge(managed_state, state_tone(managed_state))}</td>"
            f"<td>{reachable_badge(item.get('reachable'))}</td>"
            f"<td><code>{escape(endpoint)}</code></td>"
            f"<td>{process_path_cell_html(item.get('log_file'))}</td>"
            f"<td>{process_path_cell_html(item.get('pid_file'))}</td>"
            f"<td>{supervisor_control_html(name, alive_state)}</td>"
            "</tr>"
        )

    if not rows:
        return '<p class="meta">Supervisor process 상태가 없습니다.</p>'

    return (
        '<div class="table-wrap">'
        '<table class="data-table process-table">'
        "<thead><tr>"
        "<th>Service</th><th>PID</th><th>Alive</th><th>Managed</th>"
        "<th>Reachable</th><th>Endpoint</th><th>Log path</th><th>PID file</th><th>Controls</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
    )


def app_shell(
    title: str,
    body: str,
    active_nav: str,
    subtitle: str = "",
    server_tab: str | None = None,
) -> bytes:
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --surface: rgba(127, 127, 127, 0.08);
      --surface-strong: rgba(127, 127, 127, 0.12);
      --border: rgba(127, 127, 127, 0.24);
      --accent: #2563eb;
      --accent-soft: rgba(37, 99, 235, 0.12);
      --success: #15803d;
      --warning: #b45309;
      --danger: #dc2626;
    }}
    body {{
      margin: 0 auto;
      padding: 0;
      line-height: 1.6;
      background:
        linear-gradient(180deg, rgba(127, 127, 127, 0.05), transparent 260px);
    }}
    :focus-visible {{
      outline: 3px solid rgba(37, 99, 235, 0.45);
      outline-offset: 3px;
    }}
    .app-shell {{
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      min-height: 100vh;
    }}
    .sidebar {{
      border-right: 1px solid var(--border);
      padding: 28px 20px;
      background: rgba(127, 127, 127, 0.05);
    }}
    .brand {{
      display: grid;
      gap: 4px;
      margin-bottom: 24px;
    }}
    .brand-title {{
      font-size: 18px;
      font-weight: 800;
      line-height: 1.25;
    }}
    .brand-subtitle {{
      color: inherit;
      opacity: 0.72;
      font-size: 14px;
    }}
    .sidebar-section {{
      display: grid;
      gap: 10px;
      margin-top: 18px;
    }}
    .sidebar-label {{
      color: inherit;
      opacity: 0.62;
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .main-content {{
      min-width: 0;
      padding: 32px min(5vw, 56px) 56px;
    }}
    .content-inner {{
      display: grid;
      gap: 22px;
      max-width: 1040px;
    }}
    .page-header {{
      display: grid;
      gap: 8px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(1.8rem, 3vw, 2.35rem);
      line-height: 1.2;
    }}
    h2, h3 {{
      margin-top: 0;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .nav {{
      display: grid;
      gap: 8px;
    }}
    .nav-link {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: inherit;
      font-weight: 700;
    }}
    .nav-link:hover,
    .nav-link.is-active {{
      text-decoration: none;
    }}
    .nav-link.is-active {{
      color: var(--accent);
      background: var(--accent-soft);
      border-color: rgba(37, 99, 235, 0.28);
    }}
    .subnav {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin: 12px 0 18px;
    }}
    .subnav-link {{
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: inherit;
      font-size: 14px;
      font-weight: 600;
    }}
    .subnav-link.is-active {{
      color: var(--accent);
      background: var(--accent-soft);
      border-color: rgba(37, 99, 235, 0.28);
    }}
    .meta,
    .meta-label {{
      opacity: 0.78;
      font-size: 14px;
    }}
    .card,
    .metric,
    .notice {{
      border: 1px solid var(--border);
      border-radius: 16px;
      background: var(--surface);
    }}
    .card {{
      padding: 20px;
      margin: 0;
    }}
    .card.is-failed {{
      border-color: rgba(220, 38, 38, 0.36);
      background: rgba(220, 38, 38, 0.07);
    }}
    .metric {{
      padding: 18px;
    }}
    .metric-link {{
      display: block;
      color: inherit;
    }}
    .metric-link:hover {{
      text-decoration: none;
      border-color: rgba(37, 99, 235, 0.32);
    }}
    .metric-value {{
      font-size: 28px;
      font-weight: 800;
      line-height: 1.1;
      margin: 8px 0 4px;
    }}
    .notice {{
      padding: 16px 18px;
    }}
    .stack {{
      display: grid;
      gap: 16px;
    }}
    .card-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }}
    .section-title {{
      display: grid;
      gap: 6px;
      margin-bottom: 4px;
    }}
    .side-nav {{
      display: grid;
      gap: 8px;
    }}
    .side-link {{
      display: block;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: inherit;
      font-weight: 600;
    }}
    .side-link:hover,
    .side-link.is-active {{
      text-decoration: none;
    }}
    .side-link.is-active {{
      color: var(--accent);
      background: var(--accent-soft);
      border-color: rgba(37, 99, 235, 0.28);
    }}
    .kv {{
      display: grid;
      gap: 0;
    }}
    .kv-row {{
      display: grid;
      grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
      gap: 16px;
      align-items: start;
      padding: 12px 0;
      border-top: 1px solid var(--border);
    }}
    .kv-row:first-child {{
      border-top: 0;
      padding-top: 0;
    }}
    .kv-label {{
      font-weight: 700;
      min-width: 0;
      overflow-wrap: anywhere;
    }}
    .kv-value {{
      min-width: 0;
      display: flex;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 8px;
      overflow-wrap: anywhere;
    }}
    .table-wrap {{
      width: 100%;
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: var(--surface);
    }}
    .data-table {{
      width: 100%;
      min-width: 760px;
      border-collapse: collapse;
    }}
    .data-table th,
    .data-table td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
    }}
    .data-table th {{
      font-size: 13px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      opacity: 0.72;
    }}
    .data-table tbody tr:last-child td {{
      border-bottom: 0;
    }}
    .process-table {{
      min-width: 1160px;
      table-layout: fixed;
    }}
    .process-table th:nth-child(1),
    .process-table td:nth-child(1) {{
      width: 88px;
    }}
    .process-table th:nth-child(2),
    .process-table td:nth-child(2) {{
      width: 72px;
      white-space: nowrap;
    }}
    .process-table th:nth-child(3),
    .process-table td:nth-child(3),
    .process-table th:nth-child(4),
    .process-table td:nth-child(4),
    .process-table th:nth-child(5),
    .process-table td:nth-child(5) {{
      width: 108px;
      white-space: nowrap;
    }}
    .process-table th:nth-child(6),
    .process-table td:nth-child(6) {{
      width: 116px;
    }}
    .process-table td:nth-child(2) code,
    .process-table td:nth-child(6) code {{
      word-break: normal;
      white-space: nowrap;
    }}
    .process-table td:nth-child(7) code,
    .process-table td:nth-child(8) code {{
      word-break: break-word;
      overflow-wrap: anywhere;
    }}
    .process-table th:nth-child(9),
    .process-table td:nth-child(9) {{
      width: 240px;
      white-space: nowrap;
    }}
    .service-controls {{
      display: inline-flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .service-controls button {{
      padding: 7px 10px;
      font-size: 13px;
    }}
    .mode-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .mode-option {{
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 12px;
      min-height: 170px;
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
    }}
    .mode-option.selected {{
      border-color: rgba(37, 99, 235, 0.55);
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }}
    .mode-option.warning {{
      border-color: rgba(220, 38, 38, 0.28);
    }}
    .mode-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 6px;
      font-weight: 800;
    }}
    .banner {{
      border-radius: 14px;
      padding: 12px 14px;
      margin: 0 0 16px;
      border: 1px solid var(--border);
    }}
    .banner.info {{
      background: rgba(37, 99, 235, 0.08);
      border-color: rgba(37, 99, 235, 0.16);
    }}
    .banner.warning {{
      background: rgba(220, 38, 38, 0.08);
      border-color: rgba(220, 38, 38, 0.18);
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      width: fit-content;
      max-width: 100%;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 13px;
      font-weight: 700;
      border: 1px solid transparent;
      white-space: nowrap;
    }}
    .badge.ok {{
      color: var(--success);
      background: rgba(21, 128, 61, 0.12);
      border-color: rgba(21, 128, 61, 0.18);
    }}
    .badge.warn {{
      color: var(--warning);
      background: rgba(180, 83, 9, 0.12);
      border-color: rgba(180, 83, 9, 0.2);
    }}
    .badge.danger {{
      color: var(--danger);
      background: rgba(220, 38, 38, 0.12);
      border-color: rgba(220, 38, 38, 0.2);
    }}
    .badge.neutral {{
      background: var(--surface-strong);
      border-color: var(--border);
    }}
    .button-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
    }}
    form.inline {{
      display: inline;
    }}
    code, pre {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    code {{
      word-break: break-all;
    }}
    pre {{
      background: var(--surface-strong);
      border-radius: 12px;
      padding: 14px;
      overflow-x: auto;
      margin: 0;
    }}
    button {{
      font-size: 15px;
      font-weight: 700;
      padding: 10px 14px;
      border-radius: 10px;
      border: 1px solid #888;
      cursor: pointer;
    }}
    .secondary {{
      background: var(--surface-strong);
      color: inherit;
      border-color: var(--border);
    }}
    .approve {{
      background: #16a34a;
      color: white;
      border-color: #16a34a;
    }}
    .reject {{
      background: #dc2626;
      color: white;
      border-color: #dc2626;
    }}
    .pending {{
      color: #ca8a04;
      font-weight: 700;
    }}
    .applied {{
      color: #16a34a;
      font-weight: 700;
    }}
    .failed, .rejected {{
      color: #dc2626;
      font-weight: 700;
    }}
    ul.compact {{
      margin: 0;
      padding: 0 20px;
    }}
    @media (max-width: 860px) {{
      .app-shell {{
        grid-template-columns: 1fr;
      }}
      .sidebar {{
        border-right: 0;
        border-bottom: 1px solid var(--border);
        padding: 20px 16px;
      }}
      .main-content {{
        padding: 24px 16px 48px;
      }}
      .nav,
      .side-nav {{
        display: flex;
        flex-wrap: wrap;
      }}
      .nav-link,
      .side-link {{
        width: fit-content;
      }}
      .mode-grid {{
        grid-template-columns: 1fr;
      }}
      .kv-row {{
        grid-template-columns: 1fr;
        gap: 6px;
      }}
    }}
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-title">Workspace Terminal Bridge</div>
        <div class="brand-subtitle">Local MCP review panel</div>
      </div>
      <div class="sidebar-section">
        <div class="sidebar-label">Main</div>
        {primary_nav_html(active_nav)}
      </div>
      {f'<div class="sidebar-section"><div class="sidebar-label">Management</div>{management_nav_html(server_tab)}</div>' if server_tab else ''}
    </aside>
    <main class="main-content">
      <div class="content-inner">
        <div class="page-header">
          <h1>{escape(title)}</h1>
          {f'<p class="meta">{escape(subtitle)}</p>' if subtitle else ''}
        </div>
        {body}
      </div>
    </main>
  </div>
</body>
</html>
"""
    return html_text.encode("utf-8")


def page(title: str, body: str, active_nav: str = "", subtitle: str = "", server_tab: str | None = None) -> bytes:
    return app_shell(title, body, active_nav=active_nav, subtitle=subtitle, server_tab=server_tab)


def run_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=str(PROJECT_ROOT),
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=300,
        shell=False,
        check=False,
    )


def auto_apply_bundle(bundle_id: str, source: str) -> None:
    bundle_watcher.auto_apply_bundle(bundle_id, RUNNER, PROJECT_ROOT, source, "[review-ui] ")


def run_supervisor_control(action: str, service: str) -> subprocess.CompletedProcess[str]:
    command_by_action = {
        "start": ["scripts/dev_session.sh", "start-service", service],
        "stop": ["scripts/dev_session.sh", "stop-service", service],
        "restart": ["scripts/dev_session.sh", "restart", service],
    }
    command = command_by_action[action]

    return subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        shell=False,
        check=False,
    )


def is_local_client_address(value: str) -> bool:
    return value == "::1" or value == "::ffff:127.0.0.1" or value.startswith("127.")


def schedule_full_session_stop(delay_seconds: float = 0.6) -> None:
    def run_stop() -> None:
        time.sleep(delay_seconds)
        subprocess.run(
            ["scripts/dev_session.sh", "stop"],
            cwd=str(PROJECT_ROOT),
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=90,
            shell=False,
            check=False,
        )

    threading.Thread(target=run_stop, name="delayed-session-stop", daemon=True).start()


def full_session_stop_confirm_html() -> str:
    return """
    <div class="stack">
      <div class="notice">
        <strong>전체 세션 종료 확인</strong><br>
        이 작업은 review UI, MCP server, ngrok을 모두 종료합니다. 브라우저의 현재 review UI 연결도 곧 끊깁니다.
      </div>
      <section class="card">
        <h2>Stop full local session?</h2>
        <p class="meta">
          실행 명령: <code>scripts/dev_session.sh stop</code><br>
          다시 시작하려면 터미널에서 <code>scripts/dev_session.sh start</code>를 실행하세요.
        </p>
        <div class="button-row">
          <form class="inline" method="post" action="/servers/session/stop">
            <button class="reject" type="submit">Stop full session</button>
          </form>
          <a class="subnav-link" href="/servers?tab=processes">취소</a>
        </div>
      </section>
    </div>
    """


def full_session_stopping_html() -> str:
    return """
    <div class="stack">
      <div class="notice">
        <strong>Full session stop requested</strong><br>
        review UI, MCP server, ngrok이 곧 종료됩니다.
      </div>
      <section class="card">
        <h2>세션 종료 중</h2>
        <p class="meta">
          이 페이지가 열린 뒤 잠시 후 review UI 연결이 끊기는 것이 정상입니다.<br>
          다시 시작하려면 터미널에서 다음 명령을 실행하세요.
        </p>
        <pre>scripts/dev_session.sh start</pre>
      </section>
    </div>
    """


def schedule_full_session_restart(delay_seconds: float = 0.4) -> None:
    def run_restart() -> None:
        time.sleep(delay_seconds)
        subprocess.Popen(
            ["scripts/dev_session.sh", "restart-session"],
            cwd=str(PROJECT_ROOT),
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            shell=False,
            start_new_session=True,
        )

    threading.Thread(target=run_restart, name="delayed-session-restart", daemon=True).start()


def full_session_restart_confirm_html() -> str:
    return """
    <div class="stack">
      <div class="notice">
        <strong>전체 세션 재시작 확인</strong><br>
        이 작업은 review UI, MCP server, ngrok을 모두 재시작합니다. 브라우저의 현재 review UI 연결이 잠시 끊길 수 있습니다.
      </div>
      <section class="card">
        <h2>Restart full local session?</h2>
        <p class="meta">
          실행 명령: <code>scripts/dev_session.sh restart-session</code><br>
          재시작 후 review UI가 다시 올라오면 <code>/servers?tab=processes</code>를 새로고침하세요.
        </p>
        <div class="button-row">
          <form class="inline" method="post" action="/servers/session/restart">
            <button class="approve" type="submit">Restart full session</button>
          </form>
          <a class="subnav-link" href="/servers?tab=processes">취소</a>
        </div>
      </section>
    </div>
    """


def full_session_restarting_html() -> str:
    return """
    <div class="stack">
      <div class="notice">
        <strong>Full session restart requested</strong><br>
        review UI, MCP server, ngrok이 곧 재시작됩니다.
      </div>
      <section class="card">
        <h2>세션 재시작 중</h2>
        <p class="meta">
          이 페이지가 열린 뒤 잠시 후 review UI 연결이 끊겼다가 다시 살아나는 것이 정상입니다.<br>
          몇 초 후 아래 주소를 다시 여세요.
        </p>
        <pre>http://127.0.0.1:8790/servers?tab=processes</pre>
      </section>
    </div>
    """


def step_text_meta_html(step: dict[str, object], key: str, label: str) -> str:
    ref_value = step.get(f"{key}_ref")
    chars_value = step.get(f"{key}_chars")
    chunks_value = step.get(f"{key}_chunks")

    if ref_value:
        return (
            f'<p class="meta">{escape(label)} ref: '
            f'<code>{escape(ref_value)}</code>, '
            f'길이: {escape(chars_value)}자, '
            f'청크: {escape(chunks_value)}</p>'
        )

    return f'<p class="meta">{escape(label)} 길이: {len(str(step.get(key, "")))}자</p>'


def step_summary_html(step: dict[str, object], idx: int) -> str:
    kind = str(step.get("type", "command"))

    if kind == "command":
        detail = f"""
        <p class="meta">명령:</p>
        <pre>{escape(step.get("argv", []))}</pre>
        <p class="meta">제한 시간: {escape(step.get("timeout_seconds", ""))}</p>
        """
    elif kind in {"write_file", "append_file"}:
        detail = f"""
        <p class="meta">파일: <code>{escape(step.get("path", ""))}</code></p>
        {step_text_meta_html(step, "content", "내용")}
        <p class="meta">덮어쓰기: {escape(bool_label(step.get("overwrite", False)))}</p>
        """
    elif kind == "replace_text":
        detail = f"""
        <p class="meta">파일: <code>{escape(step.get("path", ""))}</code></p>
        {step_text_meta_html(step, "old_text", "기존 문구")}
        {step_text_meta_html(step, "new_text", "새 문구")}
        <p class="meta">전체 치환: {escape(bool_label(step.get("replace_all", False)))}</p>
        """
    elif kind == "apply_patch":
        detail = f"""
        <p class="meta">작업 위치: <code>{escape(step.get("cwd", ""))}</code></p>
        {step_text_meta_html(step, "patch", "Patch")}
        <p class="meta">대상 파일:</p>
        <pre>{escape(json.dumps(step.get("files", []), ensure_ascii=False, indent=2))}</pre>
        <p class="meta">Patch sha256: <code>{escape(step.get("patch_sha256", ""))}</code></p>
        """
    else:
        detail = f"<pre>{escape(step)}</pre>"

    return f"""
    <div class="card">
      <h3>{idx}. {escape(step.get("name", ""))}</h3>
      <p class="meta">작업 종류: <code>{escape(kind)}</code></p>
      <p class="meta">위험도: <code>{escape(risk_label(step.get("risk", "")))}</code></p>
      <p class="meta">이유: {escape(step.get("reason", ""))}</p>
      {detail}
    </div>
    """


def result_status_badge(status: str) -> str:
    if status == "success":
        return status_badge("success", "ok")
    if status == "failed":
        return status_badge("failed", "danger")
    return status_badge("unknown", "neutral")


def result_step_html(step: dict[str, object], idx: int) -> str:
    stdout = str(step.get("stdout", ""))
    stderr = str(step.get("stderr", ""))
    exit_code = step.get("exit_code")
    exit_value = "" if exit_code is None else str(exit_code)
    status = step_result_status(step)
    card_class = "card is-failed" if status == "failed" else "card"

    stdout_block = ""
    if stdout:
        stdout_block = f"""
        <details>
          <summary>stdout</summary>
          <pre>{escape(stdout)}</pre>
        </details>
        """

    stderr_block = ""
    if stderr:
        stderr_block = f"""
        <details>
          <summary>stderr</summary>
          <pre>{escape(stderr)}</pre>
        </details>
        """

    return f"""
    <div class="{card_class}">
      <h3>{idx}. {escape(step.get("name", ""))}</h3>
      <p class="meta">
        작업 종류: <code>{escape(step.get("type", ""))}</code><br>
        상태: {result_status_badge(status)}<br>
        exit_code: <code>{escape(exit_value)}</code>
      </p>
      {stdout_block}
      {stderr_block}
    </div>
    """


def history_summary_html(state: dict[str, object]) -> str:
    counts = state.get("counts") if isinstance(state.get("counts"), dict) else {}
    latest_failed = state.get("latest_failed_bundle_id")

    def count_card(label: str, count_key: str, href: str, tone: str = "neutral") -> str:
        count = int(counts.get(count_key, 0))
        return f"""
        <a class="metric metric-link" href="{escape(href)}">
          <div class="meta">{escape(label)}</div>
          <div class="metric-value">{escape(count)}</div>
          {status_badge(count_key, tone)}
        </a>
        """

    failed_block = (
        f'<a href="/bundles/{escape(latest_failed)}">최근 실패 번들 보기</a>'
        if latest_failed
        else f"{status_badge('실패 번들 없음', 'ok')}"
    )

    return f"""
    <section class="stack">
      <div class="card-grid">
        {count_card("승인 대기", "pending", "/pending", "warn")}
        {count_card("적용 완료", "applied", "/history?status=applied", "ok")}
        {count_card("실패", "failed", "/history?status=failed", "danger")}
        {count_card("거절됨", "rejected", "/history?status=rejected", "neutral")}
        {count_card("전체", "all", "/history?status=all", "neutral")}
      </div>
      <div class="notice">
        <strong>실패 빠른 접근</strong><br>
        {failed_block}
      </div>
    </section>
    """


def bundle_card_html(record: dict[str, object]) -> str:
    bundle_id = str(record.get("bundle_id", ""))
    status = str(record.get("status", "unknown"))
    summary = summarize_bundle_result(record)
    error_summary = str(summary.get("error_summary", ""))
    failed_class = " is-failed" if status == "failed" else ""
    error_block = (
        f'<p class="meta"><strong>오류 요약:</strong> {escape(error_summary)}</p>'
        if error_summary
        else ""
    )

    return f"""
    <div class="card{failed_class}">
      <h2><a href="/bundles/{escape(bundle_id)}">{escape(record.get("title", ""))}</a></h2>
      <p class="meta">
        ID: <code>{escape(bundle_id)}</code><br>
        작업 위치: <code>{escape(record.get("cwd", ""))}</code><br>
        상태: <span class="{escape(status)}">{escape(status_label(status))}</span><br>
        위험도: <code>{escape(risk_label(record.get("risk", "")))}</code><br>
        단계 수: <code>{escape(summary.get("command_count", 0))}</code><br>
        결과 step 수: <code>{escape(summary.get("result_step_count", 0))}</code><br>
        실패 step 수: <code>{escape(summary.get("failed_step_count", 0))}</code><br>
        수정: {escape(record.get("updated_at", ""))}
      </p>
      {error_block}
    </div>
    """


def result_html(result: object) -> str:
    raw = json.dumps(result, ensure_ascii=False, indent=2)
    step_cards = ""

    if isinstance(result, dict):
        steps = result.get("steps")
        if isinstance(steps, list):
            cards: list[str] = []
            for idx, step in enumerate(steps, 1):
                if isinstance(step, dict):
                    cards.append(result_step_html(step, idx))
            if cards:
                step_cards = "<h3>Step 결과</h3>" + "\n".join(cards)

    return f"""
    <h2>실행 결과</h2>
    {step_cards}
    <details>
      <summary>Raw result</summary>
      <pre>{escape(raw)}</pre>
    </details>
    """


def command_bundle_poll_script() -> str:
    return """
    <script>
    (function () {
      let revision = "";

      async function loadState() {
        const response = await fetch("/api/state", { cache: "no-store" });
        const state = await response.json();
        revision = state.revision || "";
      }

      async function poll() {
        try {
          const response = await fetch("/api/events?since=" + encodeURIComponent(revision), { cache: "no-store" });
          const event = await response.json();
          if (event.revision) {
            revision = event.revision;
          }
          if (event.changed) {
            location.reload();
            return;
          }
          poll();
        } catch (error) {
          setTimeout(poll, 2500);
        }
      }

      loadState().then(poll).catch(function () {
        setTimeout(poll, 2500);
      });
    }());
    </script>
    """


def bundle_detail_html(path: Path, record: dict[str, object]) -> str:
    bundle_id = str(record.get("bundle_id", path.stem))
    status = str(record.get("status", "unknown"))
    result = record.get("result")
    error = record.get("error")
    summary = summarize_bundle_result(record)
    copy_summary = copy_for_chatgpt_summary(record)

    controls = ""
    if status == "pending":
        controls = f"""
        <div class="button-row">
          <form class="inline" method="post" action="/bundles/{escape(bundle_id)}/approve">
            <button class="approve" type="submit">승인하고 실행</button>
          </form>
          <form class="inline" method="post" action="/bundles/{escape(bundle_id)}/reject">
            <button class="reject" type="submit">거절</button>
          </form>
        </div>
        """

    result_block = ""
    if result is not None:
        result_block = result_html(result)
    if error:
        result_block += f"<h2>오류</h2><pre>{escape(error)}</pre>"

    bundle_error_block = ""
    if error:
        bundle_error_block = f"""
        <div class="notice">
          <strong>Bundle error</strong><br>
          {escape(short_error(error, 300))}
        </div>
        """

    copy_json = escape(json.dumps(copy_summary, ensure_ascii=False, indent=2))

    return f"""
    <p><a href="/pending">← 승인으로 돌아가기</a> · <a href="/history">전체 목록</a></p>
    {bundle_error_block}
    <div class="card">
      <h2>{escape(record.get("title", bundle_id))}</h2>
      <p class="meta">
        ID: <code>{escape(bundle_id)}</code><br>
        작업 위치: <code>{escape(record.get("cwd", ""))}</code><br>
        상태: <span class="{escape(status)}">{escape(status_label(status))}</span><br>
        위험도: <code>{escape(risk_label(record.get("risk", "")))}</code><br>
        단계 수: <code>{escape(summary.get("command_count", 0))}</code><br>
        결과 step 수: <code>{escape(summary.get("result_step_count", 0))}</code><br>
        실패 step 수: <code>{escape(summary.get("failed_step_count", 0))}</code><br>
        승인 필요: <code>{escape(bool_label(record.get("approval_required", False)))}</code><br>
        생성: {escape(record.get("created_at", ""))}<br>
        수정: {escape(record.get("updated_at", ""))}<br>
        파일: <code>{escape(path)}</code>
      </p>
      <p><a href="/history?status={escape(status)}">같은 상태 이력 보기</a> · <a href="/api/audit-state">최근 audit event</a></p>
      {controls}
    </div>
    <h2>Copy for ChatGPT</h2>
    <pre>{copy_json}</pre>
    <h2>실행 단계</h2>
    {bundle_summary_html(record)}
    {result_block}
    {command_bundle_poll_script()}
    """


def bool_status(value: object) -> str:
    return "installed" if bool(value) else "missing"


def supervisor_action_notice_html(action: str, service: str, status: str) -> str:
    if (
        status != "ok"
        or action not in SUPERVISOR_SERVICE_ACTIONS
        or service not in SUPERVISOR_RESTARTABLE_SERVICES
    ):
        return ""

    label_by_action = {
        "start": "Start completed",
        "stop": "Stop completed",
        "restart": "Restart completed",
    }
    verb_by_action = {
        "start": "started",
        "stop": "stopped",
        "restart": "restarted",
    }

    return (
        '<div class="notice">'
        f'<strong>{escape(label_by_action[action])}</strong><br>'
        f'<code>{escape(service)}</code> {escape(verb_by_action[action])}. Status table refreshed.'
        '</div>'
    )


def server_tab_content_html(tab: str, state: dict[str, object], action_notice_html: str = "") -> str:
    tab = normalize_server_tab(tab)
    review_server = state.get("review_server") if isinstance(state.get("review_server"), dict) else {}
    review_dashboard = state.get("review_dashboard") if isinstance(state.get("review_dashboard"), dict) else {}
    tools = state.get("tools") if isinstance(state.get("tools"), dict) else {}
    environment = state.get("environment") if isinstance(state.get("environment"), dict) else {}
    mcp_server = state.get("mcp_server") if isinstance(state.get("mcp_server"), dict) else {}
    ngrok = state.get("ngrok") if isinstance(state.get("ngrok"), dict) else {}
    embedded_watcher = state.get("embedded_watcher") if isinstance(state.get("embedded_watcher"), dict) else {}
    supervisor = state.get("supervisor") if isinstance(state.get("supervisor"), dict) else supervisor_state()

    public_hint = ngrok.get("public_mcp_endpoint_hint")
    public_hint_value = f"<code>{escape(public_hint)}</code>" if public_hint else "없음"
    pending_url = str(review_dashboard.get("pending_url", "/pending"))
    history_url = str(review_dashboard.get("history_url", "/bundles?status=all"))
    review_url = str(review_server.get("url", ""))
    mcp_url = str(mcp_server.get("url", ""))
    mcp_reachable = bool(mcp_server.get("reachable"))
    token_format = "https://<NGROK_HOST>/mcp?access_token=<TOKEN>"
    read_only_notice = (
        '<div class="notice">'
        "<strong>보기 전용</strong><br>"
        "이번 단계에서는 start/stop/restart 버튼을 제공하지 않습니다."
        "</div>"
    )

    if tab == "overview":
        return f"""
        <div class="stack">
          <div class="section-title">
            <h2>{escape(SERVER_TAB_LABELS[tab])}</h2>
            <p class="meta">관리 페이지의 핵심 상태와 바로 가기를 한눈에 봅니다.</p>
          </div>
          <div class="card-grid">
            <section class="metric">
              <div class="meta">Review server</div>
              <h3>{status_chip("running" if review_server.get("status") == "running" else "unknown", "ok" if review_server.get("status") == "running" else "neutral")}</h3>
              <p class="meta">승인 UI 프로세스와 review dashboard 응답 상태</p>
            </section>
            <section class="metric">
              <div class="meta">MCP server</div>
              <h3>{status_chip("reachable" if mcp_reachable else "not reachable", "ok" if mcp_reachable else "warn")}</h3>
              <p class="meta">Local MCP endpoint TCP reachability</p>
            </section>
            <section class="metric">
              <div class="meta">ngrok</div>
              <h3>{set_missing_chip(ngrok.get("configured", "missing"))}</h3>
              <p class="meta">공개 MCP endpoint 구성을 위한 host/base URL 상태</p>
            </section>
            <section class="metric">
              <div class="meta">terminal-notifier</div>
              <h3>{bool_chip(tools.get("terminal_notifier", False), "installed", "missing")}</h3>
              <p class="meta">clickable notification 사용 가능 여부</p>
            </section>
          </div>
          <section class="card">
            <h3>빠른 이동</h3>
            <p><a href="{escape(pending_url)}">승인 대기 보기</a> · <a href="{escape(history_url)}">이력/결과 보기</a></p>
            <div class="kv">
              {kv_row_html("Public MCP endpoint 후보", public_hint_value, value_is_html=True)}
              {kv_row_html("Local MCP endpoint", mcp_url, code_value=True)}
            </div>
          </section>
        </div>
        """

    if tab == "services":
        return f"""
        <div class="stack">
          <div class="section-title">
            <h2>{escape(SERVER_TAB_LABELS[tab])}</h2>
            <p class="meta">Review UI, MCP server, ngrok 노출 정보를 보기 전용으로 확인합니다.</p>
          </div>
          {read_only_notice}
          <section class="card">
            <h3>Review server</h3>
            <div class="kv">
              {kv_row_html("Status", status_chip(str(review_server.get("status", "unknown")), "ok" if review_server.get("status") == "running" else "neutral"), value_is_html=True)}
              {kv_row_html("URL", f'<a href="{escape(review_url)}">{escape(review_url)}</a>', value_is_html=True)}
              {kv_row_html("PID", str(review_server.get("pid", "")), code_value=True)}
            </div>
          </section>
          <section class="card">
            <h3>MCP server</h3>
            <div class="kv">
              {kv_row_html("TCP reachable", status_chip("reachable" if mcp_reachable else "not reachable", "ok" if mcp_reachable else "warn"), value_is_html=True)}
              {kv_row_html("Local endpoint", mcp_url, code_value=True)}
            </div>
          </section>
          <section class="card">
            <h3>ngrok</h3>
            <div class="kv">
              {kv_row_html("Installed", bool_chip(ngrok.get("installed", False), "installed", "missing"), value_is_html=True)}
              {kv_row_html("Configured", set_missing_chip(ngrok.get("configured", "missing")), value_is_html=True)}
              {kv_row_html("Public endpoint hint", public_hint_value, value_is_html=True)}
            </div>
          </section>
        </div>
        """

    if tab == "processes":
        return f"""
        <div class="stack">
          <div class="section-title">
            <h2>{escape(SERVER_TAB_LABELS[tab])}</h2>
            <p class="meta">Status and limited controls for services managed by <code>scripts/dev_session.sh start</code>.</p>
          </div>
          <div class="notice">
            <strong>제한된 제어</strong><br>
            이 화면에서는 MCP/ngrok start/stop/restart만 제공합니다. 전체 session start/stop과 review 제어는 터미널에서 수행합니다.
          </div>
          {action_notice_html}
          <section class="card">
            <h3>Supervisor processes</h3>
            <p class="meta">
              pidfile과 TCP reachability만 확인합니다. stale pidfile은 이 화면에서 삭제하지 않습니다.
            </p>
            <div class="kv">
              {kv_row_html("Runtime root", str(supervisor.get("runtime_root", "")), code_value=True)}
              {kv_row_html("Process directory", str(supervisor.get("process_dir", "")), code_value=True)}
            </div>
          </section>
          <section class="card">
            <h3>CLI controls</h3>
            <p class="meta">전체 session start/stop은 터미널에서 수행합니다. MCP/ngrok start/stop/restart는 아래 표의 버튼으로도 실행할 수 있습니다.</p>
            <ul class="compact">
              <li>전체 세션 시작: <code>scripts/dev_session.sh start</code></li>
              <li>상태 확인: <code>scripts/dev_session.sh status</code></li>
              <li>MCP/ngrok 재시작: <code>scripts/dev_session.sh restart [mcp|ngrok]</code></li>
              <li>서비스 로그: <code>scripts/dev_session.sh logs [review|mcp|ngrok]</code></li>
              <li>전체 세션 종료: <code>scripts/dev_session.sh stop</code></li>
              <li>UI 버튼은 MCP/ngrok start/stop/restart만 제공합니다. 전체 session start/stop과 review 제어는 터미널에서 수행합니다.</li>
            </ul>
          </section>
          <section class="card">
            {supervisor_processes_html(supervisor)}
          </section>
          <section class="card">
            <h3>Full session</h3>
            <p class="meta">
              전체 session stop/restart는 review server 자기 자신을 포함하므로 별도 확인 페이지를 거칩니다.
            </p>
            <p>
              <a class="subnav-link" href="/servers/session/stop/confirm">Stop full session...</a>
              <a class="subnav-link" href="/servers/session/restart/confirm">Restart full session...</a>
            </p>
          </section>
          <p><a href="/api/supervisor-state"><code>/api/supervisor-state</code></a> 에서 같은 상태를 JSON으로 확인합니다.</p>
        </div>
        """

    if tab == "connection":
        return f"""
        <div class="stack">
          <div class="section-title">
            <h2>{escape(SERVER_TAB_LABELS[tab])}</h2>
            <p class="meta">ChatGPT 앱에 연결할 때 필요한 MCP endpoint 형식만 정리합니다.</p>
          </div>
          <section class="card">
            <div class="kv">
              {kv_row_html("Local MCP endpoint", mcp_url, code_value=True)}
              {kv_row_html("Public MCP endpoint 후보", public_hint_value, value_is_html=True)}
              {kv_row_html("ChatGPT MCP URL 형식", token_format, code_value=True)}
              {kv_row_html("MCP server reachability", status_chip("reachable" if mcp_reachable else "not reachable", "ok" if mcp_reachable else "warn"), value_is_html=True)}
            </div>
          </section>
          <div class="notice">
            <strong>토큰 값은 여기 표시하지 않습니다.</strong><br>
            ChatGPT 앱에는 <code>{escape(token_format)}</code> 형식만 사용하고 실제 <code>&lt;TOKEN&gt;</code> 값은 개인 secrets에서 관리합니다.
          </div>
        </div>
        """

    if tab == "environment":
        return f"""
        <div class="stack">
          <div class="section-title">
            <h2>{escape(SERVER_TAB_LABELS[tab])}</h2>
            <p class="meta">연결에 필요한 환경 변수가 설정되었는지 값 노출 없이 상태만 보여줍니다.</p>
          </div>
          <section class="card">
            <div class="kv">
              {kv_row_html("MCP_ACCESS_TOKEN", set_missing_chip(environment.get("mcp_access_token", "missing")), value_is_html=True)}
              {kv_row_html("NGROK_HOST/NGROK_BASE_URL", set_missing_chip(environment.get("ngrok_host", "missing")), value_is_html=True)}
              {kv_row_html("MCP_HOST", str(environment.get("mcp_host", "")), code_value=True)}
              {kv_row_html("MCP_PORT", str(environment.get("mcp_port", "")), code_value=True)}
              {kv_row_html("BUNDLE_REVIEW_HOST", str(environment.get("bundle_review_host", "")), code_value=True)}
              {kv_row_html("BUNDLE_REVIEW_PORT", str(environment.get("bundle_review_port", "")), code_value=True)}
            </div>
          </section>
        </div>
        """

    if tab == "tools":
        notifier_installed = bool(tools.get("terminal_notifier", False))
        notifier_note = (
            '<div class="notice"><strong>clickable notification 사용 가능</strong><br>'
            "watcher가 macOS 알림 클릭으로 review UI를 열 수 있습니다."
            "</div>"
            if notifier_installed
            else '<div class="notice"><strong>terminal-notifier가 없습니다.</strong><br>'
            "clickable notification을 쓰려면 <code>brew install terminal-notifier</code>를 실행하세요."
            "</div>"
        )
        return f"""
        <div class="stack">
          <div class="section-title">
            <h2>{escape(SERVER_TAB_LABELS[tab])}</h2>
            <p class="meta">로컬 세션 운영에 필요한 기본 도구 설치 여부를 봅니다.</p>
          </div>
          <section class="card">
            <div class="kv">
              {kv_row_html("uv", bool_chip(tools.get("uv", False), "installed", "missing"), value_is_html=True)}
              {kv_row_html("ngrok", bool_chip(tools.get("ngrok", False), "installed", "missing"), value_is_html=True)}
              {kv_row_html("terminal-notifier", bool_chip(notifier_installed, "installed", "missing"), value_is_html=True)}
            </div>
          </section>
          {notifier_note}
        </div>
        """

    return f"""
    <div class="stack">
      <div class="section-title">
        <h2>{escape(SERVER_TAB_LABELS['diagnostics'])}</h2>
        <p class="meta">문제 발생 시 가장 먼저 확인할 링크와 재시작 기준을 정리합니다.</p>
      </div>
      <section class="card">
        <ul class="compact">
          <li><a href="/api/server-state"><code>/api/server-state</code></a> 로 현재 review UI 상태를 JSON으로 확인합니다.</li>
          <li><a href="/api/supervisor-state"><code>/api/supervisor-state</code></a> 로 <code>scripts/dev_session.sh start</code>가 관리하는 process 상태를 JSON으로 확인합니다.</li>
          <li><a href="/api/audit-state"><code>/api/audit-state</code></a> 로 최근 로컬 작업 이벤트 요약을 JSON으로 확인합니다.</li>
          <li>Embedded watcher: {status_chip("enabled" if embedded_watcher.get("enabled") else "disabled", "ok" if embedded_watcher.get("enabled") else "neutral")}</li>
          <li>Watcher open mode: <code>{escape(embedded_watcher.get("open_mode", ""))}</code></li>
          <li>Notification target: <code>{escape(embedded_watcher.get("notification_target", ""))}</code></li>
          <li>Notification click action: <code>{escape(embedded_watcher.get("notification_click_action", ""))}</code></li>
          <li>Watcher poll seconds: <code>{escape(embedded_watcher.get("poll_seconds", ""))}</code></li>
          <li><code>scripts/dev_session.sh doctor</code> 로 review 세션과 환경 상태를 점검합니다.</li>
          <li><code>server.py</code> 또는 tool schema를 바꾼 경우 MCP server 재시작 후 ChatGPT 앱에서 Refresh가 필요합니다.</li>
          <li>review UI, watcher, README만 바꾼 경우에는 review session만 다시 시작하면 되고 MCP server 재시작은 보통 필요하지 않습니다.</li>
        </ul>
      </section>
      <section class="card">
        <h3>최근 로컬 작업 이벤트</h3>
        <p class="meta">MCP tool 호출 뒤 응답이 끊겼을 때 직전 로컬 audit event를 확인합니다. 민감한 값은 요약에서 제외합니다.</p>
        {recent_audit_events_html(10)}
      </section>
    </div>
    """


def server_state_html(state: dict[str, object], current_tab: str, action_notice_html: str = "") -> str:
    current_tab = normalize_server_tab(current_tab)
    return server_tab_content_html(current_tab, state, action_notice_html=action_notice_html)


def bundle_summary_html(record: dict[str, object]) -> str:
    steps = record.get("steps")
    if not isinstance(steps, list):
        steps = []

    step_items: list[str] = []
    for idx, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue
        step_items.append(step_summary_html(step, idx))

    return "\n".join(step_items)


class Handler(BaseHTTPRequestHandler):
    server_version = "CommandBundleReview/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[review-ui] {self.address_string()} - {fmt % args}")

    def send_html(
        self,
        title: str,
        body: str,
        status: int = 200,
        active_nav: str = "",
        subtitle: str = "",
        server_tab: str | None = None,
    ) -> None:
        payload = page(title, body, active_nav=active_nav, subtitle=subtitle, server_tab=server_tab)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, data: dict[str, object], status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(min(length, 20_000)).decode("utf-8", errors="replace")
        return parse_qs(raw_body, keep_blank_values=True)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        if parsed.path == "/api/state":
            self.send_json(command_bundle_state())
            return

        if parsed.path == "/api/server-state":
            self.send_json(server_state())
            return

        if parsed.path == "/api/supervisor-state":
            self.send_json(supervisor_state())
            return

        if parsed.path == "/api/history-state":
            self.send_json(history_state())
            return

        if parsed.path == "/api/audit-state":
            self.send_json(audit_state())
            return

        if parsed.path == "/api/events":
            params = parse_qs(parsed.query)
            since = params.get("since", [""])[0]
            deadline = time.monotonic() + EVENT_TIMEOUT_SECONDS
            state = command_bundle_state()

            while state["revision"] == since and time.monotonic() < deadline:
                time.sleep(EVENT_POLL_SECONDS)
                state = command_bundle_state()

            self.send_json(
                {
                    "changed": state["revision"] != since,
                    **state,
                }
            )
            return

        if parsed.path == "/pending":
            params = parse_qs(parsed.query)
            focused_bundle_id = params.get("bundle_id", [""])[0]
            if focused_bundle_id:
                try:
                    path, record = find_bundle(focused_bundle_id)
                except FileNotFoundError as exc:
                    self.send_html("찾을 수 없음", f"<pre>{escape(exc)}</pre>", status=404, active_nav="history")
                    return
                status = str(record.get("status", "unknown"))
                self.send_html(
                    str(record.get("title", focused_bundle_id)),
                    bundle_detail_html(path, record),
                    active_nav="pending" if status == "pending" else "history",
                    subtitle="bundle 상태와 ChatGPT 전달용 요약을 확인합니다.",
                )
                return

            rows = pending_bundles()
            approval_mode = load_approval_mode()
            cards = []
            for record in rows:
                bundle_id = str(record.get("bundle_id", ""))
                cards.append(
                    f"""
                    <div class="card">
                      <h2><a href="/bundles/{escape(bundle_id)}">{escape(record.get("title", ""))}</a></h2>
                      <p class="meta">
                        ID: <code>{escape(bundle_id)}</code><br>
                        작업 위치: <code>{escape(record.get("cwd", ""))}</code><br>
                        위험도: <code>{escape(risk_label(record.get("risk", "")))}</code><br>
                        수정: {escape(record.get("updated_at", ""))}
                      </p>
                      <div class="button-row">
                      <form class="inline" method="post" action="/bundles/{escape(bundle_id)}/approve">
                        <button class="approve" type="submit">승인하고 실행</button>
                      </form>
                      <form class="inline" method="post" action="/bundles/{escape(bundle_id)}/reject">
                        <button class="reject" type="submit">거절</button>
                      </form>
                      </div>
                    </div>
                    """
                )

            body = (
                approval_mode_banner_html(approval_mode)
                + approval_mode_card_html(approval_mode)
                + "<p><a href='/history'>전체 이력 보기</a></p>"
                + ("\n".join(cards) if cards else "<p>승인 대기 번들이 없습니다.</p>")
                + command_bundle_poll_script()
            )
            self.send_html(
                "승인",
                body,
                active_nav="pending",
                subtitle="ChatGPT가 만든 pending bundle을 검토하고 승인합니다.",
            )
            return

        if parsed.path == "/servers/session/stop/confirm":
            self.send_html(
                "전체 세션 종료 확인",
                full_session_stop_confirm_html(),
                active_nav="servers",
                subtitle="review UI, MCP server, ngrok을 모두 종료하기 전에 확인합니다.",
                server_tab="processes",
            )
            return

        if parsed.path == "/servers/session/restart/confirm":
            self.send_html(
                "전체 세션 재시작 확인",
                full_session_restart_confirm_html(),
                active_nav="servers",
                subtitle="review UI, MCP server, ngrok을 모두 재시작하기 전에 확인합니다.",
                server_tab="processes",
            )
            return

        if parsed.path == "/servers":
            params = parse_qs(parsed.query)
            current_tab = normalize_server_tab(params.get("tab", ["overview"])[0])
            action_notice_html = ""
            if current_tab == "processes":
                action_notice_html = supervisor_action_notice_html(
                    params.get("action", [""])[0],
                    params.get("service", [""])[0],
                    params.get("action_status", [""])[0],
                )
            self.send_html(
                "관리",
                server_state_html(server_state(), current_tab, action_notice_html=action_notice_html),
                active_nav="servers",
                subtitle="로컬 MCP review 환경의 상태를 보기 전용으로 확인합니다.",
                server_tab=current_tab,
            )
            return

        if parsed.path in {"/", "/bundles", "/history"}:
            params = parse_qs(parsed.query)
            status_filter = normalize_status_filter(params.get("status", ["all"])[0])
            rows = list_bundles(status_filter)
            cards = [bundle_card_html(record) for record in rows]

            self.send_html(
                "이력/결과",
                (
                    history_summary_html(history_state())
                    + "<p><a href='/pending'>승인 대기 보기</a> · "
                    "<a href='/history'>새로고침</a></p>"
                    + status_filter_links_html(status_filter)
                    + ("\n".join(cards) if cards else "<p>번들이 없습니다.</p>")
                ),
                active_nav="history",
                subtitle="적용, 실패, 거절, 대기 중인 bundle 이력을 확인합니다.",
            )
            return

        if len(parts) == 2 and parts[0] == "bundles":
            bundle_id = parts[1]
            try:
                path, record = find_bundle(bundle_id)
            except FileNotFoundError as exc:
                self.send_html("찾을 수 없음", f"<pre>{escape(exc)}</pre>", status=404, active_nav="history")
                return

            status = str(record.get("status", "unknown"))
            active_nav = "pending" if status == "pending" else "history"
            self.send_html(
                str(record.get("title", bundle_id)),
                bundle_detail_html(path, record),
                active_nav=active_nav,
                subtitle="bundle 단계, 실행 결과, 원본 JSON을 확인합니다.",
            )
            return

        if parsed.path == "/health":
            self.send_json({"ok": True, "ts": now_iso()})
            return

        self.send_html("찾을 수 없음", "<p>찾을 수 없습니다.</p>", status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        if parts == ["settings", "approval-mode"]:
            if not is_local_client_address(str(self.client_address[0])):
                self.send_html("Forbidden", "<p>Local requests only.</p>", status=403, active_nav="pending")
                return

            form = self.read_form()
            raw_mode = str(form.get("mode", [""])[0]).strip().lower()
            if raw_mode not in VALID_APPROVAL_MODES:
                self.send_html(
                    "Invalid approval mode",
                    '<p><a href="/pending">← 승인 대기로 돌아가기</a></p><p>지원하지 않는 approval mode입니다.</p>',
                    status=400,
                    active_nav="pending",
                )
                return

            if raw_mode == "yolo" and str(form.get("confirm", [""])[0]) != "YOLO":
                self.send_html(
                    "YOLO mode 확인",
                    approval_mode_confirm_html(),
                    active_nav="pending",
                    subtitle="자동 승인 범위를 넓히기 전에 명시 확인이 필요합니다.",
                )
                return

            save_approval_mode(raw_mode)
            self.redirect("/pending")
            return

        if parts == ["servers", "session", "stop"]:
            if not is_local_client_address(str(self.client_address[0])):
                self.send_html(
                    "Forbidden",
                    "<p>Local requests only.</p>",
                    status=403,
                    active_nav="servers",
                    server_tab="processes",
                )
                return

            schedule_full_session_stop()
            self.send_html(
                "세션 종료 중",
                full_session_stopping_html(),
                active_nav="servers",
                subtitle="전체 로컬 세션 종료를 요청했습니다.",
                server_tab="processes",
            )
            return

        if parts == ["servers", "session", "restart"]:
            if not is_local_client_address(str(self.client_address[0])):
                self.send_html(
                    "Forbidden",
                    "<p>Local requests only.</p>",
                    status=403,
                    active_nav="servers",
                    server_tab="processes",
                )
                return

            schedule_full_session_restart()
            self.send_html(
                "세션 재시작 중",
                full_session_restarting_html(),
                active_nav="servers",
                subtitle="전체 로컬 세션 재시작을 요청했습니다.",
                server_tab="processes",
            )
            return

        if len(parts) == 4 and parts[:2] == ["servers", "processes"] and parts[2] in SUPERVISOR_SERVICE_ACTIONS:
            action = parts[2]
            service = parts[3]

            if not is_local_client_address(str(self.client_address[0])):
                self.send_html(
                    "Forbidden",
                    "<p>Local requests only.</p>",
                    status=403,
                    active_nav="servers",
                    server_tab="processes",
                )
                return

            if service not in SUPERVISOR_RESTARTABLE_SERVICES:
                self.send_html(
                    "지원하지 않는 서비스",
                    "<p>Start, stop, and restart are supported only for mcp and ngrok.</p>",
                    status=400,
                    active_nav="servers",
                    server_tab="processes",
                )
                return

            completed = run_supervisor_control(action, service)
            if completed.returncode != 0:
                action_title = action.title()
                body = f"""
                <p><a href="/servers?tab=processes">← 프로세스로 돌아가기</a></p>
                <h2>{escape(action_title)} failed: {escape(service)}</h2>
                <details open>
                  <summary>stdout</summary>
                  <pre>{escape(mask_sensitive_text(completed.stdout))}</pre>
                </details>
                <details open>
                  <summary>stderr</summary>
                  <pre>{escape(mask_sensitive_text(completed.stderr))}</pre>
                </details>
                """
                self.send_html(
                    f"{action_title} failed",
                    body,
                    status=500,
                    active_nav="servers",
                    server_tab="processes",
                )
                return

            self.redirect(f"/servers?tab=processes&action_status=ok&action={action}&service={service}")
            return

        if len(parts) == 3 and parts[0] == "bundles" and parts[2] in {"approve", "reject"}:
            bundle_id = parts[1]
            action = parts[2]

            if action == "approve":
                completed = run_runner(["apply", bundle_id, "--yes"])
            else:
                completed = run_runner(["reject", bundle_id])

            output = {
                "exit_code": completed.returncode,
                "stdout": mask_sensitive_text(completed.stdout),
                "stderr": mask_sensitive_text(completed.stderr),
            }

            if completed.returncode != 0:
                body = f"""
                <p><a href="/bundles/{escape(bundle_id)}">← 번들로 돌아가기</a> · <a href="/pending">승인 대기</a></p>
                <h2>실행기 오류</h2>
                <details open>
                  <summary>stdout</summary>
                  <pre>{escape(mask_sensitive_text(completed.stdout))}</pre>
                </details>
                <details open>
                  <summary>stderr</summary>
                  <pre>{escape(mask_sensitive_text(completed.stderr))}</pre>
                </details>
                <details>
                  <summary>Raw result</summary>
                  <pre>{escape(json.dumps(output, ensure_ascii=False, indent=2))}</pre>
                </details>
                """
                self.send_html("실행기 오류", body, status=500, active_nav="pending")
                return

            if action == "approve":
                try:
                    _, updated_record = find_bundle(bundle_id)
                except FileNotFoundError:
                    updated_record = {}

                if updated_record.get("status") == "failed":
                    body = f"""
                    <p><a href="/bundles/{escape(bundle_id)}">← 실패한 번들 보기</a> · <a href="/pending">승인 대기</a></p>
                    <h2>번들 실행 실패</h2>
                    <details open>
                      <summary>stdout</summary>
                      <pre>{escape(mask_sensitive_text(completed.stdout))}</pre>
                    </details>
                    <details open>
                      <summary>stderr</summary>
                      <pre>{escape(mask_sensitive_text(completed.stderr))}</pre>
                    </details>
                    <h3>기록된 결과</h3>
                    {result_html(updated_record.get("result")) if updated_record.get("result") is not None else ""}
                    <h3>오류</h3>
                    <pre>{escape(mask_sensitive_text(updated_record.get("error", "")))}</pre>
                    """
                    self.send_html("번들 실행 실패", body, status=500, active_nav="history")
                    return

            self.redirect("/pending")
            return

        self.send_html("찾을 수 없음", "<p>찾을 수 없습니다.</p>", status=404)


def main() -> None:
    for directory in bundle_dirs():
        directory.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/pending"
    watcher_stop_event, watcher_thread = start_embedded_watcher()
    print(f"명령 번들 승인 UI 실행 중: {url}")
    print("종료하려면 Ctrl-C를 누르세요.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n승인 UI를 종료합니다...")
    finally:
        if watcher_stop_event is not None:
            watcher_stop_event.set()
        if watcher_thread is not None:
            watcher_thread.join(timeout=2)
        server.server_close()


if __name__ == "__main__":
    main()
