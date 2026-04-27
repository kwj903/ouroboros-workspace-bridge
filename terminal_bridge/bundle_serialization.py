from __future__ import annotations

from pathlib import Path
from typing import Literal

from terminal_bridge.bundles import _combined_bundle_risk
from terminal_bridge.commands import _classify_exec_command, _validate_exec_argv
from terminal_bridge.config import BLOCKED_DIR_NAMES, WORKSPACE_ROOT
from terminal_bridge.models import CommandBundleAction, CommandBundleStep
from terminal_bridge.payloads import _serialize_text_payload_field
from terminal_bridge.safety import _is_blocked_name, _relative


def _serialize_command_steps(
    cwd_path: Path,
    steps: list[CommandBundleStep],
) -> tuple[list[dict[str, object]], Literal["low", "medium", "high", "blocked"], bool]:
    serialized: list[dict[str, object]] = []
    risks: list[str] = []
    approval_required = False

    for step in steps:
        argv = _validate_exec_argv(step.argv)
        risk, reason = _classify_exec_command(cwd_path, argv)

        if risk != "low":
            approval_required = True

        risks.append(risk)
        serialized.append(
            {
                "name": step.name,
                "argv": argv,
                "timeout_seconds": step.timeout_seconds,
                "risk": risk,
                "reason": reason,
            }
        )

    return serialized, _combined_bundle_risk(risks), approval_required


def _validate_git_commit_message(message: str) -> str:
    normalized = message.strip()

    if normalized == "":
        raise ValueError("Commit message cannot be empty.")

    if "\n" in normalized or "\r" in normalized:
        raise ValueError("Commit message must be a single line.")

    if len(normalized) > 200:
        raise ValueError("Commit message is too long. Max characters: 200")

    return normalized


def _validate_git_commit_paths(cwd_path: Path, paths: list[str]) -> list[str]:
    if not paths:
        raise ValueError("paths cannot be empty.")

    safe_paths: list[str] = []

    for path in paths:
        value = path.strip()

        if value == "":
            raise ValueError("git commit paths cannot contain empty values.")

        if value == ".":
            safe_paths.append(".")
            continue

        if value.startswith("-"):
            raise ValueError("git commit paths cannot be flags.")

        raw = Path(value)
        if raw.is_absolute() or value.startswith("~") or ".." in raw.parts:
            raise ValueError(f"Unsafe git commit path: {value}")

        target = (cwd_path / raw).resolve(strict=False)

        if target != WORKSPACE_ROOT and not target.is_relative_to(WORKSPACE_ROOT):
            raise ValueError(f"Git commit path escapes workspace: {value}")

        rel_parts = target.relative_to(WORKSPACE_ROOT).parts
        if any(part in BLOCKED_DIR_NAMES for part in rel_parts):
            raise PermissionError(f"Git commit path touches blocked directory: {value}")

        if _is_blocked_name(target.name):
            raise PermissionError(f"Git commit path touches blocked file: {value}")

        safe_paths.append(value)

    return safe_paths


def _serialize_commit_command_step(
    cwd_path: Path,
    name: str,
    argv: list[str],
    timeout_seconds: int,
    force_approval_reason: str | None = None,
) -> dict[str, object]:
    safe_argv = _validate_exec_argv(argv)
    risk, reason = _classify_exec_command(cwd_path, safe_argv)

    if force_approval_reason is not None and risk != "blocked":
        risk = "medium"
        reason = force_approval_reason

    return {
        "name": name,
        "argv": safe_argv,
        "timeout_seconds": timeout_seconds,
        "risk": risk,
        "reason": reason,
    }


