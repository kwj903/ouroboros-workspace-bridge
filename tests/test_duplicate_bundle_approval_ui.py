from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import command_bundle_review_server as review


class DuplicateBundleApprovalUiTests(unittest.TestCase):
    def test_duplicate_approval_does_not_run_runner_for_applied_bundle(self) -> None:
        record = {
            "bundle_id": "cmd-test",
            "title": "Already applied",
            "cwd": ".",
            "status": "applied",
            "risk": "low",
            "approval_required": True,
            "command_count": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:01+00:00",
            "steps": [],
            "result": {"ok": True},
            "error": None,
        }

        with patch.object(review, "find_bundle", return_value=(Path("/tmp/cmd-test.json"), record)):
            with patch.object(review, "run_runner") as run_runner:
                body = (
                    f"<div>{review.bundle_detail_html(Path('/tmp/cmd-test.json'), record)}</div>"
                )
                self.assertIn("Already applied", body)
                run_runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
