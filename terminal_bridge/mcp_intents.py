from __future__ import annotations

import base64
import hmac
import json
from datetime import datetime, timezone


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def sign_intent_payload(payload: dict[str, object], secret: bytes) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body = b64url_encode(serialized)
    signature = hmac.new(secret, body.encode("ascii"), "sha256").digest()
    return f"{body}.{b64url_encode(signature)}"


def validate_intent_token(token: str, secret: bytes, *, now: datetime | None = None) -> dict[str, object]:
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid intent token format.") from exc

    expected = b64url_encode(hmac.new(secret, body.encode("ascii"), "sha256").digest())
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid intent token signature.")

    try:
        payload = json.loads(b64url_decode(body).decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid intent token payload.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid intent token payload.")

    expires_at = payload.get("expires_at")
    if not isinstance(expires_at, str):
        raise ValueError("Intent token is missing expires_at.")

    current = now or datetime.now(timezone.utc)
    try:
        expires = datetime.fromisoformat(expires_at)
    except ValueError as exc:
        raise ValueError("Intent token has invalid expires_at.") from exc

    if current > expires:
        raise ValueError("Intent token has expired.")

    return payload


def local_browser_host(host: str) -> str:
    normalized = host.strip()
    if normalized in {"", "0.0.0.0", "::"}:
        return "127.0.0.1"
    if ":" in normalized and not normalized.startswith("["):
        return f"[{normalized}]"
    return normalized


def local_review_url(token: str, host: str, port: int) -> str:
    return f"http://{local_browser_host(host)}:{port}/review-intent?token={token}"


def local_pending_url(host: str, port: int, bundle_id: str | None = None) -> str:
    base = f"http://{local_browser_host(host)}:{port}/pending"
    if bundle_id:
        return f"{base}?bundle_id={bundle_id}"
    return base
