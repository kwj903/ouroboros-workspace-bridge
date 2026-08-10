from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import server
from terminal_bridge import backups, safety


class CanonicalBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.workspace_root = root / "workspace"
        self.workspace_root.mkdir()
        self.backup_dir = root / "runtime" / "backups"
        self.original_backup_dir = backups.BACKUP_DIR
        self.original_workspace_root = safety.WORKSPACE_ROOT
        backups.BACKUP_DIR = self.backup_dir
        safety.WORKSPACE_ROOT = self.workspace_root

    def tearDown(self) -> None:
        backups.BACKUP_DIR = self.original_backup_dir
        safety.WORKSPACE_ROOT = self.original_workspace_root
        self.tmp.cleanup()

    def test_canonical_backup_list_and_restore_round_trip(self) -> None:
        target = self.workspace_root / "project" / "file.txt"
        target.parent.mkdir()
        target.write_text("before\n", encoding="utf-8")

        entry = backups._create_backup_entry(target)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertTrue((self.backup_dir / entry.backup_id / "manifest.json").exists())
        self.assertEqual(entry.original_path, "project/file.txt")
        self.assertEqual(Path(entry.backup_path).read_text(encoding="utf-8"), "before\n")

        listed = backups._list_backup_entries(10)
        self.assertEqual([item.backup_id for item in listed], [entry.backup_id])
        public_list = server.workspace_list_backups(limit=10)
        self.assertEqual([item.backup_id for item in public_list.entries], [entry.backup_id])

        target.write_text("after\n", encoding="utf-8")
        restored = backups._restore_backup_payload(entry.backup_id, overwrite=True)

        self.assertEqual(restored.backup_id, entry.backup_id)
        self.assertIsNotNone(restored.backup_id_before_overwrite)
        self.assertEqual(target.read_text(encoding="utf-8"), "before\n")
        listed_ids = {item.backup_id for item in backups._list_backup_entries(10)}
        self.assertIn(entry.backup_id, listed_ids)
        self.assertIn(restored.backup_id_before_overwrite, listed_ids)

    def test_fast_repeated_backups_use_distinct_ids(self) -> None:
        target = self.workspace_root / "file.txt"
        target.write_text("one\n", encoding="utf-8")

        first = backups._create_backup_entry(target)
        target.write_text("two\n", encoding="utf-8")
        second = backups._create_backup_entry(target)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertNotEqual(first.backup_id, second.backup_id)
        self.assertEqual(Path(first.backup_path).read_text(encoding="utf-8"), "one\n")
        self.assertEqual(Path(second.backup_path).read_text(encoding="utf-8"), "two\n")

    def test_missing_file_does_not_create_backup(self) -> None:
        missing = self.workspace_root / "missing.txt"

        self.assertIsNone(backups._create_backup_entry(missing))
        self.assertEqual(backups._list_backup_entries(10), [])


if __name__ == "__main__":
    unittest.main()
