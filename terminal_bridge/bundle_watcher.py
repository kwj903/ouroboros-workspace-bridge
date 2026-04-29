from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Protocol

from terminal_bridge.approval_modes import load_approval_mode, should_auto_approve


class StopEvent(Protocol):
    def is_set(self) -> bool: ...

    def wait(self, timeout: float) -> bool: ...


AutoApplyFunc = Callable[[str, Path, Path, str, str], bool]
BundleCallback = Callable[[str], None]
ModeLoader = Callable[[], str]


def load_bundle_id(path: Path) -> str | None:
    record = load_bundle_record(path)
    if record is None:
        return path.stem

    bundle_id = record.get("bundle_id")
    if isinstance(bundle_id, str) and bundle_id:
        return bundle_id

    return path.stem


def load_bundle_record(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def current_pending_bundle_ids(pending_dir: Path) -> set[str]:
    ids: set[str] = set()
    if not pending_dir.exists():
        return ids

    for path in sorted(pending_dir.glob("cmd-*.json")):
        bundle_id = load_bundle_id(path)
        if bundle_id:
            ids.add(bundle_id)
    return ids


def pending_bundle_records(pending_dir: Path) -> list[tuple[str, Path, dict[str, object] | None]]:
    rows: list[tuple[str, Path, dict[str, object] | None]] = []
    if not pending_dir.exists():
        return rows

    for path in sorted(pending_dir.glob("cmd-*.json")):
        bundle_id = load_bundle_id(path)
        if bundle_id:
            rows.append((bundle_id, path, load_bundle_record(path)))
    return rows


def auto_apply_bundle(
    bundle_id: str,
    runner: Path,
    project_root: Path,
    source: str,
    log_prefix: str = "",
) -> bool:
    try:
        completed = subprocess.run(
            [sys.executable, str(runner), "apply", bundle_id, "--yes"],
            cwd=str(project_root),
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
            shell=False,
            check=False,
        )
    except Exception as exc:
        print(f"{log_prefix}auto-approval failed before runner completed: {bundle_id}: {type(exc).__name__}")
        return False

    print(f"{log_prefix}auto-approval {source}: {bundle_id}: exit={completed.returncode}")
    return completed.returncode == 0


def handle_pending_bundle(
    bundle_id: str,
    record: dict[str, object] | None,
    *,
    approval_mode: str,
    runner: Path,
    project_root: Path,
    notify_enabled: bool,
    notify_bundle: BundleCallback | None,
    open_mode: str,
    open_bundle: BundleCallback | None,
    log_prefix: str = "",
    auto_apply_func: AutoApplyFunc = auto_apply_bundle,
) -> str:
    if record is not None and should_auto_approve(record, approval_mode):
        source = f"mode={approval_mode}"
        print(f"{log_prefix}approval mode {approval_mode}: 자동 승인 시도: {bundle_id}")
        if auto_apply_func(bundle_id, runner, project_root, source, log_prefix):
            return "auto-applied"

        print(f"{log_prefix}auto-approval failed; falling back to manual review: {bundle_id}")

    if notify_enabled and notify_bundle is not None:
        notify_bundle(bundle_id)

    if open_mode == "bundle" and open_bundle is not None:
        open_bundle(bundle_id)

    return "manual"


def watch_pending_bundles(
    *,
    pending_dir: Path,
    runner: Path,
    project_root: Path,
    seen_bundle_ids: set[str],
    poll_seconds: float,
    notify_enabled: bool,
    notify_bundle: BundleCallback | None,
    open_mode: str,
    open_bundle: BundleCallback | None,
    stop_event: StopEvent | None = None,
    load_mode: ModeLoader = load_approval_mode,
    log_prefix: str = "",
    auto_apply_func: AutoApplyFunc = auto_apply_bundle,
) -> None:
    while True:
        if stop_event is not None and stop_event.is_set():
            return

        for bundle_id, _path, record in pending_bundle_records(pending_dir):
            if bundle_id in seen_bundle_ids:
                continue

            print(f"{log_prefix}새 승인 대기 번들: {bundle_id}")
            approval_mode = load_mode()
            handle_pending_bundle(
                bundle_id,
                record,
                approval_mode=approval_mode,
                runner=runner,
                project_root=project_root,
                notify_enabled=notify_enabled,
                notify_bundle=notify_bundle,
                open_mode=open_mode,
                open_bundle=open_bundle,
                log_prefix=log_prefix,
                auto_apply_func=auto_apply_func,
            )
            seen_bundle_ids.add(bundle_id)

        if stop_event is not None:
            if stop_event.wait(poll_seconds):
                return
        else:
            time.sleep(poll_seconds)
