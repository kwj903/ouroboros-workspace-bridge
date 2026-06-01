from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from terminal_bridge.bundles import _normalize_command_bundle_metadata
from terminal_bridge.mcp_tools.metadata_filters import metadata_matches_filters
from terminal_bridge.models import (
    CommandBundleAction,
    CommandBundleListEntry,
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
WaitCommandBundleStatus = Callable[..., CommandBundleStatusResult]


def command_bundle_status_from_record(
    record: dict[str, object],
    bundle_id: str,
) -> CommandBundleStatusResult:
    steps = record.get("steps") if isinstance(record.get("steps"), list) else []
    metadata = _normalize_command_bundle_metadata(record)

    return CommandBundleStatusResult(
        bundle_id=str(record.get("bundle_id", bundle_id)),
        title=str(record.get("title", "")),
        cwd=str(record.get("cwd", "")),
        status=str(record.get("status", "unknown")),
        risk=str(record.get("risk", "unknown")),
        approval_required=bool(record.get("approval_required", False)),
        command_count=len(steps),
        created_at=str(record.get("created_at", "")),
        updated_at=str(record.get("updated_at", "")),
        result=record.get("result") if isinstance(record.get("result"), dict) else None,
        error=record.get("error") if isinstance(record.get("error"), str) else None,
        metadata=metadata,
    )


def command_bundle_status(
    find_command_bundle: FindCommandBundle,
    bundle_id: str,
) -> CommandBundleStatusResult:
    _, record = find_command_bundle(bundle_id)
    return command_bundle_status_from_record(record, bundle_id)


def wait_command_bundle_status(
    find_command_bundle: FindCommandBundle,
    bundle_id: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> CommandBundleStatusResult:
    deadline = time.monotonic() + timeout_seconds

    while True:
        result = command_bundle_status(find_command_bundle, bundle_id)

        if result.status != "pending" or time.monotonic() >= deadline:
            return result

        time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))


def stage_command_bundle_and_wait(
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
    return wait_command_bundle_status(
        staged.bundle_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def stage_patch_bundle_and_wait(
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
    return wait_command_bundle_status(
        staged.bundle_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def stage_action_bundle_and_wait(
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
    return wait_command_bundle_status(
        staged.bundle_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def stage_commit_bundle_and_wait(
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
    return wait_command_bundle_status(
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
    workspace_mode: str | None = None,
) -> CommandBundleListResult:
    entries: list[CommandBundleListEntry] = []
    filters = {
        "task_id": task_id,
        "client_id": client_id,
        "session_id": session_id,
        "project_id": project_id,
        "workspace_mode": workspace_mode,
    }

    for directory in command_bundle_dirs():
        if not directory.exists():
            continue

        for path in directory.glob("cmd-*.json"):
            try:
                record = read_json(path)
            except Exception:
                continue

            steps = record.get("steps") if isinstance(record.get("steps"), list) else []
            metadata = _normalize_command_bundle_metadata(record)
            if not metadata_matches_filters(metadata, filters):
                continue

            entries.append(
                CommandBundleListEntry(
                    bundle_id=str(record.get("bundle_id", path.stem)),
                    title=str(record.get("title", "")),
                    cwd=str(record.get("cwd", "")),
                    status=str(record.get("status", directory.name)),
                    risk=str(record.get("risk", "unknown")),
                    command_count=len(steps),
                    updated_at=str(record.get("updated_at", "")),
                    metadata=metadata,
                )
            )

    entries.sort(key=lambda item: item.updated_at, reverse=True)
    return CommandBundleListResult(entries=entries[:limit], count=min(len(entries), limit))


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
