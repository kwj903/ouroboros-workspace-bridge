from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from terminal_bridge import session_supervisor, setup_ui


class SetupUiPublicAccessTests(unittest.TestCase):
    def make_settings(
        self,
        root: Path,
        *,
        mode: str = "ngrok",
        public_mcp_url: str = "",
    ) -> session_supervisor.SessionSettings:
        workspace = root / "workspace"
        workspace.mkdir()
        return session_supervisor.SessionSettings(
            runtime_root=root / "runtime",
            mcp_access_token="test-token",
            ngrok_host="example.ngrok.app",
            workspace_root=workspace,
            public_access_mode=mode,
            public_mcp_url=public_mcp_url,
        )

    def test_ngrok_mode_keeps_ngrok_onboarding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(Path(tmp))
            with mock.patch.object(setup_ui, "_review_ui_reachable", return_value=False):
                html = setup_ui.render_setup_page(settings, language="en")

        self.assertIn("Prepare ngrok", html)
        self.assertIn("ngrok config add-authtoken", html)
        self.assertIn("NGROK_HOST", html)
        self.assertNotIn("Connect your own domain", html)

    def test_external_mode_shows_public_url_without_ngrok_install_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(
                Path(tmp),
                mode="external",
                public_mcp_url="https://terminalbridge.woojae.dev/mcp",
            )
            with mock.patch.object(setup_ui, "_review_ui_reachable", return_value=False):
                html = setup_ui.render_setup_page(settings, language="en")

        self.assertIn("Connect your own domain", html)
        self.assertIn("https://terminalbridge.woojae.dev/mcp", html)
        self.assertIn("only one computer at a time", html)
        self.assertIn("PUBLIC_ACCESS_MODE", html)
        self.assertIn("PUBLIC_MCP_URL", html)
        self.assertNotIn("ngrok config add-authtoken", html)
        self.assertNotIn("winget install ngrok", html)


if __name__ == "__main__":
    unittest.main()
