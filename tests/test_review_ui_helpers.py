from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import command_bundle_review_server as review
from scripts import command_bundle_watcher as watcher


class ReviewServerHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)

        self.original_dirs = (
            review.PENDING_DIR,
            review.APPLIED_DIR,
            review.REJECTED_DIR,
            review.FAILED_DIR,
        )

        review.PENDING_DIR = root / "pending"
        review.APPLIED_DIR = root / "applied"
        review.REJECTED_DIR = root / "rejected"
        review.FAILED_DIR = root / "failed"

        for directory in review.bundle_dirs():
            directory.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        (
            review.PENDING_DIR,
            review.APPLIED_DIR,
            review.REJECTED_DIR,
            review.FAILED_DIR,
        ) = self.original_dirs
        self.tmp.cleanup()

    def write_bundle(self, status: str, bundle_id: str, updated_at: str) -> None:
        path = getattr(review, f"{status.upper()}_DIR") / f"{bundle_id}.json"
        path.write_text(
            json.dumps(
                {
                    "bundle_id": bundle_id,
                    "title": bundle_id,
                    "cwd": ".",
                    "status": status,
                    "risk": "medium",
                    "updated_at": updated_at,
                    "steps": [],
                }
            ),
            encoding="utf-8",
        )

    def test_list_bundles_filters_by_status(self) -> None:
        self.write_bundle("pending", "cmd-pending", "2026-01-02T00:00:00+00:00")
        self.write_bundle("applied", "cmd-applied", "2026-01-01T00:00:00+00:00")

        self.assertEqual([item["bundle_id"] for item in review.list_bundles("pending")], ["cmd-pending"])
        self.assertEqual([item["bundle_id"] for item in review.list_bundles("applied")], ["cmd-applied"])
        self.assertEqual(len(review.list_bundles("all")), 2)

    def test_latest_pending_bundle_id_uses_newest_pending(self) -> None:
        self.write_bundle("pending", "cmd-old", "2026-01-01T00:00:00+00:00")
        self.write_bundle("pending", "cmd-new", "2026-01-02T00:00:00+00:00")

        self.assertEqual(review.latest_pending_bundle_id(), "cmd-new")

    def test_command_bundle_revision_changes_with_state(self) -> None:
        before = review.command_bundle_revision()
        self.write_bundle("pending", "cmd-revision", "2026-01-01T00:00:00+00:00")
        after = review.command_bundle_revision()

        self.assertNotEqual(before, after)

    def test_command_bundle_state_counts_pending(self) -> None:
        self.write_bundle("pending", "cmd-pending", "2026-01-02T00:00:00+00:00")
        self.write_bundle("failed", "cmd-failed", "2026-01-03T00:00:00+00:00")

        state = review.command_bundle_state()

        self.assertEqual(state["pending_count"], 1)
        self.assertEqual(state["latest_pending_bundle_id"], "cmd-pending")


class WatcherHelperTests(unittest.TestCase):
    def test_parse_open_mode(self) -> None:
        self.assertEqual(watcher.parse_open_mode(None), "dashboard_once")
        self.assertEqual(watcher.parse_open_mode("bundle"), "bundle")
        self.assertEqual(watcher.parse_open_mode("none"), "none")
        self.assertEqual(watcher.parse_open_mode("bad-value"), "dashboard_once")

    def test_parse_notify_flag(self) -> None:
        self.assertTrue(watcher.parse_notify_flag(None))
        self.assertTrue(watcher.parse_notify_flag("1"))
        self.assertTrue(watcher.parse_notify_flag("true"))
        self.assertTrue(watcher.parse_notify_flag("yes"))
        self.assertTrue(watcher.parse_notify_flag("on"))
        self.assertFalse(watcher.parse_notify_flag(""))
        self.assertFalse(watcher.parse_notify_flag("0"))
        self.assertFalse(watcher.parse_notify_flag("false"))
        self.assertFalse(watcher.parse_notify_flag("no"))
        self.assertFalse(watcher.parse_notify_flag("off"))

    def test_parse_notification_target(self) -> None:
        self.assertEqual(watcher.parse_notification_target(None), "bundle")
        self.assertEqual(watcher.parse_notification_target("bundle"), "bundle")
        self.assertEqual(watcher.parse_notification_target("pending"), "pending")
        self.assertEqual(watcher.parse_notification_target("bad-value"), "bundle")

    def test_notification_url(self) -> None:
        base_url = "http://127.0.0.1:8790"

        self.assertEqual(
            watcher.notification_url("cmd-test", "bundle", base_url),
            "http://127.0.0.1:8790/bundles/cmd-test",
        )
        self.assertEqual(
            watcher.notification_url("cmd-test", "pending", base_url),
            "http://127.0.0.1:8790/pending",
        )

    def test_terminal_notifier_command(self) -> None:
        command = watcher.terminal_notifier_command(
            "cmd-test",
            "bundle",
            "http://127.0.0.1:8790",
        )

        self.assertEqual(command[0], "terminal-notifier")
        self.assertIn("-open", command)
        self.assertIn("http://127.0.0.1:8790/bundles/cmd-test", command)
        self.assertIn("-group", command)
        self.assertIn("workspace-terminal-bridge", command)


if __name__ == "__main__":
    unittest.main()
