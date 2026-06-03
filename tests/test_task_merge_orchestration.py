from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import server
from terminal_bridge import merge_queue, task_merge_orchestration, task_workspaces
from terminal_bridge.models import CommandBundleStatusResult, SafeTaskMergePreparationResult


class TaskMergeOrchestrationTests(unittest.TestCase):
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
        self.run_git(self.project, ["config", "user.email", "safe-merge@example.test"])
        self.run_git(self.project, ["config", "user.name", "Safe Merge Test"])
        (self.project / "README.md").write_text("hello\n", encoding="utf-8")
        self.run_git(self.project, ["add", "README.md"])
        self.run_git(self.project, ["commit", "-m", "initial commit"])

    def create_task_worktree(self, task_id: str) -> Path:
        record = task_workspaces.create_task_worktree(
            task_id,
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        return Path(str(record["workspace_path"]))

    def proposal_result(self, bundle_id: str = "cmd-safe-merge") -> CommandBundleStatusResult:
        return CommandBundleStatusResult(
            bundle_id=bundle_id,
            title="Merge task worktree: task-ready",
            cwd="project",
            status="pending",
            risk="medium",
            approval_required=True,
            command_count=1,
            created_at="2026-06-03T00:00:00+00:00",
            updated_at="2026-06-03T00:00:00+00:00",
            metadata={
                "task_id": "task-ready",
                "project_id": "project-alpha",
                "workspace_mode": "direct",
                "source_cwd": "project",
                "effective_cwd": "project",
            },
        )

    def test_safe_merge_blocks_clean_task_before_queue_or_proposal(self) -> None:
        self.init_git_project()
        self.create_task_worktree("task-clean")
        proposal_calls: list[str] = []

        result = task_merge_orchestration.prepare_safe_task_merge_and_wait(
            "task-clean",
            cwd="project",
            project_id="project-alpha",
            proposal_callback=lambda: proposal_calls.append("called"),
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertFalse(result["ready_to_merge"])
        self.assertIn("no_changes", result["blockers"])
        self.assertEqual(result["recommended_action"], "no_changes")
        self.assertIsNone(result["merge_queue_status"])
        self.assertIsNone(result["proposal_bundle_id"])
        self.assertEqual(proposal_calls, [])
        self.assertFalse((self.runtime_root / "merge_queue").exists())

    def test_safe_merge_enqueues_ready_task_and_stages_proposal_without_source_apply(self) -> None:
        self.init_git_project()
        workspace_path = self.create_task_worktree("task-ready")
        (workspace_path / "README.md").write_text("hello\nready\n", encoding="utf-8")
        proposal_calls: list[str] = []

        def proposal_callback() -> CommandBundleStatusResult:
            proposal_calls.append("called")
            return self.proposal_result()

        result = task_merge_orchestration.prepare_safe_task_merge_and_wait(
            "task-ready",
            cwd="project",
            project_id="project-alpha",
            proposal_callback=proposal_callback,
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        queued = merge_queue.read_merge_queue_entry(
            "task-ready",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        self.assertTrue(result["ready_to_merge"])
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["conflict_risk"], "low")
        self.assertEqual(result["recommended_action"], "merge_queue")
        self.assertEqual(result["merge_queue_status"], "queued")
        self.assertEqual(result["proposal_bundle_id"], "cmd-safe-merge")
        self.assertEqual(result["proposal_status"], "pending")
        self.assertEqual(proposal_calls, ["called"])
        self.assertEqual(queued["status"], "queued")
        self.assertEqual((self.project / "README.md").read_text(encoding="utf-8"), "hello\n")
        self.assertEqual(self.run_git(self.project, ["status", "--short"]).stdout, "")

    def test_safe_merge_blocks_source_dirty_before_queue_or_proposal(self) -> None:
        self.init_git_project()
        workspace_path = self.create_task_worktree("task-source-dirty")
        (workspace_path / "README.md").write_text("hello\ntask\n", encoding="utf-8")
        (self.project / "source.txt").write_text("dirty\n", encoding="utf-8")
        proposal_calls: list[str] = []

        result = task_merge_orchestration.prepare_safe_task_merge_and_wait(
            "task-source-dirty",
            cwd="project",
            project_id="project-alpha",
            proposal_callback=lambda: proposal_calls.append("called"),
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertFalse(result["ready_to_merge"])
        self.assertIn("source_dirty", result["blockers"])
        self.assertEqual(result["recommended_action"], "clean_source_before_merge")
        self.assertIsNone(result["proposal_bundle_id"])
        self.assertEqual(proposal_calls, [])
        self.assertFalse((self.runtime_root / "merge_queue").exists())

    def test_safe_merge_blocks_source_head_drift_before_queue_or_proposal(self) -> None:
        self.init_git_project()
        workspace_path = self.create_task_worktree("task-head-drift")
        (workspace_path / "README.md").write_text("hello\ntask\n", encoding="utf-8")
        (self.project / "later.txt").write_text("later\n", encoding="utf-8")
        self.run_git(self.project, ["add", "later.txt"])
        self.run_git(self.project, ["commit", "-m", "later commit"])
        proposal_calls: list[str] = []

        result = task_merge_orchestration.prepare_safe_task_merge_and_wait(
            "task-head-drift",
            cwd="project",
            project_id="project-alpha",
            proposal_callback=lambda: proposal_calls.append("called"),
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertFalse(result["ready_to_merge"])
        self.assertTrue(result["preflight_result"]["ready_to_merge"])
        self.assertIn("source_head_drift", result["blockers"])
        self.assertEqual(result["recommended_action"], "refresh_task_worktree_or_manual_review")
        self.assertIsNone(result["proposal_bundle_id"])
        self.assertEqual(proposal_calls, [])
        self.assertFalse((self.runtime_root / "merge_queue").exists())

    def test_safe_merge_missing_task_returns_blocker(self) -> None:
        self.init_git_project()
        proposal_calls: list[str] = []

        result = task_merge_orchestration.prepare_safe_task_merge_and_wait(
            "task-missing",
            cwd="project",
            project_id="project-alpha",
            proposal_callback=lambda: proposal_calls.append("called"),
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertFalse(result["ready_to_merge"])
        self.assertIn("missing_task_workspace_record", result["blockers"])
        self.assertEqual(result["recommended_action"], "create_task_worktree_or_verify_task_id")
        self.assertIsNone(result["proposal_bundle_id"])
        self.assertEqual(proposal_calls, [])

    def test_server_wrapper_returns_safe_merge_result_model(self) -> None:
        original_record = server._record_tool_call
        original_helper = server._prepare_safe_task_merge_and_wait
        calls: list[tuple[str, dict[str, object]]] = []

        def call_through(tool_name: str, args: dict[str, object], action: object) -> object:
            calls.append((tool_name, args))
            return action()

        def fake_helper(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append(("helper", {"args": args, "kwargs": kwargs}))
            return {
                "task_id": "task-ready",
                "project_id": "project-alpha",
                "source_cwd": "project",
                "inspect_summary": {"dirty": True, "changed_file_count": 1},
                "preflight_result": {"ready_to_merge": True, "conflict_risk": "low"},
                "ready_to_merge": True,
                "conflict_risk": "low",
                "recommended_action": "merge_queue",
                "blockers": [],
                "merge_queue_status": "queued",
                "merge_queue_record": {"status": "queued"},
                "proposal_bundle_id": "cmd-safe-merge",
                "proposal_status": "pending",
                "proposal": {"bundle_id": "cmd-safe-merge", "status": "pending"},
            }

        server._record_tool_call = call_through
        server._prepare_safe_task_merge_and_wait = fake_helper
        try:
            result = server.workspace_prepare_safe_task_merge_and_wait(
                task_id="task-ready",
                cwd="project",
                project_id="project-alpha",
                timeout_seconds=7,
                poll_interval_seconds=0.5,
            )
        finally:
            server._record_tool_call = original_record
            server._prepare_safe_task_merge_and_wait = original_helper

        self.assertIsInstance(result, SafeTaskMergePreparationResult)
        self.assertEqual(calls[0][0], "workspace_prepare_safe_task_merge_and_wait")
        self.assertEqual(calls[1][0], "helper")
        self.assertEqual(calls[1][1]["kwargs"]["timeout_seconds"], 7)
        self.assertEqual(calls[1][1]["kwargs"]["poll_interval_seconds"], 0.5)
        self.assertEqual(result.proposal_bundle_id, "cmd-safe-merge")
        self.assertEqual(result.merge_queue_status, "queued")


if __name__ == "__main__":
    unittest.main()
