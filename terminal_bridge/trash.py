from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from terminal_bridge.backups import _backup_file, _sha256_file
from terminal_bridge.config import TRASH_DIR
from terminal_bridge.models import DeleteResult, RestoreResult, TrashEntry
from terminal_bridge.safety import _relative, _resolve_workspace_path
from terminal_bridge.storage import _now_iso


def _new_trash_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _trash_manifest_path(trash_id: str) -> Path:
    return TRASH_DIR / trash_id / "manifest.json"


def _read_trash_manifest(trash_id: str) -> dict[str, object]:
    manifest_path = _trash_manifest_path(trash_id)

    if not manifest_path.exists():
        raise FileNotFoundError(f"Trash manifest not found: {trash_id}")

    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _move_to_trash(target: Path, operation_id: str) -> DeleteResult:
    trash_id = _new_trash_id()
    rel = _relative(target)
    trash_target = TRASH_DIR / trash_id / rel
    trash_target.parent.mkdir(parents=True, exist_ok=True)

    shutil.move(str(target), str(trash_target))

    manifest = {
        "trash_id": trash_id,
        "original_path": rel,
        "trash_path": str(trash_target),
        "created_at": _now_iso(),
        "operation_id": operation_id,
    }

    manifest_path = _trash_manifest_path(trash_id)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return DeleteResult(
        original_path=rel,
        trash_id=trash_id,
        trash_path=str(trash_target),
        operation_id=operation_id,
    )


def _prepare_trash_restore(trash_id: str, overwrite: bool) -> tuple[Path, Path, str | None, bool]:
    manifest = _read_trash_manifest(trash_id)
    original = _resolve_workspace_path(manifest["original_path"])  # type: ignore[arg-type]
    trash_path = Path(manifest["trash_path"])  # type: ignore[arg-type]

    if not trash_path.exists():
        raise FileNotFoundError(f"Trash payload not found: {trash_id}")

    if original.exists() and not overwrite:
        raise FileExistsError(f"Original path already exists: {_relative(original)}")

    backup_id = None
    overwrote_original = False
    if original.exists() and overwrite:
        overwrote_original = True
        backup_id = _backup_file(original)
        if original.is_dir():
            shutil.rmtree(original)
        else:
            original.unlink()

    return original, trash_path, backup_id, overwrote_original


def _restore_trash_payload(trash_id: str, original: Path, trash_path: Path) -> RestoreResult:
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(trash_path), str(original))

    sha = _sha256_file(original) if original.is_file() else None

    return RestoreResult(
        restored_path=_relative(original),
        trash_id=trash_id,
        sha256=sha,
    )


def _list_trash_entries(limit: int) -> list[TrashEntry]:
    entries: list[TrashEntry] = []

    for manifest_path in sorted(TRASH_DIR.glob("*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        trash_path = Path(str(manifest.get("trash_path", "")))

        entries.append(
            TrashEntry(
                trash_id=str(manifest.get("trash_id", manifest_path.parent.name)),
                original_path=str(manifest.get("original_path", "")),
                trash_path=str(trash_path),
                created_at=manifest.get("created_at") if isinstance(manifest.get("created_at"), str) else None,
                exists=trash_path.exists(),
            )
        )

        if len(entries) >= limit:
            break

    return entries
