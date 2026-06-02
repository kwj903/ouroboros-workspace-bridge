from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import server
from terminal_bridge import merge_queue, task_workspaces
from terminal_bridge.models import MergeQueueEntryResult, MergeQueueListResult


class MergeQueueTests(unittest.TestCase):
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
        self.run_git(self.project, ["config", "user.email", "merge-queue@example.test"])
        self.run_git(self.project, ["config", "user.name", "Merge Queue Test"])
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

    def test_enqueue_ready_task_creates_idempotent_queue_record(self) -> None:
        self.init_git_project()
        self.dirty_task_worktree("task-queue-ready")

        first = merge_queue.enqueue_task_worktree_merge(
            "task-queue-ready",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        second = merge_queue.enqueue_task_worktree_merge(
            "task-queue-ready",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertEqual(first["queue_key"], second["queue_key"])
        self.assertEqual(first["status"], "queued")
        self.assertEqual(second["status"], "queued")
        self.assertTrue(first["exists"])
        self.assertEqual(first["task_id"], "task-queue-ready")
        self.assertEqual(first["project_id"], "project-alpha")
        self.assertEqual(first["source_cwd"], "project")
        self.assertEqual(first["conflict_risk"], "low")
        self.assertEqual(first["recommended_action"], "merge_queue")
        self.assertEqual(first["changed_file_count"], 1)
        self.assertTrue(Path(str(first["record_path"])).is_file())
        self.assertTrue(Path(str(first["record_path"])).is_relative_to((self.runtime_root / "merge_queue").resolve()))
        self.assertEqual(self.run_git(self.project, ["status", "--porcelain"]).stdout, "")

    def test_enqueue_rejects_not_ready_preflight(self) -> None:
        self.init_git_project()
        task_workspaces.create_task_worktree(
            "task-queue-clean",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        with self.assertRaisesRegex(ValueError, "not ready for merge queue"):
            merge_queue.enqueue_task_worktree_merge(
                "task-queue-clean",
                cwd="project",
                project_id="project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_queue_status_and_list(self) -> None:
        self.init_git_project()
        self.dirty_task_worktree("task-queue-list-a")
        self.dirty_task_worktree("task-queue-list-b")
        merge_queue.enqueue_task_worktree_merge(
            "task-queue-list-a",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        merge_queue.enqueue_task_worktree_merge(
            "task-queue-list-b",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        status = merge_queue.read_merge_queue_entry(
            "task-queue-list-a",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        listed = merge_queue.list_merge_queue(project_id="project-alpha", runtime_root=self.runtime_root)

        self.assertTrue(status["exists"])
        self.assertEqual(status["status"], "queued")
        self.assertEqual({entry["task_id"] for entry in listed}, {"task-queue-list-a", "task-queue-list-b"})

    def test_queue_status_missing(self) -> None:
        self.init_git_project()
        self.dirty_task_worktree("task-queue-missing")

        status = merge_queue.read_merge_queue_entry(
            "task-queue-missing",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertFalse(status["exists"])
        self.assertEqual(status["status"], "missing")
        self.assertTrue(str(status["record_path"]).endswith("queue.json"))

    def test_server_public_wrappers_call_merge_queue_helpers(self) -> None:
        original_record = server._record_tool_call
        original_enqueue = server._enqueue_task_worktree_merge
        original_read = server._read_merge_queue_entry
        original_list = server._list_merge_queue
        calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

        def call_through(tool_name: str, args: dict[str, object], action: object) -> object:
            return action()

        def fake_record(task_id: str = "task-a") -> dict[str, object]:
            return {
                "queue_key": f"{task_id}-123456789abc",
                "task_id": task_id,
                "project_id": "project-alpha",
                "source_cwd": "project",
                "workspace_path": "/tmp/workspace/repo",
                "worktree_branch": f"task/{task_id}-123456789abc",
                "base_ref": "main",
                "base_sha": "a" * 40,
                "source_head_sha": "a" * 40,
                "source_head_changed": False,
                "source_dirty": False,
                "changed_file_count": 1,
                "changed_files": [{"status": "M", "path": "README.md"}],
                "overlapping_files": [],
                "conflict_risk": "low",
                "recommended_action": "merge_queue",
                "status": "queued",
                "exists": True,
                "record_path": "/tmp/merge_queue/queue.json",
                "created_at": "2026-06-02T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            }

        def fake_enqueue(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append(("enqueue", args, kwargs))
            return fake_record()

        def fake_read(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append(("read", args, kwargs))
            return fake_record()

        def fake_list(*args: object, **kwargs: object) -> list[dict[str, object]]:
            calls.append(("list", args, kwargs))
            return [fake_record()]

        server._record_tool_call = call_through
        server._enqueue_task_worktree_merge = fake_enqueue
        server._read_merge_queue_entry = fake_read
        server._list_merge_queue = fake_list
        try:
            queued = server.workspace_enqueue_task_worktree_merge("task-a", cwd="project", project_id="project-alpha")
            status = server.workspace_merge_queue_status("task-a", cwd="project", project_id="project-alpha")
            listed = server.workspace_list_merge_queue(project_id="project-alpha")
        finally:
            server._record_tool_call = original_record
            server._enqueue_task_worktree_merge = original_enqueue
            server._read_merge_queue_entry = original_read
            server._list_merge_queue = original_list

        self.assertIsInstance(queued, MergeQueueEntryResult)
        self.assertIsInstance(status, MergeQueueEntryResult)
        self.assertIsInstance(listed, MergeQueueListResult)
        self.assertEqual([call[0] for call in calls], ["enqueue", "read", "list"])
        self.assertEqual(calls[0][1], ("task-a",))
        self.assertEqual(calls[0][2], {"cwd": "project", "project_id": "project-alpha"})
        self.assertEqual(listed.count, 1)
        self.assertEqual(queued.status, "queued")


if __name__ == "__main__":
    unittest.main()
