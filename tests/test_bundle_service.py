from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from terminal_bridge import bundles, handoffs
from terminal_bridge.bundle_service import BundleService


class BundleServiceBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.original_dirs = {
            "COMMAND_BUNDLE_PENDING_DIR": bundles.COMMAND_BUNDLE_PENDING_DIR,
            "COMMAND_BUNDLE_RUNNING_DIR": bundles.COMMAND_BUNDLE_RUNNING_DIR,
            "COMMAND_BUNDLE_APPLIED_DIR": bundles.COMMAND_BUNDLE_APPLIED_DIR,
            "COMMAND_BUNDLE_REJECTED_DIR": bundles.COMMAND_BUNDLE_REJECTED_DIR,
            "COMMAND_BUNDLE_FAILED_DIR": bundles.COMMAND_BUNDLE_FAILED_DIR,
            "COMMAND_BUNDLE_INTERRUPTED_DIR": bundles.COMMAND_BUNDLE_INTERRUPTED_DIR,
        }
        self.original_handoff_dir = handoffs.HANDOFF_DIR
        for status in ("pending", "running", "applied", "rejected", "failed", "interrupted"):
            setattr(bundles, f"COMMAND_BUNDLE_{status.upper()}_DIR", self.root / status)
            (self.root / status).mkdir(parents=True)
        handoffs.HANDOFF_DIR = self.root / "handoffs"
        self.audit_events: list[tuple[str, dict[str, object]]] = []
        self.service = BundleService(
            audit=lambda event, **data: self.audit_events.append((event, data))
        )

    def tearDown(self) -> None:
        for name, directory in self.original_dirs.items():
            setattr(bundles, name, directory)
        handoffs.HANDOFF_DIR = self.original_handoff_dir
        self.tmp.cleanup()

    def stage(self, *, request_key: str = f"sha256:{'a' * 64}"):
        return self.service.stage(
            version=1,
            title="Service boundary",
            cwd="project",
            risk="low",
            steps=[{"type": "command", "name": "status", "argv": ["git", "status"]}],
            request_key=request_key,
            metadata={"task_id": "task-service", "client_id": "client-service"},
            kind="command_bundle",
        )

    def test_stage_owns_dedupe_while_store_owns_canonical_artifacts(self) -> None:
        first = self.stage()
        second = self.stage()

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(second.result.bundle_id, first.result.bundle_id)
        self.assertEqual(len(list((self.root / "pending").glob("cmd-*.json"))), 1)
        self.assertTrue((self.root / ".generation.json").exists())
        self.assertEqual(len(list((self.root / "request_keys").glob("*.json"))), 1)
        self.assertEqual(self.audit_events[0][0], "dedupe_command_bundle")

    def test_status_list_and_cancel_share_the_store_boundary(self) -> None:
        staged = self.stage(request_key=f"sha256:{'b' * 64}")

        status = self.service.status(staged.result.bundle_id)
        listed = self.service.list(limit=10, task_id="task-service")
        cancelled = self.service.cancel(staged.result.bundle_id)

        self.assertEqual(status.status, "pending")
        self.assertEqual([entry.bundle_id for entry in listed.entries], [staged.result.bundle_id])
        self.assertEqual(cancelled.status, "rejected")
        self.assertFalse((self.root / "pending" / f"{staged.result.bundle_id}.json").exists())
        self.assertTrue((self.root / "rejected" / f"{staged.result.bundle_id}.json").exists())
        self.assertEqual(self.audit_events[-1][0], "cancel_command_bundle")

    def test_legacy_result_and_routing_metadata_remain_readable(self) -> None:
        bundle_id = "cmd-legacy-service"
        legacy = {
            "bundle_id": bundle_id,
            "title": "Legacy",
            "cwd": "project",
            "status": "pending",
            "risk": "low",
            "approval_required": False,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:01+00:00",
            "steps": [],
            "metadata": {
                "workspace_mode": "task-workspace",
                "source_cwd": "project",
                "effective_cwd": ".agent-workspaces/task-1",
            },
            "result": {
                "ok": True,
                "workspace_routing": {
                    "workspace_mode": "task-workspace",
                    "actual_cwd": ".agent-workspaces/task-1",
                },
            },
        }
        (self.root / "applied" / f"{bundle_id}.json").write_text(
            json.dumps(legacy), encoding="utf-8"
        )

        result = self.service.status(bundle_id)

        self.assertEqual(result.status, "applied")
        self.assertEqual(result.metadata["workspace_mode"], "task-workspace")
        assert result.result is not None
        self.assertEqual(result.result["workspace_routing"]["workspace_mode"], "task-workspace")


if __name__ == "__main__":
    unittest.main()
