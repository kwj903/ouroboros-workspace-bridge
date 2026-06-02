from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import server
from terminal_bridge import merge_queue, merge_queue_apply, task_cleanup_preview, task_workspaces
from terminal_bridge.models import TaskCleanupPreviewResult
from terminal_bridge.storage import _now_iso, _write_json


class TaskCleanupPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace_root = self.root / "workspace"
        self.runtime_root = self.root / "runtime"
        self.project = self.workspace_root / "project"
        self.project.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_git(self, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    def init_git_project(self) -> None:
        self.run_git(self.project, ["init"])
        self.run_git(self.project, ["config", "user.email", "cleanup-preview@example.test"])
        self.run_git(self.project, ["config", "user.name", "Cleanup Preview Test"])
        (self.project / "README.md").write_text("hello\n", encoding="utf-8")
        self.run_git(self.project, ["add", "README.md"])
        self.run_git(self.project, ["commit", "-m", "initial commit"])

    def dirty_task_worktree(self, task_id: str) -> dict[str, object]:
        record = task_workspaces.create_task_worktree(
            task_id,
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        workspace_path = Path(str(record["workspace_path"]))
        (workspace_path / "README.md").write_text("hello\nqueued\n", encoding="utf-8")
        return record

    def commit_task_worktree(self, record: dict[str, object]) -> None:
        workspace_path = Path(str(record["workspace_path"]))
        self.run_git(workspace_path, ["add", "README.md"])
        self.run_git(workspace_path, ["commit", "-m", "task changes"])

    def merged_archived_task(
        self,
        task_id: str,
        *,
        commit_worktree: bool,
        validation_status: str = "passed",
    ) -> dict[str, object]:
        record = self.dirty_task_worktree(task_id)
        if commit_worktree:
            self.commit_task_worktree(record)
        merge_queue.enqueue_task_worktree_merge(
            task_id,
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        merge_queue_apply.apply_queued_task_worktree_merge(
            task_id,
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        merge_queue.record_task_validation(
            task_id,
            cwd="project",
            project_id="project-alpha",
            validation_status=validation_status,
            validation_commands=["uv run python -m unittest tests.test_task_cleanup_preview"],
            validation_summary=f"validation {validation_status}",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        task_workspaces.archive_task_workspace(
            task_id,
            cwd="project",
            project_id="project-alpha",
            reason="merged and validated",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        return record

    def test_preview_marks_archived_merged_validated_clean_worktree_ready(self) -> None:
        self.init_git_project()
        record = self.merged_archived_task("task-cleanup-ready", commit_worktree=True)

        preview = task_cleanup_preview.task_cleanup_preview(project_id="project-alpha", runtime_root=self.runtime_root)

        self.assertEqual(preview["count"], 1)
        self.assertEqual(preview["ready_count"], 1)
        self.assertEqual(preview["blocked_count"], 0)
        entry = preview["entries"][0]
        self.assertEqual(entry["task_id"], "task-cleanup-ready")
        self.assertEqual(entry["workspace_path"], record["workspace_path"])
        self.assertEqual(entry["workspace_status"], "archived")
        self.assertEqual(entry["queue_status"], "merged")
        self.assertEqual(entry["validation_status"], "passed")
        self.assertTrue(entry["cleanup_ready"])
        self.assertEqual(entry["cleanup_risk"], "low")
        self.assertEqual(entry["cleanup_blockers"], [])
        self.assertEqual(entry["recommended_action"], "ready_for_physical_cleanup_review")

    def test_preview_blocks_failed_validation(self) -> None:
        self.init_git_project()
        self.merged_archived_task("task-cleanup-failed-validation", commit_worktree=True, validation_status="failed")

        preview = task_cleanup_preview.task_cleanup_preview(project_id="project-alpha", runtime_root=self.runtime_root)

        entry = preview["entries"][0]
        self.assertFalse(entry["cleanup_ready"])
        self.assertEqual(entry["validation_status"], "failed")
        self.assertIn("validation_failed", entry["cleanup_blockers"])
        self.assertEqual(entry["cleanup_risk"], "high")

    def test_preview_blocks_dirty_task_worktree(self) -> None:
        self.init_git_project()
        self.merged_archived_task("task-cleanup-dirty", commit_worktree=False)

        preview = task_cleanup_preview.task_cleanup_preview(project_id="project-alpha", runtime_root=self.runtime_root)

        entry = preview["entries"][0]
        self.assertFalse(entry["cleanup_ready"])
        self.assertIn("worktree_dirty", entry["cleanup_blockers"])
        self.assertEqual(entry["cleanup_risk"], "high")
        self.assertEqual(entry["recommended_action"], "inspect_or_preserve_worktree")

    def test_preview_blocks_archived_task_without_merge_queue_record(self) -> None:
        self.init_git_project()
        task_workspaces.create_task_worktree(
            "task-no-queue",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        task_workspaces.archive_task_workspace(
            "task-no-queue",
            cwd="project",
            project_id="project-alpha",
            reason="abandoned",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        preview = task_cleanup_preview.task_cleanup_preview(project_id="project-alpha", runtime_root=self.runtime_root)

        entry = preview["entries"][0]
        self.assertFalse(entry["cleanup_ready"])
        self.assertTrue(entry["has_task_workspace_record"])
        self.assertFalse(entry["has_merge_queue_record"])
        self.assertIn("missing_merge_queue_record", entry["cleanup_blockers"])
        self.assertIn("validation_not_passed", entry["cleanup_blockers"])

    def test_preview_blocks_workspace_path_escape(self) -> None:
        now = _now_iso()
        task_root = self.runtime_root / "task_workspaces"
        queue_root = self.runtime_root / "merge_queue"
        task_record_path = task_root / "escape-record" / "workspace.json"
        queue_record_path = queue_root / "escape-record" / "queue.json"
        escaped_workspace = self.root / "outside-worktree"
        escaped_workspace.mkdir()
        _write_json(
            task_record_path,
            {
                "task_id": "task-escape",
                "project_id": "project-alpha",
                "source_cwd": "project",
                "workspace_mode": "task-workspace",
                "workspace_key": "escape-record",
                "workspace_path": str(escaped_workspace),
                "record_path": str(task_record_path),
                "worktree_branch": "task/task-escape",
                "worktree_status": "ready",
                "status": "archived",
                "exists": True,
                "created_at": now,
                "updated_at": now,
            },
        )
        _write_json(
            queue_record_path,
            {
                "queue_key": "escape-record",
                "task_id": "task-escape",
                "project_id": "project-alpha",
                "source_cwd": "project",
                "workspace_path": str(escaped_workspace),
                "status": "merged",
                "exists": True,
                "validation_status": "passed",
                "validation_commands": [],
                "validation_summary": "passed",
                "record_path": str(queue_record_path),
                "created_at": now,
                "updated_at": now,
            },
        )

        preview = task_cleanup_preview.task_cleanup_preview(project_id="project-alpha", runtime_root=self.runtime_root)

        entry = preview["entries"][0]
        self.assertFalse(entry["cleanup_ready"])
        self.assertIn("workspace_path_outside_runtime", entry["cleanup_blockers"])
        self.assertEqual(entry["cleanup_risk"], "high")

    def test_preview_reports_queue_only_record_as_blocked_anomaly(self) -> None:
        now = _now_iso()
        queue_record_path = self.runtime_root / "merge_queue" / "queue-only" / "queue.json"
        _write_json(
            queue_record_path,
            {
                "queue_key": "queue-only",
                "task_id": "task-queue-only",
                "project_id": "project-alpha",
                "source_cwd": "project",
                "workspace_path": str(self.runtime_root / "task_workspaces" / "missing" / "repo"),
                "status": "archived",
                "exists": True,
                "validation_status": "passed",
                "validation_commands": [],
                "validation_summary": "passed",
                "record_path": str(queue_record_path),
                "created_at": now,
                "updated_at": now,
            },
        )

        preview = task_cleanup_preview.task_cleanup_preview(project_id="project-alpha", runtime_root=self.runtime_root)

        entry = preview["entries"][0]
        self.assertFalse(entry["cleanup_ready"])
        self.assertFalse(entry["has_task_workspace_record"])
        self.assertTrue(entry["has_merge_queue_record"])
        self.assertIn("missing_task_workspace_record", entry["cleanup_blockers"])

    def test_server_public_wrapper_returns_cleanup_preview_model(self) -> None:
        original_record = server._record_tool_call
        original_preview = server._task_cleanup_preview
        calls: list[tuple[str, dict[str, object]]] = []

        def call_through(tool_name: str, args: dict[str, object], action: object) -> object:
            calls.append((tool_name, args))
            return action()

        def fake_preview(*, project_id: str | None = None) -> dict[str, object]:
            self.assertEqual(project_id, "project-alpha")
            return {
                "project_id": "project-alpha",
                "entries": [
                    {
                        "task_id": "task-a",
                        "project_id": "project-alpha",
                        "source_cwd": "project",
                        "workspace_path": "/tmp/workspace",
                        "record_path": "/tmp/record.json",
                        "queue_status": "merged",
                        "workspace_status": "archived",
                        "validation_status": "passed",
                        "cleanup_ready": True,
                        "cleanup_risk": "low",
                        "cleanup_blockers": [],
                        "recommended_action": "ready_for_physical_cleanup_review",
                        "worktree_dirty": False,
                        "has_task_workspace_record": True,
                        "has_merge_queue_record": True,
                    }
                ],
                "count": 1,
                "ready_count": 1,
                "blocked_count": 0,
            }

        server._record_tool_call = call_through
        server._task_cleanup_preview = fake_preview
        try:
            result = server.workspace_task_cleanup_preview(project_id="project-alpha")
        finally:
            server._record_tool_call = original_record
            server._task_cleanup_preview = original_preview

        self.assertIsInstance(result, TaskCleanupPreviewResult)
        self.assertEqual(result.ready_count, 1)
        self.assertEqual(result.entries[0].task_id, "task-a")
        self.assertEqual(calls, [("workspace_task_cleanup_preview", {"project_id": "project-alpha"})])


if __name__ == "__main__":
    unittest.main()
