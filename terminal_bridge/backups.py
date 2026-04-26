from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from terminal_bridge.config import BACKUP_DIR
from terminal_bridge.models import BackupEntry, BackupRestoreResult
from terminal_bridge.safety import _relative, _resolve_workspace_path
from terminal_bridge.storage import _now_iso, _sha256_bytes


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _backup_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None

    backup_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    rel = _relative(path)
    target = BACKUP_DIR / backup_id / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

    manifest = {
        "backup_id": backup_id,
        "original_path": rel,
        "backup_path": str(target),
        "sha256": _sha256_file(path),
        "created_at": _now_iso(),
    }

    manifest_path = BACKUP_DIR / backup_id / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return backup_id


def _read_backup_manifest(backup_id: str) -> dict[str, object]:
    manifest_path = BACKUP_DIR / backup_id / "manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Backup manifest not found: {backup_id}")

    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _list_backup_entries(limit: int) -> list[BackupEntry]:
    entries: list[BackupEntry] = []

    for manifest_path in sorted(BACKUP_DIR.glob("*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        entries.append(
            BackupEntry(
                backup_id=str(manifest.get("backup_id", manifest_path.parent.name)),
                original_path=str(manifest.get("original_path", "")),
                backup_path=str(manifest.get("backup_path", "")),
                sha256=manifest.get("sha256") if isinstance(manifest.get("sha256"), str) else None,
                created_at=manifest.get("created_at") if isinstance(manifest.get("created_at"), str) else None,
            )
        )

        if len(entries) >= limit:
            break

    return entries


def _restore_backup_payload(backup_id: str, overwrite: bool) -> BackupRestoreResult:
    manifest = _read_backup_manifest(backup_id)
    original = _resolve_workspace_path(str(manifest["original_path"]))
    backup_path = Path(str(manifest["backup_path"]))

    if not backup_path.exists() or not backup_path.is_file():
        raise FileNotFoundError(f"Backup payload not found: {backup_id}")

    if original.exists() and not overwrite:
        raise FileExistsError(f"Original path already exists. Set overwrite=true: {_relative(original)}")

    backup_id_before_overwrite = None
    if original.exists() and overwrite:
        backup_id_before_overwrite = _backup_file(original)

    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, original)

    return BackupRestoreResult(
        backup_id=backup_id,
        restored_path=_relative(original),
        sha256=_sha256_file(original),
        backup_id_before_overwrite=backup_id_before_overwrite,
    )
