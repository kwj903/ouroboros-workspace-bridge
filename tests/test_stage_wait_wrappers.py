from __future__ import annotations

import inspect
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

import server
from terminal_bridge.bundles import _default_command_bundle_metadata
from terminal_bridge import tool_calls
from terminal_bridge.mcp_tools.bundles import command_bundle_status_from_record, list_command_bundles
from terminal_bridge.models import (
    CommandBundleAction,
    CommandBundleListResult,
    CommandBundleStageResult,
    CommandBundleStatusResult,
    CommandBundleStep,
)


class StageAndWaitWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_stage_command = server.workspace_stage_command_bundle
        self.original_stage_patch = server.workspace_stage_patch_bundle
        self.original_stage_action = server.workspace_stage_action_bundle
        self.original_stage_commit = server.workspace_stage_commit_bundle
        self.original_submit_command_impl = server._workspace_submit_command_bundle_impl
        self.original_submit_patch_impl = server._workspace_submit_patch_bundle_impl
        self.original_submit_action_impl = server._workspace_submit_action_bundle_impl
        self.original_submit_commit_impl = server._workspace_submit_commit_bundle_impl
        self.original_stage_command_wait_impl = server._workspace_stage_command_bundle_and_wait_impl
        self.original_stage_patch_wait_impl = server._workspace_stage_patch_bundle_and_wait_impl
        self.original_stage_action_wait_impl = server._workspace_stage_action_bundle_and_wait_impl
        self.original_stage_commit_wait_impl = server._workspace_stage_commit_bundle_and_wait_impl
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
        server._workspace_submit_command_bundle_impl = self.original_submit_command_impl
        server._workspace_submit_patch_bundle_impl = self.original_submit_patch_impl
        server._workspace_submit_action_bundle_impl = self.original_submit_action_impl
        server._workspace_submit_commit_bundle_impl = self.original_submit_commit_impl
        server._workspace_stage_command_bundle_and_wait_impl = self.original_stage_command_wait_impl
        server._workspace_stage_patch_bundle_and_wait_impl = self.original_stage_patch_wait_impl
        server._workspace_stage_action_bundle_and_wait_impl = self.original_stage_action_wait_impl
        server._workspace_stage_commit_bundle_and_wait_impl = self.original_stage_commit_wait_impl
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

    def stage_result(self, bundle_id: str) -> CommandBundleStageResult:
        return CommandBundleStageResult(
            bundle_id=bundle_id,
            title="fake",
            cwd=".",
            status="pending",
            risk="low",
            approval_required=True,
            path=f"/tmp/{bundle_id}.json",
            review_hint=f"uv run python scripts/command_bundle_runner.py preview {bundle_id}",
            command_count=1,
        )

    def test_command_bundle_and_wait_calls_stage_then_wait(self) -> None:
        calls: dict[str, object] = {}
        expected = self.status_result("cmd-test-command")
        steps = [CommandBundleStep(name="status", argv=["git", "status"])]

        def fake_submit(title: str, cwd: str, steps: list[CommandBundleStep], *_extra: object) -> CommandBundleStageResult:
            calls["submit"] = {"title": title, "cwd": cwd, "steps": steps}
            return self.stage_result("cmd-test-command")

        def fake_wait(bundle_id: str, *, timeout_seconds: int, poll_interval_seconds: float) -> CommandBundleStatusResult:
            calls["wait"] = {
                "bundle_id": bundle_id,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
            return expected

        server._workspace_submit_command_bundle_impl = fake_submit
        server._workspace_wait_command_bundle_status_impl = fake_wait

        result = server.workspace_stage_command_bundle_and_wait(
            title="Run status",
            cwd=".",
            steps=steps,
            timeout_seconds=7,
            poll_interval_seconds=0.5,
        )

        self.assertIs(result, expected)
        self.assertEqual(calls["submit"], {"title": "Run status", "cwd": ".", "steps": steps})
        self.assertEqual(
            calls["wait"],
            {"bundle_id": "cmd-test-command", "timeout_seconds": 7, "poll_interval_seconds": 0.5},
        )

    def test_patch_bundle_and_wait_calls_stage_then_wait(self) -> None:
        calls: dict[str, object] = {}
        expected = self.status_result("cmd-test-patch")

        def fake_submit(title: str, cwd: str, patch: str | None, patch_ref: str | None, *_extra: object) -> CommandBundleStageResult:
            calls["submit"] = {"title": title, "cwd": cwd, "patch": patch, "patch_ref": patch_ref}
            return self.stage_result("cmd-test-patch")

        def fake_wait(bundle_id: str, *, timeout_seconds: int, poll_interval_seconds: float) -> CommandBundleStatusResult:
            calls["wait"] = {
                "bundle_id": bundle_id,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
            return expected

        server._workspace_submit_patch_bundle_impl = fake_submit
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
            calls["submit"],
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

        def fake_submit(title: str, cwd: str, actions: list[CommandBundleAction], *_extra: object) -> CommandBundleStageResult:
            calls["submit"] = {"title": title, "cwd": cwd, "actions": actions}
            return self.stage_result("cmd-test-action")

        def fake_wait(bundle_id: str, *, timeout_seconds: int, poll_interval_seconds: float) -> CommandBundleStatusResult:
            calls["wait"] = {
                "bundle_id": bundle_id,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
            return expected

        server._workspace_submit_action_bundle_impl = fake_submit
        server._workspace_wait_command_bundle_status_impl = fake_wait

        result = server.workspace_stage_action_bundle_and_wait(
            title="Write file",
            cwd=".",
            actions=actions,
            timeout_seconds=9,
            poll_interval_seconds=1.25,
        )

        self.assertIs(result, expected)
        self.assertEqual(calls["submit"], {"title": "Write file", "cwd": ".", "actions": actions})
        self.assertEqual(
            calls["wait"],
            {"bundle_id": "cmd-test-action", "timeout_seconds": 9, "poll_interval_seconds": 1.25},
        )

    def test_commit_bundle_and_wait_uses_internal_default_prechecks(self) -> None:
        calls: dict[str, object] = {}
        expected = self.status_result("cmd-test-commit")

        def fake_submit(cwd: str, paths: list[str], message: str, *_extra: object) -> CommandBundleStageResult:
            calls["submit"] = {"cwd": cwd, "paths": paths, "message": message}
            return self.stage_result("cmd-test-commit")

        def fake_wait(bundle_id: str, *, timeout_seconds: int, poll_interval_seconds: float) -> CommandBundleStatusResult:
            calls["wait"] = {
                "bundle_id": bundle_id,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
            return expected

        server._workspace_submit_commit_bundle_impl = fake_submit
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
            calls["submit"],
            {"cwd": ".", "paths": ["README.md"], "message": "Update docs"},
        )
        self.assertEqual(
            calls["wait"],
            {"bundle_id": "cmd-test-commit", "timeout_seconds": 10, "poll_interval_seconds": 1.5},
        )

    def test_workspace_info_lists_proposal_tools(self) -> None:
        tools = set(server.workspace_info().tools)

        self.assertIn("workspace_wait_command_bundle_status", tools)
        self.assertIn("workspace_propose_command_and_wait", tools)
        self.assertIn("workspace_propose_file_write_and_wait", tools)
        self.assertIn("workspace_propose_file_replace_and_wait", tools)
        self.assertIn("workspace_propose_patch_and_wait", tools)
        self.assertIn("workspace_propose_git_commit_and_wait", tools)
        self.assertIn("workspace_propose_git_push_and_wait", tools)
        self.assertIn("workspace_propose_task_validation_command_and_wait", tools)
        self.assertIn("workspace_list_tool_calls", tools)
        self.assertIn("workspace_tool_call_status", tools)
        self.assertNotIn("workspace_stage_command_bundle_and_wait", tools)
        self.assertNotIn("workspace_stage_patch_bundle_and_wait", tools)
        self.assertNotIn("workspace_stage_action_bundle_and_wait", tools)
        self.assertNotIn("workspace_stage_commit_bundle_and_wait", tools)
        self.assertNotIn("workspace_submit_command_bundle", tools)
        self.assertNotIn("workspace_submit_patch_bundle", tools)
        self.assertNotIn("workspace_submit_action_bundle", tools)
        self.assertNotIn("workspace_submit_commit_bundle", tools)
        self.assertNotIn("workspace_stage_command_bundle", tools)
        self.assertNotIn("workspace_stage_action_bundle", tools)
        self.assertNotIn("workspace_stage_patch_bundle", tools)
        self.assertNotIn("workspace_stage_commit_bundle", tools)

    def test_public_proposal_wrappers_accept_metadata_inputs(self) -> None:
        wrappers = [
            server.workspace_propose_command_and_wait,
            server.workspace_propose_file_write_and_wait,
            server.workspace_propose_file_replace_and_wait,
            server.workspace_propose_patch_and_wait,
            server.workspace_propose_git_commit_and_wait,
            server.workspace_propose_git_push_and_wait,
        ]
        metadata_fields = {"task_id", "client_id", "session_id", "project_id", "workspace_mode"}

        for wrapper in wrappers:
            with self.subTest(wrapper=wrapper.__name__):
                parameters = inspect.signature(wrapper).parameters
                self.assertTrue(metadata_fields.issubset(parameters))
                for field in metadata_fields:
                    self.assertIsNone(parameters[field].default)

    def test_propose_command_wraps_one_command_step(self) -> None:
        calls: dict[str, object] = {}
        expected = self.status_result("cmd-test-propose-command")

        def fake_stage(title: str, cwd: str, steps: list[CommandBundleStep], timeout_seconds: int, poll_interval_seconds: float, *_extra: object) -> CommandBundleStatusResult:
            calls["stage"] = {
                "title": title,
                "cwd": cwd,
                "steps": steps,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
            return expected

        server._workspace_stage_command_bundle_and_wait_impl = fake_stage

        result = server.workspace_propose_command_and_wait(
            title="Run status",
            cwd=".",
            argv=["git", "status", "--short"],
            command_timeout_seconds=12,
            timeout_seconds=7,
            poll_interval_seconds=0.5,
        )

        self.assertIs(result, expected)
        steps = calls["stage"]["steps"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].argv, ["git", "status", "--short"])
        self.assertEqual(steps[0].timeout_seconds, 12)
        self.assertEqual(calls["stage"]["title"], "Run status")
        self.assertEqual(calls["stage"]["timeout_seconds"], 7)

    def test_propose_file_replace_wraps_one_action(self) -> None:
        calls: dict[str, object] = {}
        expected = self.status_result("cmd-test-propose-replace")

        def fake_stage(title: str, cwd: str, actions: list[CommandBundleAction], timeout_seconds: int, poll_interval_seconds: float, *_extra: object) -> CommandBundleStatusResult:
            calls["stage"] = {"title": title, "cwd": cwd, "actions": actions}
            return expected

        server._workspace_stage_action_bundle_and_wait_impl = fake_stage

        result = server.workspace_propose_file_replace_and_wait(
            title="Replace text",
            cwd=".",
            path="README.md",
            old_text="old",
            new_text="new",
        )

        self.assertIs(result, expected)
        actions = calls["stage"]["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].type, "replace_text")
        self.assertEqual(actions[0].path, "README.md")
        self.assertEqual(actions[0].old_text, "old")
        self.assertEqual(actions[0].new_text, "new")

    def test_propose_file_write_wraps_one_action(self) -> None:
        calls: dict[str, object] = {}
        expected = self.status_result("cmd-test-propose-write")

        def fake_stage(title: str, cwd: str, actions: list[CommandBundleAction], timeout_seconds: int, poll_interval_seconds: float, *_extra: object) -> CommandBundleStatusResult:
            calls["stage"] = {"title": title, "cwd": cwd, "actions": actions}
            return expected

        server._workspace_stage_action_bundle_and_wait_impl = fake_stage

        result = server.workspace_propose_file_write_and_wait(
            title="Write file",
            cwd=".",
            path="notes.txt",
            content="hello",
            overwrite=True,
        )

        self.assertIs(result, expected)
        actions = calls["stage"]["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].type, "write_file")
        self.assertEqual(actions[0].path, "notes.txt")
        self.assertEqual(actions[0].content, "hello")
        self.assertTrue(actions[0].overwrite)

    def test_propose_git_push_wraps_one_command_step(self) -> None:
        calls: dict[str, object] = {}
        expected = self.status_result("cmd-test-propose-push")

        def fake_stage(title: str, cwd: str, steps: list[CommandBundleStep], timeout_seconds: int, poll_interval_seconds: float, *_extra: object) -> CommandBundleStatusResult:
            calls["stage"] = {"title": title, "cwd": cwd, "steps": steps}
            return expected

        server._workspace_stage_command_bundle_and_wait_impl = fake_stage

        result = server.workspace_propose_git_push_and_wait(cwd=".", remote="origin", branch="main")

        self.assertIs(result, expected)
        steps = calls["stage"]["steps"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(calls["stage"]["title"], "Push origin main")
        self.assertEqual(steps[0].argv, ["git", "push", "origin", "main"])

    def test_proposal_wrappers_forward_metadata_to_stage_callbacks(self) -> None:
        captured: list[tuple[str, dict[str, object] | None]] = []
        expected = self.status_result("cmd-test-metadata")
        metadata_args = {
            "task_id": " task-1 ",
            "client_id": " client-a ",
            "session_id": " session-a ",
            "project_id": " project-alpha ",
            "workspace_mode": " direct ",
        }
        expected_metadata = {
            "task_id": "task-1",
            "client_id": "client-a",
            "session_id": "session-a",
            "project_id": "project-alpha",
            "workspace_mode": "direct",
        }

        def fake_command_stage(
            title: str,
            cwd: str,
            steps: list[CommandBundleStep],
            timeout_seconds: int,
            poll_interval_seconds: float,
            metadata: dict[str, object] | None = None,
        ) -> CommandBundleStatusResult:
            captured.append((title, metadata))
            return expected

        def fake_action_stage(
            title: str,
            cwd: str,
            actions: list[CommandBundleAction],
            timeout_seconds: int,
            poll_interval_seconds: float,
            metadata: dict[str, object] | None = None,
        ) -> CommandBundleStatusResult:
            captured.append((title, metadata))
            return expected

        def fake_patch_stage(
            title: str,
            cwd: str,
            patch: str | None,
            patch_ref: str | None,
            timeout_seconds: int,
            poll_interval_seconds: float,
            metadata: dict[str, object] | None = None,
        ) -> CommandBundleStatusResult:
            captured.append((title, metadata))
            return expected

        def fake_commit_stage(
            cwd: str,
            paths: list[str],
            message: str,
            timeout_seconds: int,
            poll_interval_seconds: float,
            metadata: dict[str, object] | None = None,
        ) -> CommandBundleStatusResult:
            captured.append(("commit", metadata))
            return expected

        server._workspace_stage_command_bundle_and_wait_impl = fake_command_stage
        server._workspace_stage_action_bundle_and_wait_impl = fake_action_stage
        server._workspace_stage_patch_bundle_and_wait_impl = fake_patch_stage
        server._workspace_stage_commit_bundle_and_wait_impl = fake_commit_stage

        calls = [
            server.workspace_propose_command_and_wait(
                title="Run status",
                cwd=".",
                argv=["git", "status"],
                **metadata_args,
            ),
            server.workspace_propose_file_write_and_wait(
                title="Write file",
                cwd=".",
                path="notes.txt",
                content="hello",
                overwrite=True,
                **metadata_args,
            ),
            server.workspace_propose_file_replace_and_wait(
                title="Replace text",
                cwd=".",
                path="README.md",
                old_text="old",
                new_text="new",
                **metadata_args,
            ),
            server.workspace_propose_patch_and_wait(
                title="Apply patch",
                cwd=".",
                patch="diff --git a/file.txt b/file.txt",
                **metadata_args,
            ),
            server.workspace_propose_git_commit_and_wait(
                cwd=".",
                paths=["README.md"],
                message="Test metadata",
                **metadata_args,
            ),
            server.workspace_propose_git_push_and_wait(
                cwd=".",
                remote="origin",
                branch="main",
                **metadata_args,
            ),
        ]

        self.assertEqual(calls, [expected] * 6)
        self.assertEqual(len(captured), 6)
        self.assertEqual([metadata for _, metadata in captured], [expected_metadata] * 6)

    def test_proposal_metadata_input_ignores_blank_strings(self) -> None:
        self.assertIsNone(
            server._proposal_metadata_input(
                task_id=" ",
                client_id="\t",
                session_id="\n",
                project_id="  ",
                workspace_mode=" ",
            )
        )

    def test_proposal_metadata_input_accepts_direct_workspace_mode(self) -> None:
        self.assertEqual(
            server._proposal_metadata_input(workspace_mode=" direct "),
            {"workspace_mode": "direct"},
        )

    def test_proposal_metadata_input_normalizes_scope_fields(self) -> None:
        self.assertEqual(
            server._proposal_metadata_input(
                task_id=" task-1 ",
                client_id=" client-a ",
                session_id=" ",
                project_id="project-alpha",
                workspace_mode="direct",
            ),
            {
                "task_id": "task-1",
                "client_id": "client-a",
                "project_id": "project-alpha",
                "workspace_mode": "direct",
            },
        )

    def test_proposal_metadata_input_accepts_task_workspace_with_task_id(self) -> None:
        self.assertEqual(
            server._proposal_metadata_input(task_id=" task-1 ", workspace_mode=" task-workspace "),
            {"task_id": "task-1", "workspace_mode": "task-workspace"},
        )

    def test_proposal_metadata_input_rejects_task_workspace_without_task_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires task_id"):
            server._proposal_metadata_input(workspace_mode="task-workspace")

    def test_proposal_metadata_input_rejects_unknown_workspace_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "supports 'direct' or 'task-workspace'"):
            server._proposal_metadata_input(task_id="task-1", workspace_mode="isolated")

    def test_propose_git_push_rejects_flag_like_remote(self) -> None:
        with self.assertRaises(ValueError):
            server.workspace_propose_git_push_and_wait(cwd=".", remote="--force", branch="main")

    def test_instrumented_function_creates_completed_tool_call_record(self) -> None:
        expected = self.status_result("cmd-test-journal")

        server._workspace_submit_command_bundle_impl = lambda *args, **kwargs: self.stage_result("cmd-test-journal")
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
        server._workspace_submit_command_bundle_impl = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad submit"))

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


class CommandBundleMetadataTests(unittest.TestCase):
    def test_status_from_old_record_without_metadata_uses_defaults(self) -> None:
        record: dict[str, object] = {
            "bundle_id": "cmd-old",
            "title": "Old bundle",
            "cwd": "project",
            "status": "applied",
            "risk": "low",
            "approval_required": True,
            "created_at": "2026-06-02T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:01+00:00",
            "steps": [{"type": "command"}],
        }

        result = command_bundle_status_from_record(record, "cmd-old")

        self.assertEqual(result.metadata, _default_command_bundle_metadata("project"))
        self.assertEqual(result.metadata["client_id"], "default")
        self.assertEqual(result.metadata["workspace_mode"], "direct")

    def test_list_command_bundles_exposes_metadata_and_handles_old_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            old_record: dict[str, object] = {
                "bundle_id": "cmd-old",
                "title": "Old bundle",
                "cwd": "legacy",
                "status": "pending",
                "risk": "low",
                "updated_at": "2026-06-02T00:00:01+00:00",
                "steps": [],
            }
            new_record: dict[str, object] = {
                "bundle_id": "cmd-new",
                "title": "New bundle",
                "cwd": "project",
                "status": "pending",
                "risk": "medium",
                "updated_at": "2026-06-02T00:00:02+00:00",
                "steps": [{"type": "command"}],
                "metadata": {
                    **_default_command_bundle_metadata("project"),
                    "task_id": "task-123",
                    "client_id": "client-a",
                },
            }
            (directory / "cmd-old.json").write_text(json.dumps(old_record), encoding="utf-8")
            (directory / "cmd-new.json").write_text(json.dumps(new_record), encoding="utf-8")

            result = list_command_bundles(
                lambda: [directory],
                lambda path: json.loads(path.read_text(encoding="utf-8")),
                limit=10,
            )

        entries = {entry.bundle_id: entry for entry in result.entries}
        self.assertEqual(result.count, 2)
        self.assertEqual(entries["cmd-old"].metadata, _default_command_bundle_metadata("legacy"))
        self.assertEqual(entries["cmd-new"].metadata["task_id"], "task-123")
        self.assertEqual(entries["cmd-new"].metadata["client_id"], "client-a")

    def test_list_command_bundles_filters_metadata_with_and_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            records = [
                {
                    "bundle_id": "cmd-old",
                    "title": "Old bundle",
                    "cwd": "legacy",
                    "status": "pending",
                    "risk": "low",
                    "updated_at": "2026-06-02T00:00:04+00:00",
                    "steps": [],
                },
                {
                    "bundle_id": "cmd-a",
                    "title": "A",
                    "cwd": "project",
                    "status": "pending",
                    "risk": "low",
                    "updated_at": "2026-06-02T00:00:03+00:00",
                    "steps": [],
                    "metadata": {
                        "task_id": "task-1",
                        "client_id": "client-a",
                        "session_id": "session-a",
                        "project_id": "project-alpha",
                        "workspace_mode": "direct",
                    },
                },
                {
                    "bundle_id": "cmd-b",
                    "title": "B",
                    "cwd": "project",
                    "status": "pending",
                    "risk": "low",
                    "updated_at": "2026-06-02T00:00:02+00:00",
                    "steps": [],
                    "metadata": {
                        "task_id": "task-1",
                        "client_id": "client-a",
                        "session_id": "session-b",
                        "project_id": "project-alpha",
                        "workspace_mode": "task-workspace",
                    },
                },
                {
                    "bundle_id": "cmd-c",
                    "title": "C",
                    "cwd": "project",
                    "status": "pending",
                    "risk": "low",
                    "updated_at": "2026-06-02T00:00:01+00:00",
                    "steps": [],
                    "metadata": {
                        "task_id": "task-2",
                        "client_id": "client-b",
                        "session_id": "session-a",
                        "project_id": "project-beta",
                        "workspace_mode": "direct",
                    },
                },
            ]
            for record in records:
                (directory / f"{record['bundle_id']}.json").write_text(json.dumps(record), encoding="utf-8")

            def run_list(**filters: str | None) -> list[str]:
                result = list_command_bundles(
                    lambda: [directory],
                    lambda path: json.loads(path.read_text(encoding="utf-8")),
                    limit=10,
                    **filters,
                )
                return [entry.bundle_id for entry in result.entries]

            legacy_project_id = str(_default_command_bundle_metadata("legacy")["project_id"])

            self.assertEqual(run_list(), ["cmd-old", "cmd-a", "cmd-b", "cmd-c"])
            self.assertEqual(run_list(client_id="client-a"), ["cmd-a", "cmd-b"])
            self.assertEqual(run_list(session_id="session-a"), ["cmd-a", "cmd-c"])
            self.assertEqual(run_list(project_id="project-alpha"), ["cmd-a", "cmd-b"])
            self.assertEqual(run_list(workspace_mode="task-workspace"), ["cmd-b"])
            self.assertEqual(run_list(task_id="task-1"), ["cmd-a", "cmd-b"])
            self.assertEqual(run_list(task_id="task-1", session_id="session-b", workspace_mode="task-workspace"), ["cmd-b"])
            self.assertEqual(run_list(client_id="default", project_id=legacy_project_id), ["cmd-old"])
            self.assertEqual(run_list(client_id=""), ["cmd-old", "cmd-a", "cmd-b", "cmd-c"])

    def test_workspace_list_command_bundles_forwards_metadata_filters(self) -> None:
        original_list_command_bundles = server._bundle_list_command_bundles
        captured: dict[str, object] = {}

        def fake_list_command_bundles(
            command_bundle_dirs: object,
            read_json: object,
            limit: int,
            *,
            task_id: str | None = None,
            client_id: str | None = None,
            session_id: str | None = None,
            project_id: str | None = None,
            workspace_mode: str | None = None,
        ) -> CommandBundleListResult:
            captured.update(
                {
                    "limit": limit,
                    "task_id": task_id,
                    "client_id": client_id,
                    "session_id": session_id,
                    "project_id": project_id,
                    "workspace_mode": workspace_mode,
                }
            )
            return CommandBundleListResult(entries=[], count=0)

        server._bundle_list_command_bundles = fake_list_command_bundles
        try:
            result = server.workspace_list_command_bundles(
                limit=3,
                task_id="task-1",
                client_id="client-a",
                session_id="session-a",
                project_id="project-alpha",
                workspace_mode="direct",
            )
        finally:
            server._bundle_list_command_bundles = original_list_command_bundles

        self.assertEqual(result.count, 0)
        self.assertEqual(
            captured,
            {
                "limit": 3,
                "task_id": "task-1",
                "client_id": "client-a",
                "session_id": "session-a",
                "project_id": "project-alpha",
                "workspace_mode": "direct",
            },
        )
