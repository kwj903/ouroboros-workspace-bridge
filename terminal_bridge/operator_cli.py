from __future__ import annotations

import argparse
import ctypes
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from dataclasses import replace
from pathlib import Path

from terminal_bridge import public_access
from terminal_bridge import session_supervisor as supervisor
from terminal_bridge import setup_ui
from terminal_bridge.cli_common import print_version_info as _print_shared_version_info
from terminal_bridge.version import version_summary


CLOUDFLARED_SERVICE = "cloudflared"
PROCESS_METADATA_VERSION = 1
LOCAL_READY_TIMEOUT_SECONDS = 15.0
PUBLIC_READY_TIMEOUT_SECONDS = 20.0


def selected_operator_mode(settings: supervisor.SessionSettings) -> str:
    if settings.public_access_mode == "ngrok":
        return "ngrok"
    if settings.external_tunnel_provider == "cloudflare":
        return "cloudflare"
    return "external"


def settings_for_operator_mode(
    settings: supervisor.SessionSettings,
    mode: str,
) -> supervisor.SessionSettings:
    normalized = public_access.normalize_operator_mode(mode)
    if normalized == "ngrok":
        return replace(settings, public_access_mode="ngrok")

    public_mcp_url = public_access.normalize_external_mcp_url(
        settings.public_mcp_url
    )
    provider = "cloudflare" if normalized == "cloudflare" else "manual"
    return replace(
        settings,
        public_access_mode="external",
        public_mcp_url=public_mcp_url,
        external_tunnel_provider=provider,
    )


def persist_operator_mode(mode: str) -> supervisor.SessionSettings:
    settings = settings_for_operator_mode(
        supervisor.load_settings(strict_public_access=False), mode
    )
    if selected_operator_mode(settings) == "cloudflare":
        cloudflared_command(settings)
    supervisor.write_session_files(settings)
    return settings


def cloudflared_pid_file(settings: supervisor.SessionSettings) -> Path:
    return settings.process_dir / f"{CLOUDFLARED_SERVICE}.pid"


def cloudflared_log_file(settings: supervisor.SessionSettings) -> Path:
    return settings.process_dir / f"{CLOUDFLARED_SERVICE}.log"


def cloudflared_metadata_file(settings: supervisor.SessionSettings) -> Path:
    return settings.process_dir / f"{CLOUDFLARED_SERVICE}.process.json"


def resolve_cloudflared_binary(settings: supervisor.SessionSettings) -> str:
    configured = settings.cloudflared_bin.strip() or "cloudflared"
    expanded = Path(configured).expanduser()
    looks_like_path = expanded.is_absolute() or any(
        separator in configured for separator in ("/", "\\")
    )
    if looks_like_path:
        if not expanded.exists():
            raise public_access.PublicAccessConfigError(
                f"Configured CLOUDFLARED_BIN does not exist: {expanded}"
            )
        return str(expanded.resolve(strict=False))

    discovered = shutil.which(configured)
    if not discovered:
        raise public_access.PublicAccessConfigError(
            "cloudflared is not installed or not on PATH. Install it or set CLOUDFLARED_BIN."
        )
    return str(Path(discovered).resolve(strict=False))


def resolve_cloudflared_config_path(
    settings: supervisor.SessionSettings,
) -> Path:
    raw = settings.cloudflared_config_path.strip()
    if not raw:
        raise public_access.PublicAccessConfigError(
            "CLOUDFLARED_CONFIG_PATH is required for Cloudflare mode."
        )
    path = Path(raw).expanduser().resolve(strict=False)
    if not path.is_file():
        raise public_access.PublicAccessConfigError(
            f"Cloudflare config file does not exist: {path}"
        )
    return path


def cloudflared_command(settings: supervisor.SessionSettings) -> list[str]:
    tunnel_name = settings.cloudflared_tunnel_name.strip()
    if not tunnel_name:
        raise public_access.PublicAccessConfigError(
            "CLOUDFLARED_TUNNEL_NAME is required for Cloudflare mode."
        )
    return [
        resolve_cloudflared_binary(settings),
        "tunnel",
        "--config",
        str(resolve_cloudflared_config_path(settings)),
        "run",
        tunnel_name,
    ]


