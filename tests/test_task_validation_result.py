from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import server
from terminal_bridge import task_validation_result
from terminal_bridge.models import TaskValidationResultHintResult


class TaskValidationResultHintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime_root = self.root / "runtime"
        self.workspace_root = self.root / "workspace"
        self.workspace_root.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_bundle(self, status: str, bundle_id: str, record: dict[str, object]) -> Path:
        path = self.runtime_root / "command_bundles" / status / f"{bundle_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "bundle_id": bundle_id,
            "title": "Validate merged task: task-a",
            "cwd": "project",
            "status": status,
            "risk": "medium",
            "approval_required": True,
            "created_at": "2026-06-03T00:00:00+00:00",
            "updated_at": "2026-06-03T00:00:00+00:00",
            "steps": [
                {
                    "type": "command",
                    "name": "Run source validation",
                    "argv": ["uv", "run", "python", "-m", "unittest"],
                    "timeout_seconds": 300,
                }
            ],
            "metadata": {
                "task_id": "task-a",
                "project_id": "project-alpha",
                "workspace_mode": "direct",
                "source_cwd": "project",
                "effective_cwd": "project",
                "validation_command": ["uv", "run", "python", "-m", "unittest"],
                "validation_command_name": "Run source validation",
                "merge_queue_status": "merged",
            },
            "result": None,
            "error": None,
        }
        payload.update(record)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_hint_from_bundle_id_infers_passed_candidate(self) -> None:
        self.write_bundle(
            "applied",
            "cmd-validation-pass",
            {
                "result": {
                    "cwd": "project",
                    "ok": True,
                    "steps": [
                        {
                            "type": "command",
                            "name": "Run source validation",
                            "argv": ["uv", "run", "python", "-m", "unittest"],
                            "exit_code": 0,
                            "stdout": "all tests passed\n",
                            "stderr": "",
                            "truncated": False,
                        }
                    ],
                }
            },
        )

        hint = task_validation_result.task_validation_result_hint(
            bundle_id="cmd-validation-pass",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertEqual(hint["task_id"], "task-a")
        self.assertEqual(hint["project_id"], "project-alpha")
        self.assertEqual(hint["source_cwd"], "project")
        self.assertEqual(hint["bundle_id"], "cmd-validation-pass")
        self.assertEqual(hint["bundle_status"], "applied")
        self.assertEqual(hint["command_argv"], ["uv", "run", "python", "-m", "unittest"])
        self.assertEqual(hint["command_summary"], "uv run python -m unittest")
        self.assertEqual(hint["exit_code"], 0)
        self.assertEqual(hint["stdout_preview"], "all tests passed\n")
        self.assertEqual(hint["stderr_preview"], "")
        self.assertEqual(hint["inferred_status"], "passed")
        self.assertEqual(hint["recommended_next_action"], "record_passed_validation")
        self.assertEqual(hint["suggested_record_input"]["validation_status"], "passed")
        self.assertEqual(
            hint["suggested_record_input"]["validation_commands"],
            ["uv run python -m unittest"],
        )

    def test_hint_from_task_id_finds_latest_validation_bundle_and_infers_failed_candidate(self) -> None:
        self.write_bundle(
            "applied",
            "cmd-validation-old",
            {
                "updated_at": "2026-06-03T00:00:00+00:00",
                "result": {
                    "cwd": "project",
                    "ok": True,
                    "steps": [
                        {
                            "type": "command",
                            "name": "Run source validation",
                            "argv": ["uv", "run", "python", "-m", "unittest"],
                            "exit_code": 0,
                            "stdout": "old pass\n",
                            "stderr": "",
                            "truncated": False,
                        }
                    ],
                },
            },
        )
        self.write_bundle(
            "failed",
            "cmd-validation-new",
            {
                "updated_at": "2026-06-03T01:00:00+00:00",
                "result": {
                    "cwd": "project",
                    "ok": False,
                    "steps": [
                        {
                            "type": "command",
                            "name": "Run source validation",
                            "argv": ["uv", "run", "python", "-m", "unittest"],
                            "exit_code": 2,
                            "stdout": "one test failed\n",
                            "stderr": "AssertionError\n",
                            "truncated": False,
                        }
                    ],
                },
                "error": "command exited with code 2",
            },
        )

        hint = task_validation_result.task_validation_result_hint(
            task_id="task-a",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertEqual(hint["bundle_id"], "cmd-validation-new")
        self.assertEqual(hint["bundle_status"], "failed")
        self.assertEqual(hint["exit_code"], 2)
        self.assertEqual(hint["stderr_preview"], "AssertionError\n")
        self.assertEqual(hint["inferred_status"], "failed")
        self.assertEqual(hint["recommended_next_action"], "record_failed_validation")
        self.assertEqual(hint["suggested_record_input"]["validation_status"], "failed")

    def test_pending_bundle_without_result_stays_unknown(self) -> None:
        self.write_bundle("pending", "cmd-validation-pending", {"updated_at": "2026-06-03T02:00:00+00:00"})

        hint = task_validation_result.task_validation_result_hint(
            task_id="task-a",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertEqual(hint["bundle_id"], "cmd-validation-pending")
        self.assertEqual(hint["bundle_status"], "pending")
        self.assertIsNone(hint["exit_code"])
        self.assertEqual(hint["inferred_status"], "unknown")
        self.assertEqual(hint["recommended_next_action"], "wait_for_validation_command_bundle")
        self.assertEqual(hint["suggested_record_input"]["validation_status"], "pending")

    def test_server_validation_result_hint_wrapper_is_read_only(self) -> None:
        original_record = server._record_tool_call
        original_hint = server._task_validation_result_hint
        calls: list[tuple[str, dict[str, object]]] = []

        def call_through(tool_name: str, args: dict[str, object], action: object) -> object:
            calls.append((tool_name, args))
            return action()

        def fake_hint(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append(("hint", {"args": args, "kwargs": kwargs}))
            return {
                "task_id": "task-a",
                "project_id": "project-alpha",
                "source_cwd": "project",
                "bundle_id": "cmd-validation-pass",
                "bundle_status": "applied",
                "command_argv": ["uv", "run", "python", "-m", "unittest"],
                "command_summary": "uv run python -m unittest",
                "exit_code": 0,
                "stdout_preview": "all tests passed\n",
                "stderr_preview": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
                "result_available": True,
                "inferred_status": "passed",
                "recommended_next_action": "record_passed_validation",
                "suggested_record_input": {
                    "task_id": "task-a",
                    "cwd": "project",
                    "project_id": "project-alpha",
                    "validation_status": "passed",
                    "validation_commands": ["uv run python -m unittest"],
                    "validation_summary": "Validation command bundle cmd-validation-pass exited with code 0.",
                    "validated_by": None,
                    "client_id": None,
                    "session_id": None,
                },
            }

        server._record_tool_call = call_through
        server._task_validation_result_hint = fake_hint
        try:
            result = server.workspace_task_validation_result_hint(
                task_id="task-a",
                cwd="project",
                project_id="project-alpha",
                bundle_id="cmd-validation-pass",
            )
        finally:
            server._record_tool_call = original_record
            server._task_validation_result_hint = original_hint

        self.assertIsInstance(result, TaskValidationResultHintResult)
        self.assertEqual(calls[0][0], "workspace_task_validation_result_hint")
        self.assertEqual(calls[1][0], "hint")
        self.assertEqual(calls[1][1]["kwargs"]["bundle_id"], "cmd-validation-pass")
        self.assertEqual(result.inferred_status, "passed")
        self.assertEqual(result.suggested_record_input.validation_status, "passed")


if __name__ == "__main__":
    unittest.main()
