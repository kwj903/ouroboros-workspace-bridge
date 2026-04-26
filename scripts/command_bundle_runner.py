#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
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
BACKUP_DIR = RUNTIME_ROOT / "command_bundle_file_backups"
TEXT_PAYLOAD_DIR = RUNTIME_ROOT / "text_payloads"

MAX_STDOUT_CHARS = 20_000
MAX_STDERR_CHARS = 8_000
TEXT_PAYLOAD_MAX_TOTAL_CHARS = 1_000_000

BLOCKED_DIR_NAMES = {
    ".ssh",
    ".aws",
    ".gnupg",
    ".config",
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".mcp_trash",
}

BLOCKED_FILE_PATTERNS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_ed25519",
    ".git-credentials",
    "credentials",
    "credentials.json",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_text_payload_id(payload_id: str) -> str:
    normalized = payload_id.strip()

    if normalized == "":
        raise ValueError("payload_id cannot be empty.")

    if len(normalized) > 120:
        raise ValueError("payload_id is too long.")

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(ch not in allowed for ch in normalized):
        raise ValueError("payload_id can only contain letters, numbers, '-' and '_'.")

    return normalized


def read_text_payload_ref(payload_ref: str) -> str:
    payload_id = normalize_text_payload_id(payload_ref)
    payload_dir = TEXT_PAYLOAD_DIR / payload_id
    manifest_path = payload_dir / "manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"text payload ref does not exist: {payload_id}")

    manifest = read_json(manifest_path)

    if not bool(manifest.get("complete", False)):
        raise ValueError(f"text payload ref is incomplete: {payload_id}")

    total_chunks = int(manifest.get("total_chunks", 0))
    if total_chunks < 1:
        raise ValueError(f"text payload manifest is invalid: {payload_id}")

    parts: list[str] = []
    for idx in range(total_chunks):
        chunk_path = payload_dir / f"chunk_{idx:06d}.txt"
        if not chunk_path.exists():
            raise FileNotFoundError(f"text payload chunk is missing: {payload_id}#{idx}")
        parts.append(chunk_path.read_text(encoding="utf-8"))

    content = "".join(parts)
    if len(content) > TEXT_PAYLOAD_MAX_TOTAL_CHARS:
        raise ValueError(f"text payload too large: {payload_id}")

    return content


def step_text(step: dict[str, Any], key: str) -> str:
    inline_value = step.get(key)
    ref_value = step.get(f"{key}_ref")

    if inline_value is not None and ref_value:
        raise ValueError(f"{key} and {key}_ref cannot both be set.")

    if inline_value is not None:
        return str(inline_value)

    if ref_value:
        return read_text_payload_ref(str(ref_value))

    raise ValueError(f"{key} or {key}_ref is required.")


def text_source_preview(step: dict[str, Any], key: str) -> str:
    ref_value = step.get(f"{key}_ref")
    chars_value = step.get(f"{key}_chars")

    if ref_value:
        return f"ref={ref_value}, chars={chars_value}"

    return f"inline_chars={len(str(step.get(key, '')))}"


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


def is_blocked_name(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in BLOCKED_FILE_PATTERNS)


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
        "HOME": os.environ.get("HOME", str(Path.home())),
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


def resolve_file_path(raw_path: str) -> Path:
    raw = Path(raw_path)
    if raw.is_absolute() or raw_path.startswith("~") or ".." in raw.parts:
        raise ValueError(f"unsafe file action path: {raw_path}")

    target = (WORKSPACE_ROOT / raw).resolve(strict=False)
    if target != WORKSPACE_ROOT and not target.is_relative_to(WORKSPACE_ROOT):
        raise ValueError(f"file action path escapes ~/workspace: {raw_path}")

    rel_parts = target.relative_to(WORKSPACE_ROOT).parts
    if any(part in BLOCKED_DIR_NAMES for part in rel_parts):
        raise PermissionError(f"file action touches blocked directory: {raw_path}")

    if is_blocked_name(target.name):
        raise PermissionError(f"file action touches blocked file: {raw_path}")

    return target


