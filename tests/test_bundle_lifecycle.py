from __future__ import annotations

import concurrent.futures
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from terminal_bridge import bundles, handoffs, storage
from terminal_bridge.mcp_tools.bundles import command_bundle_status_from_record


class BundleLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pending = self.root / "pending"
        self.running = self.root / "running"
        self.applied = self.root / "applied"
        self.failed = self.root / "failed"
        self.interrupted = self.root / "interrupted"
        self.rejected = self.root / "rejected"
        for directory in (
            self.pending,
            self.running,
            self.applied,
            self.failed,
            self.interrupted,
            self.rejected,
        ):
            directory.mkdir(parents=True)
        self.original_handoff_dir = handoffs.HANDOFF_DIR
        handoffs.HANDOFF_DIR = self.root / "handoffs"

    def tearDown(self) -> None:
        handoffs.HANDOFF_DIR = self.original_handoff_dir
        self.tmp.cleanup()

    def record(self, bundle_id: str, *, status: str = "pending") -> dict[str, object]:
        timestamp = "2026-08-09T00:00:00+00:00"
        return {
            "bundle_id": bundle_id,
            "title": "Lifecycle test",
            "cwd": ".",
            "status": status,
            "risk": "low",
            "approval_required": status == "pending",
            "created_at": timestamp,
            "updated_at": timestamp,
            "steps": [],
            "metadata": {
                "task_id": "task-test",
                "client_id": "client-test",
                "session_id": "session-test",
                "project_id": "project-test",
            },
            "result": None,
            "error": None,
        }

    def write_pending(self, bundle_id: str) -> None:
        storage._write_json(self.pending / f"{bundle_id}.json", self.record(bundle_id))

    def test_atomic_json_publish_preserves_old_file_when_replace_fails(self) -> None:
        path = self.root / "record.json"
        storage._write_json(path, {"value": "old"})

        with mock.patch("terminal_bridge.storage.os.replace", side_effect=OSError("publish failed")):
            with self.assertRaises(OSError):
                storage._write_json(path, {"value": "new"})

        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"value": "old"})
        self.assertEqual(list(self.root.glob(".record.json.*.tmp")), [])

    def test_competing_claims_have_one_owner(self) -> None:
        bundle_id = "cmd-concurrent-claim"
        self.write_pending(bundle_id)
        start = threading.Barrier(3)

        def claim(execution_id: str) -> tuple[Path, dict[str, object], str] | str:
            start.wait()
            try:
                return bundles._claim_pending_command_bundle(
                    bundle_id,
                    pending_dir=self.pending,
                    running_dir=self.running,
                    execution_id=execution_id,
                )
            except bundles.BundleClaimError as exc:
                return str(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(claim, execution_id) for execution_id in ("exec-one", "exec-two")]
            start.wait()
            outcomes = [future.result(timeout=5) for future in futures]

        winners = [outcome for outcome in outcomes if isinstance(outcome, tuple)]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len([outcome for outcome in outcomes if isinstance(outcome, str)]), 1)
        running_record = storage._read_json(self.running / f"{bundle_id}.json")
        self.assertEqual(running_record["status"], "running")
        self.assertEqual(running_record["execution"]["execution_id"], winners[0][2])
        self.assertFalse((self.pending / f"{bundle_id}.json").exists())

    def test_generation_and_request_slot_follow_create_claim_and_finalize(self) -> None:
        bundle_id = "cmd-generation-lifecycle"
        request_key = f"sha256:{'a' * 64}"
        record = self.record(bundle_id)
        record["request_key"] = request_key
        pending_path = self.pending / f"{bundle_id}.json"

        stored_path, _stored_record, created = bundles._write_pending_command_bundle(
            pending_path,
            record,
        )
        created_generation = bundles._read_command_bundle_generation(root=self.root)
        slot_path = bundles._request_key_slot_path(request_key, root=self.root)

        self.assertTrue(created)
        self.assertEqual(stored_path, pending_path)
        self.assertIsNotNone(created_generation)
        self.assertEqual(storage._read_json(slot_path)["status"], "pending")

        _running_path, _running_record, execution_id = bundles._claim_pending_command_bundle(
            bundle_id,
            pending_dir=self.pending,
            running_dir=self.running,
            execution_id="exec-generation",
        )
        running_generation = bundles._read_command_bundle_generation(root=self.root)
        self.assertNotEqual(running_generation, created_generation)
        self.assertEqual(storage._read_json(slot_path)["status"], "running")

        bundles._finalize_running_command_bundle(
            bundle_id,
            execution_id,
            "applied",
            {"result": {"ok": True}},
            running_dir=self.running,
            applied_dir=self.applied,
            failed_dir=self.failed,
            interrupted_dir=self.interrupted,
        )
        applied_generation = bundles._read_command_bundle_generation(root=self.root)
        self.assertNotEqual(applied_generation, running_generation)
        self.assertEqual(storage._read_json(slot_path)["status"], "applied")

    def test_concurrent_same_request_key_creates_one_pending_bundle(self) -> None:
        request_key = f"sha256:{'c' * 64}"
        start = threading.Barrier(3)

        def create(bundle_id: str) -> tuple[Path, dict[str, object], bool]:
            record = self.record(bundle_id)
            record["request_key"] = request_key
            start.wait()
            return bundles._write_pending_command_bundle(
                self.pending / f"{bundle_id}.json",
                record,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(create, "cmd-request-owner-one"),
                pool.submit(create, "cmd-request-owner-two"),
            ]
            start.wait()
            outcomes = [future.result(timeout=5) for future in futures]

        self.assertEqual(sum(1 for _, _, created in outcomes if created), 1)
        self.assertEqual(len({str(record["bundle_id"]) for _, record, _ in outcomes}), 1)
        self.assertEqual(len(list(self.pending.glob("cmd-*.json"))), 1)

    def test_reject_bumps_generation_and_updates_request_slot(self) -> None:
        bundle_id = "cmd-generation-reject"
        request_key = f"sha256:{'b' * 64}"
        record = self.record(bundle_id)
        record["request_key"] = request_key
        bundles._write_pending_command_bundle(self.pending / f"{bundle_id}.json", record)
        before = bundles._read_command_bundle_generation(root=self.root)

        bundles._reject_pending_command_bundle(
            bundle_id,
            {"error": "Rejected in test."},
            pending_dir=self.pending,
            running_dir=self.running,
            rejected_dir=self.rejected,
        )

        after = bundles._read_command_bundle_generation(root=self.root)
        slot = storage._read_json(bundles._request_key_slot_path(request_key, root=self.root))
        self.assertNotEqual(after, before)
        self.assertEqual(slot["status"], "rejected")

    def test_legacy_terminal_record_without_execution_metadata_is_readable(self) -> None:
        record = self.record("cmd-legacy", status="applied")
        record.pop("metadata")
        storage._write_json(self.applied / "cmd-legacy.json", record)

        path, loaded = bundles._find_command_bundle(
            "cmd-legacy",
            directories=[
                self.running,
                self.pending,
                self.applied,
                self.rejected,
                self.failed,
                self.interrupted,
            ],
        )
        status = command_bundle_status_from_record(loaded, "cmd-legacy")

        self.assertEqual(path.parent, self.applied)
        self.assertEqual(status.status, "applied")
        self.assertNotIn("execution", loaded)
        self.assertEqual(status.metadata["client_id"], "default")

    def test_running_directory_is_canonical_for_partial_claim_record(self) -> None:
        record = self.record("cmd-partial-claim", status="pending")
        storage._write_json(self.running / "cmd-partial-claim.json", record)

        _path, loaded = bundles._find_command_bundle(
            "cmd-partial-claim",
            directories=[self.running, self.pending],
        )

        self.assertEqual(loaded["status"], "running")

    def test_windows_process_probe_does_not_use_os_kill(self) -> None:
        with (
            mock.patch.object(bundles.os, "name", "nt"),
            mock.patch.object(bundles, "_windows_process_is_alive", return_value=False) as windows_probe,
            mock.patch.object(bundles.os, "kill") as kill,
        ):
            self.assertFalse(bundles._process_is_alive(12345))

        windows_probe.assert_called_once_with(12345)
        kill.assert_not_called()

    def test_stale_running_record_becomes_interrupted_without_replay(self) -> None:
        bundle_id = "cmd-stale-running"
        old = datetime.now(timezone.utc) - timedelta(days=2)
        record = self.record(bundle_id, status="running")
        record["updated_at"] = old.isoformat()
        record["execution"] = {
            "execution_id": "exec-stale",
            "pid": 99_999_999,
            "started_at": old.isoformat(),
        }
        storage._write_json(self.running / f"{bundle_id}.json", record)
        (self.running / f".{bundle_id}.claim").mkdir()

        recovered = bundles._interrupt_stale_running_bundles(
            running_dir=self.running,
            interrupted_dir=self.interrupted,
            stale_after_seconds=24 * 60 * 60,
        )

        self.assertEqual(recovered, [bundle_id])
        interrupted = storage._read_json(self.interrupted / f"{bundle_id}.json")
        self.assertEqual(interrupted["status"], "interrupted")
        self.assertFalse(interrupted["recovery"]["automatic_replay"])
        self.assertFalse((self.running / f"{bundle_id}.json").exists())
        self.assertFalse((self.running / f".{bundle_id}.claim").exists())

    def test_old_running_record_with_live_owner_is_not_interrupted(self) -> None:
        bundle_id = "cmd-live-running"
        old = datetime.now(timezone.utc) - timedelta(days=2)
        record = self.record(bundle_id, status="running")
        record["updated_at"] = old.isoformat()
        record["execution"] = {
            "execution_id": "exec-live",
            "pid": os.getpid(),
            "started_at": old.isoformat(),
        }
        storage._write_json(self.running / f"{bundle_id}.json", record)

        recovered = bundles._interrupt_stale_running_bundles(
            running_dir=self.running,
            interrupted_dir=self.interrupted,
            stale_after_seconds=24 * 60 * 60,
        )

        self.assertEqual(recovered, [])
        self.assertTrue((self.running / f"{bundle_id}.json").exists())
        self.assertFalse((self.interrupted / f"{bundle_id}.json").exists())


if __name__ == "__main__":
    unittest.main()
