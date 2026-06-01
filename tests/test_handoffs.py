from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import server
from scripts import command_bundle_runner as runner
from terminal_bridge import handoffs


class HandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.original_runner_dirs = {
            "PENDING_DIR": runner.PENDING_DIR,
            "APPLIED_DIR": runner.APPLIED_DIR,
            "REJECTED_DIR": runner.REJECTED_DIR,
            "FAILED_DIR": runner.FAILED_DIR,
        }
        self.original_handoff_dir = handoffs.HANDOFF_DIR

        runner.PENDING_DIR = root / "pending"
        runner.APPLIED_DIR = root / "applied"
        runner.REJECTED_DIR = root / "rejected"
        runner.FAILED_DIR = root / "failed"
        handoffs.HANDOFF_DIR = root / "handoffs"
        for directory in (runner.PENDING_DIR, runner.APPLIED_DIR, runner.REJECTED_DIR, runner.FAILED_DIR):
            directory.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        runner.PENDING_DIR = self.original_runner_dirs["PENDING_DIR"]
        runner.APPLIED_DIR = self.original_runner_dirs["APPLIED_DIR"]
        runner.REJECTED_DIR = self.original_runner_dirs["REJECTED_DIR"]
        runner.FAILED_DIR = self.original_runner_dirs["FAILED_DIR"]
        handoffs.HANDOFF_DIR = self.original_handoff_dir
        self.tmp.cleanup()

    def write_pending_record(self, bundle_id: str, record: dict[str, object]) -> Path:
        path = runner.PENDING_DIR / f"{bundle_id}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    def write_handoff_record(
        self,
        bundle_id: str,
        updated_at: str,
        metadata: dict[str, object] | None,
    ) -> None:
        handoffs.HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
        record: dict[str, object] = {
            "handoff_id": f"handoff-{bundle_id}",
            "bundle_id": bundle_id,
            "status": "applied",
            "ok": True,
            "risk": "low",
            "title": bundle_id,
            "cwd": ".",
            "next": "continue",
            "stdout_tail": "",
            "stderr_tail": "",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": updated_at,
        }
        if metadata is not None:
            record["metadata"] = metadata

        (handoffs.HANDOFF_DIR / f"handoff-{bundle_id}.json").write_text(json.dumps(record), encoding="utf-8")

    def base_record(self, bundle_id: str) -> dict[str, object]:
        return {
            "bundle_id": bundle_id,
            "title": "Test handoff",
            "cwd": ".",
            "status": "pending",
            "risk": "low",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "steps": [{"name": "one"}],
            "result": {
                "ok": True,
                "steps": [
                    {
                        "name": "one",
                        "exit_code": 0,
                        "stdout": "ok\naccess_token=secret-token-value",
                        "stderr": "",
                    }
                ],
            },
            "error": None,
            "metadata": {
                "task_id": None,
                "client_id": "default",
                "session_id": "default",
                "project_id": "sha256:test",
                "workspace_mode": "direct",
                "source_cwd": ".",
                "effective_cwd": ".",
            },
        }

    def test_applied_bundle_creates_handoff_record(self) -> None:
        bundle_id = "cmd-handoff-applied"
        record = self.base_record(bundle_id)
        path = self.write_pending_record(bundle_id, record)

        runner.move_bundle(path, record, "applied")

        handoff = handoffs.next_handoff()
        self.assertIsNotNone(handoff)
        assert handoff is not None
        self.assertEqual(handoff["bundle_id"], bundle_id)
        self.assertEqual(handoff["status"], "applied")
        self.assertEqual(handoff["ok"], True)
        self.assertEqual(handoff["next"], "continue")
        self.assertNotIn("secret-token-value", str(handoff))
        self.assertIn("[redacted]", handoff["stdout_tail"])
        self.assertEqual(handoff["metadata"]["project_id"], "sha256:test")

        by_bundle = handoffs.handoff_for_bundle(bundle_id)
        self.assertEqual(by_bundle, handoff)

    def test_failed_bundle_creates_handoff_record(self) -> None:
        bundle_id = "cmd-handoff-failed"
        record = self.base_record(bundle_id)
        record["result"] = {
            "ok": False,
            "steps": [{"name": "one", "exit_code": 1, "stdout": "", "stderr": "failed"}],
        }
        record["error"] = "One or more steps failed."
        path = self.write_pending_record(bundle_id, record)

        runner.move_bundle(path, record, "failed")

        handoff = handoffs.next_handoff()
        self.assertIsNotNone(handoff)
        assert handoff is not None
        self.assertEqual(handoff["bundle_id"], bundle_id)
        self.assertEqual(handoff["status"], "failed")
        self.assertEqual(handoff["ok"], False)
        self.assertEqual(handoff["next"], "fix_failure")
        self.assertIn("failed", handoff["stderr_tail"])

    def test_workspace_handoff_tools_return_compact_records(self) -> None:
        handoffs.write_handoff_from_bundle({**self.base_record("cmd-one"), "status": "applied"})
        handoffs.write_handoff_from_bundle({**self.base_record("cmd-two"), "status": "failed", "error": "failed"})

        next_handoff = server.workspace_next_handoff()
        listed = server.workspace_list_handoffs(limit=10)
        by_bundle = server.workspace_get_handoff_for_bundle("cmd-one")

        self.assertIsNotNone(next_handoff)
        assert next_handoff is not None
        self.assertIn(next_handoff.bundle_id, {"cmd-one", "cmd-two"})
        self.assertIsNotNone(by_bundle)
        assert by_bundle is not None
        self.assertEqual(by_bundle.bundle_id, "cmd-one")
        self.assertEqual(by_bundle.metadata["workspace_mode"], "direct")
        self.assertEqual(listed.count, 2)
        self.assertTrue(all(entry.handoff_id.startswith("handoff-") for entry in listed.entries))

    def test_workspace_list_handoffs_filters_metadata_with_and_semantics(self) -> None:
        self.write_handoff_record("cmd-old", "2026-06-02T00:00:04+00:00", None)
        self.write_handoff_record(
            "cmd-a",
            "2026-06-02T00:00:03+00:00",
            {
                "task_id": "task-1",
                "client_id": "client-a",
                "session_id": "session-a",
                "project_id": "project-alpha",
                "workspace_mode": "direct",
            },
        )
        self.write_handoff_record(
            "cmd-b",
            "2026-06-02T00:00:02+00:00",
            {
                "task_id": "task-1",
                "client_id": "client-a",
                "session_id": "session-b",
                "project_id": "project-alpha",
                "workspace_mode": "task-workspace",
            },
        )
        self.write_handoff_record(
            "cmd-c",
            "2026-06-02T00:00:01+00:00",
            {
                "task_id": "task-2",
                "client_id": "client-b",
                "session_id": "session-a",
                "project_id": "project-beta",
                "workspace_mode": "direct",
            },
        )

        def bundle_ids(**filters: str | None) -> list[str]:
            result = server.workspace_list_handoffs(limit=10, **filters)
            return [entry.bundle_id for entry in result.entries]

        self.assertEqual(bundle_ids(), ["cmd-old", "cmd-a", "cmd-b", "cmd-c"])
        self.assertEqual(bundle_ids(client_id="client-a"), ["cmd-a", "cmd-b"])
        self.assertEqual(bundle_ids(session_id="session-a"), ["cmd-a", "cmd-c"])
        self.assertEqual(bundle_ids(project_id="project-alpha"), ["cmd-a", "cmd-b"])
        self.assertEqual(bundle_ids(workspace_mode="task-workspace"), ["cmd-b"])
        self.assertEqual(bundle_ids(task_id="task-1"), ["cmd-a", "cmd-b"])
        self.assertEqual(bundle_ids(task_id="task-1", session_id="session-b", workspace_mode="task-workspace"), ["cmd-b"])
        self.assertEqual(bundle_ids(client_id="default"), [])
        self.assertEqual(bundle_ids(client_id=" "), ["cmd-old", "cmd-a", "cmd-b", "cmd-c"])

    def test_old_handoff_without_metadata_still_converts(self) -> None:
        handoffs.HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
        path = handoffs.HANDOFF_DIR / "handoff-cmd-old.json"
        path.write_text(
            json.dumps(
                {
                    "handoff_id": "handoff-cmd-old",
                    "bundle_id": "cmd-old",
                    "status": "applied",
                    "ok": True,
                    "risk": "low",
                    "title": "Old handoff",
                    "cwd": ".",
                    "next": "continue",
                    "stdout_tail": "",
                    "stderr_tail": "",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )

        handoff = handoffs.handoff_for_bundle("cmd-old")
        tool_result = server.workspace_get_handoff_for_bundle("cmd-old")

        self.assertIsNotNone(handoff)
        assert handoff is not None
        self.assertEqual(handoff["metadata"], {})
        self.assertIsNotNone(tool_result)
        assert tool_result is not None
        self.assertEqual(tool_result.metadata, {})

    def test_handoff_for_bundle_returns_none_when_missing(self) -> None:
        self.assertIsNone(handoffs.handoff_for_bundle("cmd-missing"))
        self.assertIsNone(server.workspace_get_handoff_for_bundle("cmd-missing"))

    def test_handoff_for_bundle_rejects_invalid_bundle_id(self) -> None:
        with self.assertRaises(ValueError):
            handoffs.handoff_for_bundle("bad-id")
        with self.assertRaises(ValueError):
            server.workspace_get_handoff_for_bundle("../cmd-bad")

    def test_workspace_info_lists_handoff_tools_and_hides_primitives(self) -> None:
        tools = set(server.workspace_info().tools)

        self.assertIn("workspace_next_handoff", tools)
        self.assertIn("workspace_get_handoff_for_bundle", tools)
        self.assertIn("workspace_list_handoffs", tools)
        self.assertFalse(
            {
                "workspace_stage_command_bundle",
                "workspace_stage_action_bundle",
                "workspace_stage_patch_bundle",
                "workspace_stage_commit_bundle",
            }.intersection(tools)
        )