def clean_patch_path(raw_path: str) -> str | None:
    value = raw_path.strip()

    if "\t" in value:
        value = value.split("\t", 1)[0]

    if value == "/dev/null":
        return None

    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]

    if value == "":
        return None

    path = Path(value)

    if path.is_absolute() or value.startswith("~") or ".." in path.parts:
        raise ValueError(f"unsafe patch path: {raw_path}")

    if value.startswith(".git/") or "/.git/" in value:
        raise PermissionError(f"patch path touches .git: {raw_path}")

    return value


def extract_patch_paths(patch: str) -> list[str]:
    paths: set[str] = set()

    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                for raw in (parts[2], parts[3]):
                    cleaned = clean_patch_path(raw)
                    if cleaned is not None:
                        paths.add(cleaned)

        elif line.startswith("--- ") or line.startswith("+++ "):
            cleaned = clean_patch_path(line[4:])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("rename from "):
            cleaned = clean_patch_path(line[len("rename from ") :])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("rename to "):
            cleaned = clean_patch_path(line[len("rename to ") :])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("copy from "):
            cleaned = clean_patch_path(line[len("copy from ") :])
            if cleaned is not None:
                paths.add(cleaned)

        elif line.startswith("copy to "):
            cleaned = clean_patch_path(line[len("copy to ") :])
            if cleaned is not None:
                paths.add(cleaned)

    if not paths:
        raise ValueError("No patch file paths were found.")

    return sorted(paths)


def resolve_patch_path(cwd: Path, patch_path: str) -> Path:
    cwd_rel = relative(cwd)
    combined = Path(patch_path) if cwd_rel == "." else Path(cwd_rel) / patch_path
    return resolve_file_path(str(combined))


def validate_patch_paths(cwd: Path, patch_paths: list[str]) -> None:
    for patch_path in patch_paths:
        resolve_patch_path(cwd, patch_path)


def run_git_apply(cwd: Path, args: list[str], patch: str, timeout_seconds: int = 30) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "apply", *args],
        input=patch,
        cwd=str(cwd),
        env=safe_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
        shell=False,
        check=False,
    )
    stdout, out_truncated = truncate(completed.stdout, MAX_STDOUT_CHARS)
    stderr, err_truncated = truncate(completed.stderr, MAX_STDERR_CHARS)
    return {
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "truncated": out_truncated or err_truncated,
    }


def step_patch_paths(step: dict[str, Any], patch: str) -> list[str]:
    raw_files = step.get("files")
    if isinstance(raw_files, list) and raw_files:
        return [str(item) for item in raw_files]
    return extract_patch_paths(patch)


def relative(path: Path) -> str:
    return str(path.resolve(strict=False).relative_to(WORKSPACE_ROOT))


def backup_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / stamp / relative(path)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return str(backup_path)


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


def step_type(step: dict[str, Any]) -> str:
    return str(step.get("type", "command"))


