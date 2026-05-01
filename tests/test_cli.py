from __future__ import annotations

import contextlib
import io
import unittest

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
