from __future__ import annotations

import contextlib
import io
import unittest

from terminal_bridge import cli


class CliCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_run_dev_session = cli.run_dev_session
        self.original_version_summary = cli.version_summary

    def tearDown(self) -> None:
        cli.run_dev_session = self.original_run_dev_session
        cli.version_summary = self.original_version_summary

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

    def test_version_prints_without_dev_session(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_run_dev_session(*args: str) -> int:
            calls.append(args)
            return 0

        def fake_version_summary() -> dict[str, str]:
            return {
                "name": "Ouroboros Workspace Bridge",
                "version": "0.3.0",
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
        self.assertIn("Ouroboros Workspace Bridge 0.3.0", stdout.getvalue())
        self.assertIn("commit: unknown", stdout.getvalue())
