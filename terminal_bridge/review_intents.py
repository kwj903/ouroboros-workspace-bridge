from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from terminal_bridge.config import WORKSPACE_ROOT


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


ALLOWED_COMPANION_INTENT_KEYS = {"version", "intent_kind", "intent_type", "cwd", "params"}
COMPANION_CHECKS = {"git_status", "py_compile", "unit_tests", "check_all"}
COMPANION_DEV_SESSION_ACTIONS = {"status", "doctor", "restart_mcp", "restart_session"}


def normalize_companion_cwd(value: object) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError("cwd must be a non-empty string.")

    raw = Path(value.strip())
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("cwd must be a safe relative path.")

    target = (WORKSPACE_ROOT / raw).resolve(strict=False)
    if target != WORKSPACE_ROOT and not target.is_relative_to(WORKSPACE_ROOT):
        raise ValueError("cwd must resolve under WORKSPACE_ROOT.")
    if not target.exists() or not target.is_dir():
        raise NotADirectoryError("cwd must exist and be a directory.")
    return "." if target == WORKSPACE_ROOT else str(target.relative_to(WORKSPACE_ROOT))


def validate_companion_intent(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Intent JSON must be an object.")

    unknown_keys = set(value) - ALLOWED_COMPANION_INTENT_KEYS
    if unknown_keys:
        raise ValueError(f"Unknown top-level intent keys: {', '.join(sorted(unknown_keys))}")

    if value.get("version") != 1:
        raise ValueError("Unsupported intent version.")

    if value.get("intent_kind") != "run":
        raise ValueError("intent_kind must be 'run'.")

    intent_type = str(value.get("intent_type", "")).strip()
    if intent_type not in {"check", "commit_current_changes", "dev_session"}:
        raise ValueError(f"Unsupported intent_type: {intent_type}")

    cwd = normalize_companion_cwd(value.get("cwd"))
    params = value.get("params")
    if not isinstance(params, dict):
        raise ValueError("Intent params must be an object.")

    normalized_params: dict[str, object]
    if intent_type == "check":
        unknown_params = set(params) - {"check"}
        if unknown_params:
            raise ValueError(f"Unknown check params: {', '.join(sorted(unknown_params))}")
        check = params.get("check")
        if check not in COMPANION_CHECKS:
            raise ValueError("Unsupported check intent.")
        normalized_params = {"check": check}
    elif intent_type == "dev_session":
        unknown_params = set(params) - {"action"}
        if unknown_params:
            raise ValueError(f"Unknown dev_session params: {', '.join(sorted(unknown_params))}")
        action = params.get("action")
        if action not in COMPANION_DEV_SESSION_ACTIONS:
            raise ValueError("Unsupported dev_session action.")
        normalized_params = {"action": action}
    elif intent_type == "commit_current_changes":
        unknown_params = set(params) - {"message", "include_untracked"}
        if unknown_params:
            raise ValueError(f"Unknown commit_current_changes params: {', '.join(sorted(unknown_params))}")
        message = params.get("message")
        if not isinstance(message, str) or message.strip() == "":
            raise ValueError("commit message must be a non-empty string.")
        if "\n" in message or "\r" in message:
            raise ValueError("commit message must be single-line.")
        include_untracked = params.get("include_untracked", False)
        if not isinstance(include_untracked, bool):
            raise ValueError("include_untracked must be a boolean.")
        normalized_params = {"message": message.strip(), "include_untracked": include_untracked}

    return {
        "version": 1,
        "intent_kind": "run",
        "intent_type": intent_type,
        "cwd": cwd,
        "params": normalized_params,
    }


def import_intent_json(value: object) -> str:
    import server as mcp_server

    intent = validate_companion_intent(value)
    canonical = json.dumps(
        intent,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    nonce = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    created = datetime.now(timezone.utc)
    payload = {
        "intent_type": intent["intent_type"],
        "cwd": intent["cwd"],
        "params": intent["params"],
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(seconds=mcp_server.INTENT_TOKEN_TTL_SECONDS)).isoformat(),
        "nonce": nonce,
    }
    result = mcp_server._import_intent(payload)
    return str(result.bundle_id)


def import_intent_value(value: object) -> str:
    if isinstance(value, dict):
        return import_intent_json(value)
    return import_intent_token(value)


def pending_bundle_url(bundle_id: str) -> str:
    return f"/pending?bundle_id={bundle_id}"


def intent_import_result(value: object) -> dict[str, object]:
    bundle_id = import_intent_value(value)
    return {
        "ok": True,
        "bundle_id": bundle_id,
        "pending_url": pending_bundle_url(bundle_id),
    }


def intent_import_redirect_location(value: object) -> str:
    return str(intent_import_result(value)["pending_url"])

