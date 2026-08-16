from __future__ import annotations

import unittest
from unittest.mock import Mock

from terminal_bridge.cloudflare_access import (
    CloudflareAccessJWTVerifier,
    CloudflareAccessSettings,
    CloudflareAccessVerificationError,
    access_jwt_from_headers,
)
from server import AccessTokenMiddleware


class CloudflareAccessSettingsTests(unittest.TestCase):
    def test_normalizes_team_domain_and_audience(self) -> None:
        settings = CloudflareAccessSettings(
            team_domain="https://Example-Team.cloudflareaccess.com/",
            audience="audience-token",
        )
        self.assertEqual(
            settings.team_domain,
            "https://example-team.cloudflareaccess.com",
        )
        self.assertEqual(settings.issuer, settings.team_domain)
        self.assertEqual(
            settings.jwks_url,
            "https://example-team.cloudflareaccess.com/cdn-cgi/access/certs",
        )

    def test_rejects_non_cloudflare_team_domain(self) -> None:
        with self.assertRaises(ValueError):
            CloudflareAccessSettings(
                team_domain="https://example.com",
                audience="audience-token",
            )

    def test_rejects_blank_audience(self) -> None:
        with self.assertRaises(ValueError):
            CloudflareAccessSettings(
                team_domain="https://example-team.cloudflareaccess.com",
                audience="",
            )


class AccessJWTHeaderTests(unittest.TestCase):
    def test_extracts_bounded_access_jwt(self) -> None:
        self.assertEqual(
            access_jwt_from_headers({"cf-access-jwt-assertion": "token"}),
            "token",
        )

    def test_rejects_missing_or_oversized_access_jwt(self) -> None:
        self.assertIsNone(access_jwt_from_headers({}))
        self.assertIsNone(
            access_jwt_from_headers({"cf-access-jwt-assertion": "x" * 16_385})
        )


class CloudflareAccessJWTVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = CloudflareAccessSettings(
            team_domain="https://example-team.cloudflareaccess.com",
            audience="audience-token",
        )

    def test_rejects_invalid_jwt_without_fetching_jwks(self) -> None:
        jwks_client = Mock()
        verifier = CloudflareAccessJWTVerifier(
            self.settings,
            jwks_client=jwks_client,
        )
        with self.assertRaises(CloudflareAccessVerificationError):
            verifier.verify("not-a-jwt")
        jwks_client.get_signing_key_from_jwt.assert_not_called()

    def test_rejects_oversized_jwt(self) -> None:
        verifier = CloudflareAccessJWTVerifier(
            self.settings,
            jwks_client=Mock(),
        )
        with self.assertRaises(CloudflareAccessVerificationError):
            verifier.verify("x" * 16_385)


class AccessTokenMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def _run_request(
        self,
        *,
        headers: list[tuple[bytes, bytes]] | None = None,
        query_string: bytes = b"",
        verifier: object | None = None,
    ) -> tuple[bool, list[dict[str, object]]]:
        called = False
        sent: list[dict[str, object]] = []

        async def app(scope: object, receive: object, send: object) -> None:
            nonlocal called
            called = True

        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        middleware = AccessTokenMiddleware(
            app,
            "static-token",
            access_jwt_verifier=verifier,  # type: ignore[arg-type]
        )
        await middleware(
            {
                "type": "http",
                "headers": headers or [],
                "query_string": query_string,
            },
            receive,
            send,
        )
        return called, sent

    async def test_keeps_existing_static_bearer_auth(self) -> None:
        called, sent = await self._run_request(
            headers=[(b"authorization", b"Bearer static-token")],
        )
        self.assertTrue(called)
        self.assertEqual(sent, [])

    async def test_accepts_valid_cloudflare_access_assertion(self) -> None:
        verifier = Mock()
        verifier.verify.return_value = {"sub": "user"}
        called, sent = await self._run_request(
            headers=[(b"cf-access-jwt-assertion", b"access-jwt")],
            verifier=verifier,
        )
        self.assertTrue(called)
        self.assertEqual(sent, [])
        verifier.verify.assert_called_once_with("access-jwt")

    async def test_rejects_invalid_cloudflare_access_assertion(self) -> None:
        verifier = Mock()
        verifier.verify.side_effect = CloudflareAccessVerificationError("invalid")
        called, sent = await self._run_request(
            headers=[(b"cf-access-jwt-assertion", b"bad-jwt")],
            verifier=verifier,
        )
        self.assertFalse(called)
        self.assertEqual(sent[0]["status"], 401)

    async def test_rejects_request_without_either_authentication(self) -> None:
        called, sent = await self._run_request()
        self.assertFalse(called)
        self.assertEqual(sent[0]["status"], 401)


if __name__ == "__main__":
    unittest.main()
