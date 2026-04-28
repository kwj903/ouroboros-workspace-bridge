from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import webbrowser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEV_SESSION = PROJECT_ROOT / "scripts" / "dev_session.sh"
REVIEW_DASHBOARD_URL = "http://127.0.0.1:8790/pending"
DEFAULT_RUNTIME_ROOT = Path.home() / ".mcp_terminal_bridge" / "my-terminal-tool"


def run_dev_session(*args: str) -> int:
    if not DEV_SESSION.exists():
        print(f"dev session script not found: {DEV_SESSION}", file=sys.stderr)
        return 1

    return subprocess.run([str(DEV_SESSION), *args], check=False).returncode


def open_review_dashboard() -> int:
    if sys.platform == "darwin":
        return subprocess.run(["open", REVIEW_DASHBOARD_URL], check=False).returncode

    opened = webbrowser.open(REVIEW_DASHBOARD_URL)
    return 0 if opened else 1


def runtime_root() -> Path:
    return Path(os.environ.get("MCP_TERMINAL_BRIDGE_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT))).expanduser()


def session_env_value(name: str) -> str | None:
    path = runtime_root() / "session.env"
    if not path.exists():
        return None

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    prefixes = (f"export {name}=", f"{name}=")
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(prefixes):
            continue

        assignment = stripped.removeprefix("export ")
        try:
            parts = shlex.split(assignment, comments=False, posix=True)
        except ValueError:
            continue
        if not parts or not parts[0].startswith(f"{name}="):
            continue
        return parts[0].split("=", 1)[1]

    return None


def env_or_session(name: str) -> str:
    return os.environ.get(name) or session_env_value(name) or ""


def normalize_ngrok_host(value: str) -> str:
    host = value.strip()
    host = host.removeprefix("https://").removeprefix("http://")
    host = host.split("/", 1)[0]
    host = host.split("?", 1)[0]
    host = host.split("#", 1)[0]
    return host


def configured_ngrok_host() -> str:
    return normalize_ngrok_host(env_or_session("NGROK_HOST") or env_or_session("NGROK_BASE_URL"))


def mcp_url(token: str) -> str | None:
    host = configured_ngrok_host()
    if not host:
        return None
    return f"https://{host}/mcp?access_token={token}"


def print_mcp_url_preview() -> int:
    host = configured_ngrok_host()
    if not host:
        print("NGROK_HOST is not configured.")
        print("Run `woojae start` first; temporary ngrok URL mode may require checking ngrok output/logs.")
        print("Run `woojae setup` to save a fixed NGROK_HOST.")
        return 1

    print(f"https://{host}/mcp?access_token=<redacted>")
    if not env_or_session("MCP_ACCESS_TOKEN"):
        print("MCP_ACCESS_TOKEN is not configured. Run `woojae setup` before connecting ChatGPT.")
        return 1
    return 0


def copy_mcp_url() -> int:
    if sys.platform != "darwin":
        print("copy-url is currently supported only on macOS with pbcopy.", file=sys.stderr)
        return 1

    token = env_or_session("MCP_ACCESS_TOKEN")
    if not token:
        print("NGROK_HOST and MCP_ACCESS_TOKEN are required for copy-url.", file=sys.stderr)
        print("Run `woojae setup` to configure them.", file=sys.stderr)
        return 1

    url = mcp_url(token)
    if not url:
        print("NGROK_HOST and MCP_ACCESS_TOKEN are required for copy-url.", file=sys.stderr)
        print("Run `woojae setup` to configure them.", file=sys.stderr)
        return 1

    process = subprocess.run(["pbcopy"], input=url, text=True, check=False)
    if process.returncode != 0:
        print("Failed to copy MCP URL with pbcopy.", file=sys.stderr)
        return process.returncode

    host = configured_ngrok_host()
    print(f"Copied MCP URL: https://{host}/mcp?access_token=<redacted>")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="woojae",
        description="Manage a local Workspace Terminal Bridge session.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("setup", "configure", "doctor", "start", "status", "stop"):
        subparsers.add_parser(name)

    restart = subparsers.add_parser("restart")
    restart.add_argument("service", choices=("mcp", "ngrok"))

    logs = subparsers.add_parser("logs")
    logs.add_argument("service", nargs="?", choices=("review", "mcp", "ngrok"))

    subparsers.add_parser("open")
    subparsers.add_parser("mcp-url")
    subparsers.add_parser("copy-url")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in {"setup", "configure"}:
        return run_dev_session("configure")
    if args.command in {"doctor", "start", "status", "stop"}:
        return run_dev_session(args.command)
    if args.command == "restart":
        return run_dev_session("restart", args.service)
    if args.command == "logs":
        if args.service:
            return run_dev_session("logs", args.service)
        return run_dev_session("logs")
    if args.command == "open":
        return open_review_dashboard()
    if args.command == "mcp-url":
        return print_mcp_url_preview()
    if args.command == "copy-url":
        return copy_mcp_url()

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
