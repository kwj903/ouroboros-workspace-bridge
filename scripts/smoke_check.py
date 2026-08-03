#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from terminal_bridge import session_supervisor
from terminal_bridge.public_access import PublicAccessConfigError


def redact_sensitive_text(value: str) -> str:
    value = re.sub(r"(?i)(access_token=)[^&\s]+", r"\1<redacted>", value)
    value = re.sub(r"(?i)(token=)[^&\s]+", r"\1<redacted>", value)
    value = re.sub(r"(?i)(Authorization:\s*Bearer\s+)\S+", r"\1<redacted>", value)
    return value


def format_command(command: list[str]) -> str:
    return " ".join(redact_sensitive_text(item) for item in command)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TOOLS = {
    "workspace_project_snapshot",
    "workspace_preview_patch",
    "workspace_transport_probe",
    "workspace_prepare_check_intent",
    "workspace_prepare_commit_current_changes_intent",
    "workspace_prepare_dev_session_intent",
    "workspace_recover_last_activity",
    "workspace_next_handoff",
    "workspace_list_handoffs",
    "workspace_list_tool_calls",
    "workspace_tool_call_status",
    "workspace_stage_text_payload",
    "workspace_propose_command_and_wait",
    "workspace_propose_file_write_and_wait",
    "workspace_propose_file_replace_and_wait",
    "workspace_propose_patch_and_wait",
    "workspace_propose_git_commit_and_wait",
    "workspace_propose_git_push_and_wait",
    "workspace_command_bundle_status",
    "workspace_wait_command_bundle_status",
    "workspace_list_command_bundles",
    "workspace_cancel_command_bundle",
    "workspace_task_start",
    "workspace_list_tasks",
}

DISALLOWED_TOOLS = {
    "workspace_stage_command_bundle",
    "workspace_stage_action_bundle",
    "workspace_stage_patch_bundle",
    "workspace_stage_commit_bundle",
}


def run_command(command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    print(f"$ {format_command(command)}")
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )

    if completed.stdout:
        print(completed.stdout.rstrip())

    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)

    return completed


def require_success(name: str, completed: subprocess.CompletedProcess[str]) -> None:
    if completed.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {completed.returncode}")


def check_local_python() -> None:
    result = run_command([sys.executable, "-m", "py_compile", "server.py"], timeout=30)
    require_success("py_compile", result)


def check_script_entrypoint_imports() -> None:
    scripts = [
        "scripts/command_bundle_review_server.py",
        "scripts/command_bundle_watcher.py",
    ]

    for script in scripts:
        snippet = f"""
import runpy
import sys
from pathlib import Path

project_root = Path.cwd().resolve()
script_path = (project_root / {script!r}).resolve()
script_dir = str(script_path.parent)

sys.path = [script_dir] + [
    item for item in sys.path
    if item not in ("", str(project_root), str(script_path.parent))
]

runpy.run_path(str(script_path), run_name="__smoke_import__")
print("script entrypoint import OK: {script}")
""".strip()
        result = run_command([sys.executable, "-c", snippet], timeout=30)
        require_success(f"script entrypoint import {script}", result)


def check_unit_tests() -> None:
    result = run_command([sys.executable, "-m", "unittest", "discover", "-s", "tests"], timeout=180)
    require_success("unit tests", result)


def check_git_diff() -> None:
    result = run_command(["git", "diff", "--check"], timeout=30)
    require_success("git diff --check", result)


async def call_workspace_info(
    base_url: str,
    token: str,
    timeout: int,
) -> dict[str, object]:
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(
        base_url,
        headers=headers,
        timeout=float(timeout),
        sse_read_timeout=float(timeout),
    ) as (read_stream, write_stream, _get_session_id):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool("workspace_info", {})

    if result.isError:
        raise RuntimeError("workspace_info returned isError=true")
    structured = result.structuredContent
    if not isinstance(structured, dict):
        raise RuntimeError("workspace_info response did not include structuredContent.")
    return structured


def check_workspace_info(base_url: str, token: str, timeout: int) -> None:
    structured = asyncio.run(call_workspace_info(base_url, token, timeout))
    tools = structured.get("tools")
    if not isinstance(tools, list):
        raise RuntimeError("workspace_info response did not include a tools list.")

    exposed_tools = {str(tool) for tool in tools}

    missing = sorted(EXPECTED_TOOLS.difference(exposed_tools))
    if missing:
        raise RuntimeError(f"workspace_info is missing expected tools: {', '.join(missing)}")

    exposed_disallowed = sorted(DISALLOWED_TOOLS.intersection(exposed_tools))
    if exposed_disallowed:
        raise RuntimeError(f"workspace_info exposed disallowed tools: {', '.join(exposed_disallowed)}")

    print(f"workspace_info OK: {len(tools)} tools exposed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local smoke checks for Workspace Terminal Bridge.")
    parser.add_argument(
        "--mcp-url",
        default=os.environ.get("MCP_URL"),
        help=(
            "Optional token-free public MCP base URL. The token is loaded from "
            "MCP_ACCESS_TOKEN. Token-bearing URLs are rejected."
        ),
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Verify the configured public MCP endpoint using the private session token.",
    )
    parser.add_argument(
        "--remote-only",
        action="store_true",
        help="Run only the configured remote MCP check, without repeating local checks.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout in seconds for remote MCP checks.",
    )

    args = parser.parse_args()

    checks = []
    if not args.remote_only:
        checks.extend(
            [
                ("py_compile", lambda: check_local_python()),
                ("script entrypoint imports", lambda: check_script_entrypoint_imports()),
                ("unit tests", lambda: check_unit_tests()),
                ("git diff --check", lambda: check_git_diff()),
            ]
        )

    if args.remote or args.remote_only:
        try:
            settings = session_supervisor.load_settings()
        except PublicAccessConfigError as exc:
            print(f"Remote MCP smoke skipped: {exc}")
        else:
            if settings.public_mcp_base_url and settings.mcp_access_token:
                checks.append(
                    (
                        "workspace_info",
                        lambda: check_workspace_info(
                            settings.public_mcp_base_url,
                            settings.mcp_access_token,
                            args.timeout,
                        ),
                    )
                )
            else:
                print(
                    "A fixed public MCP endpoint and MCP_ACCESS_TOKEN are required; "
                    "skipping remote MCP checks."
                )
    elif args.mcp_url:
        from urllib.parse import parse_qs, urlsplit, urlunsplit

        parsed = urlsplit(args.mcp_url)
        query = parse_qs(parsed.query, keep_blank_values=False)
        if query.get("access_token") or query.get("token"):
            print(
                "Smoke check failed: token-bearing --mcp-url values are not allowed. "
                "Use --remote or pass a token-free base URL with MCP_ACCESS_TOKEN "
                "stored privately.",
                file=sys.stderr,
            )
            return 2
        token = os.environ.get("MCP_ACCESS_TOKEN", "")
        base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        if base_url and token:
            checks.append(
                (
                    "workspace_info",
                    lambda: check_workspace_info(base_url, token, args.timeout),
                )
            )
        else:
            print(
                "A token-free --mcp-url and private MCP_ACCESS_TOKEN are both required; "
                "skipping remote checks."
            )
    else:
        print("Remote MCP checks were not requested; use --remote to enable them.")

    try:
        for name, check in checks:
            print(f"\n==> {name}")
            check()
    except Exception as exc:
        print(f"\nSmoke check failed: {exc}", file=sys.stderr)
        return 1

    print("\nSmoke check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
