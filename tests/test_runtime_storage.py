from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from terminal_bridge import runtime_storage


class RuntimeStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = (Path(self.tmp.name) / "runtime").resolve(strict=False)
        self.root.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_file(self, relative: str, content: str = "data", *, days_old: int | None = None) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if days_old is not None:
            timestamp = time.time() - (days_old * 86400)
            os.utime(path, (timestamp, timestamp))
        return path

    def make_dir(self, relative: str, *, days_old: int | None = None) -> Path:
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        if days_old is not None:
            timestamp = time.time() - (days_old * 86400)
            os.utime(path, (timestamp, timestamp))
        return path

    def touch_relative(self, relative: str, *, seconds_old: int) -> Path:
        path = self.write_file(relative, "{}")
        timestamp = time.time() - seconds_old
        os.utime(path, (timestamp, timestamp))
        return path

    def relative_candidate_paths(self, candidates: list[runtime_storage.CleanupCandidate]) -> set[str]:
        return {candidate.path.relative_to(self.root).as_posix() for candidate in candidates}

    def test_storage_summary_contains_expected_categories(self) -> None:
        self.write_file("audit.jsonl", "audit")
        self.write_file("tool_calls/call-1.json", "{}")

        names = {entry.name for entry in runtime_storage.storage_summary(self.root)}

        self.assertIn("audit.jsonl", names)
        self.assertIn("processes", names)
        self.assertIn("command_bundles", names)
        self.assertIn("command_bundle_file_backups", names)
        self.assertIn("backups", names)
        self.assertIn("trash", names)
        self.assertIn("operations", names)
        self.assertIn("tasks", names)
        self.assertIn("text_payloads", names)
        self.assertIn("tool_calls", names)
        self.assertIn("handoffs", names)
        self.assertIn("intent_imports", names)

    def test_default_cleanup_policy_loads_when_missing_or_invalid(self) -> None:
        self.assertEqual(runtime_storage.load_cleanup_policy(self.root), runtime_storage.default_cleanup_policy())

        runtime_storage.cleanup_policy_path(self.root).write_text("not-json", encoding="utf-8")

        self.assertEqual(runtime_storage.load_cleanup_policy(self.root), runtime_storage.default_cleanup_policy())

    def test_cleanup_policy_save_load_and_validation(self) -> None:
        saved = runtime_storage.save_cleanup_policy(
            self.root,
            {
                "keep_applied": "12",
                "keep_failed": "5",
                "keep_rejected": "3",
                "keep_tool_calls": "20",
                "keep_handoffs": "9",
                "keep_text_payloads": "4",
                "older_than_text_payload_days": "8",
                "older_than_operations_days": "15",
                "older_than_backups_days": "21",
                "include_backups_by_default": "true",
            },
        )

        self.assertEqual(saved.keep_applied, 12)
        self.assertTrue(saved.include_backups_by_default)
        self.assertEqual(runtime_storage.load_cleanup_policy(self.root), saved)

        with self.assertRaises(runtime_storage.CleanupPolicyValidationError):
            runtime_storage.validate_cleanup_policy({"keep_applied": -1})
        with self.assertRaises(runtime_storage.CleanupPolicyValidationError):
            runtime_storage.validate_cleanup_policy({"keep_applied": 0})

        defaults = runtime_storage.default_cleanup_policy()
        self.assertEqual(runtime_storage.validate_cleanup_policy({"keep_applied": ""}).keep_applied, defaults.keep_applied)

    def test_cleanup_candidates_exclude_protected_files_and_pending_bundles(self) -> None:
        self.write_file("session.json", "{}", days_old=365)
        self.write_file("session.env", "TOKEN=x", days_old=365)
        self.write_file("intent_hmac_secret", "secret", days_old=365)
        self.write_file("processes/review.pid", "123", days_old=365)
        self.write_file("command_bundles/pending/cmd-pending.json", "{}", days_old=365)

        candidates = runtime_storage.cleanup_candidates(self.root, older_than_days=1, include_backups=True)
        paths = self.relative_candidate_paths(candidates)

        self.assertNotIn("session.json", paths)
        self.assertNotIn("session.env", paths)
        self.assertNotIn("intent_hmac_secret", paths)
        self.assertNotIn("processes/review.pid", paths)
        self.assertNotIn("command_bundles/pending/cmd-pending.json", paths)

    def test_old_completed_bundles_are_candidates(self) -> None:
        self.write_file("command_bundles/applied/cmd-applied.json", "{}", days_old=90)
        self.write_file("command_bundles/rejected/cmd-rejected.json", "{}", days_old=90)
        self.write_file("command_bundles/failed/cmd-failed.json", "{}", days_old=90)

        candidates = runtime_storage.cleanup_candidates(self.root)
        paths = self.relative_candidate_paths(candidates)

        self.assertIn("command_bundles/applied/cmd-applied.json", paths)
        self.assertIn("command_bundles/rejected/cmd-rejected.json", paths)
        self.assertIn("command_bundles/failed/cmd-failed.json", paths)

    def test_count_based_bundle_candidates_keep_newest_records(self) -> None:
        for index in range(4):
            self.touch_relative(f"command_bundles/applied/cmd-{index}.json", seconds_old=(4 - index) * 10)
        policy = runtime_storage.CleanupPolicy(keep_applied=2)

        candidates = runtime_storage.cleanup_candidates(self.root, policy=policy)
        paths = self.relative_candidate_paths(candidates)

        self.assertIn("command_bundles/applied/cmd-0.json", paths)
        self.assertIn("command_bundles/applied/cmd-1.json", paths)
        self.assertNotIn("command_bundles/applied/cmd-2.json", paths)
        self.assertNotIn("command_bundles/applied/cmd-3.json", paths)

    def test_count_based_records_use_metadata_timestamp_when_available(self) -> None:
        older = self.write_file("tool_calls/older.json", json.dumps({"created_at": "2026-01-01T00:00:00Z"}))
        newer = self.write_file("tool_calls/newer.json", json.dumps({"created_at": "2026-01-02T00:00:00Z"}))
        now = time.time()
        os.utime(older, (now, now))
        os.utime(newer, (now - 1000, now - 1000))
        policy = runtime_storage.CleanupPolicy(keep_tool_calls=1)

        candidates = runtime_storage.cleanup_candidates(self.root, policy=policy)
        paths = self.relative_candidate_paths(candidates)

        self.assertIn("tool_calls/older.json", paths)
        self.assertNotIn("tool_calls/newer.json", paths)

    def test_count_based_tool_call_handoff_and_payload_candidates(self) -> None:
        self.touch_relative("tool_calls/call-old.json", seconds_old=20)
        self.touch_relative("tool_calls/call-new.json", seconds_old=10)
        self.touch_relative("handoffs/handoff-old.json", seconds_old=20)
        self.touch_relative("handoffs/handoff-new.json", seconds_old=10)
        self.touch_relative("text_payloads/payload-old.txt", seconds_old=20)
        self.touch_relative("text_payloads/payload-new.txt", seconds_old=10)
        policy = runtime_storage.CleanupPolicy(keep_tool_calls=1, keep_handoffs=1, keep_text_payloads=1)

        candidates = runtime_storage.cleanup_candidates(self.root, policy=policy)
        paths = self.relative_candidate_paths(candidates)

        self.assertIn("tool_calls/call-old.json", paths)
        self.assertIn("handoffs/handoff-old.json", paths)
        self.assertIn("text_payloads/payload-old.txt", paths)
        self.assertNotIn("tool_calls/call-new.json", paths)
        self.assertNotIn("handoffs/handoff-new.json", paths)
        self.assertNotIn("text_payloads/payload-new.txt", paths)

    def test_prune_all_history_selects_eligible_history_but_preserves_protected_state(self) -> None:
        self.write_file("command_bundles/applied/cmd-applied.json", "{}")
        self.write_file("command_bundles/failed/cmd-failed.json", "{}")
        self.write_file("command_bundles/rejected/cmd-rejected.json", "{}")
        self.write_file("command_bundles/pending/cmd-pending.json", "{}")
        self.write_file("session.json", "{}")
        self.write_file("processes/review.pid", "123")
        self.write_file("tool_calls/call.json", "{}")
        self.write_file("handoffs/handoff.json", "{}")
        self.write_file("operations/op.json", "{}")
        self.write_file("text_payloads/payload.txt", "payload")
        self.write_file("intent_imports/intent.json", "{}")
        self.write_file("trash/item.txt", "trash")
        self.write_file("backups/backup.txt", "backup")

        candidates = runtime_storage.cleanup_candidates(self.root, prune_all_history=True)
        paths = self.relative_candidate_paths(candidates)

        self.assertIn("command_bundles/applied/cmd-applied.json", paths)
        self.assertIn("command_bundles/failed/cmd-failed.json", paths)
        self.assertIn("command_bundles/rejected/cmd-rejected.json", paths)
        self.assertIn("tool_calls/call.json", paths)
        self.assertIn("handoffs/handoff.json", paths)
        self.assertIn("operations/op.json", paths)
        self.assertIn("text_payloads/payload.txt", paths)
        self.assertIn("intent_imports/intent.json", paths)
        self.assertIn("trash/item.txt", paths)
        self.assertNotIn("backups/backup.txt", paths)
        self.assertNotIn("command_bundles/pending/cmd-pending.json", paths)
        self.assertNotIn("session.json", paths)
        self.assertNotIn("processes/review.pid", paths)

        with_backups = self.relative_candidate_paths(runtime_storage.cleanup_candidates(self.root, prune_all_history=True, include_backups=True))
        self.assertIn("backups/backup.txt", with_backups)

    def test_dry_run_does_not_delete_files(self) -> None:
        target = self.write_file("operations/op-old.json", "{}", days_old=90)

        result = runtime_storage.cleanup_runtime(self.root, dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertTrue(target.exists())
        self.assertEqual(result.deleted_files, 0)

    def test_apply_deletes_only_candidates(self) -> None:
        old_operation = self.write_file("operations/op-old.json", "{}", days_old=90)
        pending = self.write_file("command_bundles/pending/cmd-pending.json", "{}", days_old=90)
        session = self.write_file("session.json", "{}", days_old=90)

        result = runtime_storage.cleanup_runtime(self.root, dry_run=False)

        self.assertFalse(result.dry_run)
        self.assertFalse(old_operation.exists())
        self.assertTrue(pending.exists())
        self.assertTrue(session.exists())
        self.assertEqual(result.errors, [])
        self.assertGreaterEqual(result.deleted_files, 1)

    def test_cleanup_excludes_symlink_candidates(self) -> None:
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = self.root / "operations" / "op-link.json"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside)
        with mock.patch.object(runtime_storage, "_mtime_older_than", return_value=True):
            result = runtime_storage.cleanup_runtime(self.root, dry_run=False)

        self.assertTrue(link.exists())
        self.assertTrue(outside.exists())
        self.assertEqual(result.deleted_files, 0)

    def test_include_backups_controls_backup_trash_candidates(self) -> None:
        backup_dir = self.make_dir("backups/backup-old")
        self.write_file("backups/backup-old/file.txt", "old", days_old=90)
        trash_dir = self.make_dir("trash/trash-old")
        self.write_file("trash/trash-old/file.txt", "old", days_old=90)
        old_timestamp = time.time() - (90 * 86400)
        os.utime(backup_dir, (old_timestamp, old_timestamp))
        os.utime(trash_dir, (old_timestamp, old_timestamp))

        default_paths = self.relative_candidate_paths(runtime_storage.cleanup_candidates(self.root))
        included_paths = self.relative_candidate_paths(runtime_storage.cleanup_candidates(self.root, include_backups=True))

        self.assertNotIn("backups/backup-old", default_paths)
        self.assertNotIn("trash/trash-old", default_paths)
        self.assertIn("backups/backup-old", included_paths)
        self.assertIn("trash/trash-old", included_paths)

    def test_policy_can_include_backups_by_default(self) -> None:
        backup_dir = self.make_dir("backups/backup-old")
        self.write_file("backups/backup-old/file.txt", "old", days_old=90)
        old_timestamp = time.time() - (90 * 86400)
        os.utime(backup_dir, (old_timestamp, old_timestamp))
        runtime_storage.save_cleanup_policy(self.root, {"include_backups_by_default": True})

        paths = self.relative_candidate_paths(runtime_storage.cleanup_candidates(self.root))

        self.assertIn("backups/backup-old", paths)


if __name__ == "__main__":
    unittest.main()
