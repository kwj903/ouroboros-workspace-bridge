from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from terminal_bridge import session_supervisor as supervisor


class SessionSupervisorLanguageTests(unittest.TestCase):
    def test_normalize_help_language_accepts_supported_values(self) -> None:
        self.assertEqual(supervisor.normalize_help_language("auto"), "auto")
        self.assertEqual(supervisor.normalize_help_language("en"), "en")
        self.assertEqual(supervisor.normalize_help_language("ko"), "ko")
        self.assertEqual(supervisor.normalize_help_language(" KO "), "ko")

    def test_normalize_help_language_falls_back_to_auto(self) -> None:
        self.assertEqual(supervisor.normalize_help_language(""), "auto")
        self.assertEqual(supervisor.normalize_help_language("fr"), "auto")

    def test_write_and_load_settings_preserves_help_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_root = Path(tmp) / "runtime"
            workspace_root = Path(tmp) / "workspace"
            workspace_root.mkdir()
            settings = supervisor.SessionSettings(
                runtime_root=runtime_root,
                mcp_access_token="test-token",
                ngrok_host="example.ngrok.app",
                workspace_root=workspace_root,
                help_language="ko",
            )

            supervisor.write_session_files(settings)

            with mock.patch.dict(os.environ, {"MCP_TERMINAL_BRIDGE_RUNTIME_ROOT": str(runtime_root)}, clear=True):
                loaded = supervisor.load_settings()

            self.assertEqual(loaded.help_language, "ko")
            self.assertEqual(loaded.workspace_root, workspace_root.resolve(strict=False))
            self.assertIn('"help_language": "ko"', supervisor.session_json_path(runtime_root).read_text(encoding="utf-8"))
            self.assertIn("export WOOJAE_HELP_LANG=ko", supervisor.session_env_path(runtime_root).read_text(encoding="utf-8"))

    def test_start_session_skips_browser_open_when_flag_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_root = Path(tmp) / "runtime"
            workspace_root = Path(tmp) / "workspace"
            workspace_root.mkdir()
            settings = supervisor.SessionSettings(
                runtime_root=runtime_root,
                mcp_access_token="test-token",
                ngrok_host="example.ngrok.app",
                workspace_root=workspace_root,
            )
            calls: list[str] = []

            original_load_settings = supervisor.load_settings
            original_start_service = supervisor.start_service
            original_status_session = supervisor.status_session
            original_open_review_dashboard = supervisor.open_review_dashboard
            try:
                supervisor.load_settings = lambda: settings
                supervisor.start_service = lambda service: calls.append(service) or 0
                supervisor.status_session = lambda: calls.append("status") or 0

                def fail_open() -> int:
                    raise AssertionError("open_review_dashboard should not be called")

                supervisor.open_review_dashboard = fail_open
                with mock.patch.dict(os.environ, {"WOOJAE_SKIP_OPEN_REVIEW": "1"}, clear=False):
                    result = supervisor.start_session()
            finally:
                supervisor.load_settings = original_load_settings
                supervisor.start_service = original_start_service
                supervisor.status_session = original_status_session
                supervisor.open_review_dashboard = original_open_review_dashboard

            self.assertEqual(result, 0)
            self.assertIn("review", calls)
            self.assertIn("mcp", calls)
            self.assertIn("ngrok", calls)
            self.assertIn("status", calls)


if __name__ == "__main__":
    unittest.main()
