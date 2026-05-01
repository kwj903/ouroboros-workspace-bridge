from __future__ import annotations

import getpass
import json
import os
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from terminal_bridge import runtime_storage


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNTIME_ROOT = Path.home() / ".mcp_terminal_bridge" / "my-terminal-tool"
SERVICES = ("review", "mcp", "ngrok")
RESTARTABLE_SERVICES = {"mcp", "ngrok"}


@dataclass(frozen=True)
class SessionSettings:
    runtime_root: Path
    mcp_access_token: str
    ngrok_host: str
    workspace_root: Path
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8787
    review_host: str = "127.0.0.1"
    review_port: int = 8790

    @property
    def process_dir(self) -> Path:
        return self.runtime_root / "processes"

    @property
    def review_base_url(self) -> str:
        return f"http://{self.review_host}:{self.review_port}"

    @property
    def review_dashboard_url(self) -> str:
        return f"{self.review_base_url}/pending"

    def as_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["MCP_TERMINAL_BRIDGE_RUNTIME_ROOT"] = str(self.runtime_root)
        env["WORKSPACE_ROOT"] = str(self.workspace_root)
        env["MCP_HOST"] = self.mcp_host
        env["MCP_PORT"] = str(self.mcp_port)
        env["BUNDLE_REVIEW_HOST"] = self.review_host
        env["BUNDLE_REVIEW_PORT"] = str(self.review_port)
        env["NGROK_HOST"] = self.ngrok_host
        if self.mcp_access_token:
            env["MCP_ACCESS_TOKEN"] = self.mcp_access_token
        else:
            env.pop("MCP_ACCESS_TOKEN", None)
        return env


def is_windows() -> bool:
    return os.name == "nt"


