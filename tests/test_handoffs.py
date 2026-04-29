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

        self.assertIsNotNone(next_handoff)
        assert next_handoff is not None
        self.assertIn(next_handoff.bundle_id, {"cmd-one", "cmd-two"})
        self.assertEqual(listed.count, 2)
        self.assertTrue(all(entry.handoff_id.startswith("handoff-") for entry in listed.entries))

    def test_workspace_info_lists_handoff_tools_and_hides_primitives(self) -> None:
        tools = set(server.workspace_info().tools)

        self.assertIn("workspace_next_handoff", tools)
        self.assertIn("workspace_list_handoffs", tools)
        self.assertFalse(
            {
                "workspace_stage_command_bundle",
                "workspace_stage_action_bundle",
                "workspace_stage_patch_bundle",
                "workspace_stage_commit_bundle",
            }.intersection(tools)
        )
