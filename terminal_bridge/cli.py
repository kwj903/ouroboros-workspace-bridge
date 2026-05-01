from __future__ import annotations

import argparse
import sys

from terminal_bridge import session_supervisor as supervisor
from terminal_bridge.version import version_summary


def run_dev_session(*args: str) -> int:
    """Backward-compatible adapter for the old dev_session helper commands."""
    if not args:
        return supervisor.print_checklist()

    command = args[0]
    if command == "configure":
        return supervisor.configure()
    if command == "checklist":
        return supervisor.print_checklist()
    if command == "doctor":
        return supervisor.doctor()
    if command == "review":
        return supervisor.review_foreground()
    if command == "start":
        return supervisor.start_session()
    if command == "status":
        return supervisor.status_session()
    if command == "stop":
        return supervisor.stop_session()
    if command == "restart-session":
        return supervisor.restart_session()
    if command == "start-service" and len(args) > 1:
        return supervisor.start_single_service(args[1])
    if command == "stop-service" and len(args) > 1:
        return supervisor.stop_single_service(args[1])
    if command == "restart" and len(args) > 1:
        return supervisor.restart_service(args[1])
    if command == "logs":
        return supervisor.logs_service(args[1] if len(args) > 1 else None)

    print(f"Unknown dev session command: {' '.join(args)}", file=sys.stderr)
    return 2


def configured_ngrok_host() -> str:
    return supervisor.load_settings().ngrok_host


def mcp_url(token: str) -> str | None:
    host = configured_ngrok_host()
    if not host:
        return None
    return f"https://{host}/mcp?access_token={token}"


def open_review_dashboard() -> int:
    return supervisor.open_review_dashboard()


def print_mcp_url_preview() -> int:
    return supervisor.mcp_url_preview()


def copy_mcp_url() -> int:
    return supervisor.copy_mcp_url()


def print_version_info() -> int:
    summary = version_summary()
    print(f"{summary['name']} {summary['version']}")
    print(f"commit: {summary['commit']}")
    print(f"branch: {summary['branch']}")
    print(f"dirty: {summary['dirty']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="woojae",
        description="Manage a local Workspace Terminal Bridge session.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("setup", "configure", "checklist", "doctor", "review", "start", "status", "stop"):
        subparsers.add_parser(name)

    subparsers.add_parser("restart-session", help="Restart the full local review, MCP, and ngrok session.")

    for name in ("start-service", "stop-service"):
        parser_for_service = subparsers.add_parser(name)
        parser_for_service.add_argument("service", choices=("mcp", "ngrok"))

    restart = subparsers.add_parser("restart")
    restart.add_argument("service", choices=("mcp", "ngrok"))

    logs = subparsers.add_parser("logs")
    logs.add_argument("service", nargs="?", choices=("review", "mcp", "ngrok"))

    subparsers.add_parser("open")
    subparsers.add_parser("mcp-url")
    subparsers.add_parser("copy-url")
    subparsers.add_parser("paths", help="Print project, runtime, and workspace paths.")
    subparsers.add_parser("storage", help="Print runtime storage usage by category.")
    cleanup = subparsers.add_parser("cleanup", help="Inspect or delete conservative runtime cleanup candidates.")
    cleanup_mode = cleanup.add_mutually_exclusive_group()
    cleanup_mode.add_argument("--dry-run", action="store_true", help="Show cleanup candidates without deleting anything.")
    cleanup_mode.add_argument("--apply", action="store_true", help="Delete eligible cleanup candidates.")
    cleanup.add_argument("--older-than-days", type=int, default=None, help="Override age threshold for age-based cleanup candidates.")
    cleanup.add_argument("--include-backups", action="store_true", help="Include backups, command bundle file backups, and trash in cleanup candidates.")
    subparsers.add_parser("version", help="Show version and git metadata.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in {"setup", "configure"}:
        return run_dev_session("configure")
    if args.command in {"checklist", "doctor", "review", "start", "status", "stop"}:
        return run_dev_session(args.command)
    if args.command == "restart-session":
        return run_dev_session("restart-session")
    if args.command in {"start-service", "stop-service", "restart"}:
        return run_dev_session(args.command, args.service)
    if args.command == "logs":
        return run_dev_session("logs", args.service) if args.service else run_dev_session("logs")
    if args.command == "open":
        return open_review_dashboard()
    if args.command == "mcp-url":
        return print_mcp_url_preview()
    if args.command == "copy-url":
        return copy_mcp_url()
    if args.command == "paths":
        return supervisor.print_paths()
    if args.command == "storage":
        return supervisor.print_storage()
    if args.command == "cleanup":
        if args.older_than_days is not None and args.older_than_days < 1:
            print("[error] --older-than-days must be a positive integer.", file=sys.stderr)
            return 2
        return supervisor.cleanup_storage(
            apply=bool(args.apply),
            older_than_days=args.older_than_days,
            include_backups=bool(args.include_backups),
        )
    if args.command == "version":
        return print_version_info()

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
