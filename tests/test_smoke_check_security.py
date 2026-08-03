from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

from scripts import smoke_check


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SmokeCheckSecurityTests(unittest.TestCase):
    def test_sensitive_url_output_is_redacted(self) -> None:
        value = "https://example.com/mcp?access_token=secret-value"

        redacted = smoke_check.redact_sensitive_text(value)

        self.assertIn("access_token=<redacted>", redacted)
        self.assertNotIn("secret-value", redacted)

    def test_check_all_does_not_put_tokenized_url_in_argv(self) -> None:
        source = (PROJECT_ROOT / "scripts" / "check_all.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("smoke_check.py --remote-only", source)
        self.assertNotIn("--mcp-url", source)
        self.assertNotIn("tokenized_mcp_url", source)
        self.assertNotIn("MCP_ACCESS_TOKEN", source)

    def test_token_bearing_mcp_url_is_rejected(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    "smoke_check.py",
                    "--mcp-url",
                    "https://example.com/mcp?access_token=secret-value",
                ],
            ),
            contextlib.redirect_stderr(stderr),
        ):
            result = smoke_check.main()

        self.assertEqual(result, 2)
        self.assertIn("token-bearing --mcp-url values are not allowed", stderr.getvalue())
        self.assertNotIn("secret-value", stderr.getvalue())

    def test_remote_smoke_uses_authorization_header_not_inspector_argv(self) -> None:
        source = (PROJECT_ROOT / "scripts" / "smoke_check.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('headers = {"Authorization": f"Bearer {token}"}', source)
        self.assertIn("streamablehttp_client", source)
        self.assertNotIn("@modelcontextprotocol/inspector", source)


if __name__ == "__main__":
    unittest.main()
