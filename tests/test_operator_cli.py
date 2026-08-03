from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from terminal_bridge import operator_cli
from terminal_bridge import session_supervisor as supervisor


def make_settings(tmp: str, **overrides: object) -> supervisor.SessionSettings:
    values: dict[str, object] = {
        "runtime_root": Path(tmp) / "runtime",
        "mcp_access_token": "test-token",
        "ngrok_host": "example.ngrok.app",
        "workspace_root": Path(tmp) / "workspace",
        "public_access_mode": "external",
        "public_mcp_url": "https://terminalbridge.example.com/mcp",
        "external_tunnel_provider": "cloudflare",
        "cloudflared_config_path": str(Path(tmp) / "cloudflared.yml"),
        "cloudflared_tunnel_name": "example-tunnel",
        "cloudflared_bin": "cloudflared",
    }
    values.update(overrides)
    return supervisor.SessionSettings(**values)


class OperatorModeTests(unittest.TestCase):
    def test_selected_operator_mode_maps_compatible_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cloudflare = make_settings(tmp)
            ngrok = make_settings(tmp, public_access_mode="ngrok")
            external = make_settings(
                tmp,
                external_tunnel_provider="manual",
            )

        self.assertEqual(operator_cli.selected_operator_mode(ngrok), "ngrok")
        self.assertEqual(
            operator_cli.selected_operator_mode(cloudflare), "cloudflare"
        )
        self.assertEqual(operator_cli.selected_operator_mode(external), "external")

    def test_settings_for_operator_mode_preserves_provider_specific_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(tmp)

            ngrok = operator_cli.settings_for_operator_mode(settings, "ngrok")
            cloudflare = operator_cli.settings_for_operator_mode(
                ngrok, "cloudflare"
            )
            external = operator_cli.settings_for_operator_mode(
                cloudflare, "external"
            )

        self.assertEqual(ngrok.public_access_mode, "ngrok")
        self.assertEqual(ngrok.cloudflared_tunnel_name, "example-tunnel")
        self.assertEqual(cloudflare.public_access_mode, "external")
        self.assertEqual(cloudflare.external_tunnel_provider, "cloudflare")
        self.assertEqual(external.external_tunnel_provider, "manual")

    def test_parser_accepts_explicit_start_mode(self) -> None:
        args = operator_cli.build_parser().parse_args(
            ["start", "--mode", "cloudflare"]
        )

        self.assertEqual(args.command, "start")
        self.assertEqual(args.mode, "cloudflare")

    def test_parser_accepts_setup_ui_options(self) -> None:
        args = operator_cli.build_parser().parse_args(
            ["setup-ui", "--port", "8891", "--no-open"]
        )

        self.assertEqual(args.command, "setup-ui")
        self.assertEqual(args.port, 8891)
        self.assertTrue(args.no_open)


class CloudflaredConfigurationTests(unittest.TestCase):
    def test_cloudflared_command_uses_user_owned_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "cloudflared.yml"
            config.write_text("ingress: []\n", encoding="utf-8")
            settings = make_settings(tmp)
            with mock.patch.object(
                operator_cli.shutil,
                "which",
                return_value="/usr/local/bin/cloudflared",
            ):
                command = operator_cli.cloudflared_command(settings)

        self.assertEqual(Path(command[0]).name, "cloudflared")
        self.assertEqual(
            command[1:4],
            ["tunnel", "--config", str(config.resolve(strict=False))],
        )
        self.assertEqual(command[-2:], ["run", "example-tunnel"])
        self.assertNotIn("woojae.dev", " ".join(command))

    def test_cloudflared_command_requires_config_and_tunnel_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(
                tmp,
                cloudflared_config_path="",
                cloudflared_tunnel_name="",
            )
            with self.assertRaises(
                operator_cli.public_access.PublicAccessConfigError
            ):
                operator_cli.cloudflared_command(settings)

    def test_cloudflared_process_metadata_requires_matching_process(self) -> None:
        metadata = {
            "pid": 1234,
            "command": [
                "/usr/local/bin/cloudflared",
                "tunnel",
                "--config",
                "/tmp/config.yml",
                "run",
                "example-tunnel",
            ],
        }
        with (
            mock.patch.object(operator_cli.supervisor, "is_windows", return_value=False),
            mock.patch.object(
                operator_cli,
                "_posix_process_command",
                return_value="/usr/local/bin/cloudflared tunnel --config /tmp/config.yml run example-tunnel",
            ),
        ):
            self.assertTrue(
                operator_cli.cloudflared_process_matches_metadata(1234, metadata)
            )

        with (
            mock.patch.object(operator_cli.supervisor, "is_windows", return_value=False),
            mock.patch.object(
                operator_cli,
                "_posix_process_command",
                return_value="python unrelated.py",
            ),
        ):
            self.assertFalse(
                operator_cli.cloudflared_process_matches_metadata(1234, metadata)
            )

    def test_windows_process_metadata_requires_tunnel_and_config_match(self) -> None:
        metadata = {
            "pid": 1234,
            "command": [
                r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
                "tunnel",
                "--config",
                r"C:\Users\Example\.cloudflared\terminalbridge.yml",
                "run",
                "example-tunnel",
            ],
        }
        matching_command = (
            r'"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel '
            r'--config C:\Users\Example\.cloudflared\terminalbridge.yml run example-tunnel'
        )
        with (
            mock.patch.object(operator_cli.supervisor, "is_windows", return_value=True),
            mock.patch.object(
                operator_cli,
                "_windows_process_executable",
                return_value=r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
            ),
            mock.patch.object(
                operator_cli,
                "_windows_process_command",
                return_value=matching_command,
            ),
        ):
            self.assertTrue(
                operator_cli.cloudflared_process_matches_metadata(1234, metadata)
            )

        with (
            mock.patch.object(operator_cli.supervisor, "is_windows", return_value=True),
            mock.patch.object(
                operator_cli,
                "_windows_process_executable",
                return_value=r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
            ),
            mock.patch.object(
                operator_cli,
                "_windows_process_command",
                return_value=matching_command.replace(
                    "example-tunnel", "different-tunnel"
                ),
            ),
        ):
            self.assertFalse(
                operator_cli.cloudflared_process_matches_metadata(1234, metadata)
            )


