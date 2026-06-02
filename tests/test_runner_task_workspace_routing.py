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
from terminal_bridge import task_workspaces


class RunnerTaskWorkspaceRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.workspace_root = (root / "workspace").resolve()
        self.runtime_root = (root / "runtime").resolve()
        self.project = self.workspace_root / "project"
        self.project.mkdir(parents=True)
        self.project_id = "project-alpha"

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

        self.run_git(self.project, ["init", "-q"])
        self.run_git(self.project, ["config", "user.email", "task-workspace@example.test"])
        self.run_git(self.project, ["config", "user.name", "Task Workspace Test"])
        (self.project / "README.md").write_text("initial\n", encoding="utf-8")
        (self.project / "subdir").mkdir()
        (self.project / "subdir" / "README.md").write_text("subdir\n", encoding="utf-8")
        self.run_git(self.project, ["add", "."])
        self.run_git(self.project, ["commit", "-q", "-m", "initial"])

    def tearDown(self) -> None:
        for name, value in self.original_paths.items():
            setattr(runner, name, value)
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

    def git_status(self, cwd: Path) -> str:
        return self.run_git(cwd, ["status", "--porcelain"]).stdout

    def create_task_worktree(self, task_id: str = "task-route") -> dict[str, object]:
        return task_workspaces.create_task_worktree(
            task_id,
            cwd="project",
            project_id=self.project_id,
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

    def write_pending_bundle(
        self,
        *,
        cwd: str,
        steps: list[dict[str, object]],
        metadata: dict[str, object] | None = None,
    ) -> str:
        bundle_id = f"cmd-runner-route-{uuid4().hex[:8]}"
        record = {
            "version": 2,
            "bundle_id": bundle_id,
            "title": "Runner route bundle",
            "cwd": cwd,
            "status": "pending",
            "risk": "medium",
            "approval_required": True,
            "created_at": runner.now_iso(),
            "updated_at": runner.now_iso(),
            "steps": steps,
            "metadata": metadata or {
                "workspace_mode": "direct",
                "project_id": self.project_id,
                "source_cwd": cwd,
                "effective_cwd": cwd,
            },
            "result": None,
            "error": None,
        }
        runner.write_json(runner.PENDING_DIR / f"{bundle_id}.json", record)
        return bundle_id

    def task_metadata(self, task_id: str = "task-route", source_cwd: str = "project") -> dict[str, object]:
        return {
            "workspace_mode": "task-workspace",
            "task_id": task_id,
            "project_id": self.project_id,
            "source_cwd": source_cwd,
            "effective_cwd": source_cwd,
        }

    def apply_bundle(self, bundle_id: str) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            runner.apply_bundle(bundle_id, yes=True)

    def applied_record(self, bundle_id: str) -> dict[str, object]:
        return json.loads((runner.APPLIED_DIR / f"{bundle_id}.json").read_text(encoding="utf-8"))

    def failed_record(self, bundle_id: str) -> dict[str, object]:
        return json.loads((runner.FAILED_DIR / f"{bundle_id}.json").read_text(encoding="utf-8"))

    def test_direct_bundle_still_applies_in_source_workspace(self) -> None:
        bundle_id = self.write_pending_bundle(
            cwd="project",
            steps=[
                {
                    "type": "write_file",
                    "name": "Create direct file",
                    "path": "project/direct.txt",
                    "content": "direct\n",
                    "overwrite": False,
                    "create_parent_dirs": True,
                    "risk": "medium",
                }
            ],
        )

        self.apply_bundle(bundle_id)

        self.assertTrue((self.project / "direct.txt").exists())
        self.assertTrue(self.applied_record(bundle_id)["result"]["ok"])

    def test_task_workspace_file_action_routes_to_worktree(self) -> None:
        worktree = self.create_task_worktree()
        worktree_path = Path(str(worktree["workspace_path"]))
        bundle_id = self.write_pending_bundle(
            cwd="project",
            metadata=self.task_metadata(),
            steps=[
                {
                    "type": "write_file",
                    "name": "Create task file",
                    "path": "project/task.txt",
                    "content": "task worktree\n",
                    "overwrite": False,
                    "create_parent_dirs": True,
                    "risk": "medium",
                }
            ],
        )

        self.apply_bundle(bundle_id)

        record = self.applied_record(bundle_id)
        self.assertTrue(record["result"]["ok"])
        self.assertEqual(record["result"]["workspace_routing"]["workspace_mode"], "task-workspace")
        self.assertEqual(record["result"]["workspace_routing"]["actual_cwd"], str(worktree_path))
        self.assertTrue((worktree_path / "task.txt").exists())
        self.assertFalse((self.project / "task.txt").exists())
        self.assertEqual(self.git_status(self.project), "")

    def test_task_workspace_command_routes_to_worktree_cwd(self) -> None:
        worktree = self.create_task_worktree()
        worktree_path = Path(str(worktree["workspace_path"]))
        bundle_id = self.write_pending_bundle(
            cwd="project",
            metadata=self.task_metadata(),
            steps=[
                {
                    "type": "command",
                    "name": "Write command marker",
                    "argv": [
                        "python3",
                        "-c",
                        "from pathlib import Path; Path('command-marker.txt').write_text('task\\n')",
                    ],
                    "timeout_seconds": 30,
                    "risk": "low",
                }
            ],
        )

        self.apply_bundle(bundle_id)

        self.assertTrue((worktree_path / "command-marker.txt").exists())
        self.assertFalse((self.project / "command-marker.txt").exists())
        self.assertTrue(self.applied_record(bundle_id)["result"]["ok"])

    def test_task_workspace_subdir_cwd_routes_to_worktree_subdir(self) -> None:
        worktree = self.create_task_worktree()
        worktree_path = Path(str(worktree["workspace_path"]))
        bundle_id = self.write_pending_bundle(
            cwd="project/subdir",
            metadata=self.task_metadata(),
            steps=[
                {
                    "type": "write_file",
                    "name": "Create subdir file",
                    "path": "project/subdir/task-subdir.txt",
                    "content": "subdir\n",
                    "overwrite": False,
                    "create_parent_dirs": True,
                    "risk": "medium",
                }
            ],
        )

        self.apply_bundle(bundle_id)

        record = self.applied_record(bundle_id)
        self.assertEqual(record["result"]["workspace_routing"]["actual_cwd"], str(worktree_path / "subdir"))
        self.assertTrue((worktree_path / "subdir" / "task-subdir.txt").exists())
        self.assertFalse((self.project / "subdir" / "task-subdir.txt").exists())

    def test_task_workspace_missing_record_fails(self) -> None:
        bundle_id = self.write_pending_bundle(
            cwd="project",
            metadata=self.task_metadata(task_id="missing-task"),
            steps=[],
        )

        self.apply_bundle(bundle_id)

        record = self.failed_record(bundle_id)
        self.assertFalse(record["result"]["ok"])
        self.assertIn("task workspace worktree is not ready", str(record["error"]))
        self.assertIn("workspace_create_task_worktree", str(record["error"]))

    def test_task_workspace_prepared_only_fails(self) -> None:
        task_workspaces.prepare_task_workspace(
            "task-prepared",
            cwd="project",
            project_id=self.project_id,
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        bundle_id = self.write_pending_bundle(
            cwd="project",
            metadata=self.task_metadata(task_id="task-prepared"),
            steps=[],
        )

        self.apply_bundle(bundle_id)

        self.assertIn("task workspace worktree is not ready", str(self.failed_record(bundle_id)["error"]))

    def test_task_workspace_requires_task_id(self) -> None:
        metadata = self.task_metadata()
        metadata.pop("task_id")
        bundle_id = self.write_pending_bundle(cwd="project", metadata=metadata, steps=[])

        self.apply_bundle(bundle_id)

        self.assertIn("requires task_id", str(self.failed_record(bundle_id)["error"]))

    def test_task_workspace_rejects_non_git_workspace_path(self) -> None:
        worktree = self.create_task_worktree("task-bad-path")
        record_path = Path(str(worktree["record_path"]))
        data = json.loads(record_path.read_text(encoding="utf-8"))
        data["workspace_path"] = str(self.runtime_root / "task_workspaces" / "not-a-worktree" / "repo")
        Path(str(data["workspace_path"])).mkdir(parents=True)
        runner.write_json(record_path, data)
        bundle_id = self.write_pending_bundle(
            cwd="project",
            metadata=self.task_metadata(task_id="task-bad-path"),
            steps=[],
        )

        self.apply_bundle(bundle_id)

        self.assertIn("workspace_path is not a git worktree", str(self.failed_record(bundle_id)["error"]))

    def test_task_workspace_rejects_workspace_path_outside_runtime_root(self) -> None:
        worktree = self.create_task_worktree("task-outside")
        record_path = Path(str(worktree["record_path"]))
        data = json.loads(record_path.read_text(encoding="utf-8"))
        data["workspace_path"] = str(self.workspace_root / "outside-worktree")
        runner.write_json(record_path, data)
        bundle_id = self.write_pending_bundle(
            cwd="project",
            metadata=self.task_metadata(task_id="task-outside"),
            steps=[],
        )

        self.apply_bundle(bundle_id)

        self.assertIn("workspace_path escapes task workspace root", str(self.failed_record(bundle_id)["error"]))

    def test_task_workspace_rejects_bundle_cwd_outside_source_git_root(self) -> None:
        (self.workspace_root / "other").mkdir()
        self.create_task_worktree("task-cwd-mismatch")
        bundle_id = self.write_pending_bundle(
            cwd="other",
            metadata=self.task_metadata(task_id="task-cwd-mismatch"),
            steps=[],
        )

        self.apply_bundle(bundle_id)

        self.assertIn("bundle cwd is outside task workspace source_git_root", str(self.failed_record(bundle_id)["error"]))


if __name__ == "__main__":
    unittest.main()
