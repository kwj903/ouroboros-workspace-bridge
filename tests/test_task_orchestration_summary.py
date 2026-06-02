from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import server
from terminal_bridge import merge_queue, task_orchestration_summary, task_workspaces
from terminal_bridge.models import TaskOrchestrationSummaryResult


class TaskOrchestrationSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime_root = self.root / "runtime"
        self.workspace_root = self.root / "workspace"
        self.project = self.workspace_root / "project"
        self.project.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def prepare_task(self, task_id: str, *, project_id: str = "project-alpha") -> dict[str, object]:
        return task_workspaces.prepare_task_workspace(
            task_id,
            cwd="project",
            project_id=project_id,
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

    def test_summary_includes_task_workspace_without_queue_record(self) -> None:
        task = self.prepare_task("task-only")

        summary = task_orchestration_summary.task_orchestration_summary(
            project_id="project-alpha",
            runtime_root=self.runtime_root,
        )

        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["project_id"], "project-alpha")
        entry = summary["entries"][0]
        self.assertEqual(entry["task_id"], "task-only")
        self.assertEqual(entry["source_cwd"], "project")
        self.assertEqual(entry["task_workspace_status"], "created")
        self.assertIsNone(entry["merge_queue_status"])
        self.assertFalse(entry["has_merge_queue_record"])
        self.assertFalse(entry["archived"])
        self.assertFalse(entry["anomaly"])
        self.assertEqual(entry["workspace_path"], task["workspace_path"])

    def test_summary_joins_task_workspace_and_merge_queue_record(self) -> None:
        task = self.prepare_task("task-queued")
        queue = {
            "queue_key": "task-queued-queuekey",
            "task_id": "task-queued",
            "project_id": "project-alpha",
            "source_cwd": "project",
            "workspace_path": task["workspace_path"],
            "worktree_branch": "task/task-queued",
            "changed_file_count": 3,
            "conflict_risk": "low",
            "recommended_action": "merge_queue",
            "status": "queued",
            "exists": True,
            "record_path": "",
            "created_at": "2026-06-02T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        }
        queue_key = str(queue["queue_key"])
        record_path = merge_queue._queue_record_path(queue_key, runtime_root=self.runtime_root)
        queue["record_path"] = str(record_path)
        merge_queue._write_json(record_path, queue)

        summary = task_orchestration_summary.task_orchestration_summary(
            project_id="project-alpha",
            runtime_root=self.runtime_root,
        )

        entry = summary["entries"][0]
        self.assertTrue(entry["has_task_workspace_record"])
        self.assertTrue(entry["has_merge_queue_record"])
        self.assertEqual(entry["merge_queue_status"], "queued")
        self.assertEqual(entry["conflict_risk"], "low")
        self.assertEqual(entry["recommended_action"], "merge_queue")
        self.assertEqual(entry["changed_file_count"], 3)
        self.assertEqual(entry["worktree_branch"], task["worktree_branch"])
        self.assertFalse(entry["anomaly"])

    def test_summary_preserves_conflict_handling_fields_from_queue_record(self) -> None:
        task = self.prepare_task("task-conflict")
        queue = {
            "queue_key": "task-conflict-queuekey",
            "task_id": "task-conflict",
            "project_id": "project-alpha",
            "source_cwd": "project",
            "workspace_path": task["workspace_path"],
            "worktree_branch": "task/task-conflict",
            "changed_file_count": 2,
            "source_head_changed": True,
            "source_dirty": True,
            "overlapping_files": ["README.md", "terminal_bridge/task_workspaces.py"],
            "conflict_risk": "high",
            "recommended_action": "manual_conflict_review",
            "status": "queued",
            "exists": True,
            "record_path": "",
            "created_at": "2026-06-02T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        }
        record_path = merge_queue._queue_record_path(str(queue["queue_key"]), runtime_root=self.runtime_root)
        queue["record_path"] = str(record_path)
        merge_queue._write_json(record_path, queue)

        summary = task_orchestration_summary.task_orchestration_summary(
            project_id="project-alpha",
            runtime_root=self.runtime_root,
        )

        entry = summary["entries"][0]
        self.assertTrue(entry["source_head_changed"])
        self.assertTrue(entry["source_dirty"])
        self.assertEqual(entry["overlapping_files"], ["README.md", "terminal_bridge/task_workspaces.py"])
        self.assertTrue(entry["operator_attention"])
        self.assertEqual(
            entry["operator_attention_reasons"],
            ["high_risk", "source_dirty", "source_head_changed", "overlapping_files"],
        )

    def test_summary_includes_queue_record_without_task_workspace_as_anomaly(self) -> None:
        queue = {
            "queue_key": "task-missing-queuekey",
            "task_id": "task-missing",
            "project_id": "project-alpha",
            "source_cwd": "project",
            "workspace_path": "/tmp/missing-worktree",
            "changed_file_count": 1,
            "conflict_risk": "high",
            "recommended_action": "manual_conflict_review",
            "status": "queued",
            "exists": True,
            "record_path": "",
            "created_at": "2026-06-02T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        }
        record_path = merge_queue._queue_record_path(str(queue["queue_key"]), runtime_root=self.runtime_root)
        queue["record_path"] = str(record_path)
        merge_queue._write_json(record_path, queue)

        summary = task_orchestration_summary.task_orchestration_summary(
            project_id="project-alpha",
            runtime_root=self.runtime_root,
        )

        entry = summary["entries"][0]
        self.assertEqual(entry["task_id"], "task-missing")
        self.assertFalse(entry["has_task_workspace_record"])
        self.assertTrue(entry["has_merge_queue_record"])
        self.assertEqual(entry["task_workspace_status"], "missing")
        self.assertEqual(entry["merge_queue_status"], "queued")
        self.assertTrue(entry["anomaly"])
        self.assertIn("missing_task_workspace_record", entry["anomaly_reasons"])

    def test_summary_project_filter_and_archived_counts(self) -> None:
        self.prepare_task("task-alpha", project_id="project-alpha")
        archived = self.prepare_task("task-beta", project_id="project-beta")
        task_workspaces.archive_task_workspace(
            "task-beta",
            cwd="project",
            project_id="project-beta",
            reason="done",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        summary = task_orchestration_summary.task_orchestration_summary(
            project_id="project-beta",
            runtime_root=self.runtime_root,
        )

        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["active_count"], 0)
        self.assertEqual(summary["archived_count"], 1)
        entry = summary["entries"][0]
        self.assertEqual(entry["task_id"], "task-beta")
        self.assertEqual(entry["workspace_path"], archived["workspace_path"])
        self.assertTrue(entry["archived"])

    def test_server_public_wrapper_returns_summary_model(self) -> None:
        original_record = server._record_tool_call
        original_summary = server._task_orchestration_summary
        calls: list[tuple[str, dict[str, object]]] = []

        def call_through(tool_name: str, args: dict[str, object], action: object) -> object:
            calls.append((tool_name, args))
            return action()

        def fake_summary(*, project_id: str | None = None) -> dict[str, object]:
            return {
                "project_id": project_id,
                "entries": [
                    {
                        "project_id": "project-alpha",
                        "source_cwd": "project",
                        "task_id": "task-a",
                        "task_workspace_status": "worktree",
                        "worktree_status": "ready",
                        "worktree_branch": "task/task-a",
                        "workspace_path": "/tmp/task-a/repo",
                        "merge_queue_status": "queued",
                        "conflict_risk": "low",
                        "recommended_action": "merge_queue",
                        "changed_file_count": 2,
                        "archived": False,
                        "has_task_workspace_record": True,
                        "has_merge_queue_record": True,
                        "anomaly": False,
                        "anomaly_reasons": [],
                    }
                ],
                "count": 1,
                "active_count": 1,
                "archived_count": 0,
                "anomaly_count": 0,
            }

        server._record_tool_call = call_through
        server._task_orchestration_summary = fake_summary
        try:
            result = server.workspace_task_orchestration_summary(project_id="project-alpha")
        finally:
            server._record_tool_call = original_record
            server._task_orchestration_summary = original_summary

        self.assertIsInstance(result, TaskOrchestrationSummaryResult)
        self.assertEqual(calls, [("workspace_task_orchestration_summary", {"project_id": "project-alpha"})])
        self.assertEqual(result.entries[0].task_id, "task-a")
        self.assertEqual(result.entries[0].merge_queue_status, "queued")


if __name__ == "__main__":
    unittest.main()
