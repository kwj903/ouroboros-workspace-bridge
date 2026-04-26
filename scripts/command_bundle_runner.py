#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path.home() / "workspace"
RUNTIME_ROOT = Path.home() / ".mcp_terminal_bridge" / "my-terminal-tool"
COMMAND_BUNDLES_DIR = RUNTIME_ROOT / "command_bundles"
PENDING_DIR = COMMAND_BUNDLES_DIR / "pending"
APPLIED_DIR = COMMAND_BUNDLES_DIR / "applied"
REJECTED_DIR = COMMAND_BUNDLES_DIR / "rejected"
FAILED_DIR = COMMAND_BUNDLES_DIR / "failed"

MAX_STDOUT_CHARS = 20_000
MAX_STDERR_CHARS = 8_000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bundle_dirs() -> list[Path]:
    return [PENDING_DIR, APPLIED_DIR, REJECTED_DIR, FAILED_DIR]


def find_bundle(bundle_id: str) -> tuple[Path, dict[str, Any]]:
    for directory in bundle_dirs():
        path = directory / f"{bundle_id}.json"
        if path.exists():
            return path, read_json(path)
    raise FileNotFoundError(f"Bundle not found: {bundle_id}")


def truncate(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[:limit] + "\n...[truncated]...", True


def safe_env() -> dict[str, str]:
    project_root = Path(__file__).resolve().parent.parent
    fallback_path = ":".join(
        [
            str(project_root / ".venv/bin"),
            str(Path.home() / ".local/bin"),
            str(Path.home() / ".local/share/mise/shims"),
            str(Path.home() / ".local/share/mise/installs/python/3.12/bin"),
            "/usr/local/bin",
            "/opt/homebrew/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
        ]
    )
    return {
        "PATH": os.environ.get("PATH") or fallback_path,
        "HOME": str(WORKSPACE_ROOT / ".mcp_home"),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
        "USER": os.environ.get("USER", ""),
        "LOGNAME": os.environ.get("LOGNAME", ""),
        "SHELL": os.environ.get("SHELL", ""),
        "TERM": os.environ.get("TERM", ""),
    }


def resolve_cwd(cwd: str) -> Path:
    raw = Path(cwd)
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("cwd must be a relative path under ~/workspace")

    target = (WORKSPACE_ROOT / raw).resolve(strict=False)
    if target != WORKSPACE_ROOT and not target.is_relative_to(WORKSPACE_ROOT):
        raise ValueError("cwd escapes ~/workspace")
    if not target.exists() or not target.is_dir():
        raise NotADirectoryError(f"cwd does not exist or is not a directory: {cwd}")

    return target


def move_bundle(source: Path, record: dict[str, Any], status: str) -> None:
    target = {
        "applied": APPLIED_DIR,
        "rejected": REJECTED_DIR,
        "failed": FAILED_DIR,
    }[status] / source.name

    record["status"] = status
    record["updated_at"] = now_iso()
    write_json(target, record)

    if source != target and source.exists():
        source.unlink()


def list_bundles() -> None:
    rows: list[tuple[str, str, str, str, str]] = []

    for directory in bundle_dirs():
        for path in sorted(directory.glob("cmd-*.json")):
            try:
                record = read_json(path)
            except Exception:
                continue

            rows.append(
                (
                    str(record.get("updated_at", "")),
                    str(record.get("bundle_id", path.stem)),
                    str(record.get("status", directory.name)),
                    str(record.get("risk", "")),
                    str(record.get("title", "")),
                )
            )

    rows.sort(reverse=True)

    for _, bundle_id, status, risk, title in rows:
        print(f"{bundle_id}\t{status}\t{risk}\t{title}")


def preview(bundle_id: str) -> None:
    path, record = find_bundle(bundle_id)
    print(f"bundle_id: {record.get('bundle_id')}")
    print(f"title: {record.get('title')}")
    print(f"cwd: {record.get('cwd')}")
    print(f"status: {record.get('status')}")
    print(f"risk: {record.get('risk')}")
    print(f"file: {path}")
    print()

    for idx, step in enumerate(record.get("steps", []), 1):
        print(f"{idx}. {step.get('name')}")
        print(f"   argv: {step.get('argv')}")
        print(f"   risk: {step.get('risk')}")
        print(f"   reason: {step.get('reason')}")
        print(f"   timeout: {step.get('timeout_seconds')}")


def reject(bundle_id: str) -> None:
    path, record = find_bundle(bundle_id)
    if record.get("status") != "pending":
        raise SystemExit(f"Only pending bundles can be rejected. Current: {record.get('status')}")

    record["error"] = "Rejected by local command_bundle_runner."
    record["result"] = None
    move_bundle(path, record, "rejected")
    print(f"rejected {bundle_id}")


def apply_bundle(bundle_id: str, yes: bool) -> None:
    path, record = find_bundle(bundle_id)
    if record.get("status") != "pending":
        raise SystemExit(f"Only pending bundles can be applied. Current: {record.get('status')}")

    preview(bundle_id)

    if not yes:
        answer = input("\nApply this command bundle? Type 'yes' to continue: ")
        if answer.strip() != "yes":
            raise SystemExit("aborted")

    cwd = resolve_cwd(str(record.get("cwd", ".")))
    results: list[dict[str, Any]] = []
    failed = False

    for idx, step in enumerate(record.get("steps", []), 1):
        argv = step.get("argv")
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            raise SystemExit(f"Invalid argv in step {idx}")

        timeout = int(step.get("timeout_seconds", 60))
        print(f"\n[{idx}] running: {argv}")

        try:
            completed = subprocess.run(
                argv,
                cwd=str(cwd),
                env=safe_env(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                shell=False,
                check=False,
            )
            stdout, out_truncated = truncate(completed.stdout, MAX_STDOUT_CHARS)
            stderr, err_truncated = truncate(completed.stderr, MAX_STDERR_CHARS)

            results.append(
                {
                    "name": step.get("name"),
                    "argv": argv,
                    "exit_code": completed.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "truncated": out_truncated or err_truncated,
                }
            )

            if stdout:
                print(stdout, end="" if stdout.endswith("\n") else "\n")
            if stderr:
                print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)

            if completed.returncode != 0:
                failed = True
                break

        except Exception as exc:
            failed = True
            results.append(
                {
                    "name": step.get("name"),
                    "argv": argv,
                    "exit_code": None,
                    "stdout": "",
                    "stderr": str(exc),
                    "truncated": False,
                }
            )
            print(str(exc), file=sys.stderr)
            break

    record["result"] = {
        "cwd": str(record.get("cwd", ".")),
        "steps": results,
        "ok": not failed,
    }
    record["error"] = None if not failed else "One or more command steps failed."

    move_bundle(path, record, "failed" if failed else "applied")
    print(f"\n{'failed' if failed else 'applied'} {bundle_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview/apply staged MCP command bundles.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    p_preview = sub.add_parser("preview")
    p_preview.add_argument("bundle_id")

    p_apply = sub.add_parser("apply")
    p_apply.add_argument("bundle_id")
    p_apply.add_argument("--yes", action="store_true")

    p_reject = sub.add_parser("reject")
    p_reject.add_argument("bundle_id")

    args = parser.parse_args()

    if args.cmd == "list":
        list_bundles()
    elif args.cmd == "preview":
        preview(args.bundle_id)
    elif args.cmd == "apply":
        apply_bundle(args.bundle_id, yes=args.yes)
    elif args.cmd == "reject":
        reject(args.bundle_id)
    else:
        parser.error("unknown command")


if __name__ == "__main__":
    main()