def preview(bundle_id: str) -> None:
    path, record = find_bundle(bundle_id)
    print(f"bundle_id: {record.get('bundle_id')}")
    print(f"title: {record.get('title')}")
    print(f"cwd: {record.get('cwd')}")
    print(f"status: {record.get('status')}")
    print(f"risk: {record.get('risk')}")
    print(f"file: {path}")
    print()

    for idx, raw_step in enumerate(record.get("steps", []), 1):
        if not isinstance(raw_step, dict):
            continue

        kind = step_type(raw_step)
        print(f"{idx}. {raw_step.get('name')}")
        print(f"   type: {kind}")
        print(f"   risk: {raw_step.get('risk')}")
        print(f"   reason: {raw_step.get('reason')}")

        if kind == "command":
            print(f"   argv: {raw_step.get('argv')}")
            print(f"   timeout: {raw_step.get('timeout_seconds')}")
        elif kind == "apply_patch":
            print(f"   cwd: {raw_step.get('cwd', record.get('cwd'))}")
            print(f"   patch source: {text_source_preview(raw_step, 'patch')}")
            print(f"   files: {raw_step.get('files')}")
            try:
                step_cwd = resolve_cwd(str(raw_step.get("cwd", record.get("cwd", "."))))
                patch = step_text(raw_step, "patch")
                if not raw_step.get("patch_ref"):
                    patch_preview, _ = truncate(patch, 1000)
                    print("   inline patch preview:")
                    for line in patch_preview.splitlines():
                        print(f"     {line}")
                patch_paths = step_patch_paths(raw_step, patch)
                validate_patch_paths(step_cwd, patch_paths)
                check = run_git_apply(step_cwd, ["--check"], patch)
                print(f"   can_apply: {check['exit_code'] == 0}")
                print(f"   git apply --check exit_code: {check['exit_code']}")
                if check["stdout"]:
                    print(f"   check stdout: {check['stdout']}")
                if check["stderr"]:
                    print(f"   check stderr: {check['stderr']}")
            except Exception as exc:
                print(f"   git apply --check error: {exc}")
        else:
            print(f"   path: {raw_step.get('path')}")
            if kind in {"write_file", "append_file"}:
                print(f"   content: {text_source_preview(raw_step, 'content')}")
                print(f"   overwrite: {raw_step.get('overwrite')}")
            elif kind == "replace_text":
                print(f"   old_text: {text_source_preview(raw_step, 'old_text')}")
                print(f"   new_text: {text_source_preview(raw_step, 'new_text')}")
                print(f"   replace_all: {raw_step.get('replace_all')}")


def reject(bundle_id: str) -> None:
    path, record = find_bundle(bundle_id)
    if record.get("status") != "pending":
        raise SystemExit(f"Only pending bundles can be rejected. Current: {record.get('status')}")

    record["error"] = "Rejected by local command_bundle_runner."
    record["result"] = None
    move_bundle(path, record, "rejected")
    print(f"rejected {bundle_id}")


def apply_command(cwd: Path, step: dict[str, Any]) -> dict[str, Any]:
    argv = step.get("argv")
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
        raise ValueError("Invalid command argv")

    timeout = int(step.get("timeout_seconds", 60))
    print(f"running command: {argv}")

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

    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)

    return {
        "type": "command",
        "name": step.get("name"),
        "argv": argv,
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "truncated": out_truncated or err_truncated,
    }


def apply_write_file(step: dict[str, Any]) -> dict[str, Any]:
    target = resolve_file_path(str(step.get("path", "")))
    content = step_text(step, "content")
    overwrite = bool(step.get("overwrite", False))
    create_parent_dirs = bool(step.get("create_parent_dirs", True))

    if target.exists() and not overwrite:
        raise FileExistsError(f"file already exists and overwrite=false: {relative(target)}")

    if create_parent_dirs:
        target.parent.mkdir(parents=True, exist_ok=True)

    backup_path = backup_file(target)
    target.write_text(content, encoding="utf-8")

    return {
        "type": "write_file",
        "name": step.get("name"),
        "path": relative(target),
        "size_bytes": target.stat().st_size,
        "backup_path": backup_path,
    }


def apply_append_file(step: dict[str, Any]) -> dict[str, Any]:
    target = resolve_file_path(str(step.get("path", "")))
    content = step_text(step, "content")
    create_parent_dirs = bool(step.get("create_parent_dirs", True))

    if create_parent_dirs:
        target.parent.mkdir(parents=True, exist_ok=True)

    backup_path = backup_file(target)
    with target.open("a", encoding="utf-8") as f:
        f.write(content)

    return {
        "type": "append_file",
        "name": step.get("name"),
        "path": relative(target),
        "size_bytes": target.stat().st_size,
        "backup_path": backup_path,
    }


