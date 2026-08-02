from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from terminal_bridge import session_supervisor as supervisor


class SessionSupervisorEnvTests(unittest.TestCase):
    def test_parse_legacy_session_env_preserves_windows_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.env"
            path.write_text(
                "export WORKSPACE_ROOT=C:\\Users\\Example User\\workspace\n"
                "export NGROK_HOST='example.ngrok.app'\n",
                encoding="utf-8",
            )

            values = supervisor.parse_legacy_session_env(path)

        self.assertEqual(values["WORKSPACE_ROOT"], r"C:\Users\Example User\workspace")
        self.assertEqual(values["NGROK_HOST"], "example.ngrok.app")


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


class SessionSupervisorPublicAccessTests(unittest.TestCase):
    def test_write_and_load_settings_preserves_external_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_root = Path(tmp) / "runtime"
            workspace_root = Path(tmp) / "workspace"
            workspace_root.mkdir()
            settings = supervisor.SessionSettings(
                runtime_root=runtime_root,
                mcp_access_token="test-token",
                ngrok_host="previous.ngrok.app",
                workspace_root=workspace_root,
                public_access_mode="external",
                public_mcp_url="https://terminalbridge.woojae.dev/mcp",
            )

            supervisor.write_session_files(settings)

            with mock.patch.dict(
                os.environ,
                {"MCP_TERMINAL_BRIDGE_RUNTIME_ROOT": str(runtime_root)},
                clear=True,
            ):
                loaded = supervisor.load_settings()

            self.assertEqual(loaded.public_access_mode, "external")
            self.assertEqual(
                loaded.public_mcp_base_url,
                "https://terminalbridge.woojae.dev/mcp",
            )
            self.assertEqual(loaded.ngrok_host, "previous.ngrok.app")
            env_text = supervisor.session_env_path(runtime_root).read_text(encoding="utf-8")
            self.assertIn("export PUBLIC_ACCESS_MODE=external", env_text)
            self.assertIn(
                "export PUBLIC_MCP_URL=https://terminalbridge.woojae.dev/mcp",
                env_text,
            )

    def test_lenient_settings_load_allows_repairing_invalid_external_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_root = Path(tmp) / "runtime"
            runtime_root.mkdir()
            supervisor.session_json_path(runtime_root).write_text(
                '{"public_access_mode":"external","public_mcp_url":"http://invalid.example/mcp"}\n',
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"MCP_TERMINAL_BRIDGE_RUNTIME_ROOT": str(runtime_root)},
                clear=True,
            ):
                expected_workspace_root = supervisor.default_workspace_root().resolve(
                    strict=False
                )
                with self.assertRaises(supervisor.public_access.PublicAccessConfigError):
                    supervisor.load_settings()
                loaded = supervisor.load_settings(strict_public_access=False)

        self.assertEqual(loaded.public_access_mode, "external")
        self.assertEqual(loaded.public_mcp_url, "http://invalid.example/mcp")
        self.assertEqual(loaded.workspace_root, expected_workspace_root)

    def test_default_workspace_root_uses_project_when_home_is_unavailable(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(supervisor.Path, "home", side_effect=RuntimeError),
        ):
            self.assertEqual(supervisor.default_workspace_root(), supervisor.PROJECT_ROOT)

    def test_active_services_follow_public_access_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = dict(
                runtime_root=Path(tmp) / "runtime",
                mcp_access_token="test-token",
                ngrok_host="example.ngrok.app",
                workspace_root=Path(tmp) / "workspace",
            )
            ngrok_settings = supervisor.SessionSettings(**base)
            external_settings = supervisor.SessionSettings(
                **base,
                public_access_mode="external",
                public_mcp_url="https://terminalbridge.woojae.dev/mcp",
            )

        self.assertEqual(supervisor.active_services(ngrok_settings), supervisor.SERVICES)
        self.assertEqual(supervisor.active_services(external_settings), ("review", "mcp"))

    def test_start_session_external_mode_skips_ngrok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = supervisor.SessionSettings(
                runtime_root=Path(tmp) / "runtime",
                mcp_access_token="test-token",
                ngrok_host="example.ngrok.app",
                workspace_root=Path(tmp) / "workspace",
                public_access_mode="external",
                public_mcp_url="https://terminalbridge.woojae.dev/mcp",
            )
            calls: list[str] = []
            with (
                mock.patch.object(supervisor, "load_settings", return_value=settings),
                mock.patch.object(
                    supervisor,
                    "start_service",
                    side_effect=lambda service: calls.append(service) or 0,
                ),
                mock.patch.object(supervisor, "status_session", return_value=0),
                mock.patch.dict(os.environ, {"WOOJAE_SKIP_OPEN_REVIEW": "1"}),
            ):
                result = supervisor.start_session()

        self.assertEqual(result, 0)
        self.assertEqual(calls, ["review", "mcp"])

    def test_stop_session_always_stops_ngrok_for_mode_transitions(self) -> None:
        calls: list[str] = []
        with mock.patch.object(
            supervisor,
            "stop_service",
            side_effect=lambda service: calls.append(service) or 0,
        ):
            result = supervisor.stop_session()

        self.assertEqual(result, 0)
        self.assertEqual(calls, ["ngrok", "mcp", "review"])

    def test_starting_ngrok_is_rejected_in_external_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = supervisor.SessionSettings(
                runtime_root=Path(tmp) / "runtime",
                mcp_access_token="test-token",
                ngrok_host="example.ngrok.app",
                workspace_root=Path(tmp) / "workspace",
                public_access_mode="external",
                public_mcp_url="https://terminalbridge.woojae.dev/mcp",
            )
            with (
                mock.patch.object(supervisor, "load_settings", return_value=settings),
                mock.patch.object(supervisor.subprocess, "Popen") as popen,
            ):
                result = supervisor.start_service("ngrok")

        self.assertEqual(result, 1)
        popen.assert_not_called()


class SessionSupervisorProcessTests(unittest.TestCase):
    def test_is_pid_alive_routes_windows_to_non_destructive_probe(self) -> None:
        with (
            mock.patch.object(supervisor, "is_windows", return_value=True),
            mock.patch.object(supervisor, "_windows_pid_is_alive", return_value=True) as windows_probe,
            mock.patch.object(supervisor.os, "kill") as os_kill,
        ):
            self.assertTrue(supervisor.is_pid_alive(1234))

        windows_probe.assert_called_once_with(1234)
        os_kill.assert_not_called()

    def test_is_pid_alive_keeps_posix_probe(self) -> None:
        with (
            mock.patch.object(supervisor, "is_windows", return_value=False),
            mock.patch.object(supervisor.os, "kill") as os_kill,
        ):
            self.assertTrue(supervisor.is_pid_alive(1234))

        os_kill.assert_called_once_with(1234, 0)

    def test_windows_termination_does_not_kill_supervisor_child_tree(self) -> None:
        with (
            mock.patch.object(supervisor, "is_windows", return_value=True),
            mock.patch.object(supervisor.subprocess, "run") as run,
        ):
            supervisor.terminate_pid_tree(1234)

        command = run.call_args.args[0]
        self.assertEqual(command, ["taskkill", "/PID", "1234", "/F"])
        self.assertNotIn("/T", command)

    @unittest.skipUnless(os.name == "nt", "Windows-only Win32 process probe")
    def test_windows_probe_reports_current_process_without_terminating_it(self) -> None:
        self.assertTrue(supervisor._windows_pid_is_alive(os.getpid()))


if __name__ == "__main__":
    unittest.main()
