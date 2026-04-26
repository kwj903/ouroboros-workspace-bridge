from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from terminal_bridge.config import (
    MAX_WRITE_CHARS,
    TEXT_PAYLOAD_CHUNK_MAX_CHARS,
    TEXT_PAYLOAD_DIR,
    TEXT_PAYLOAD_MAX_TOTAL_CHARS,
)
from terminal_bridge.models import TextPayloadStageResult
from terminal_bridge.storage import _now_iso, _read_json, _sha256_bytes, _write_json


def _new_text_payload_id() -> str:
    return f"txt-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _normalize_text_payload_id(payload_id: str) -> str:
    normalized = payload_id.strip()

    if normalized == "":
        raise ValueError("payload_id cannot be empty.")

    if len(normalized) > 120:
        raise ValueError("payload_id is too long.")

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(ch not in allowed for ch in normalized):
        raise ValueError("payload_id can only contain letters, numbers, '-' and '_'.")

    return normalized


def _text_payload_dir(payload_id: str) -> Path:
    return TEXT_PAYLOAD_DIR / _normalize_text_payload_id(payload_id)


def _text_payload_manifest_path(payload_id: str) -> Path:
    return _text_payload_dir(payload_id) / "manifest.json"


def _stage_text_payload_chunk(
    payload_id: str,
    chunk_index: int,
    total_chunks: int,
    text: str,
) -> TextPayloadStageResult:
    if total_chunks < 1:
        raise ValueError("total_chunks must be at least 1.")

    if chunk_index < 0 or chunk_index >= total_chunks:
        raise ValueError("chunk_index must be in range 0 <= chunk_index < total_chunks.")

    if len(text) > TEXT_PAYLOAD_CHUNK_MAX_CHARS:
        raise ValueError(f"text chunk too large. Max characters: {TEXT_PAYLOAD_CHUNK_MAX_CHARS}")

    payload_dir = _text_payload_dir(payload_id)
    payload_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = _text_payload_manifest_path(payload_id)
    if manifest_path.exists():
        manifest = _read_json(manifest_path)
        if int(manifest.get("total_chunks", total_chunks)) != total_chunks:
            raise ValueError("total_chunks does not match existing payload manifest.")
        created_at = str(manifest.get("created_at", _now_iso()))
        chunks = manifest.get("chunks") if isinstance(manifest.get("chunks"), dict) else {}
    else:
        created_at = _now_iso()
        chunks = {}

    chunk_path = payload_dir / f"chunk_{chunk_index:06d}.txt"
    if chunk_path.exists():
        existing = chunk_path.read_text(encoding="utf-8")
        if existing != text:
            raise ValueError(f"chunk {chunk_index} already exists with different content.")
    else:
        chunk_path.write_text(text, encoding="utf-8")

    chunk_bytes = text.encode("utf-8")
    chunks[str(chunk_index)] = {
        "chars": len(text),
        "sha256": _sha256_bytes(chunk_bytes),
    }

    chunk_paths = [payload_dir / f"chunk_{idx:06d}.txt" for idx in range(total_chunks)]
    complete = all(item.exists() for item in chunk_paths)
    total_chars = 0

    for item in chunk_paths:
        if item.exists():
            total_chars += len(item.read_text(encoding="utf-8"))

    if total_chars > TEXT_PAYLOAD_MAX_TOTAL_CHARS:
        raise ValueError(f"text payload too large. Max characters: {TEXT_PAYLOAD_MAX_TOTAL_CHARS}")

    manifest = {
        "payload_id": payload_id,
        "created_at": created_at,
        "updated_at": _now_iso(),
        "total_chunks": total_chunks,
        "chunks": chunks,
        "total_chars": total_chars,
        "complete": complete,
    }
    _write_json(manifest_path, manifest)

    return TextPayloadStageResult(
        payload_id=payload_id,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        chunk_chars=len(text),
        total_chars=total_chars,
        complete=complete,
        path=str(payload_dir),
    )


def _validate_text_payload_ref(payload_ref: str) -> dict[str, object]:
    payload_id = _normalize_text_payload_id(payload_ref)
    manifest_path = _text_payload_manifest_path(payload_id)

    if not manifest_path.exists():
        raise FileNotFoundError(f"text payload ref does not exist: {payload_id}")

    manifest = _read_json(manifest_path)

    if not bool(manifest.get("complete", False)):
        raise ValueError(f"text payload ref is incomplete: {payload_id}")

    total_chunks = int(manifest.get("total_chunks", 0))
    if total_chunks < 1:
        raise ValueError(f"text payload manifest is invalid: {payload_id}")

    for idx in range(total_chunks):
        chunk_path = _text_payload_dir(payload_id) / f"chunk_{idx:06d}.txt"
        if not chunk_path.exists():
            raise FileNotFoundError(f"text payload chunk is missing: {payload_id}#{idx}")

    total_chars = int(manifest.get("total_chars", 0))
    if total_chars > TEXT_PAYLOAD_MAX_TOTAL_CHARS:
        raise ValueError(f"text payload too large: {payload_id}")

    return {
        "payload_id": payload_id,
        "total_chunks": total_chunks,
        "total_chars": total_chars,
    }


def _serialize_text_payload_field(
    action_name: str,
    field_name: str,
    inline_value: str | None,
    ref_value: str | None,
) -> dict[str, object]:
    if inline_value is not None and ref_value is not None:
        raise ValueError(f"{field_name} and {field_name}_ref cannot both be set: {action_name}")

    if inline_value is None and ref_value is None:
        raise ValueError(f"{field_name} or {field_name}_ref is required: {action_name}")

    if inline_value is not None:
        if len(inline_value) > MAX_WRITE_CHARS:
            raise ValueError(f"{field_name} content is too large: {action_name}")
        return {
            field_name: inline_value,
            f"{field_name}_chars": len(inline_value),
        }

    assert ref_value is not None
    ref_info = _validate_text_payload_ref(ref_value)
    return {
        f"{field_name}_ref": str(ref_info["payload_id"]),
        f"{field_name}_chars": int(ref_info["total_chars"]),
        f"{field_name}_chunks": int(ref_info["total_chunks"]),
    }