def runtime_root() -> Path:
    raw = os.getenv("MCP_TERMINAL_BRIDGE_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT))
    return Path(raw).expanduser().resolve(strict=False)


def session_json_path(root: Path | None = None) -> Path:
    return (root or runtime_root()) / "session.json"


def session_env_path(root: Path | None = None) -> Path:
    return (root or runtime_root()) / "session.env"


def normalize_ngrok_host(value: str) -> str:
    host = value.strip()
    host = host.removeprefix("https://").removeprefix("http://")
    host = host.split("/", 1)[0]
    host = host.split("?", 1)[0]
    host = host.split("#", 1)[0]
    return host


def parse_legacy_session_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assignment = stripped.removeprefix("export ")
        try:
            parts = shlex.split(assignment, comments=False, posix=True)
        except ValueError:
            continue
        if not parts or "=" not in parts[0]:
            continue
        key, value = parts[0].split("=", 1)
        values[key] = value
    return values


def read_session_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def session_value(env_name: str, json_key: str | None = None) -> str:
    if os.getenv(env_name) is not None:
        return os.getenv(env_name, "")

    root = runtime_root()
    key = json_key or env_name.lower()
    json_value = read_session_json(session_json_path(root)).get(key)
    if json_value is not None:
        return str(json_value)

    return parse_legacy_session_env(session_env_path(root)).get(env_name, "")


def int_session_value(env_name: str, json_key: str, default: int) -> int:
    raw = session_value(env_name, json_key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_settings() -> SessionSettings:
    root = runtime_root()
    ngrok_host = normalize_ngrok_host(session_value("NGROK_HOST") or session_value("NGROK_BASE_URL", "ngrok_base_url"))
    return SessionSettings(
        runtime_root=root,
        mcp_access_token=session_value("MCP_ACCESS_TOKEN", "mcp_access_token"),
        ngrok_host=ngrok_host,
        workspace_root=Path(session_value("WORKSPACE_ROOT", "workspace_root") or Path.home() / "workspace").expanduser().resolve(strict=False),
        mcp_host=session_value("MCP_HOST", "mcp_host") or "127.0.0.1",
        mcp_port=int_session_value("MCP_PORT", "mcp_port", 8787),
        review_host=session_value("BUNDLE_REVIEW_HOST", "review_host") or "127.0.0.1",
        review_port=int_session_value("BUNDLE_REVIEW_PORT", "review_port", 8790),
    )


def is_dangerous_workspace_root(path: Path) -> bool:
    if is_windows():
        return path == Path(path.anchor)
    dangerous = {Path("/"), Path("/System"), Path("/Library"), Path("/private"), Path("/etc"), Path("/usr"), Path("/bin"), Path("/sbin")}
    return path.resolve(strict=False) in {item.resolve(strict=False) for item in dangerous}


def write_session_files(settings: SessionSettings) -> None:
    settings.runtime_root.mkdir(parents=True, exist_ok=True)
    try:
        settings.runtime_root.chmod(0o700)
    except OSError:
        pass

    session_json_path(settings.runtime_root).write_text(
        json.dumps(
            {
                "mcp_access_token": settings.mcp_access_token,
                "ngrok_host": settings.ngrok_host,
                "workspace_root": str(settings.workspace_root),
                "mcp_host": settings.mcp_host,
                "mcp_port": settings.mcp_port,
                "review_host": settings.review_host,
                "review_port": settings.review_port,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    legacy_lines = [
        "# Generated by woojae configure",
        "# Stored outside the git repository. Do not commit token values.",
        f"export MCP_ACCESS_TOKEN={shlex.quote(settings.mcp_access_token)}",
        f"export NGROK_HOST={shlex.quote(settings.ngrok_host)}",
        f"export WORKSPACE_ROOT={shlex.quote(str(settings.workspace_root))}",
        f"export MCP_HOST={shlex.quote(settings.mcp_host)}",
        f"export MCP_PORT={shlex.quote(str(settings.mcp_port))}",
        f"export BUNDLE_REVIEW_HOST={shlex.quote(settings.review_host)}",
        f"export BUNDLE_REVIEW_PORT={shlex.quote(str(settings.review_port))}",
        "",
    ]
    session_env_path(settings.runtime_root).write_text("\n".join(legacy_lines), encoding="utf-8")

    for path in (session_json_path(settings.runtime_root), session_env_path(settings.runtime_root)):
        try:
            path.chmod(0o600)
        except OSError:
            pass


def prompt_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def configure() -> int:
    current = load_settings()
    print("Workspace Terminal Bridge session configure")
    print(f"Runtime root: {current.runtime_root}")
    print(f"Session JSON: {session_json_path(current.runtime_root)}")
    print()

    if current.mcp_access_token:
        typed = getpass.getpass("MCP_ACCESS_TOKEN is already set. Press Enter to keep it, or type a new value: ")
        token = typed or current.mcp_access_token
        token_status = "updated" if typed else "kept"
    else:
        typed = getpass.getpass("MCP_ACCESS_TOKEN [auto-generate]: ")
        token = typed or secrets.token_urlsafe(32)
        token_status = "provided" if typed else "generated"

    ngrok_host = normalize_ngrok_host(prompt_text("NGROK_HOST, fixed domain optional", current.ngrok_host))
    workspace_root = Path(prompt_text("WORKSPACE_ROOT", str(current.workspace_root))).expanduser().resolve(strict=False)
    if is_dangerous_workspace_root(workspace_root):
        print(f"[error] Refusing dangerous WORKSPACE_ROOT: {workspace_root}", file=sys.stderr)
        return 1
    if not workspace_root.exists():
        answer = prompt_text("WORKSPACE_ROOT does not exist. Create it? [y/N]", "N").lower()
        if answer not in {"y", "yes"}:
            return 1
        workspace_root.mkdir(parents=True, exist_ok=True)

    settings = SessionSettings(
        runtime_root=current.runtime_root,
        mcp_access_token=token,
        ngrok_host=ngrok_host,
        workspace_root=workspace_root,
        mcp_host=prompt_text("MCP_HOST", current.mcp_host),
        mcp_port=int(prompt_text("MCP_PORT", str(current.mcp_port))),
        review_host=prompt_text("BUNDLE_REVIEW_HOST", current.review_host),
        review_port=int(prompt_text("BUNDLE_REVIEW_PORT", str(current.review_port))),
    )
    write_session_files(settings)
    print()
    print(f"Saved session config: {session_json_path(settings.runtime_root)}")
    print(f"MCP_ACCESS_TOKEN: {token_status}")
    print(f"NGROK_HOST: {settings.ngrok_host or 'not set; ngrok temporary URL mode will be used'}")
    print(f"WORKSPACE_ROOT: {settings.workspace_root}")
    return 0


def tcp_reachable(host: str, port: int, timeout_seconds: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def is_pid_alive(pid: int | None) -> bool:
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


def pid_file(settings: SessionSettings, service: str) -> Path:
    return settings.process_dir / f"{service}.pid"


def log_file(settings: SessionSettings, service: str) -> Path:
    return settings.process_dir / f"{service}.log"


def read_pid(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(value) if value.isdigit() else None


def service_endpoint(settings: SessionSettings, service: str) -> tuple[str | None, int | None]:
    if service == "review":
        return settings.review_host, settings.review_port
    if service == "mcp":
        return settings.mcp_host, settings.mcp_port
    return None, None


def service_command(settings: SessionSettings, service: str) -> list[str]:
    if service == "review":
        return [sys.executable, "scripts/command_bundle_review_server.py"]
    if service == "mcp":
        return [sys.executable, "server.py"]
    if service == "ngrok":
        if settings.ngrok_host:
            return ["ngrok", "http", f"--url={settings.ngrok_host}", str(settings.mcp_port)]
        return ["ngrok", "http", str(settings.mcp_port)]
    raise ValueError(f"unknown service: {service}")


def ensure_service(service: str) -> None:
    if service not in SERVICES:
        raise ValueError(f"unknown service: {service}")


def ensure_restartable(service: str) -> None:
    if service not in RESTARTABLE_SERVICES:
        raise ValueError("supported services: mcp, ngrok")


def start_service(service: str) -> int:
    ensure_service(service)
    settings = load_settings()
    settings.process_dir.mkdir(parents=True, exist_ok=True)
    path = pid_file(settings, service)
    pid = read_pid(path)
    if is_pid_alive(pid):
        print(f"[reuse] {service} pid={pid} log={log_file(settings, service)}")
        return 0
    if path.exists():
        path.unlink(missing_ok=True)

    host, port = service_endpoint(settings, service)
    if host and port and tcp_reachable(host, port, timeout_seconds=0.25):
        print(f"[warn] {service} is reachable but not supervisor-managed; not starting duplicate.")
        return 0
    if service == "ngrok" and shutil.which("ngrok") is None:
        print("[error] ngrok is not installed or not on PATH.", file=sys.stderr)
        return 1

    env = settings.as_env()
    if service == "review" and env.get("BUNDLE_WATCH_OPEN_MODE", "dashboard_once") == "dashboard_once":
        env["BUNDLE_WATCH_OPEN_MODE"] = "none"

    target_log = log_file(settings, service)
    with target_log.open("ab", buffering=0) as log:
        log.write(f"\n== {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} starting {service} ==\n".encode())
        kwargs: dict[str, object] = {
            "cwd": str(PROJECT_ROOT),
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "shell": False,
        }
        if is_windows():
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(service_command(settings, service), **kwargs)

    path.write_text(f"{process.pid}\n", encoding="utf-8")
    print(f"[start] {service} pid={process.pid} log={target_log}")
    time.sleep(0.4)
    if not is_pid_alive(process.pid):
        path.unlink(missing_ok=True)
        print(f"[warn] {service} exited quickly; see log={target_log}")
    return 0


def terminate_pid_tree(pid: int) -> None:
    if is_windows():
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
    for _ in range(15):
        if not is_pid_alive(pid):
            return
        time.sleep(0.2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass


def stop_service(service: str) -> int:
    ensure_service(service)
    settings = load_settings()
    path = pid_file(settings, service)
    pid = read_pid(path)
    if pid is None:
        print(f"[stop] {service} not managed")
        return 0
    if not is_pid_alive(pid):
        path.unlink(missing_ok=True)
        print(f"[stop] {service} stale pid removed")
        return 0
    print(f"[stop] {service} pid={pid}")
    terminate_pid_tree(pid)
    if is_pid_alive(pid):
        print(f"[warn] {service} may still be running; pid file kept: {path}")
        return 1
    path.unlink(missing_ok=True)
    print(f"[ok] {service} stopped")
    return 0


def print_service_status(settings: SessionSettings, service: str) -> None:
    path = pid_file(settings, service)
    pid = read_pid(path)
    state = "yes" if is_pid_alive(pid) else "stale" if path.exists() else "no"
    host, port = service_endpoint(settings, service)
    reach = ""
    if host and port:
        reach = f" reachable={'yes' if tcp_reachable(host, port, timeout_seconds=0.25) else 'no'} {host}:{port}"
    print(f"{service} pid={pid or 'none'} alive={state} log={log_file(settings, service)}{reach}")


def status_session() -> int:
    settings = load_settings()
    print("Workspace Terminal Bridge service status")
    print(f"Process directory: {settings.process_dir}")
    print()
    for service in SERVICES:
        print_service_status(settings, service)
    return 0


def start_session() -> int:
    settings = load_settings()
    settings.process_dir.mkdir(parents=True, exist_ok=True)
    print("Starting Workspace Terminal Bridge local session")
    print(f"Process directory: {settings.process_dir}")
    print()
    code = 0
    for service in SERVICES:
        code = max(code, start_service(service))
    print()
    open_review_dashboard()
    print()
    status_session()
    return code


def stop_session() -> int:
    print("Stopping Workspace Terminal Bridge local session")
    code = 0
    for service in reversed(SERVICES):
        code = max(code, stop_service(service))
    return code


def restart_service(service: str) -> int:
    ensure_restartable(service)
    stop_service(service)
    return start_service(service)


def start_single_service(service: str) -> int:
    ensure_restartable(service)
    return start_service(service)


def stop_single_service(service: str) -> int:
    ensure_restartable(service)
    return stop_service(service)


def restart_session() -> int:
    print("Restarting Workspace Terminal Bridge full local session")
    stop_session()
    return start_session()


def open_review_dashboard() -> int:
    settings = load_settings()
    print(f"Review dashboard: {settings.review_dashboard_url}")
    return 0 if webbrowser.open(settings.review_dashboard_url) else 1


def logs_service(service: str | None) -> int:
    settings = load_settings()
    if not service:
        print("Usage: woojae logs [review|mcp|ngrok]")
        for item in SERVICES:
            print(f"{item}: {log_file(settings, item)}")
        return 2
    ensure_service(service)
    path = log_file(settings, service)
    if not path.exists():
        print(f"[warn] log file does not exist yet: {path}")
        return 0
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
    for line in lines:
        print(line)
    return 0


def review_foreground() -> int:
    settings = load_settings()
    print("Starting command bundle review server with embedded watcher...")
    print(f"Review dashboard: {settings.review_dashboard_url}")
    print("Press Ctrl-C to stop the review server.")
    print()
    return subprocess.run([sys.executable, "scripts/command_bundle_review_server.py"], cwd=str(PROJECT_ROOT), env=settings.as_env(), check=False).returncode


def doctor() -> int:
    settings = load_settings()
    code = 0
    print("Workspace Terminal Bridge doctor")
    print()
    if session_json_path(settings.runtime_root).exists():
        print(f"[ok] session.json: found at {session_json_path(settings.runtime_root)}")
    elif session_env_path(settings.runtime_root).exists():
        print(f"[ok] legacy session.env: found at {session_env_path(settings.runtime_root)}")
    else:
        print("[info] session config not found; run `woojae configure` if you want runtime env auto-loading.")
    if shutil.which("uv"):
        print("[ok] uv: found")
    else:
        print("[error] uv: missing")
        code = 1
    print("[ok] ngrok: found" if shutil.which("ngrok") else "[warn] ngrok: missing; ngrok service will fail until ngrok is installed.")
    if sys.platform == "darwin":
        print("[ok] terminal-notifier: found" if shutil.which("terminal-notifier") else "[warn] terminal-notifier: missing; clickable macOS notifications require it.")
        print("[ok] osascript fallback: found" if shutil.which("osascript") else "[warn] osascript fallback: missing")
    elif sys.platform.startswith("linux"):
        print("[ok] notify-send: found" if shutil.which("notify-send") else "[info] notify-send: missing; desktop notifications disabled")
        print("[ok] xdg-open: found" if shutil.which("xdg-open") else "[info] xdg-open: missing; browser open falls back to Python webbrowser")
    elif is_windows():
        print("[ok] PowerShell: found" if (shutil.which("powershell") or shutil.which("pwsh")) else "[info] PowerShell: missing; desktop notifications disabled")
        print("[ok] clip: found" if shutil.which("clip") else "[info] clip: missing; copy-url clipboard helper unavailable")
    else:
        print("[info] desktop notifications: optional and platform-specific")
    print(f"[{'ok' if settings.mcp_access_token else 'warn'}] MCP_ACCESS_TOKEN: {'set' if settings.mcp_access_token else 'not set'}")
    print(f"[info] NGROK_HOST: {settings.ngrok_host or 'not set; temporary URL mode'}")
    print(f"[info] WORKSPACE_ROOT: {settings.workspace_root}")
    print()
    print("Supervisor services:")
    for service in SERVICES:
        print_service_status(settings, service)
    return code


def mcp_url_preview() -> int:
    settings = load_settings()
    if not settings.ngrok_host:
        print("NGROK_HOST is not configured.")
        print("Run `woojae configure` to save a fixed NGROK_HOST.")
        return 1
    print(f"https://{settings.ngrok_host}/mcp?access_token=<redacted>")
    return 0 if settings.mcp_access_token else 1


def copy_mcp_url() -> int:
    settings = load_settings()
    if not settings.ngrok_host or not settings.mcp_access_token:
        print("NGROK_HOST and MCP_ACCESS_TOKEN are required for copy-url.", file=sys.stderr)
        return 1
    url = f"https://{settings.ngrok_host}/mcp?access_token={settings.mcp_access_token}"
    if sys.platform == "darwin" and shutil.which("pbcopy"):
        completed = subprocess.run(["pbcopy"], input=url, text=True, check=False)
    elif is_windows() and shutil.which("clip"):
        completed = subprocess.run(["clip"], input=url, text=True, check=False)
    elif shutil.which("xclip"):
        completed = subprocess.run(["xclip", "-selection", "clipboard"], input=url, text=True, check=False)
    else:
        print("No supported clipboard command found.", file=sys.stderr)
        return 1
    if completed.returncode != 0:
        return completed.returncode
    print(f"Copied MCP URL: https://{settings.ngrok_host}/mcp?access_token=<redacted>")
    return 0


def print_paths() -> int:
    settings = load_settings()
    print("Workspace Terminal Bridge paths")
    print()
    for label, path in runtime_storage.runtime_paths(settings.runtime_root, settings.workspace_root):
        print(f"{label}: {path}")
    return 0


def print_storage() -> int:
    settings = load_settings()
    total = runtime_storage.total_storage(settings.runtime_root)
    print("Workspace Terminal Bridge runtime storage")
    print()
    print(f"Runtime root: {settings.runtime_root}")
    print(f"Total: {runtime_storage.format_bytes(total.bytes)} ({total.files} files, {total.dirs} dirs)")
    print()
    print("By category:")
    for entry in runtime_storage.storage_summary(settings.runtime_root):
        status = "present" if entry.exists else "missing"
        print(
            f"- {entry.name}: {runtime_storage.format_bytes(entry.bytes)} "
            f"({entry.files} files, {entry.dirs} dirs, {status})"
        )
    return 0


def cleanup_storage(*, apply: bool, older_than_days: int | None = None, include_backups: bool = False) -> int:
    if older_than_days is not None and older_than_days < 1:
        print("[error] --older-than-days must be a positive integer.", file=sys.stderr)
        return 2

    settings = load_settings()
    dry_run = not apply
    result = runtime_storage.cleanup_runtime(
        settings.runtime_root,
        dry_run=dry_run,
        older_than_days=older_than_days,
        include_backups=include_backups,
    )

    print("Workspace Terminal Bridge runtime cleanup")
    print()
    print(f"Runtime root: {settings.runtime_root}")
    print(f"Mode: {'dry-run' if result.dry_run else 'apply'}")
    print(f"Backup/trash cleanup: {'included' if include_backups else 'excluded'}")
    if older_than_days is not None:
        print(f"Age override: older than {older_than_days} days")
    print()

    if not result.candidates:
        print("No cleanup candidates found.")
    else:
        print("Candidates:")
        for candidate in result.candidates:
            action = candidate.action
            print(
                f"- [{action}] {candidate.path} "
                f"({candidate.kind}, {runtime_storage.format_bytes(candidate.bytes)}, {candidate.reason})"
            )

    print()
    if result.dry_run:
        print("No files were deleted. Re-run with `uv run woojae cleanup --apply` to delete eligible candidates.")
    else:
        print(
            "Deleted: "
            f"{result.deleted_files} files, {result.deleted_dirs} dirs, "
            f"estimated {runtime_storage.format_bytes(result.reclaimed_bytes)} reclaimed"
        )

    if result.errors:
        print()
        print("Errors:")
        for error in result.errors:
            print(f"- {error.path}: {error.error}")
        return 1

    return 0


def print_checklist() -> int:
    print("""Workspace Terminal Bridge development session checklist

1. Check local prerequisites:
   woojae doctor

2. Create a private runtime config:
   woojae configure

3. Start the full local session:
   woojae start

4. Confirm status:
   woojae status

5. Tail logs when debugging:
   woojae logs [review|mcp|ngrok]

6. Stop when finished:
   woojae stop

Compatibility wrappers:
  - macOS/Linux: scripts/dev_session.sh start
  - Windows PowerShell: scripts/dev_session.ps1 start
""")
    return 0
