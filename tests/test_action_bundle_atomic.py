from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from scripts import command_bundle_runner as runner


class ActionBundleAtomicApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.workspace_root = (root / "workspace").resolve()
        self.project = self.workspace_root / "project"
        self.runtime_root = root / "runtime"

        self.project.mkdir(parents=True)
        self.original_paths = {
            "WORKSPACE_ROOT": runner.WORKSPACE_ROOT,
            "RUNTIME_ROOT": runner.RUNTIME_ROOT,
            "COMMAND_BUNDLES_DIR": runner.COMMAND_BUNDLES_DIR,
            "PENDING_DIR": runner.PENDING_DIR,
            "APPLIED_DIR": runner.APPLIED_DIR,
            "REJECTED_DIR": runner.REJECTED_DIR,
            "FAILED_DIR": runner.FAILED_DIR,
            "BACKUP_DIR": runner.BACKUP_DIR,
            "TEXT_PAYLOAD_DIR": runner.TEXT_PAYLOAD_DIR,
        }

        runner.WORKSPACE_ROOT = self.workspace_root
        runner.RUNTIME_ROOT = self.runtime_root
        runner.COMMAND_BUNDLES_DIR = self.runtime_root / "command_bundles"
        runner.PENDING_DIR = runner.COMMAND_BUNDLES_DIR / "pending"
        runner.APPLIED_DIR = runner.COMMAND_BUNDLES_DIR / "applied"
        runner.REJECTED_DIR = runner.COMMAND_BUNDLES_DIR / "rejected"
        runner.FAILED_DIR = runner.COMMAND_BUNDLES_DIR / "failed"
        runner.BACKUP_DIR = self.runtime_root / "command_bundle_file_backups"
        runner.TEXT_PAYLOAD_DIR = self.runtime_root / "text_payloads"

        for directory in runner.bundle_dirs():
            directory.mkdir(parents=True, exist_ok=True)

        self.run_git(["init", "-q"])
        self.run_git(["config", "user.email", "test@example.invalid"])
        self.run_git(["config", "user.name", "Test User"])
        self.readme = self.project / "README.md"
        self.readme.write_text("initial\n", encoding="utf-8")
        self.run_git(["add", "README.md"])
        self.run_git(["commit", "-q", "-m", "initial"])

    def tearDown(self) -> None:
        for name, value in self.original_paths.items():
            setattr(runner, name, value)
        self.tmp.cleanup()

    def run_git(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.project,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    def git_status(self) -> str:
        return self.run_git(["status", "--porcelain"]).stdout

    def write_action_bundle(self, steps: list[dict[str, object]]) -> str:
        bundle_id = f"cmd-action-atomic-{uuid4().hex[:8]}"
        record = {
            "version": 2,
            "bundle_id": bundle_id,
            "title": "Atomic action bundle",
            "cwd": "project",
            "status": "pending",
            "risk": "medium",
            "approval_required": True,
            "created_at": runner.now_iso(),
            "updated_at": runner.now_iso(),
            "steps": steps,
            "result": None,
            "error": None,
        }
        runner.write_json(runner.PENDING_DIR / f"{bundle_id}.json", record)
        return bundle_id

    def apply_bundle(self, bundle_id: str) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            runner.apply_bundle(bundle_id, yes=True)

    def failed_record(self, bundle_id: str) -> dict[str, object]:
        return json.loads((runner.FAILED_DIR / f"{bundle_id}.json").read_text(encoding="utf-8"))

    def applied_record(self, bundle_id: str) -> dict[str, object]:
        return json.loads((runner.APPLIED_DIR / f"{bundle_id}.json").read_text(encoding="utf-8"))

    def test_failed_action_rolls_back_prior_replace_text(self) -> None:
        bundle_id = self.write_action_bundle(
            [
                {
                    "type": "replace_text",
                    "name": "Replace README",
                    "path": "project/README.md",
                    "old_text": "initial",
                    "new_text": "changed",
                    "replace_all": False,
                    "risk": "medium",
                },
                {
                    "type": "replace_text",
                    "name": "Missing text",
                    "path": "project/README.md",
                    "old_text": "does-not-exist",
                    "new_text": "unused",
                    "replace_all": False,
                    "risk": "medium",
                },
            ]
        )

        self.apply_bundle(bundle_id)

        record = self.failed_record(bundle_id)
        self.assertEqual(self.readme.read_text(encoding="utf-8"), "initial\n")
        self.assertEqual(self.git_status(), "")
        self.assertIn("Action 2 failed: Missing text", str(record["error"]))
        self.assertIn("type: replace_text", str(record["error"]))
        self.assertIn("rollback: completed", str(record["error"]))

    def test_failed_action_removes_created_untracked_file(self) -> None:
        new_file = self.project / "generated.txt"
        bundle_id = self.write_action_bundle(
            [
                {
                    "type": "write_file",
                    "name": "Create generated file",
                    "path": "project/generated.txt",
                    "content": "created\n",
                    "overwrite": False,
                    "create_parent_dirs": True,
                    "risk": "medium",
                },
                {
                    "type": "replace_text",
                    "name": "Fail after create",
                    "path": "project/README.md",
                    "old_text": "missing",
                    "new_text": "unused",
                    "replace_all": False,
                    "risk": "medium",
                },
            ]
        )

        self.apply_bundle(bundle_id)

        self.assertFalse(new_file.exists())
        self.assertEqual(self.git_status(), "")
        self.assertIn("rollback: completed", str(self.failed_record(bundle_id)["error"]))

    def test_dirty_worktree_rejects_action_bundle_without_touching_changes(self) -> None:
        self.readme.write_text("dirty\n", encoding="utf-8")
        bundle_id = self.write_action_bundle(
            [
                {
                    "type": "replace_text",
                    "name": "Would replace README",
                    "path": "project/README.md",
                    "old_text": "initial",
                    "new_text": "changed",
                    "replace_all": False,
                    "risk": "medium",
                }
            ]
        )

        self.apply_bundle(bundle_id)

        record = self.failed_record(bundle_id)
        self.assertEqual(self.readme.read_text(encoding="utf-8"), "dirty\n")
        self.assertIn("worktree is not clean", str(record["error"]))
        self.assertIn("commit/stash/revert changes first", str(record["error"]))

    def test_clean_action_bundle_still_applies(self) -> None:
        bundle_id = self.write_action_bundle(
            [
                {
                    "type": "replace_text",
                    "name": "Replace README",
                    "path": "project/README.md",
                    "old_text": "initial",
                    "new_text": "changed",
                    "replace_all": False,
                    "risk": "medium",
                }
            ]
        )

        self.apply_bundle(bundle_id)

        record = self.applied_record(bundle_id)
        self.assertTrue(record["result"]["ok"])
        self.assertEqual(self.readme.read_text(encoding="utf-8"), "changed\n")


if __name__ == "__main__":
    unittest.main()
