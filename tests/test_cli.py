from __future__ import annotations

import contextlib
import io
import unittest
from unittest import mock

from terminal_bridge import cli


class CliCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_run_dev_session = cli.run_dev_session
        self.original_version_summary = cli.version_summary
        self.original_print_paths = cli.supervisor.print_paths
        self.original_print_storage = cli.supervisor.print_storage
        self.original_cleanup_storage = cli.supervisor.cleanup_storage

    def tearDown(self) -> None:
        cli.run_dev_session = self.original_run_dev_session
        cli.version_summary = self.original_version_summary
        cli.supervisor.print_paths = self.original_print_paths
        cli.supervisor.print_storage = self.original_print_storage
        cli.supervisor.cleanup_storage = self.original_cleanup_storage

    def test_parser_accepts_restart_session(self) -> None:
        args = cli.build_parser().parse_args(["restart-session"])

        self.assertEqual(args.command, "restart-session")

    def test_restart_session_calls_dev_session_helper(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_run_dev_session(*args: str) -> int:
            calls.append(args)
            return 0

        cli.run_dev_session = fake_run_dev_session

        self.assertEqual(cli.main(["restart-session"]), 0)
        self.assertEqual(calls, [("restart-session",)])

    def test_restart_mcp_behavior_is_unchanged(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_run_dev_session(*args: str) -> int:
            calls.append(args)
            return 0

        cli.run_dev_session = fake_run_dev_session

        self.assertEqual(cli.main(["restart", "mcp"]), 0)
        self.assertEqual(calls, [("restart", "mcp")])

    def test_parser_accepts_version(self) -> None:
        args = cli.build_parser().parse_args(["version"])

        self.assertEqual(args.command, "version")

    def test_parser_accepts_help(self) -> None:
        parser = cli.build_parser()

        help_args = parser.parse_args(["help"])
        self.assertEqual(help_args.command, "help")
        self.assertIsNone(help_args.topic)
        self.assertEqual(help_args.lang, "auto")

        topic_args = parser.parse_args(["help", "cleanup", "--lang", "ko"])
        self.assertEqual(topic_args.command, "help")
        self.assertEqual(topic_args.topic, "cleanup")
        self.assertEqual(topic_args.lang, "ko")

        shorthand_args = parser.parse_args(["help", "cleanup", "--ko"])
        self.assertEqual(shorthand_args.command, "help")
        self.assertEqual(shorthand_args.topic, "cleanup")
        self.assertEqual(shorthand_args.lang, "ko")

    def test_parser_accepts_runtime_storage_commands(self) -> None:
        parser = cli.build_parser()

        self.assertEqual(parser.parse_args(["paths"]).command, "paths")
        self.assertEqual(parser.parse_args(["storage"]).command, "storage")
        cleanup = parser.parse_args(["cleanup", "--dry-run", "--older-than-days", "7"])
        self.assertEqual(cleanup.command, "cleanup")
        self.assertTrue(cleanup.dry_run)
        self.assertFalse(cleanup.apply)
        self.assertEqual(cleanup.older_than_days, 7)

    def test_runtime_storage_commands_call_supervisor(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_paths() -> int:
            calls.append(("paths", None))
            return 0

        def fake_storage() -> int:
            calls.append(("storage", None))
            return 0

        def fake_cleanup_storage(*, apply: bool, older_than_days: int | None = None, include_backups: bool = False) -> int:
            calls.append(("cleanup", (apply, older_than_days, include_backups)))
            return 0

        cli.supervisor.print_paths = fake_paths
        cli.supervisor.print_storage = fake_storage
        cli.supervisor.cleanup_storage = fake_cleanup_storage

        self.assertEqual(cli.main(["paths"]), 0)
        self.assertEqual(cli.main(["storage"]), 0)
        self.assertEqual(cli.main(["cleanup", "--apply", "--older-than-days", "3", "--include-backups"]), 0)
        self.assertEqual(calls, [("paths", None), ("storage", None), ("cleanup", (True, 3, True))])

    def test_cleanup_rejects_non_positive_older_than_days(self) -> None:
        called = False

        def fake_cleanup_storage(*, apply: bool, older_than_days: int | None = None, include_backups: bool = False) -> int:
            nonlocal called
            called = True
            return 0

        cli.supervisor.cleanup_storage = fake_cleanup_storage
        result = cli.main(["cleanup", "--older-than-days", "0"])

        self.assertEqual(result, 2)
        self.assertFalse(called)

    def test_help_lists_commands_without_dev_session(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_run_dev_session(*args: str) -> int:
            calls.append(args)
            return 0

        cli.run_dev_session = fake_run_dev_session

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = cli.main(["help", "--lang", "en"])

        self.assertEqual(result, 0)
        self.assertEqual(calls, [])
        output = stdout.getvalue()
        self.assertIn("Ouroboros Workspace Bridge commands", output)
        self.assertIn("Common workflow", output)
        self.assertIn("cleanup", output)
        self.assertIn("Run `uv run woojae help <command>`", output)

    def test_help_lists_korean_commands_without_dev_session(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_run_dev_session(*args: str) -> int:
            calls.append(args)
            return 0

        cli.run_dev_session = fake_run_dev_session

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = cli.main(["help", "--lang", "ko"])

        self.assertEqual(result, 0)
        self.assertEqual(calls, [])
        output = stdout.getvalue()
        self.assertIn("Ouroboros Workspace Bridge 명령어", output)
        self.assertIn("기본 작업 흐름", output)
        self.assertIn("cleanup", output)
        self.assertIn("상세 설명", output)

    def test_help_topic_prints_korean_details(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = cli.main(["help", "cleanup", "--lang", "ko"])

        self.assertEqual(result, 0)
        output = stdout.getvalue()
        self.assertIn("Usage: uv run woojae cleanup", output)
        self.assertIn("런타임 정리 후보", output)
        self.assertIn("예시:", output)
        self.assertIn("주의:", output)
        self.assertIn("--dry-run", output)

    def test_help_unknown_topic_returns_error(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = cli.main(["help", "missing-command", "--lang", "ko"])

        self.assertEqual(result, 2)
        output = stderr.getvalue()
        self.assertIn("알 수 없는 help 주제", output)
        self.assertIn("사용 가능한 주제", output)

    def test_help_language_auto_detects_korean_locale(self) -> None:
        with mock.patch.dict("os.environ", {"LANG": "ko_KR.UTF-8"}, clear=True):
            self.assertEqual(cli.resolve_help_language(), "ko")

    def test_help_language_prefers_environment_setting_over_locale(self) -> None:
        with mock.patch.dict("os.environ", {"WOOJAE_HELP_LANG": "ko", "LANG": "en_US.UTF-8"}, clear=True):
            self.assertEqual(cli.resolve_help_language(), "ko")

    def test_help_language_prefers_cli_argument_over_environment(self) -> None:
        with mock.patch.dict("os.environ", {"WOOJAE_HELP_LANG": "ko"}, clear=True):
            self.assertEqual(cli.resolve_help_language("en"), "en")

    def test_help_language_uses_saved_setting_before_locale(self) -> None:
        with mock.patch.dict("os.environ", {"LANG": "en_US.UTF-8"}, clear=True):
            self.assertEqual(cli.resolve_help_language(saved_language="ko"), "ko")

    def test_version_prints_without_dev_session(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_run_dev_session(*args: str) -> int:
            calls.append(args)
            return 0

        def fake_version_summary() -> dict[str, str]:
            return {
                "name": "Ouroboros Workspace Bridge",
                "version": "0.3.1",
                "commit": "unknown",
                "branch": "unknown",
                "dirty": "unknown",
            }

        cli.run_dev_session = fake_run_dev_session
        cli.version_summary = fake_version_summary

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = cli.main(["version"])

        self.assertEqual(result, 0)
        self.assertEqual(calls, [])
        self.assertIn("Ouroboros Workspace Bridge 0.3.1", stdout.getvalue())
        self.assertIn("commit: unknown", stdout.getvalue())
