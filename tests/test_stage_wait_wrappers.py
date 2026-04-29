from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

import server
from terminal_bridge import tool_calls
from terminal_bridge.models import CommandBundleAction, CommandBundleStatusResult, CommandBundleStep


class StageAndWaitWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_stage_command = server.workspace_stage_command_bundle
        self.original_stage_patch = server.workspace_stage_patch_bundle
        self.original_stage_action = server.workspace_stage_action_bundle
        self.original_stage_commit = server.workspace_stage_commit_bundle
        self.original_wait = server.workspace_wait_command_bundle_status
        self.original_wait_impl = server._workspace_wait_command_bundle_status_impl
        self.original_tool_call_dir = tool_calls.TOOL_CALL_DIR
        self.tmp = tempfile.TemporaryDirectory()
        tool_calls.TOOL_CALL_DIR = Path(self.tmp.name)

    def tearDown(self) -> None:
        server.workspace_stage_command_bundle = self.original_stage_command
        server.workspace_stage_patch_bundle = self.original_stage_patch
        server.workspace_stage_action_bundle = self.original_stage_action
        server.workspace_stage_commit_bundle = self.original_stage_commit
        server.workspace_wait_command_bundle_status = self.original_wait
        server._workspace_wait_command_bundle_status_impl = self.original_wait_impl
        tool_calls.TOOL_CALL_DIR = self.original_tool_call_dir
        self.tmp.cleanup()

    def status_result(self, bundle_id: str) -> CommandBundleStatusResult:
        return CommandBundleStatusResult(
            bundle_id=bundle_id,
            title="fake",
            cwd=".",
            status="pending",
            risk="low",
            approval_required=True,
            command_count=1,
            created_at="",
            updated_at="",
        )

    def test_command_bundle_and_wait_calls_stage_then_wait(self) -> None:
        calls: dict[str, object] = {}
        expected = self.status_result("cmd-test-command")
        steps = [CommandBundleStep(name="status", argv=["git", "status"])]

        def fake_stage(**kwargs: object) -> SimpleNamespace:
            calls["stage"] = kwargs
            return SimpleNamespace(bundle_id="cmd-test-command")

        def fake_wait(bundle_id: str, *, timeout_seconds: int, poll_interval_seconds: float) -> CommandBundleStatusResult:
            calls["wait"] = {
                "bundle_id": bundle_id,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
            return expected

        server.workspace_stage_command_bundle = fake_stage
        server._workspace_wait_command_bundle_status_impl = fake_wait

        result = server.workspace_stage_command_bundle_and_wait(
            title="Run status",
            cwd=".",
            steps=steps,
            timeout_seconds=7,
            poll_interval_seconds=0.5,
        )

        self.assertIs(result, expected)
        self.assertEqual(calls["stage"], {"title": "Run status", "cwd": ".", "steps": steps})
        self.assertEqual(
            calls["wait"],
            {"bundle_id": "cmd-test-command", "timeout_seconds": 7, "poll_interval_seconds": 0.5},
        )

    def test_patch_bundle_and_wait_calls_stage_then_wait(self) -> None:
        calls: dict[str, object] = {}
        expected = self.status_result("cmd-test-patch")

        def fake_stage(**kwargs: object) -> SimpleNamespace:
            calls["stage"] = kwargs
            return SimpleNamespace(bundle_id="cmd-test-patch")

        def fake_wait(bundle_id: str, *, timeout_seconds: int, poll_interval_seconds: float) -> CommandBundleStatusResult:
            calls["wait"] = {
                "bundle_id": bundle_id,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
            return expected

        server.workspace_stage_patch_bundle = fake_stage
        server._workspace_wait_command_bundle_status_impl = fake_wait

        result = server.workspace_stage_patch_bundle_and_wait(
            title="Apply patch",
            cwd=".",
            patch="diff --git a/file b/file",
            patch_ref=None,
            timeout_seconds=8,
            poll_interval_seconds=0.75,
        )

        self.assertIs(result, expected)
        self.assertEqual(
            calls["stage"],
            {"title": "Apply patch", "cwd": ".", "patch": "diff --git a/file b/file", "patch_ref": None},
        )
        self.assertEqual(
            calls["wait"],
            {"bundle_id": "cmd-test-patch", "timeout_seconds": 8, "poll_interval_seconds": 0.75},
        )

    def test_action_bundle_and_wait_calls_stage_then_wait(self) -> None:
        calls: dict[str, object] = {}
        expected = self.status_result("cmd-test-action")
        actions = [CommandBundleAction(name="write", type="write_file", path="file.txt", content="hello")]

        def fake_stage(**kwargs: object) -> SimpleNamespace:
            calls["stage"] = kwargs
            return SimpleNamespace(bundle_id="cmd-test-action")

        def fake_wait(bundle_id: str, *, timeout_seconds: int, poll_interval_seconds: float) -> CommandBundleStatusResult:
            calls["wait"] = {
                "bundle_id": bundle_id,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
            return expected

        server.workspace_stage_action_bundle = fake_stage
        server._workspace_wait_command_bundle_status_impl = fake_wait

        result = server.workspace_stage_action_bundle_and_wait(
            title="Write file",
            cwd=".",
            actions=actions,
            timeout_seconds=9,
            poll_interval_seconds=1.25,
        )

        self.assertIs(result, expected)
        self.assertEqual(calls["stage"], {"title": "Write file", "cwd": ".", "actions": actions})
        self.assertEqual(
            calls["wait"],
            {"bundle_id": "cmd-test-action", "timeout_seconds": 9, "poll_interval_seconds": 1.25},
        )

    def test_commit_bundle_and_wait_uses_internal_default_prechecks(self) -> None:
        calls: dict[str, object] = {}
        expected = self.status_result("cmd-test-commit")

        def fake_stage(**kwargs: object) -> SimpleNamespace:
            calls["stage"] = kwargs
            return SimpleNamespace(bundle_id="cmd-test-commit")

        def fake_wait(bundle_id: str, *, timeout_seconds: int, poll_interval_seconds: float) -> CommandBundleStatusResult:
            calls["wait"] = {
                "bundle_id": bundle_id,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
            return expected

        server.workspace_stage_commit_bundle = fake_stage
        server._workspace_wait_command_bundle_status_impl = fake_wait

        result = server.workspace_stage_commit_bundle_and_wait(
            cwd=".",
            paths=["README.md"],
            message="Update docs",
            timeout_seconds=10,
            poll_interval_seconds=1.5,
        )

        self.assertIs(result, expected)
        self.assertEqual(
            calls["stage"],
            {"cwd": ".", "paths": ["README.md"], "message": "Update docs", "precheck_commands": None},
        )
        self.assertEqual(
            calls["wait"],
            {"bundle_id": "cmd-test-commit", "timeout_seconds": 10, "poll_interval_seconds": 1.5},
        )

    def test_workspace_info_lists_wait_tools(self) -> None:
        tools = set(server.workspace_info().tools)

        self.assertIn("workspace_wait_command_bundle_status", tools)
        self.assertIn("workspace_stage_command_bundle_and_wait", tools)
        self.assertIn("workspace_stage_patch_bundle_and_wait", tools)
        self.assertIn("workspace_stage_action_bundle_and_wait", tools)
        self.assertIn("workspace_stage_commit_bundle_and_wait", tools)
        self.assertIn("workspace_list_tool_calls", tools)
        self.assertIn("workspace_tool_call_status", tools)
        self.assertNotIn("workspace_stage_command_bundle", tools)
        self.assertNotIn("workspace_stage_action_bundle", tools)
        self.assertNotIn("workspace_stage_patch_bundle", tools)
        self.assertNotIn("workspace_stage_commit_bundle", tools)

    def test_instrumented_function_creates_completed_tool_call_record(self) -> None:
        expected = self.status_result("cmd-test-journal")

        server.workspace_stage_command_bundle = lambda **kwargs: SimpleNamespace(bundle_id="cmd-test-journal")
        server._workspace_wait_command_bundle_status_impl = lambda *args, **kwargs: expected

        result = server.workspace_stage_command_bundle_and_wait(
            title="Run status",
            cwd=".",
            steps=[CommandBundleStep(name="status", argv=["git", "status"])],
        )

        self.assertIs(result, expected)
        records = tool_calls.list_tool_calls()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["tool_name"], "workspace_stage_command_bundle_and_wait")
        self.assertEqual(records[0]["status"], "completed")
        self.assertIsInstance(records[0]["duration_ms"], int)
        self.assertEqual(records[0]["result_summary"]["bundle_id"], "cmd-test-journal")

    def test_failed_instrumentation_records_failed_status(self) -> None:
        server.workspace_stage_command_bundle = lambda **kwargs: (_ for _ in ()).throw(ValueError("bad stage"))

        with self.assertRaises(ValueError):
            server.workspace_stage_command_bundle_and_wait(
                title="Bad stage",
                cwd=".",
                steps=[CommandBundleStep(name="status", argv=["git", "status"])],
            )

        records = tool_calls.list_tool_calls()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["tool_name"], "workspace_stage_command_bundle_and_wait")
        self.assertEqual(records[0]["status"], "failed")
        self.assertIsInstance(records[0]["duration_ms"], int)
        self.assertIn("ValueError", records[0]["error"])


class ToolCallJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_tool_call_dir = tool_calls.TOOL_CALL_DIR
        self.tmp = tempfile.TemporaryDirectory()
        tool_calls.TOOL_CALL_DIR = Path(self.tmp.name)

    def tearDown(self) -> None:
        tool_calls.TOOL_CALL_DIR = self.original_tool_call_dir
        self.tmp.cleanup()

    def test_tool_call_records_can_be_written_listed_and_read(self) -> None:
        call_id = tool_calls.write_started(
            "workspace_stage_patch_bundle_and_wait",
            {
                "cwd": ".",
                "patch": "secret patch body" * 100,
                "access_token": "secret-token",
                "header": "Authorization: Bearer secret-token",
                "url": "https://example.test/mcp?access_token=secret-token",
            },
        )
        tool_calls.write_completed(
            call_id,
            CommandBundleStatusResult(
                bundle_id="cmd-test",
                title="fake",
                cwd=".",
                status="pending",
                risk="medium",
                approval_required=True,
                command_count=2,
                created_at="",
                updated_at="",
            ),
        )

        listed = tool_calls.list_tool_calls()
        read = tool_calls.read_tool_call(call_id)

        self.assertEqual(len(listed), 1)
        self.assertEqual(read["call_id"], call_id)
        self.assertEqual(read["status"], "completed")
        self.assertEqual(read["args_summary"]["access_token"], "<redacted>")
        self.assertNotIn("secret-token", read["args_summary"]["header"])
        self.assertNotIn("secret-token", read["args_summary"]["url"])
        self.assertTrue(read["args_summary"]["patch"]["omitted"])
        self.assertEqual(read["result_summary"]["bundle_id"], "cmd-test")

    def test_list_skips_malformed_records_and_read_reports_malformed(self) -> None:
        call_id = tool_calls.write_started("workspace_command_bundle_status", {"bundle_id": "cmd-test"})
        (tool_calls.TOOL_CALL_DIR / "call-99999999-999999-bad.json").write_text("{bad json", encoding="utf-8")

        listed = tool_calls.list_tool_calls()

        self.assertEqual([record["call_id"] for record in listed], [call_id])
        with self.assertRaises(ValueError):
            tool_calls.read_tool_call("call-99999999-999999-bad")
