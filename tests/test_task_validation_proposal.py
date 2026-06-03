from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import server
from terminal_bridge import merge_queue, merge_queue_apply, task_validation_proposal, task_workspaces
from terminal_bridge.models import CommandBundleStatusResult


class TaskValidationProposalTests(unittest.TestCase):
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
        self.run_git(self.project, ["config", "user.email", "validation-proposal@example.test"])
        self.run_git(self.project, ["config", "user.name", "Validation Proposal Test"])
        (self.project / "README.md").write_text("hello\n", encoding="utf-8")
        self.run_git(self.project, ["add", "README.md"])
        self.run_git(self.project, ["commit", "-m", "initial commit"])

    def merged_task(self, task_id: str = "task-validation-proposal") -> dict[str, object]:
        record = task_workspaces.create_task_worktree(
            task_id,
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        workspace_path = Path(str(record["workspace_path"]))
        (workspace_path / "README.md").write_text("hello\nmerged\n", encoding="utf-8")
        merge_queue.enqueue_task_worktree_merge(
            task_id,
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        return merge_queue_apply.apply_queued_task_worktree_merge(
            task_id,
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

    def test_prepare_validation_command_proposal_requires_merged_queue(self) -> None:
        self.init_git_project()
        record = task_workspaces.create_task_worktree(
            "task-not-merged",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        workspace_path = Path(str(record["workspace_path"]))
        (workspace_path / "README.md").write_text("hello\nqueued\n", encoding="utf-8")
        merge_queue.enqueue_task_worktree_merge(
            "task-not-merged",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        with self.assertRaisesRegex(ValueError, "must be merged"):
            task_validation_proposal.prepare_task_validation_command_proposal(
                "task-not-merged",
                cwd="project",
                project_id="project-alpha",
                argv=["uv", "run", "python", "-m", "unittest"],
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_prepare_validation_command_proposal_marks_dirty_source_as_high_risk_blocker(self) -> None:
        self.init_git_project()
        self.merged_task()

        proposal = task_validation_proposal.prepare_task_validation_command_proposal(
            "task-validation-proposal",
            cwd="project",
            project_id="project-alpha",
            argv=["uv", "run", "python", "-m", "unittest"],
            command_name="Run source validation",
            command_timeout_seconds=300,
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertEqual(proposal["title"], "Validate merged task: task-validation-proposal")
        self.assertEqual(proposal["cwd"], "project")
        step = proposal["step"]
        self.assertEqual(step.argv, ["uv", "run", "python", "-m", "unittest"])
        self.assertEqual(step.name, "Run source validation")
        self.assertEqual(step.timeout_seconds, 300)
        self.assertEqual(
            proposal["metadata"],
            {
                "task_id": "task-validation-proposal",
                "project_id": "project-alpha",
                "workspace_mode": "direct",
                "source_cwd": "project",
                "effective_cwd": "project",
                "validation_command": ["uv", "run", "python", "-m", "unittest"],
                "validation_command_name": "Run source validation",
                "merge_queue_status": "merged",
                "source_dirty": True,
                "validation_blockers": ["source_dirty"],
                "validation_risk": "high",
            },
        )

    def test_server_validation_command_wrapper_stages_one_pending_command(self) -> None:
        original_record = server._record_tool_call
        original_prepare = server._prepare_task_validation_command_proposal
        original_stage = server._workspace_stage_command_bundle_and_wait_impl
        calls: list[tuple[str, dict[str, object]]] = []
        staged: dict[str, object] = {}

        def call_through(tool_name: str, args: dict[str, object], action: object) -> object:
            calls.append((tool_name, args))
            return action()

        def fake_prepare(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append(("prepare", {"args": args, "kwargs": kwargs}))
            return {
                "title": "Validate merged task: task-a",
                "cwd": "project",
                "step": server.CommandBundleStep(
                    name="Run validation",
                    argv=["uv", "run", "python", "-m", "unittest"],
                    timeout_seconds=300,
                ),
                "metadata": {
                    "task_id": "task-a",
                    "project_id": "project-alpha",
                    "workspace_mode": "direct",
                    "source_cwd": "project",
                    "effective_cwd": "project",
                    "validation_command": ["uv", "run", "python", "-m", "unittest"],
                    "validation_command_name": "Run validation",
                    "merge_queue_status": "merged",
                    "source_dirty": True,
                    "validation_blockers": ["source_dirty"],
                    "validation_risk": "high",
                },
            }

        def fake_stage(
            title: str,
            cwd: str,
            steps: list[object],
            timeout: int,
            poll: float,
            metadata: dict[str, object],
        ) -> CommandBundleStatusResult:
            staged["title"] = title
            staged["cwd"] = cwd
            staged["steps"] = steps
            staged["timeout"] = timeout
            staged["poll"] = poll
            staged["metadata"] = metadata
            return CommandBundleStatusResult(
                bundle_id="cmd-validation",
                title=title,
                cwd=cwd,
                status="pending",
                risk="medium",
                approval_required=True,
                command_count=1,
                created_at="now",
                updated_at="now",
                metadata=metadata,
            )

        server._record_tool_call = call_through
        server._prepare_task_validation_command_proposal = fake_prepare
        server._workspace_stage_command_bundle_and_wait_impl = fake_stage
        try:
            result = server.workspace_propose_task_validation_command_and_wait(
                task_id="task-a",
                cwd="project",
                project_id="project-alpha",
                argv=["uv", "run", "python", "-m", "unittest"],
                command_name="Run validation",
                command_timeout_seconds=300,
                timeout_seconds=7,
                poll_interval_seconds=0.5,
            )
        finally:
            server._record_tool_call = original_record
            server._prepare_task_validation_command_proposal = original_prepare
            server._workspace_stage_command_bundle_and_wait_impl = original_stage

        self.assertIsInstance(result, CommandBundleStatusResult)
        self.assertEqual(calls[0][0], "workspace_propose_task_validation_command_and_wait")
        self.assertEqual(calls[1][0], "prepare")
        self.assertEqual(staged["title"], "Validate merged task: task-a")
        self.assertEqual(staged["cwd"], "project")
        self.assertEqual(staged["timeout"], 7)
        self.assertEqual(staged["poll"], 0.5)
        self.assertEqual(len(staged["steps"]), 1)
        self.assertEqual(staged["metadata"]["workspace_mode"], "direct")
        self.assertEqual(staged["metadata"]["validation_command"], ["uv", "run", "python", "-m", "unittest"])
        self.assertEqual(staged["metadata"]["validation_blockers"], ["source_dirty"])


if __name__ == "__main__":
    unittest.main()
