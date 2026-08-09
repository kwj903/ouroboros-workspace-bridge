from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from terminal_bridge.bundle_service import BundleService, command_bundle_status_result
from terminal_bridge.models import (
    CommandBundleAction,
    CommandBundleListResult,
    CommandBundleStageResult,
    CommandBundleStatusResult,
    CommandBundleStep,
)


FindCommandBundle = Callable[[str], tuple[Path, dict[str, object]]]
MoveCommandBundle = Callable[[str, str, dict[str, object]], dict[str, object]]
Audit = Callable[..., None]
ReadJson = Callable[[Path], dict[str, object]]
CommandBundleDirs = Callable[[], list[Path]]
MetadataInput = dict[str, object] | None
SubmitCommandBundle = Callable[[str, str, list[CommandBundleStep], MetadataInput], CommandBundleStageResult]
SubmitPatchBundle = Callable[[str, str, str | None, str | None, MetadataInput], CommandBundleStageResult]
SubmitActionBundle = Callable[[str, str, list[CommandBundleAction], MetadataInput], CommandBundleStageResult]
SubmitCommitBundle = Callable[[str, list[str], str, MetadataInput], CommandBundleStageResult]
WaitCommandBundleStatus = Callable[..., Awaitable[CommandBundleStatusResult]]


def command_bundle_status_from_record(
    record: dict[str, object],
    bundle_id: str,
) -> CommandBundleStatusResult:
    return command_bundle_status_result(record, bundle_id)


def command_bundle_status(
    find_command_bundle: FindCommandBundle,
    bundle_id: str,
) -> CommandBundleStatusResult:
    _, record = find_command_bundle(bundle_id)
    return command_bundle_status_from_record(record, bundle_id)


async def wait_command_bundle_status(
    find_command_bundle: FindCommandBundle,
    bundle_id: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> CommandBundleStatusResult:
    deadline = time.monotonic() + timeout_seconds

    while True:
        result = command_bundle_status(find_command_bundle, bundle_id)

        if result.status not in {"pending", "running"} or time.monotonic() >= deadline:
            return result

        await asyncio.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))


async def stage_command_bundle_and_wait(
    submit_command_bundle: SubmitCommandBundle,
    wait_command_bundle_status: WaitCommandBundleStatus,
    title: str,
    cwd: str,
    steps: list[CommandBundleStep],
    timeout_seconds: int,
    poll_interval_seconds: float,
    metadata: MetadataInput = None,
) -> CommandBundleStatusResult:
    if len(steps) != 1:
        raise ValueError(
            "Only one command step is allowed per approval proposal. "
            "Use repeated calls for multiple checks or commands."
        )

    staged = submit_command_bundle(title, cwd, steps, metadata)
    return await wait_command_bundle_status(
        staged.bundle_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


async def stage_patch_bundle_and_wait(
    submit_patch_bundle: SubmitPatchBundle,
    wait_command_bundle_status: WaitCommandBundleStatus,
    title: str,
    cwd: str,
    patch: str | None,
    patch_ref: str | None,
    timeout_seconds: int,
    poll_interval_seconds: float,
    metadata: MetadataInput = None,
) -> CommandBundleStatusResult:
    staged = submit_patch_bundle(title, cwd, patch, patch_ref, metadata)
    return await wait_command_bundle_status(
        staged.bundle_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


async def stage_action_bundle_and_wait(
    submit_action_bundle: SubmitActionBundle,
    wait_command_bundle_status: WaitCommandBundleStatus,
    title: str,
    cwd: str,
    actions: list[CommandBundleAction],
    timeout_seconds: int,
    poll_interval_seconds: float,
    metadata: MetadataInput = None,
) -> CommandBundleStatusResult:
    if len(actions) != 1:
        raise ValueError(
            "Only one action is allowed per approval proposal. "
            "Use repeated calls for multi-step edits."
        )

    staged = submit_action_bundle(title, cwd, actions, metadata)
    return await wait_command_bundle_status(
        staged.bundle_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


async def stage_commit_bundle_and_wait(
    submit_commit_bundle: SubmitCommitBundle,
    wait_command_bundle_status: WaitCommandBundleStatus,
    cwd: str,
    paths: list[str],
    message: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
    metadata: MetadataInput = None,
) -> CommandBundleStatusResult:
    staged = submit_commit_bundle(cwd, paths, message, metadata)
    return await wait_command_bundle_status(
        staged.bundle_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def list_command_bundles(
    command_bundle_dirs: CommandBundleDirs,
    read_json: ReadJson,
    limit: int,
    *,
    task_id: str | None = None,
    client_id: str | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
) -> CommandBundleListResult:
    return BundleService().list(
        limit,
        task_id=task_id,
        client_id=client_id,
        session_id=session_id,
        project_id=project_id,
        command_bundle_dirs=command_bundle_dirs,
        read_json=read_json,
    )


def cancel_command_bundle(
    find_command_bundle: FindCommandBundle,
    move_command_bundle: MoveCommandBundle,
    audit: Audit,
    bundle_id: str,
) -> CommandBundleStatusResult:
    _, record = find_command_bundle(bundle_id)

    if record.get("status") != "pending":
        raise ValueError(f"Only pending bundles can be cancelled. Current status: {record.get('status')}")

    updated = move_command_bundle(
        bundle_id,
        "rejected",
        {
            "error": "Cancelled from ChatGPT.",
            "result": None,
        },
    )
    audit("cancel_command_bundle", bundle_id=bundle_id)

    return command_bundle_status_from_record(updated, bundle_id)
