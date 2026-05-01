from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

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

    def test_cleanup_candidates_exclude_protected_files_and_pending_bundles(self) -> None:
        self.write_file("session.json", "{}", days_old=365)
        self.write_file("session.env", "TOKEN=x", days_old=365)
        self.write_file("intent_hmac_secret", "secret", days_old=365)
        self.write_file("processes/review.pid", "123", days_old=365)
        self.write_file("command_bundles/pending/cmd-pending.json", "{}", days_old=365)

        candidates = runtime_storage.cleanup_candidates(self.root, older_than_days=1, include_backups=True)
        paths = {candidate.path.relative_to(self.root).as_posix() for candidate in candidates}

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
        paths = {candidate.path.relative_to(self.root).as_posix() for candidate in candidates}

        self.assertIn("command_bundles/applied/cmd-applied.json", paths)
        self.assertIn("command_bundles/rejected/cmd-rejected.json", paths)
        self.assertIn("command_bundles/failed/cmd-failed.json", paths)

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
        old_timestamp = time.time() - (90 * 86400)
        os.utime(link, (old_timestamp, old_timestamp), follow_symlinks=False)

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

        default_paths = {candidate.path.relative_to(self.root).as_posix() for candidate in runtime_storage.cleanup_candidates(self.root)}
        included_paths = {
            candidate.path.relative_to(self.root).as_posix()
            for candidate in runtime_storage.cleanup_candidates(self.root, include_backups=True)
        }

        self.assertNotIn("backups/backup-old", default_paths)
        self.assertNotIn("trash/trash-old", default_paths)
        self.assertIn("backups/backup-old", included_paths)
        self.assertIn("trash/trash-old", included_paths)


if __name__ == "__main__":
    unittest.main()