def _serialize_commit_steps(
    cwd_path: Path,
    paths: list[str],
    message: str,
    precheck_commands: list[CommandBundleStep] | None = None,
) -> tuple[list[dict[str, object]], Literal["low", "medium", "high", "blocked"], list[str], str]:
    safe_paths = _validate_git_commit_paths(cwd_path, paths)
    commit_message = _validate_git_commit_message(message)
    prechecks = precheck_commands or [
        CommandBundleStep(
            name="Precheck git status",
            argv=["git", "status", "--short", "--branch"],
            timeout_seconds=30,
        ),
        CommandBundleStep(
            name="Precheck git diff --check",
            argv=["git", "diff", "--check"],
            timeout_seconds=30,
        ),
    ]

    if len(prechecks) > 10:
        raise ValueError("precheck_commands can include at most 10 commands.")

    serialized: list[dict[str, object]] = []
    risks: list[str] = []

    for precheck in prechecks:
        step = _serialize_commit_command_step(
            cwd_path,
            precheck.name,
            precheck.argv,
            precheck.timeout_seconds,
        )
        if step["risk"] != "low":
            raise ValueError(f"Commit precheck must be low risk: {precheck.name}")
        serialized.append(step)
        risks.append(str(step["risk"]))

    mutation_reason = "Git index/history mutation requires local approval."
    commit_steps = [
        ("Stage requested paths", ["git", "add", "--", *safe_paths], 30, mutation_reason),
        ("Create commit", ["git", "commit", "-m", commit_message], 30, mutation_reason),
        ("Show post-commit status", ["git", "status", "--short", "--branch"], 30, None),
        ("Show latest commit", ["git", "log", "--oneline", "-1"], 30, None),
    ]

    for name, argv, timeout_seconds, forced_reason in commit_steps:
        step = _serialize_commit_command_step(cwd_path, name, argv, timeout_seconds, forced_reason)
        serialized.append(step)
        risks.append(str(step["risk"]))

    return serialized, _combined_bundle_risk(risks), safe_paths, commit_message


def _resolve_bundle_file_action_path(cwd_path: Path, action_path: str | None) -> str:
    if action_path is None or action_path.strip() == "":
        raise ValueError("File action path is required.")

    raw = Path(action_path)
    if raw.is_absolute() or action_path.startswith("~") or ".." in raw.parts:
        raise ValueError(f"Unsafe file action path: {action_path}")

    target = (cwd_path / raw).resolve(strict=False)

    if target != WORKSPACE_ROOT and not target.is_relative_to(WORKSPACE_ROOT):
        raise ValueError(f"File action path escapes workspace: {action_path}")

    rel_parts = target.relative_to(WORKSPACE_ROOT).parts
    if any(part in BLOCKED_DIR_NAMES for part in rel_parts):
        raise PermissionError(f"File action touches blocked directory: {action_path}")

    if _is_blocked_name(target.name):
        raise PermissionError(f"File action touches blocked file: {action_path}")

    return _relative(target)


def _serialize_action_steps(
    cwd_path: Path,
    actions: list[CommandBundleAction],
) -> tuple[list[dict[str, object]], Literal["low", "medium", "high", "blocked"], bool]:
    serialized: list[dict[str, object]] = []
    risks: list[str] = []
    approval_required = False

    for action in actions:
        action_type = action.type

        if action_type == "command":
            if action.argv is None:
                raise ValueError(f"Command action requires argv: {action.name}")

            argv = _validate_exec_argv(action.argv)
            risk, reason = _classify_exec_command(cwd_path, argv)

            if risk != "low":
                approval_required = True

            risks.append(risk)
            serialized.append(
                {
                    "type": "command",
                    "name": action.name,
                    "argv": argv,
                    "timeout_seconds": action.timeout_seconds,
                    "risk": risk,
                    "reason": reason,
                }
            )
            continue

        file_path = _resolve_bundle_file_action_path(cwd_path, action.path)

        if action_type in {"write_file", "append_file"}:
            content_field = _serialize_text_payload_field(
                action.name,
                "content",
                action.content,
                action.content_ref,
            )

            risks.append("medium")
            approval_required = True
            serialized.append(
                {
                    "type": action_type,
                    "name": action.name,
                    "path": file_path,
                    **content_field,
                    "overwrite": action.overwrite,
                    "create_parent_dirs": action.create_parent_dirs,
                    "risk": "medium",
                    "reason": "File write action requires local approval.",
                }
            )
            continue

        if action_type == "replace_text":
            old_text_field = _serialize_text_payload_field(
                action.name,
                "old_text",
                action.old_text,
                action.old_text_ref,
            )
            new_text_field = _serialize_text_payload_field(
                action.name,
                "new_text",
                action.new_text,
                action.new_text_ref,
            )

            risks.append("medium")
            approval_required = True
            serialized.append(
                {
                    "type": "replace_text",
                    "name": action.name,
                    "path": file_path,
                    **old_text_field,
                    **new_text_field,
                    "replace_all": action.replace_all,
                    "risk": "medium",
                    "reason": "File replace action requires local approval.",
                }
            )
            continue

        raise ValueError(f"Unsupported action type: {action_type}")

    return serialized, _combined_bundle_risk(risks), approval_required
