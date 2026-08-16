from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError

_MAX_ACCESS_JWT_CHARS = 16_384


class CloudflareAccessVerificationError(Exception):
    """Raised when a Cloudflare Access application JWT cannot be trusted."""


@dataclass(frozen=True, slots=True)
class CloudflareAccessSettings:
    """Validated Cloudflare Access application identity."""

    team_domain: str
    audience: str
    jwks_timeout_seconds: float = 5.0
    jwks_cache_seconds: int = 300

    def __post_init__(self) -> None:
        normalized_domain = _normalize_team_domain(self.team_domain)
        normalized_audience = _normalize_audience(self.audience)
        if not 0.1 <= self.jwks_timeout_seconds <= 30:
            raise ValueError("Cloudflare Access JWKS timeout must be between 0.1 and 30 seconds")
        if not 30 <= self.jwks_cache_seconds <= 86_400:
            raise ValueError("Cloudflare Access JWKS cache must be between 30 and 86400 seconds")
        object.__setattr__(self, "team_domain", normalized_domain)
        object.__setattr__(self, "audience", normalized_audience)

    @property
    def issuer(self) -> str:
        return self.team_domain

    @property
    def jwks_url(self) -> str:
        return f"{self.team_domain}/cdn-cgi/access/certs"


def _normalize_team_domain(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    hostname = (parsed.hostname or "").casefold()
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".cloudflareaccess.com")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Cloudflare Access team domain must be an HTTPS *.cloudflareaccess.com origin"
        )
    return f"https://{hostname}"


def _normalize_audience(value: str) -> str:
    candidate = value.strip()
    if not candidate or len(candidate) > 512 or any(char.isspace() for char in candidate):
        raise ValueError("Cloudflare Access audience must be a non-empty bounded token")
    return candidate


def access_jwt_from_headers(headers: dict[str, str]) -> str | None:
    token = headers.get("cf-access-jwt-assertion")
    if not token or len(token) > _MAX_ACCESS_JWT_CHARS:
        return None
    return token


class CloudflareAccessJWTVerifier:
    """Verify Access application JWTs against Cloudflare's rotating JWKS."""

    def __init__(
        self,
        settings: CloudflareAccessSettings,
        *,
        jwks_client: PyJWKClient | None = None,
    ) -> None:
        self._settings = settings
        self._jwks_client = jwks_client or PyJWKClient(
            settings.jwks_url,
            cache_jwk_set=True,
            lifespan=settings.jwks_cache_seconds,
            timeout=settings.jwks_timeout_seconds,
            headers={"User-Agent": "workspace-terminal-bridge-cloudflare-access-verifier"},
        )
        self._jwks_lock = Lock()

    def verify(self, token: str) -> Mapping[str, Any]:
        if not token or len(token) > _MAX_ACCESS_JWT_CHARS:
            raise CloudflareAccessVerificationError("invalid Cloudflare Access JWT")
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                raise CloudflareAccessVerificationError("invalid Cloudflare Access JWT")
            with self._jwks_lock:
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key=signing_key.key,
                algorithms=["RS256"],
                audience=self._settings.audience,
                issuer=self._settings.issuer,
                options={"require": ["aud", "exp", "iss"]},
                leeway=30,
            )
        except CloudflareAccessVerificationError:
            raise
        except (PyJWKClientError, PyJWTError, OSError, TimeoutError, ValueError):
            raise CloudflareAccessVerificationError("invalid Cloudflare Access JWT") from None
        return claims
