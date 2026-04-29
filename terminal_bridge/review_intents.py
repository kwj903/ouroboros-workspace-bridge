from __future__ import annotations

from urllib.parse import parse_qs, urlparse


def extract_intent_token(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Intent token is required.")

    parsed = urlparse(text)
    if parsed.query:
        token_values = parse_qs(parsed.query).get("token")
        if token_values and token_values[0].strip():
            return token_values[0].strip()

    if "token=" in text:
        query = text.split("?", 1)[1] if "?" in text else text
        token_values = parse_qs(query).get("token")
        if token_values and token_values[0].strip():
            return token_values[0].strip()

    return text


def import_intent_token(value: object) -> str:
    import server as mcp_server

    token = extract_intent_token(value)
    payload = mcp_server._validate_intent_token(token)
    result = mcp_server._import_intent(payload)
    return str(result.bundle_id)


def pending_bundle_url(bundle_id: str) -> str:
    return f"/pending?bundle_id={bundle_id}"


def intent_import_result(value: object) -> dict[str, object]:
    bundle_id = import_intent_token(value)
    return {
        "ok": True,
        "bundle_id": bundle_id,
        "pending_url": pending_bundle_url(bundle_id),
    }


def intent_import_redirect_location(value: object) -> str:
    return str(intent_import_result(value)["pending_url"])
