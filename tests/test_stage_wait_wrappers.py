from __future__ import annotations

from types import SimpleNamespace
import unittest

import server
from terminal_bridge.models import CommandBundleAction, CommandBundleStatusResult, CommandBundleStep


class StageAndWaitWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_stage_command = server.workspace_stage_command_bundle
        self.original_stage_patch = server.workspace_stage_patch_bundle
        self.original_stage_action = server.workspace_stage_action_bundle
        self.original_stage_commit = server.workspace_stage_commit_bundle
        self.original_wait = server.workspace_wait_command_bundle_status

    def tearDown(self) -> None:
        server.workspace_stage_command_bundle = self.original_stage_command
        server.workspace_stage_patch_bundle = self.original_stage_patch
        server.workspace_stage_action_bundle = self.original_stage_action
        server.workspace_stage_commit_bundle = self.original_stage_commit
        server.workspace_wait_command_bundle_status = self.original_wait

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
        server.workspace_wait_command_bundle_status = fake_wait

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
        server.workspace_wait_command_bundle_status = fake_wait

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
        server.workspace_wait_command_bundle_status = fake_wait

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
        server.workspace_wait_command_bundle_status = fake_wait

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
        self.assertNotIn("workspace_stage_command_bundle", tools)
        self.assertNotIn("workspace_stage_action_bundle", tools)
        self.assertNotIn("workspace_stage_patch_bundle", tools)
        self.assertNotIn("workspace_stage_commit_bundle", tools)
