from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from terminal_bridge import public_access


class PublicAccessModeTests(unittest.TestCase):
    def test_normalize_mode_defaults_to_ngrok(self) -> None:
        self.assertEqual(public_access.normalize_public_access_mode(""), "ngrok")
        self.assertEqual(public_access.normalize_public_access_mode(" NGROK "), "ngrok")
        self.assertEqual(public_access.normalize_public_access_mode(" External "), "external")

    def test_normalize_mode_rejects_unknown_value(self) -> None:
        with self.assertRaisesRegex(public_access.PublicAccessConfigError, "PUBLIC_ACCESS_MODE"):
            public_access.normalize_public_access_mode("cloudflare")


class ExternalPublicUrlTests(unittest.TestCase):
    def test_normalize_external_url_accepts_origin_or_mcp_path(self) -> None:
        self.assertEqual(
            public_access.normalize_external_mcp_url("https://terminalbridge.woojae.dev"),
            "https://terminalbridge.woojae.dev/mcp",
        )
        self.assertEqual(
            public_access.normalize_external_mcp_url("https://terminalbridge.woojae.dev/"),
            "https://terminalbridge.woojae.dev/mcp",
        )
        self.assertEqual(
            public_access.normalize_external_mcp_url("https://terminalbridge.woojae.dev/mcp/"),
            "https://terminalbridge.woojae.dev/mcp",
        )

    def test_normalize_external_url_rejects_unsafe_forms(self) -> None:
        invalid_values = (
            "",
            "http://terminalbridge.woojae.dev/mcp",
            "https://terminalbridge.woojae.dev/other",
            "https://terminalbridge.woojae.dev/mcp?access_token=secret",
            "https://terminalbridge.woojae.dev/mcp#fragment",
            "https://user:password@terminalbridge.woojae.dev/mcp",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(public_access.PublicAccessConfigError):
                    public_access.normalize_external_mcp_url(value)

    def test_public_endpoint_and_hostname_follow_selected_mode(self) -> None:
        self.assertEqual(
            public_access.public_mcp_base_url(
                mode="ngrok",
                ngrok_host="example.ngrok.app",
                external_mcp_url="",
            ),
            "https://example.ngrok.app/mcp",
        )
        self.assertEqual(
            public_access.public_mcp_base_url(
                mode="external",
                ngrok_host="example.ngrok.app",
                external_mcp_url="https://terminalbridge.woojae.dev/mcp",
            ),
            "https://terminalbridge.woojae.dev/mcp",
        )
        self.assertEqual(
            public_access.public_mcp_hostname(
                mode="external",
                ngrok_host="",
                external_mcp_url="https://terminalbridge.woojae.dev/mcp",
            ),
            "terminalbridge.woojae.dev",
        )

    def test_tokenized_url_encodes_token_and_redacts_output(self) -> None:
        base_url = "https://terminalbridge.woojae.dev/mcp"
        self.assertEqual(
            public_access.tokenized_mcp_url(base_url, "a b&c"),
            "https://terminalbridge.woojae.dev/mcp?access_token=a+b%26c",
        )
        self.assertEqual(
            public_access.redacted_mcp_url(base_url),
            "https://terminalbridge.woojae.dev/mcp?access_token=<redacted>",
        )


class PublicAccessTransportTests(unittest.TestCase):
    def test_external_mode_selects_external_transport_host(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runtime = root / "runtime"
            workspace.mkdir()
            env = os.environ.copy()
            env.update(
                {
                    "WORKSPACE_ROOT": str(workspace),
                    "MCP_TERMINAL_BRIDGE_RUNTIME_ROOT": str(runtime),
                    "MCP_ACCESS_TOKEN": "test-token",
                    "PUBLIC_ACCESS_MODE": "external",
                    "PUBLIC_MCP_URL": "https://terminalbridge.woojae.dev/mcp",
                    "NGROK_HOST": "ignored.ngrok.app",
                }
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json, server; "
                        "print(json.dumps({'hosts': server.allowed_hosts, "
                        "'origins': server.allowed_origins}))"
                    ),
                ],
                cwd=project_root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

        payload = json.loads(completed.stdout.strip())
        self.assertIn("terminalbridge.woojae.dev", payload["hosts"])
        self.assertIn("https://terminalbridge.woojae.dev", payload["origins"])
        self.assertNotIn("ignored.ngrok.app", payload["hosts"])
        self.assertNotIn("https://ignored.ngrok.app", payload["origins"])


if __name__ == "__main__":
    unittest.main()
