#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


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
    result = run_command([sys.executable, "-m", "unittest", "discover", "-s", "tests"], timeout=60)
    require_success("unit tests", result)


def check_git_diff() -> None:
    result = run_command(["git", "diff", "--check"], timeout=30)
    require_success("git diff --check", result)


def check_workspace_info(mcp_url: str, timeout: int) -> None:
    if shutil.which("npx") is None:
        raise RuntimeError("npx is required for MCP inspector checks but was not found on PATH.")

    result = run_command(
        [
            "npx",
            "-y",
            "@modelcontextprotocol/inspector",
            "--cli",
            mcp_url,
            "--transport",
            "http",
            "--method",
            "tools/call",
            "--tool-name",
            "workspace_info",
        ],
        timeout=timeout,
    )
    require_success("workspace_info inspector call", result)

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Inspector output was not valid JSON: {exc}") from exc

    if payload.get("isError"):
        raise RuntimeError(f"workspace_info returned isError=true: {payload}")

    structured = payload.get("structuredContent")
    if not isinstance(structured, dict):
        raise RuntimeError("workspace_info response did not include structuredContent.")

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
        help="Optional MCP URL to verify through MCP Inspector. Can also be set via MCP_URL.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout in seconds for Inspector-based checks.",
    )

    args = parser.parse_args()

    checks = [
        ("py_compile", lambda: check_local_python()),
        ("script entrypoint imports", lambda: check_script_entrypoint_imports()),
        ("unit tests", lambda: check_unit_tests()),
        ("git diff --check", lambda: check_git_diff()),
    ]

    if args.mcp_url:
        checks.append(("workspace_info", lambda: check_workspace_info(args.mcp_url, args.timeout)))
    else:
        print("MCP_URL was not provided; skipping Inspector-based MCP checks.")

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
