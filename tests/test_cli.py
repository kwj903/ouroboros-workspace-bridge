from __future__ import annotations

import unittest

from terminal_bridge import cli


class CliCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_run_dev_session = cli.run_dev_session

    def tearDown(self) -> None:
        cli.run_dev_session = self.original_run_dev_session

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
