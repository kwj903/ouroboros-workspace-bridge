from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from terminal_bridge.bundles import _normalize_command_bundle_metadata
from terminal_bridge.config import RUNTIME_ROOT, WORKSPACE_ROOT
from terminal_bridge.task_workspaces import _normalize_project_id, _resolve_source_cwd
from terminal_bridge.truncation import truncate_text


COMMAND_BUNDLE_STATUSES = ("pending", "applied", "rejected", "failed")
PREVIEW_LIMIT = 4_000


def _command_bundle_dirs(runtime_root: Path) -> list[Path]:
    base = runtime_root.expanduser().resolve(strict=False) / "command_bundles"
    return [base / status for status in COMMAND_BUNDLE_STATUSES]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_bundle(bundle_id: str, *, runtime_root: Path) -> tuple[Path, dict[str, Any]] | None:
    normalized = str(bundle_id or "").strip()
    if not normalized:
        return None
    if not normalized.startswith("cmd-"):
        raise ValueError("bundle_id must start with 'cmd-'.")

    for directory in _command_bundle_dirs(runtime_root):
        path = directory / f"{normalized}.json"
        if not path.exists():
            continue
        return path, _read_json(path)

    return None


def _iter_bundle_records(runtime_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    records: list[tuple[Path, dict[str, Any]]] = []
    for directory in _command_bundle_dirs(runtime_root):
        if not directory.exists():
            continue
        for path in directory.glob("cmd-*.json"):
            try:
                records.append((path, _read_json(path)))
            except Exception:
                continue
    return records


def _as_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _as_argv(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    argv = [str(item) for item in value]
    return argv if argv and argv[0].strip() else []


def _command_summary(argv: list[str]) -> str | None:
    if not argv:
        return None
    return shlex.join(argv)


def _is_validation_bundle(_record: dict[str, Any], metadata: dict[str, object]) -> bool:
    return bool(_as_argv(metadata.get("validation_command")))


def _find_latest_validation_bundle(
    *,
    task_id: str,
    source_cwd: str,
    project_id: str,
    runtime_root: Path,
) -> tuple[Path, dict[str, Any]] | None:
    matches: list[tuple[str, Path, dict[str, Any]]] = []
    for path, record in _iter_bundle_records(runtime_root):
        metadata = _normalize_command_bundle_metadata(record)
        if not _is_validation_bundle(record, metadata):
            continue
        if str(metadata.get("task_id") or "") != task_id:
            continue
        if str(metadata.get("project_id") or "") != project_id:
            continue
        if str(metadata.get("source_cwd") or ".") != source_cwd:
            continue
        matches.append((str(record.get("updated_at") or ""), path, record))

    if not matches:
        return None

    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1], matches[0][2]


def _record_status(record: dict[str, Any], path: Path | None) -> str:
    status = _as_text(record.get("status"))
    if status:
        return status
    if path is not None:
        return path.parent.name
    return "not_found"


def _record_steps(record: dict[str, Any]) -> list[dict[str, Any]]:
    steps = record.get("steps")
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def _result_steps(record: dict[str, Any]) -> list[dict[str, Any]]:
    result = record.get("result")
    if not isinstance(result, dict):
        return []
    steps = result.get("steps")
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def _command_argv(record: dict[str, Any], result_step: dict[str, Any] | None, metadata: dict[str, object]) -> list[str]:
    if result_step is not None:
        argv = _as_argv(result_step.get("argv"))
        if argv:
            return argv

    argv = _as_argv(metadata.get("validation_command"))
    if argv:
        return argv

    for step in _record_steps(record):
        argv = _as_argv(step.get("argv"))
        if argv:
            return argv

    return []


def _latest_result_step(record: dict[str, Any]) -> dict[str, Any] | None:
    steps = _result_steps(record)
    command_steps = [step for step in steps if step.get("type") == "command" or _as_argv(step.get("argv"))]
    if command_steps:
        return command_steps[-1]
    if steps:
        return steps[-1]
    return None


def _exit_code(step: dict[str, Any] | None) -> int | None:
    if step is None:
        return None
    value = step.get("exit_code")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _preview(value: object, *, runner_truncated: bool) -> tuple[str, bool]:
    text = value if isinstance(value, str) else ""
    preview, truncated = truncate_text(text, PREVIEW_LIMIT)
    return preview, bool(runner_truncated or truncated)


def _inferred_status(exit_code: int | None) -> str:
    if exit_code is None:
        return "unknown"
    if exit_code == 0:
        return "passed"
    return "failed"


def _recommended_action(
    *,
    inferred_status: str,
    bundle_status: str,
    bundle_id: str | None,
) -> str:
    if inferred_status == "passed":
        return "record_passed_validation"
    if inferred_status == "failed":
        return "record_failed_validation"
    if bundle_id is None:
        return "propose_validation_command"
    if bundle_status == "pending":
        return "wait_for_validation_command_bundle"
    return "inspect_validation_command_bundle"


def _suggested_record_status(inferred_status: str, bundle_status: str, bundle_id: str | None) -> str:
    if inferred_status in {"passed", "failed"}:
        return inferred_status
    if bundle_id is not None and bundle_status == "pending":
        return "pending"
    return "unknown"


def _validation_summary(
    *,
    bundle_id: str | None,
    exit_code: int | None,
    bundle_status: str,
    task_id: str,
) -> str:
    if bundle_id is None:
        return f"No validation command bundle found for task {task_id}."
    if exit_code is not None:
        return f"Validation command bundle {bundle_id} exited with code {exit_code}."
    return f"Validation command bundle {bundle_id} has status {bundle_status} and no command exit code yet."


def _not_found_hint(
    *,
    task_id: str,
    project_id: str,
    source_cwd: str,
) -> dict[str, Any]:
    summary = _validation_summary(bundle_id=None, exit_code=None, bundle_status="not_found", task_id=task_id)
    return {
        "task_id": task_id,
        "project_id": project_id,
        "source_cwd": source_cwd,
        "bundle_id": None,
        "bundle_status": "not_found",
        "command_argv": [],
        "command_summary": None,
        "exit_code": None,
        "stdout_preview": "",
        "stderr_preview": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "result_available": False,
        "inferred_status": "unknown",
        "recommended_next_action": "propose_validation_command",
        "suggested_record_input": {
            "task_id": task_id,
            "cwd": source_cwd,
            "project_id": project_id,
            "validation_status": "unknown",
            "validation_commands": [],
            "validation_summary": summary,
            "validated_by": None,
            "client_id": None,
            "session_id": None,
        },
    }


def _hint_from_record(
    *,
    path: Path | None,
    record: dict[str, Any],
    task_id_fallback: str | None,
    project_id_fallback: str | None,
    source_cwd_fallback: str | None,
) -> dict[str, Any]:
    metadata = _normalize_command_bundle_metadata(record)
    bundle_id = _as_text(record.get("bundle_id")) or (path.stem if path is not None else None)
    bundle_status = _record_status(record, path)
    result_step = _latest_result_step(record)
    exit_code = _exit_code(result_step)
    argv = _command_argv(record, result_step, metadata)
    summary = _command_summary(argv)
    result_available = isinstance(record.get("result"), dict)
    runner_truncated = bool(result_step.get("truncated")) if result_step is not None else False
    stdout_preview, stdout_truncated = _preview(
        result_step.get("stdout") if result_step is not None else "",
        runner_truncated=runner_truncated,
    )
    stderr_preview, stderr_truncated = _preview(
        result_step.get("stderr") if result_step is not None else "",
        runner_truncated=runner_truncated,
    )

    task_id = _as_text(metadata.get("task_id")) or task_id_fallback or ""
    source_cwd = _as_text(metadata.get("source_cwd")) or source_cwd_fallback or _as_text(record.get("cwd")) or "."
    project_id = _as_text(metadata.get("project_id")) or project_id_fallback
    inferred_status = _inferred_status(exit_code)
    recommended_next_action = _recommended_action(
        inferred_status=inferred_status,
        bundle_status=bundle_status,
        bundle_id=bundle_id,
    )
    suggested_status = _suggested_record_status(inferred_status, bundle_status, bundle_id)
    suggested_commands = [summary] if summary else []
    validation_summary = _validation_summary(
        bundle_id=bundle_id,
        exit_code=exit_code,
        bundle_status=bundle_status,
        task_id=task_id or "unknown",
    )

    return {
        "task_id": task_id or None,
        "project_id": project_id,
        "source_cwd": source_cwd,
        "bundle_id": bundle_id,
        "bundle_status": bundle_status,
        "command_argv": argv,
        "command_summary": summary,
        "exit_code": exit_code,
        "stdout_preview": stdout_preview,
        "stderr_preview": stderr_preview,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "result_available": result_available,
        "inferred_status": inferred_status,
        "recommended_next_action": recommended_next_action,
        "suggested_record_input": {
            "task_id": task_id,
            "cwd": source_cwd,
            "project_id": project_id,
            "validation_status": suggested_status,
            "validation_commands": suggested_commands,
            "validation_summary": validation_summary,
            "validated_by": None,
            "client_id": None,
            "session_id": None,
        },
    }


def task_validation_result_hint(
    task_id: str | None = None,
    *,
    cwd: object = ".",
    project_id: object | None = None,
    bundle_id: str | None = None,
    runtime_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, Any]:
    """Summarize a validation command bundle result without recording validation metadata."""
    root = (runtime_root or RUNTIME_ROOT).expanduser().resolve(strict=False)
    normalized_bundle_id = _as_text(bundle_id)

    source_cwd: str | None = None
    normalized_project_id: str | None = None
    task_id_text = _as_text(task_id)
    if task_id_text is not None or normalized_bundle_id is None:
        if task_id_text is None:
            raise ValueError("task_id is required when bundle_id is not provided.")
        source_cwd, _source_path = _resolve_source_cwd(cwd, workspace_root=workspace_root)
        normalized_project_id = _normalize_project_id(project_id, source_cwd)

    if normalized_bundle_id is not None:
        found = _find_bundle(normalized_bundle_id, runtime_root=root)
        if found is None:
            if task_id_text is not None and source_cwd is not None and normalized_project_id is not None:
                return _not_found_hint(
                    task_id=task_id_text,
                    project_id=normalized_project_id,
                    source_cwd=source_cwd,
                )
            raise FileNotFoundError(f"Command bundle not found: {normalized_bundle_id}")
        path, record = found
        return _hint_from_record(
            path=path,
            record=record,
            task_id_fallback=task_id_text,
            project_id_fallback=normalized_project_id,
            source_cwd_fallback=source_cwd,
        )

    if task_id_text is None or source_cwd is None or normalized_project_id is None:
        raise ValueError("task_id is required when bundle_id is not provided.")

    found = _find_latest_validation_bundle(
        task_id=task_id_text,
        source_cwd=source_cwd,
        project_id=normalized_project_id,
        runtime_root=root,
    )
    if found is None:
        return _not_found_hint(task_id=task_id_text, project_id=normalized_project_id, source_cwd=source_cwd)

    path, record = found
    return _hint_from_record(
        path=path,
        record=record,
        task_id_fallback=task_id_text,
        project_id_fallback=normalized_project_id,
        source_cwd_fallback=source_cwd,
    )
