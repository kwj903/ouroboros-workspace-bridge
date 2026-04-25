#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TOOLS = {
    "workspace_project_snapshot",
    "workspace_preview_patch",
    "workspace_apply_patch",
    "workspace_task_start",
    "workspace_list_tasks",
}


def run_command(command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(command)}")
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

    missing = sorted(EXPECTED_TOOLS.difference(str(tool) for tool in tools))
    if missing:
        raise RuntimeError(f"workspace_info is missing expected tools: {', '.join(missing)}")

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
