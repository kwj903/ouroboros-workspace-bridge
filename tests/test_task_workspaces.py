from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import server
from terminal_bridge import task_workspaces
from terminal_bridge.models import (
    TaskWorkspaceListResult,
    TaskWorkspaceStatusResult,
    TaskWorktreeInspectionResult,
    TaskWorktreeMergePreflightResult,
)


class TaskWorkspaceTests(unittest.TestCase):
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
        self.run_git(self.project, ["config", "user.email", "task-workspace@example.test"])
        self.run_git(self.project, ["config", "user.name", "Task Workspace Test"])
        (self.project / "README.md").write_text("hello\n", encoding="utf-8")
        self.run_git(self.project, ["add", "README.md"])
        self.run_git(self.project, ["commit", "-m", "initial commit"])

    def test_prepare_rejects_missing_task_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "task_id cannot be empty"):
            task_workspaces.prepare_task_workspace(
                "",
                cwd="project",
                project_id="project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_prepare_rejects_unsafe_task_id(self) -> None:
        for task_id in ("../task-a", "task/a", ".", "task a"):
            with self.subTest(task_id=task_id):
                with self.assertRaises(ValueError):
                    task_workspaces.prepare_task_workspace(
                        task_id,
                        cwd="project",
                        project_id="project-alpha",
                        runtime_root=self.runtime_root,
                        workspace_root=self.workspace_root,
                    )

    def test_prepare_rejects_source_cwd_outside_workspace_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "escapes WORKSPACE_ROOT"):
            task_workspaces.prepare_task_workspace(
                "task-a",
                cwd="../outside",
                project_id="project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_create_worktree_rejects_non_git_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a git repository"):
            task_workspaces.create_task_worktree(
                "task-a",
                cwd="project",
                project_id="project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_create_worktree_rejects_unsafe_project_id(self) -> None:
        self.init_git_project()

        with self.assertRaisesRegex(ValueError, "project_id cannot contain path separators"):
            task_workspaces.create_task_worktree(
                "task-a",
                cwd="project",
                project_id="../project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_create_worktree_rejects_unknown_files_in_target_path(self) -> None:
        self.init_git_project()
        prepared = task_workspaces.prepare_task_workspace(
            "task-a",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        workspace_path = Path(str(prepared["workspace_path"]))
        (workspace_path / "unexpected.txt").write_text("do not overwrite\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "not empty"):
            task_workspaces.create_task_worktree(
                "task-a",
                cwd="project",
                project_id="project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_create_worktree_invokes_expected_git_worktree_add_argv(self) -> None:
        calls: list[list[str]] = []
        head_sha = "a" * 40

        def fake_git(argv: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            if argv[-2:] == ["rev-parse", "--show-toplevel"]:
                return subprocess.CompletedProcess(argv, 0, stdout=f"{self.project}\n", stderr="")
            if argv[-3:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return subprocess.CompletedProcess(argv, 0, stdout="main\n", stderr="")
            if argv[-2:] == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(argv, 0, stdout=f"{head_sha}\n", stderr="")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        record = task_workspaces.create_task_worktree(
            "task-a",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
            git_runner=fake_git,
        )

        worktree_add = [call for call in calls if call[3:5] == ["worktree", "add"]]
        self.assertEqual(len(worktree_add), 1)
        self.assertEqual(worktree_add[0][0:3], ["git", "-C", str(self.project.resolve())])
        self.assertEqual(worktree_add[0][5], "-b")
        self.assertEqual(worktree_add[0][6], record["worktree_branch"])
        self.assertEqual(worktree_add[0][7], record["workspace_path"])
        self.assertEqual(worktree_add[0][8], head_sha)
        self.assertEqual(record["status"], "worktree")
        self.assertEqual(record["worktree_status"], "ready")
        self.assertEqual(record["base_ref"], "main")
        self.assertEqual(record["base_sha"], head_sha)

    def test_create_worktree_integration_and_idempotent_refresh(self) -> None:
        self.init_git_project()

        first = task_workspaces.create_task_worktree(
            "task-real",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        (self.project / "later.txt").write_text("later\n", encoding="utf-8")
        self.run_git(self.project, ["add", "later.txt"])
        self.run_git(self.project, ["commit", "-m", "later commit"])
        second = task_workspaces.create_task_worktree(
            "task-real",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        workspace_path = Path(str(first["workspace_path"]))
        self.assertEqual(first["workspace_key"], second["workspace_key"])
        self.assertEqual(first["status"], "worktree")
        self.assertEqual(second["status"], "worktree")
        self.assertEqual(first["worktree_branch"], second["worktree_branch"])
        self.assertEqual(first["base_sha"], second["base_sha"])
        self.assertEqual(first["source_cwd"], "project")
        self.assertEqual(first["project_id"], "project-alpha")
        self.assertEqual(first["workspace_mode"], "task-workspace")
        self.assertEqual(first["worktree_status"], "ready")
        self.assertTrue(str(first["base_sha"]))
        self.assertTrue(str(first["base_ref"]))
        self.assertTrue((workspace_path / ".git").exists())
        self.assertTrue(workspace_path.is_relative_to((self.runtime_root / "task_workspaces").resolve()))

    def test_create_worktree_uses_existing_empty_prepared_directory(self) -> None:
        self.init_git_project()
        prepared = task_workspaces.prepare_task_workspace(
            "task-prepared",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        created = task_workspaces.create_task_worktree(
            "task-prepared",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertEqual(created["workspace_path"], prepared["workspace_path"])
        self.assertEqual(created["status"], "worktree")
        self.assertTrue((Path(str(created["workspace_path"])) / ".git").exists())

    def test_inspect_task_worktree_clean_ready_worktree(self) -> None:
        self.init_git_project()
        task_workspaces.create_task_worktree(
            "task-inspect-clean",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        inspected = task_workspaces.inspect_task_worktree(
            "task-inspect-clean",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertEqual(inspected["status"], "worktree")
        self.assertFalse(inspected["dirty"])
        self.assertEqual(inspected["git_status_short"], "")
        self.assertEqual(inspected["diff_stat"], "")
        self.assertEqual(inspected["changed_files"], [])

    def test_inspect_task_worktree_reports_status_and_diff(self) -> None:
        self.init_git_project()
        record = task_workspaces.create_task_worktree(
            "task-inspect-dirty",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        workspace_path = Path(str(record["workspace_path"]))
        (workspace_path / "README.md").write_text("hello\nchanged\n", encoding="utf-8")
        (workspace_path / "new.txt").write_text("new\n", encoding="utf-8")

        inspected = task_workspaces.inspect_task_worktree(
            "task-inspect-dirty",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        changed_paths = {str(item["path"]) for item in inspected["changed_files"]}
        self.assertTrue(inspected["dirty"])
        self.assertIn("README.md", inspected["git_status_short"])
        self.assertIn("?? new.txt", inspected["git_status_short"])
        self.assertIn("README.md", inspected["diff_stat"])
        self.assertIn("README.md", changed_paths)
        self.assertIn("new.txt", changed_paths)
        self.assertEqual(inspected["changed_file_count"], 2)
        self.assertEqual(self.run_git(self.project, ["status", "--porcelain"]).stdout, "")

    def test_inspect_task_worktree_rejects_missing_record(self) -> None:
        self.init_git_project()

        with self.assertRaisesRegex(ValueError, "task workspace worktree is not ready"):
            task_workspaces.inspect_task_worktree(
                "task-missing",
                cwd="project",
                project_id="project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_inspect_task_worktree_rejects_prepared_only_record(self) -> None:
        self.init_git_project()
        task_workspaces.prepare_task_workspace(
            "task-prepared-only",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        with self.assertRaisesRegex(ValueError, "task workspace worktree is not ready"):
            task_workspaces.inspect_task_worktree(
                "task-prepared-only",
                cwd="project",
                project_id="project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_inspect_task_worktree_rejects_non_git_workspace_path(self) -> None:
        self.init_git_project()
        record = task_workspaces.create_task_worktree(
            "task-non-git",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        record_path = Path(str(record["record_path"]))
        data = json.loads(record_path.read_text(encoding="utf-8"))
        data["workspace_path"] = str(self.runtime_root / "task_workspaces" / "not-a-worktree" / "repo")
        Path(str(data["workspace_path"])).mkdir(parents=True)
        record_path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "workspace_path is not a git worktree"):
            task_workspaces.inspect_task_worktree(
                "task-non-git",
                cwd="project",
                project_id="project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_inspect_task_worktree_rejects_workspace_path_escape(self) -> None:
        self.init_git_project()
        record = task_workspaces.create_task_worktree(
            "task-escape",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        record_path = Path(str(record["record_path"]))
        data = json.loads(record_path.read_text(encoding="utf-8"))
        data["workspace_path"] = str(self.workspace_root / "outside-worktree")
        record_path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "workspace_path escapes task workspace root"):
            task_workspaces.inspect_task_worktree(
                "task-escape",
                cwd="project",
                project_id="project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_inspect_task_worktree_rejects_git_command_failure(self) -> None:
        self.init_git_project()
        task_workspaces.create_task_worktree(
            "task-git-failure",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        def failing_git(argv: list[str]) -> subprocess.CompletedProcess[str]:
            raise subprocess.CalledProcessError(128, argv, output="", stderr="not a git repository")

        with self.assertRaisesRegex(RuntimeError, "git status --short failed: not a git repository"):
            task_workspaces.inspect_task_worktree(
                "task-git-failure",
                cwd="project",
                project_id="project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
                git_runner=failing_git,
            )

    def test_merge_preflight_ready_when_source_unchanged(self) -> None:
        self.init_git_project()
        record = task_workspaces.create_task_worktree(
            "task-preflight-ready",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        workspace_path = Path(str(record["workspace_path"]))
        (workspace_path / "README.md").write_text("hello\nready\n", encoding="utf-8")

        preflight = task_workspaces.merge_preflight_task_worktree(
            "task-preflight-ready",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertTrue(preflight["ready_to_merge"])
        self.assertEqual(preflight["conflict_risk"], "low")
        self.assertEqual(preflight["recommended_action"], "merge_queue")
        self.assertFalse(preflight["source_head_changed"])
        self.assertFalse(preflight["source_dirty"])
        self.assertEqual(preflight["overlapping_files"], [])

    def test_merge_preflight_no_changes_is_not_ready(self) -> None:
        self.init_git_project()
        task_workspaces.create_task_worktree(
            "task-preflight-clean",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        preflight = task_workspaces.merge_preflight_task_worktree(
            "task-preflight-clean",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertFalse(preflight["ready_to_merge"])
        self.assertEqual(preflight["conflict_risk"], "none")
        self.assertEqual(preflight["recommended_action"], "no_changes")

    def test_merge_preflight_detects_overlapping_source_changes(self) -> None:
        self.init_git_project()
        record = task_workspaces.create_task_worktree(
            "task-preflight-overlap",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        workspace_path = Path(str(record["workspace_path"]))
        (workspace_path / "README.md").write_text("hello\ntask\n", encoding="utf-8")
        (self.project / "README.md").write_text("hello\nsource\n", encoding="utf-8")
        self.run_git(self.project, ["add", "README.md"])
        self.run_git(self.project, ["commit", "-m", "source README change"])

        preflight = task_workspaces.merge_preflight_task_worktree(
            "task-preflight-overlap",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertFalse(preflight["ready_to_merge"])
        self.assertTrue(preflight["source_head_changed"])
        self.assertEqual(preflight["conflict_risk"], "high")
        self.assertEqual(preflight["recommended_action"], "manual_conflict_review")
        self.assertEqual(preflight["overlapping_files"], ["README.md"])

    def test_merge_preflight_detects_source_dirty_state(self) -> None:
        self.init_git_project()
        record = task_workspaces.create_task_worktree(
            "task-preflight-source-dirty",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        workspace_path = Path(str(record["workspace_path"]))
        (workspace_path / "README.md").write_text("hello\ntask\n", encoding="utf-8")
        (self.project / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        preflight = task_workspaces.merge_preflight_task_worktree(
            "task-preflight-source-dirty",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertFalse(preflight["ready_to_merge"])
        self.assertTrue(preflight["source_dirty"])
        self.assertEqual(preflight["conflict_risk"], "high")
        self.assertEqual(preflight["recommended_action"], "clean_source_before_merge")

    def test_merge_preflight_reuses_inspection_readiness_checks(self) -> None:
        self.init_git_project()

        with self.assertRaisesRegex(ValueError, "task workspace worktree is not ready"):
            task_workspaces.merge_preflight_task_worktree(
                "task-preflight-missing",
                cwd="project",
                project_id="project-alpha",
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_archive_task_workspace_marks_record_without_deleting_worktree(self) -> None:
        self.init_git_project()
        record = task_workspaces.create_task_worktree(
            "task-archive",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        workspace_path = Path(str(record["workspace_path"]))

        archived = task_workspaces.archive_task_workspace(
            "task-archive",
            cwd="project",
            project_id="project-alpha",
            reason="done",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertEqual(archived["status"], "archived")
        self.assertEqual(archived["archive_reason"], "done")
        self.assertTrue(workspace_path.exists())
        stored = task_workspaces.read_task_workspace(
            "task-archive",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        self.assertEqual(stored["status"], "archived")

    def test_prepare_read_list_and_deterministic_key(self) -> None:
        first = task_workspaces.prepare_task_workspace(
            "task-a",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        second = task_workspaces.prepare_task_workspace(
            "task-a",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertEqual(first["workspace_key"], second["workspace_key"])
        self.assertEqual(first["workspace_path"], second["workspace_path"])
        self.assertEqual(first["status"], "created")
        self.assertEqual(first["workspace_mode"], "task-workspace")
        self.assertEqual(first["source_cwd"], "project")
        self.assertEqual(first["project_id"], "project-alpha")
        self.assertTrue(Path(str(first["workspace_path"])).is_dir())
        self.assertTrue(Path(str(first["record_path"])).is_file())

        read = task_workspaces.read_task_workspace(
            "task-a",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        self.assertEqual(read["workspace_key"], first["workspace_key"])
        self.assertTrue(read["exists"])

        listed = task_workspaces.list_task_workspaces(
            project_id="project-alpha",
            runtime_root=self.runtime_root,
        )
        self.assertEqual([item["workspace_key"] for item in listed], [first["workspace_key"]])

    def test_different_task_ids_use_different_workspace_paths(self) -> None:
        first = task_workspaces.prepare_task_workspace(
            "task-a",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        second = task_workspaces.prepare_task_workspace(
            "task-b",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertNotEqual(first["workspace_key"], second["workspace_key"])
        self.assertNotEqual(first["workspace_path"], second["workspace_path"])

    def test_resolve_direct_mode_skips_workspace_lookup(self) -> None:
        resolution = task_workspaces.resolve_task_workspace_for_bundle(
            {
                "cwd": "project",
                "metadata": {
                    "workspace_mode": "direct",
                    "task_id": "task-a",
                    "project_id": "project-alpha",
                },
            },
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )

        self.assertEqual(resolution.status, "skipped")
        self.assertEqual(resolution.reason, "direct-mode")
        self.assertFalse(resolution.exists)

    def test_resolve_task_workspace_found_and_missing(self) -> None:
        record = {
            "cwd": "project",
            "metadata": {
                "workspace_mode": "task-workspace",
                "task_id": "task-a",
                "project_id": "project-alpha",
                "source_cwd": "project",
            },
        }

        missing = task_workspaces.resolve_task_workspace_for_bundle(
            record,
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        self.assertEqual(missing.status, "missing")
        self.assertFalse(missing.exists)

        task_workspaces.prepare_task_workspace(
            "task-a",
            cwd="project",
            project_id="project-alpha",
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        found = task_workspaces.resolve_task_workspace_for_bundle(
            record,
            runtime_root=self.runtime_root,
            workspace_root=self.workspace_root,
        )
        self.assertEqual(found.status, "created")
        self.assertTrue(found.exists)

    def test_resolve_task_workspace_rejects_missing_task_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires task_id"):
            task_workspaces.resolve_task_workspace_for_bundle(
                {"cwd": "project", "metadata": {"workspace_mode": "task-workspace"}},
                runtime_root=self.runtime_root,
                workspace_root=self.workspace_root,
            )

    def test_server_public_wrappers_call_task_workspace_helpers(self) -> None:
        original_record = server._record_tool_call
        original_prepare = server._prepare_task_workspace
        original_read = server._read_task_workspace
        original_list = server._list_task_workspaces
        original_create = server._create_task_worktree
        original_inspect = server._inspect_task_worktree
        original_merge_preflight = server._merge_preflight_task_worktree
        calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

        def call_through(tool_name: str, args: dict[str, object], action: object) -> object:
            return action()

        def fake_record(task_id: str = "task-a", project_id: str = "project-alpha") -> dict[str, object]:
            return {
                "task_id": task_id,
                "project_id": project_id,
                "source_cwd": "project",
                "workspace_mode": "task-workspace",
                "workspace_key": f"{task_id}-123456789abc",
                "workspace_path": "/tmp/workspace/repo",
                "record_path": "/tmp/workspace/workspace.json",
                "worktree_branch": f"task/{task_id}-123456789abc",
                "status": "created",
                "exists": True,
                "created_at": "2026-06-02T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            }

        def fake_prepare(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append(("prepare", args, kwargs))
            return fake_record()

        def fake_read(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append(("read", args, kwargs))
            return fake_record()

        def fake_list(*args: object, **kwargs: object) -> list[dict[str, object]]:
            calls.append(("list", args, kwargs))
            return [fake_record()]

        def fake_create(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append(("create", args, kwargs))
            return fake_record()

        def fake_inspect(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append(("inspect", args, kwargs))
            record = fake_record()
            return {
                **record,
                "dirty": True,
                "changed_file_count": 1,
                "git_status_short": " M README.md",
                "diff_stat": " README.md | 1 +",
                "diff_name_status": "M\tREADME.md",
                "changed_files": [{"status": "M", "path": "README.md"}],
            }

        def fake_merge_preflight(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append(("merge_preflight", args, kwargs))
            record = fake_record()
            return {
                **record,
                "dirty": True,
                "changed_file_count": 1,
                "git_status_short": " M README.md",
                "diff_stat": " README.md | 1 +",
                "diff_name_status": "M\tREADME.md",
                "changed_files": [{"status": "M", "path": "README.md"}],
                "source_head_sha": "b" * 40,
                "source_head_changed": False,
                "source_dirty": False,
                "source_git_status_short": "",
                "source_diff_name_status": "",
                "source_changed_files": [],
                "overlapping_files": [],
                "ready_to_merge": True,
                "conflict_risk": "low",
                "recommended_action": "merge_queue",
            }

        server._record_tool_call = call_through
        server._prepare_task_workspace = fake_prepare
        server._read_task_workspace = fake_read
        server._list_task_workspaces = fake_list
        server._create_task_worktree = fake_create
        server._inspect_task_worktree = fake_inspect
        server._merge_preflight_task_worktree = fake_merge_preflight
        try:
            prepared = server.workspace_prepare_task_workspace("task-a", cwd="project", project_id="project-alpha")
            status = server.workspace_task_workspace_status("task-a", cwd="project", project_id="project-alpha")
            listed = server.workspace_list_task_workspaces(project_id="project-alpha")
            created = server.workspace_create_task_worktree("task-a", cwd="project", project_id="project-alpha")
            inspected = server.workspace_inspect_task_worktree("task-a", cwd="project", project_id="project-alpha")
            preflight = server.workspace_merge_preflight_task_worktree("task-a", cwd="project", project_id="project-alpha")
        finally:
            server._record_tool_call = original_record
            server._prepare_task_workspace = original_prepare
            server._read_task_workspace = original_read
            server._list_task_workspaces = original_list
            server._create_task_worktree = original_create
            server._inspect_task_worktree = original_inspect
            server._merge_preflight_task_worktree = original_merge_preflight

        self.assertIsInstance(prepared, TaskWorkspaceStatusResult)
        self.assertIsInstance(status, TaskWorkspaceStatusResult)
        self.assertIsInstance(listed, TaskWorkspaceListResult)
        self.assertIsInstance(created, TaskWorkspaceStatusResult)
        self.assertIsInstance(inspected, TaskWorktreeInspectionResult)
        self.assertIsInstance(preflight, TaskWorktreeMergePreflightResult)
        self.assertEqual([call[0] for call in calls], ["prepare", "read", "list", "create", "inspect", "merge_preflight"])
        self.assertEqual(calls[0][1], ("task-a",))
        self.assertEqual(calls[0][2], {"cwd": "project", "project_id": "project-alpha"})
        self.assertEqual(calls[4][2], {"cwd": "project", "project_id": "project-alpha"})
        self.assertEqual(calls[5][2], {"cwd": "project", "project_id": "project-alpha"})
        self.assertEqual(listed.count, 1)
        self.assertTrue(inspected.dirty)
        self.assertEqual(inspected.changed_file_count, 1)
        self.assertTrue(preflight.ready_to_merge)


if __name__ == "__main__":
    unittest.main()
