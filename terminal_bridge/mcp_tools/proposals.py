from __future__ import annotations

from collections.abc import Callable

from terminal_bridge.models import (
    CommandBundleAction,
    CommandBundleStatusResult,
    CommandBundleStep,
)


StageCommandAndWait = Callable[
    [str, str, list[CommandBundleStep], int, float],
    CommandBundleStatusResult,
]
StageActionAndWait = Callable[
    [str, str, list[CommandBundleAction], int, float],
    CommandBundleStatusResult,
]
StagePatchAndWait = Callable[
    [str, str, str | None, str | None, int, float],
    CommandBundleStatusResult,
]
StageCommitAndWait = Callable[
    [str, list[str], str, int, float],
    CommandBundleStatusResult,
]


def command_proposal_step(
    title: str,
    argv: list[str],
    command_name: str | None,
    command_timeout_seconds: int,
) -> CommandBundleStep:
    return CommandBundleStep(
        name=command_name or title,
        argv=argv,
        timeout_seconds=command_timeout_seconds,
    )


def file_write_proposal_action(
    title: str,
    path: str,
    content: str,
    overwrite: bool,
    create_parent_dirs: bool,
) -> CommandBundleAction:
    return CommandBundleAction(
        name=title,
        type="write_file",
        path=path,
        content=content,
        overwrite=overwrite,
        create_parent_dirs=create_parent_dirs,
    )


def file_replace_proposal_action(
    title: str,
    path: str,
    old_text: str,
    new_text: str,
    replace_all: bool,
) -> CommandBundleAction:
    return CommandBundleAction(
        name=title,
        type="replace_text",
        path=path,
        old_text=old_text,
        new_text=new_text,
        replace_all=replace_all,
    )


def validate_git_remote_or_branch(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty.")
    if normalized.startswith("-"):
        raise ValueError(f"{label} cannot start with '-'.")
    if any(ch.isspace() for ch in normalized):
        raise ValueError(f"{label} cannot contain whitespace.")
    return normalized


def git_push_proposal(
    remote: str,
    branch: str,
) -> tuple[str, str, str, CommandBundleStep]:
    safe_remote = validate_git_remote_or_branch(remote, "remote")
    safe_branch = validate_git_remote_or_branch(branch, "branch")
    title = f"Push {safe_remote} {safe_branch}"
    step = CommandBundleStep(
        name=f"git push {safe_remote} {safe_branch}",
        argv=["git", "push", safe_remote, safe_branch],
        timeout_seconds=60,
    )
    return safe_remote, safe_branch, title, step


def command_proposal_and_wait(
    stage_command_and_wait: StageCommandAndWait,
    title: str,
    cwd: str,
    step: CommandBundleStep,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> CommandBundleStatusResult:
    return stage_command_and_wait(
        title,
        cwd,
        [step],
        timeout_seconds,
        poll_interval_seconds,
    )


def action_proposal_and_wait(
    stage_action_and_wait: StageActionAndWait,
    title: str,
    cwd: str,
    action: CommandBundleAction,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> CommandBundleStatusResult:
    return stage_action_and_wait(
        title,
        cwd,
        [action],
        timeout_seconds,
        poll_interval_seconds,
    )


def patch_proposal_and_wait(
    stage_patch_and_wait: StagePatchAndWait,
    title: str,
    cwd: str,
    patch: str | None,
    patch_ref: str | None,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> CommandBundleStatusResult:
    return stage_patch_and_wait(
        title,
        cwd,
        patch,
        patch_ref,
        timeout_seconds,
        poll_interval_seconds,
    )


def commit_proposal_and_wait(
    stage_commit_and_wait: StageCommitAndWait,
    cwd: str,
    paths: list[str],
    message: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> CommandBundleStatusResult:
    return stage_commit_and_wait(
        cwd,
        paths,
        message,
        timeout_seconds,
        poll_interval_seconds,
    )
