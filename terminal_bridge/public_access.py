from __future__ import annotations

from urllib.parse import urlencode, urlsplit, urlunsplit


PUBLIC_ACCESS_MODES = frozenset({"ngrok", "external"})


class PublicAccessConfigError(ValueError):
    """Raised when public access settings are invalid or unsafe."""


def normalize_public_access_mode(value: str) -> str:
    mode = value.strip().lower() or "ngrok"
    if mode not in PUBLIC_ACCESS_MODES:
        supported = ", ".join(sorted(PUBLIC_ACCESS_MODES))
        raise PublicAccessConfigError(
            f"Unsupported PUBLIC_ACCESS_MODE={value!r}. Supported values: {supported}."
        )
    return mode


def normalize_ngrok_host(value: str) -> str:
    host = value.strip()
    host = host.removeprefix("https://").removeprefix("http://")
    host = host.split("/", 1)[0]
    host = host.split("?", 1)[0]
    host = host.split("#", 1)[0]
    return host


def normalize_external_mcp_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise PublicAccessConfigError(
            "PUBLIC_MCP_URL is required when PUBLIC_ACCESS_MODE=external."
        )

    parsed = urlsplit(raw)
    if parsed.scheme.lower() != "https":
        raise PublicAccessConfigError("PUBLIC_MCP_URL must use https://.")
    if not parsed.hostname:
        raise PublicAccessConfigError("PUBLIC_MCP_URL must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise PublicAccessConfigError(
            "PUBLIC_MCP_URL must not include embedded credentials."
        )
    if parsed.query or parsed.fragment:
        raise PublicAccessConfigError(
            "PUBLIC_MCP_URL must not include a query string, fragment, or access token."
        )

    path = parsed.path.rstrip("/")
    if path not in {"", "/mcp"}:
        raise PublicAccessConfigError(
            "PUBLIC_MCP_URL must use the /mcp endpoint."
        )

    return urlunsplit(("https", parsed.netloc, "/mcp", "", ""))


def public_mcp_base_url(
    *,
    mode: str,
    ngrok_host: str,
    external_mcp_url: str,
) -> str | None:
    normalized_mode = normalize_public_access_mode(mode)
    if normalized_mode == "external":
        return normalize_external_mcp_url(external_mcp_url)

    host = normalize_ngrok_host(ngrok_host)
    return f"https://{host}/mcp" if host else None


def public_mcp_hostname(
    *,
    mode: str,
    ngrok_host: str,
    external_mcp_url: str,
) -> str:
    base_url = public_mcp_base_url(
        mode=mode,
        ngrok_host=ngrok_host,
        external_mcp_url=external_mcp_url,
    )
    if not base_url:
        return ""
    return urlsplit(base_url).hostname or ""


def tokenized_mcp_url(base_url: str, token: str) -> str:
    if not base_url:
        raise PublicAccessConfigError("A public MCP base URL is required.")
    if not token:
        raise PublicAccessConfigError("MCP_ACCESS_TOKEN is required.")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'access_token': token})}"


def redacted_mcp_url(base_url: str) -> str:
    if not base_url:
        raise PublicAccessConfigError("A public MCP base URL is required.")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}access_token=<redacted>"