def apply_replace_text(step: dict[str, Any]) -> dict[str, Any]:
    target = resolve_file_path(str(step.get("path", "")))
    old_text = step_text(step, "old_text")
    new_text = step_text(step, "new_text")
    replace_all = bool(step.get("replace_all", False))

    if old_text == "":
        raise ValueError("old_text cannot be empty.")

    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"file does not exist: {relative(target)}")

    original = target.read_text(encoding="utf-8")
    if old_text not in original:
        raise ValueError(f"old_text was not found in {relative(target)}")

    backup_path = backup_file(target)
    if replace_all:
        updated = original.replace(old_text, new_text)
        replacements = original.count(old_text)
    else:
        updated = original.replace(old_text, new_text, 1)
        replacements = 1

    target.write_text(updated, encoding="utf-8")

    return {
        "type": "replace_text",
        "name": step.get("name"),
        "path": relative(target),
        "replacements": replacements,
        "size_bytes": target.stat().st_size,
        "backup_path": backup_path,
    }


def apply_patch_step(cwd: Path, step: dict[str, Any]) -> dict[str, Any]:
    step_cwd = resolve_cwd(str(step.get("cwd", relative(cwd))))
    patch = step_text(step, "patch")
    expected_sha256 = step.get("patch_sha256")
    patch_sha256 = hashlib.sha256(patch.encode("utf-8")).hexdigest()

    if expected_sha256 is not None and str(expected_sha256) != patch_sha256:
        raise ValueError("patch_sha256 does not match patch content.")

    patch_paths = step_patch_paths(step, patch)
    validate_patch_paths(step_cwd, patch_paths)

    check = run_git_apply(step_cwd, ["--check"], patch)
    if check["exit_code"] != 0:
        raise RuntimeError(f"git apply --check failed: {check['stderr'] or check['stdout']}")

    backup_ids: dict[str, str | None] = {}
    for patch_path in patch_paths:
        workspace_path = resolve_patch_path(step_cwd, patch_path)
        if workspace_path.exists() and workspace_path.is_file():
            backup_ids[patch_path] = backup_file(workspace_path)
        else:
            backup_ids[patch_path] = None

    applied = run_git_apply(step_cwd, [], patch)
    if applied["exit_code"] != 0:
        raise RuntimeError(f"git apply failed: {applied['stderr'] or applied['stdout']}")

    return {
        "type": "apply_patch",
        "name": step.get("name"),
        "cwd": relative(step_cwd),
        "files": patch_paths,
        "exit_code": applied["exit_code"],
        "stdout": applied["stdout"],
        "stderr": applied["stderr"],
        "backup_ids": backup_ids,
        "patch_sha256": patch_sha256,
        "truncated": applied["truncated"],
    }


def apply_step(cwd: Path, step: dict[str, Any]) -> dict[str, Any]:
    if step.get("risk") == "blocked":
        raise PermissionError(f"blocked step cannot be applied: {step.get('name')}")

    kind = step_type(step)
    if kind == "command":
        return apply_command(cwd, step)
    if kind == "write_file":
        return apply_write_file(step)
    if kind == "append_file":
        return apply_append_file(step)
    if kind == "replace_text":
        return apply_replace_text(step)
    if kind == "apply_patch":
        return apply_patch_step(cwd, step)

    raise ValueError(f"unsupported step type: {kind}")


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

    for idx, raw_step in enumerate(record.get("steps", []), 1):
        if not isinstance(raw_step, dict):
            failed = True
            results.append({"exit_code": None, "stderr": f"Invalid step at index {idx}"})
            break

        print(f"\n[{idx}] applying: {raw_step.get('name')}")

        try:
            result = apply_step(cwd, raw_step)
            results.append(result)

            if result.get("type") == "command" and result.get("exit_code") != 0:
                failed = True
                break

        except Exception as exc:
            failed = True
            results.append(
                {
                    "type": step_type(raw_step),
                    "name": raw_step.get("name"),
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
    record["error"] = None if not failed else "One or more bundle steps failed."

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