class CloudflaredLifecycleTests(unittest.TestCase):
    def test_stop_does_not_terminate_reused_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(tmp)
            settings.process_dir.mkdir(parents=True)
            operator_cli.cloudflared_pid_file(settings).write_text(
                "1234\n", encoding="utf-8"
            )
            operator_cli.cloudflared_metadata_file(settings).write_text(
                '{"pid":1234,"command":["cloudflared","tunnel","run","example-tunnel"]}\n',
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    operator_cli.supervisor, "is_pid_alive", return_value=True
                ),
                mock.patch.object(
                    operator_cli,
                    "cloudflared_process_matches_metadata",
                    return_value=False,
                ),
                mock.patch.object(
                    operator_cli.supervisor, "terminate_pid_tree"
                ) as terminate,
            ):
                result = operator_cli.stop_cloudflared(settings)

            self.assertEqual(result, 0)
            self.assertFalse(operator_cli.cloudflared_pid_file(settings).exists())
            self.assertFalse(
                operator_cli.cloudflared_metadata_file(settings).exists()
            )
            terminate.assert_not_called()

    def test_start_cloudflared_writes_pid_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "cloudflared.yml"
            config.write_text("ingress: []\n", encoding="utf-8")
            settings = make_settings(tmp)
            process = mock.Mock(pid=4567)
            with (
                mock.patch.object(
                    operator_cli.shutil,
                    "which",
                    return_value="/usr/local/bin/cloudflared",
                ),
                mock.patch.object(
                    operator_cli,
                    "managed_cloudflared_pid",
                    return_value=(None, False),
                ),
                mock.patch.object(
                    operator_cli.subprocess, "Popen", return_value=process
                ) as popen,
                mock.patch.object(
                    operator_cli.supervisor, "is_pid_alive", return_value=True
                ),
                mock.patch.object(operator_cli.time, "sleep"),
            ):
                result = operator_cli.start_cloudflared(settings)

            self.assertEqual(result, 0)
            self.assertEqual(
                operator_cli.cloudflared_pid_file(settings).read_text(
                    encoding="utf-8"
                ),
                "4567\n",
            )
            metadata = operator_cli._read_process_metadata(
                operator_cli.cloudflared_metadata_file(settings)
            )
            self.assertEqual(metadata["pid"], 4567)
            self.assertEqual(metadata["command"][-1], "example-tunnel")
            popen.assert_called_once()

    def test_start_operator_cloudflare_preflights_before_stopping_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(
                tmp,
                cloudflared_config_path=str(Path(tmp) / "missing.yml"),
            )
            with (
                mock.patch.object(
                    operator_cli.supervisor, "load_settings", return_value=settings
                ),
                mock.patch.object(
                    operator_cli.supervisor, "stop_service"
                ) as stop_service,
                mock.patch.object(
                    operator_cli.supervisor, "start_session"
                ) as start_session,
            ):
                with self.assertRaises(
                    operator_cli.public_access.PublicAccessConfigError
                ):
                    operator_cli.start_operator()

            stop_service.assert_not_called()
            start_session.assert_not_called()

    def test_start_operator_cloudflare_stops_ngrok_then_starts_connector(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(tmp)
            calls: list[str] = []
            with (
                mock.patch.object(
                    operator_cli.supervisor, "load_settings", return_value=settings
                ),
                mock.patch.object(
                    operator_cli,
                    "cloudflared_command",
                    return_value=["cloudflared", "tunnel", "run", "example-tunnel"],
                ),
                mock.patch.object(
                    operator_cli.supervisor,
                    "stop_service",
                    side_effect=lambda service: calls.append(f"stop:{service}") or 0,
                ),
                mock.patch.object(
                    operator_cli.supervisor,
                    "start_session",
                    side_effect=lambda: calls.append("start:bridge") or 0,
                ),
                mock.patch.object(
                    operator_cli,
                    "wait_for_local_bridge",
                    return_value=True,
                ),
                mock.patch.object(
                    operator_cli,
                    "start_cloudflared",
                    side_effect=lambda _settings: calls.append("start:cloudflared") or 0,
                ),
                mock.patch.object(
                    operator_cli,
                    "wait_for_public_endpoint",
                    return_value=401,
                ),
            ):
                result = operator_cli.start_operator()

        self.assertEqual(result, 0)
        self.assertEqual(
            calls,
            ["stop:ngrok", "start:bridge", "start:cloudflared"],
        )

    def test_start_operator_cloudflare_connector_failure_cleans_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(tmp)
            with (
                mock.patch.object(
                    operator_cli.supervisor, "load_settings", return_value=settings
                ),
                mock.patch.object(
                    operator_cli,
                    "cloudflared_command",
                    return_value=["cloudflared", "tunnel", "run", "example-tunnel"],
                ),
                mock.patch.object(
                    operator_cli.supervisor, "stop_service", return_value=0
                ),
                mock.patch.object(
                    operator_cli.supervisor, "start_session", return_value=0
                ),
                mock.patch.object(
                    operator_cli, "wait_for_local_bridge", return_value=True
                ),
                mock.patch.object(
                    operator_cli, "start_cloudflared", return_value=1
                ),
                mock.patch.object(
                    operator_cli.supervisor, "stop_session", return_value=0
                ) as stop_session,
            ):
                result = operator_cli.start_operator()

        self.assertEqual(result, 1)
        stop_session.assert_called_once_with()

    def test_start_operator_ngrok_stops_managed_cloudflared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(tmp, public_access_mode="ngrok")
            calls: list[str] = []
            with (
                mock.patch.object(
                    operator_cli.supervisor, "load_settings", return_value=settings
                ),
                mock.patch.object(
                    operator_cli,
                    "stop_cloudflared",
                    side_effect=lambda _settings: calls.append("stop:cloudflared") or 0,
                ),
                mock.patch.object(
                    operator_cli.supervisor,
                    "start_session",
                    side_effect=lambda: calls.append("start:bridge") or 0,
                ),
                mock.patch.object(
                    operator_cli,
                    "wait_for_local_bridge",
                    return_value=True,
                ),
            ):
                result = operator_cli.start_operator()

        self.assertEqual(result, 0)
        self.assertEqual(calls, ["stop:cloudflared", "start:bridge"])

    def test_public_endpoint_readiness_requires_authentication_challenge(self) -> None:
        self.assertTrue(operator_cli.public_endpoint_is_ready(401))
        self.assertFalse(operator_cli.public_endpoint_is_ready(200))
        self.assertFalse(operator_cli.public_endpoint_is_ready(403))
        self.assertFalse(operator_cli.public_endpoint_is_ready(404))
        self.assertFalse(operator_cli.public_endpoint_is_ready(530))
        self.assertFalse(operator_cli.public_endpoint_is_ready(None))

    def test_status_reports_http_5xx_as_unreachable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(tmp)
            stdout = io.StringIO()
            with (
                mock.patch.object(
                    operator_cli.supervisor, "load_settings", return_value=settings
                ),
                mock.patch.object(operator_cli.supervisor, "status_session", return_value=0),
                mock.patch.object(operator_cli, "print_cloudflared_status"),
                mock.patch.object(
                    operator_cli, "public_endpoint_http_status", return_value=530
                ),
                contextlib.redirect_stdout(stdout),
            ):
                result = operator_cli.status_operator()

        self.assertEqual(result, 0)
        self.assertIn("Public endpoint reachable: no (HTTP 530)", stdout.getvalue())

    def test_main_routes_setup_to_existing_supervisor_configuration(self) -> None:
        with mock.patch.object(
            operator_cli.supervisor, "configure", return_value=0
        ) as configure:
            self.assertEqual(operator_cli.main(["setup"]), 0)

        configure.assert_called_once_with()

    def test_main_routes_setup_ui_to_existing_onboarding_server(self) -> None:
        with mock.patch.object(
            operator_cli.setup_ui, "run_setup_ui", return_value=0
        ) as run_setup_ui:
            result = operator_cli.main(
                ["setup-ui", "--port", "8891", "--no-open"]
            )

        self.assertEqual(result, 0)
        run_setup_ui.assert_called_once_with(port=8891, open_browser=False)

    def test_invalid_mode_error_is_redacted_and_nonzero(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch.object(
                operator_cli.supervisor,
                "load_settings",
                return_value=make_settings(tempfile.gettempdir(), public_mcp_url=""),
            ),
            contextlib.redirect_stderr(stderr),
        ):
            result = operator_cli.main(["start", "--mode", "cloudflare"])

        self.assertNotEqual(result, 0)
        self.assertNotIn("test-token", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