def _read_process_metadata(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_process_metadata(
    settings: supervisor.SessionSettings,
    *,
    pid: int,
    command: list[str],
) -> None:
    metadata = {
        "version": PROCESS_METADATA_VERSION,
        "pid": pid,
        "command": command,
        "started_at": time.time(),
    }
    cloudflared_metadata_file(settings).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _remove_cloudflared_tracking(settings: supervisor.SessionSettings) -> None:
    cloudflared_pid_file(settings).unlink(missing_ok=True)
    cloudflared_metadata_file(settings).unlink(missing_ok=True)


def _windows_process_executable(pid: int) -> str:
    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def _windows_process_command(pid: int) -> str:
    script = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "[System.Text.UTF8Encoding]::new(); "
        f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; "
        "if ($null -ne $p) { $p.CommandLine }"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _posix_process_command(pid: int) -> str:
    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        text=True,
        capture_output=True,
        errors="replace",
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def cloudflared_process_matches_metadata(
    pid: int,
    metadata: dict[str, object],
) -> bool:
    try:
        metadata_pid = int(metadata.get("pid", 0) or 0)
    except (TypeError, ValueError):
        return False
    if metadata_pid != pid:
        return False
    command = metadata.get("command")
    if not isinstance(command, list) or not command or not all(
        isinstance(item, str) for item in command
    ):
        return False

    expected_binary = Path(command[0]).name.lower()
    if supervisor.is_windows():
        actual = _windows_process_executable(pid)
        actual_command = _windows_process_command(pid)
        return (
            bool(actual)
            and Path(actual).name.lower() == expected_binary
            and bool(actual_command)
            and str(command[-1]) in actual_command
            and str(command[-3]) in actual_command
        )

    actual_command = _posix_process_command(pid)
    if not actual_command:
        return False
    if expected_binary not in actual_command.lower():
        return False
    tunnel_name = command[-1]
    return tunnel_name in actual_command


def managed_cloudflared_pid(
    settings: supervisor.SessionSettings,
) -> tuple[int | None, bool]:
    pid = supervisor.read_pid(cloudflared_pid_file(settings))
    if pid is None or not supervisor.is_pid_alive(pid):
        return pid, False
    metadata = _read_process_metadata(cloudflared_metadata_file(settings))
    return pid, cloudflared_process_matches_metadata(pid, metadata)


def start_cloudflared(settings: supervisor.SessionSettings) -> int:
    settings.process_dir.mkdir(parents=True, exist_ok=True)
    command = cloudflared_command(settings)
    pid, matches = managed_cloudflared_pid(settings)
    if pid is not None and supervisor.is_pid_alive(pid):
        if matches:
            metadata = _read_process_metadata(cloudflared_metadata_file(settings))
            if metadata.get("command") == command:
                print(
                    f"[reuse] cloudflared pid={pid} log={cloudflared_log_file(settings)}"
                )
                return 0
            print("[info] Cloudflare configuration changed; restarting managed connector.")
            if stop_cloudflared(settings) != 0:
                return 1
        else:
            _remove_cloudflared_tracking(settings)
            print(
                f"[warn] cloudflared pid={pid} no longer matches its process metadata; "
                "tracking files were removed without terminating that process."
            )
    else:
        _remove_cloudflared_tracking(settings)

    target_log = cloudflared_log_file(settings)
    with target_log.open("ab", buffering=0) as log:
        log.write(
            f"\n== {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} starting cloudflared ==\n".encode()
        )
        kwargs: dict[str, object] = {
            "cwd": str(supervisor.PROJECT_ROOT),
            "env": settings.as_env(),
            "stdin": subprocess.DEVNULL,
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "shell": False,
        }
        if supervisor.is_windows():
            kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(command, **kwargs)

    cloudflared_pid_file(settings).write_text(
        f"{process.pid}\n", encoding="utf-8"
    )
    _write_process_metadata(settings, pid=process.pid, command=command)
    print(f"[start] cloudflared pid={process.pid} log={target_log}")
    time.sleep(0.5)
    if not supervisor.is_pid_alive(process.pid):
        _remove_cloudflared_tracking(settings)
        print(f"[error] cloudflared exited quickly; see log={target_log}")
        return 1
    return 0


def stop_cloudflared(settings: supervisor.SessionSettings) -> int:
    pid = supervisor.read_pid(cloudflared_pid_file(settings))
    if pid is None:
        print("[stop] cloudflared not managed")
        _remove_cloudflared_tracking(settings)
        return 0
    if not supervisor.is_pid_alive(pid):
        _remove_cloudflared_tracking(settings)
        print("[stop] cloudflared stale pid removed")
        return 0

    metadata = _read_process_metadata(cloudflared_metadata_file(settings))
    if not cloudflared_process_matches_metadata(pid, metadata):
        _remove_cloudflared_tracking(settings)
        print(
            f"[stop] cloudflared stale tracking removed; pid={pid} was not terminated"
        )
        return 0

    print(f"[stop] cloudflared pid={pid}")
    supervisor.terminate_pid_tree(pid)
    if supervisor.is_pid_alive(pid):
        print(
            f"[warn] cloudflared may still be running; pid file kept: {cloudflared_pid_file(settings)}"
        )
        return 1
    _remove_cloudflared_tracking(settings)
    print("[ok] cloudflared stopped")
    return 0


def public_endpoint_http_status(
    settings: supervisor.SessionSettings,
    *,
    timeout_seconds: float = 2.0,
) -> int | None:
    base_url = settings.public_mcp_base_url
    if not base_url:
        return None
    request = urllib.request.Request(
        base_url,
        method="GET",
        headers={"User-Agent": "terminalbridge-status/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def wait_for_local_bridge(
    settings: supervisor.SessionSettings,
    *,
    timeout_seconds: float = LOCAL_READY_TIMEOUT_SECONDS,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if supervisor.tcp_reachable(
            settings.review_host, settings.review_port, timeout_seconds=0.25
        ) and supervisor.tcp_reachable(
            settings.mcp_host, settings.mcp_port, timeout_seconds=0.25
        ):
            return True
        time.sleep(0.25)
    return False


def public_endpoint_is_ready(status: int | None) -> bool:
    return status == 401


def wait_for_public_endpoint(
    settings: supervisor.SessionSettings,
    *,
    timeout_seconds: float = PUBLIC_READY_TIMEOUT_SECONDS,
) -> int | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = public_endpoint_http_status(settings)
        if public_endpoint_is_ready(status):
            return status
        time.sleep(0.5)
    return None


def start_operator(mode: str | None = None) -> int:
    settings = (
        persist_operator_mode(mode)
        if mode is not None
        else supervisor.load_settings()
    )
    selected = selected_operator_mode(settings)
    if selected == "cloudflare":
        cloudflared_command(settings)
    print(f"Starting Terminal Bridge operator mode: {selected}")

    code = 0
    if selected == "cloudflare":
        code = max(code, supervisor.stop_service("ngrok"))
    else:
        code = max(code, stop_cloudflared(settings))

    code = max(code, supervisor.start_session())
    settings = supervisor.load_settings()
    if not wait_for_local_bridge(settings):
        print("[error] Review or MCP service did not become ready.", file=sys.stderr)
        supervisor.stop_session()
        return max(code, 1)

    if selected == "cloudflare":
        connector_code = start_cloudflared(settings)
        code = max(code, connector_code)
        if connector_code != 0:
            supervisor.stop_session()
            return code
        status = wait_for_public_endpoint(settings)
        if status is None:
            print(
                "[warn] Cloudflare connector is running but the public endpoint is not reachable yet."
            )
            code = max(code, 1)
        else:
            print(f"[ok] Public endpoint reachable: HTTP {status}")
    elif selected == "external":
        print("[info] External tunnel lifecycle remains operator-managed.")

    return code


def stop_operator() -> int:
    settings = supervisor.load_settings(strict_public_access=False)
    print("Stopping Terminal Bridge operator session")
    code = stop_cloudflared(settings)
    code = max(code, supervisor.stop_session())
    return code


def restart_operator(mode: str | None = None) -> int:
    code = stop_operator()
    return max(code, start_operator(mode))


def print_cloudflared_status(settings: supervisor.SessionSettings) -> None:
    pid = supervisor.read_pid(cloudflared_pid_file(settings))
    pid_alive = supervisor.is_pid_alive(pid)
    metadata = _read_process_metadata(cloudflared_metadata_file(settings))
    matches = bool(pid_alive and pid is not None and cloudflared_process_matches_metadata(pid, metadata))
    state = "yes" if matches else "stale" if cloudflared_pid_file(settings).exists() else "no"
    print(
        f"cloudflared pid={pid or 'none'} alive={state} log={cloudflared_log_file(settings)}"
    )


def status_operator() -> int:
    settings = supervisor.load_settings()
    selected = selected_operator_mode(settings)
    print("Terminal Bridge operator status")
    print(f"Selected mode: {selected}")
    print()
    supervisor.status_session()
    print()
    print_cloudflared_status(settings)
    if settings.public_mcp_base_url:
        status = public_endpoint_http_status(settings)
        if status is None:
            print("Public endpoint reachable: no")
        elif public_endpoint_is_ready(status):
            print(f"Public endpoint reachable: yes (HTTP {status})")
        else:
            print(f"Public endpoint reachable: no (HTTP {status})")
    return 0


def logs_cloudflared(settings: supervisor.SessionSettings) -> int:
    path = cloudflared_log_file(settings)
    if not path.exists():
        print(f"[warn] log file does not exist yet: {path}")
        return 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]:
        print(line)
    return 0


def logs_operator(service: str) -> int:
    settings = supervisor.load_settings(strict_public_access=False)
    if service == "cloudflared":
        return logs_cloudflared(settings)
    if service != "all":
        return supervisor.logs_service(service)

    code = 0
    for item in ("review", "mcp", "ngrok"):
        print(f"== {item} ==")
        code = max(code, supervisor.logs_service(item))
        print()
    print("== cloudflared ==")
    code = max(code, logs_cloudflared(settings))
    return code


def doctor_operator() -> int:
    settings = supervisor.load_settings()
    selected = selected_operator_mode(settings)
    code = supervisor.doctor()
    print()
    print("Terminal Bridge operator checks")
    print(f"[ok] selected mode: {selected}")
    if selected == "cloudflare":
        try:
            executable = resolve_cloudflared_binary(settings)
            config_path = resolve_cloudflared_config_path(settings)
            if not settings.cloudflared_tunnel_name.strip():
                raise public_access.PublicAccessConfigError(
                    "CLOUDFLARED_TUNNEL_NAME is required for Cloudflare mode."
                )
        except public_access.PublicAccessConfigError as exc:
            print(f"[error] {exc}")
            return 1
        print(f"[ok] cloudflared: {executable}")
        print(f"[ok] Cloudflare config: {config_path}")
        print(f"[ok] Cloudflare tunnel: {settings.cloudflared_tunnel_name}")
    return code


def print_version_info() -> int:
    return _print_shared_version_info(version_summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="terminalbridge",
        description="Operate the complete Workspace Terminal Bridge connection stack.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("setup", help="Configure this user's local connection profile.")
    setup_ui_parser = subparsers.add_parser(
        "setup-ui", help="Open the optional localhost onboarding UI."
    )
    setup_ui_parser.add_argument(
        "--port", type=int, default=setup_ui.DEFAULT_PORT
    )
    setup_ui_parser.add_argument("--no-open", action="store_true")
    subparsers.add_parser("doctor", help="Check Bridge and selected tunnel prerequisites.")

    start = subparsers.add_parser("start", help="Start Bridge and the selected public connector.")
    start.add_argument("--mode", choices=tuple(sorted(public_access.OPERATOR_MODES)))

    subparsers.add_parser("stop", help="Stop Bridge and every managed public connector.")

    restart = subparsers.add_parser("restart", help="Restart Bridge and the selected public connector.")
    restart.add_argument("--mode", choices=tuple(sorted(public_access.OPERATOR_MODES)))

    subparsers.add_parser("status", help="Show Bridge, connector, and endpoint status.")
    logs = subparsers.add_parser("logs", help="Print bounded service logs.")
    logs.add_argument(
        "service",
        nargs="?",
        default="all",
        choices=("all", "review", "mcp", "ngrok", "cloudflared"),
    )
    subparsers.add_parser("open", help="Open the local review dashboard.")
    subparsers.add_parser("mcp-url", help="Print a redacted public MCP URL.")
    subparsers.add_parser("copy-url", help="Copy the tokenized MCP URL locally.")
    subparsers.add_parser("version", help="Show package and git version information.")
    return parser


def _main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "setup":
        return supervisor.configure()
    if args.command == "setup-ui":
        if args.port < 1 or args.port > 65535:
            print("[error] --port must be between 1 and 65535.", file=sys.stderr)
            return 2
        return setup_ui.run_setup_ui(
            port=args.port, open_browser=not args.no_open
        )
    if args.command == "doctor":
        return doctor_operator()
    if args.command == "start":
        return start_operator(args.mode)
    if args.command == "stop":
        return stop_operator()
    if args.command == "restart":
        return restart_operator(args.mode)
    if args.command == "status":
        return status_operator()
    if args.command == "logs":
        return logs_operator(args.service)
    if args.command == "open":
        return supervisor.open_review_dashboard()
    if args.command == "mcp-url":
        return supervisor.mcp_url_preview()
    if args.command == "copy-url":
        return supervisor.copy_mcp_url()
    if args.command == "version":
        return print_version_info()
    return 2


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except public_access.PublicAccessConfigError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
