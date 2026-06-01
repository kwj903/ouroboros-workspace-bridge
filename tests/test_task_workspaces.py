from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import server
from terminal_bridge import task_workspaces
from terminal_bridge.models import TaskWorkspaceListResult, TaskWorkspaceStatusResult


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

        server._record_tool_call = call_through
        server._prepare_task_workspace = fake_prepare
        server._read_task_workspace = fake_read
        server._list_task_workspaces = fake_list
        try:
            prepared = server.workspace_prepare_task_workspace("task-a", cwd="project", project_id="project-alpha")
            status = server.workspace_task_workspace_status("task-a", cwd="project", project_id="project-alpha")
            listed = server.workspace_list_task_workspaces(project_id="project-alpha")
        finally:
            server._record_tool_call = original_record
            server._prepare_task_workspace = original_prepare
            server._read_task_workspace = original_read
            server._list_task_workspaces = original_list

        self.assertIsInstance(prepared, TaskWorkspaceStatusResult)
        self.assertIsInstance(status, TaskWorkspaceStatusResult)
        self.assertIsInstance(listed, TaskWorkspaceListResult)
        self.assertEqual([call[0] for call in calls], ["prepare", "read", "list"])
        self.assertEqual(calls[0][1], ("task-a",))
        self.assertEqual(calls[0][2], {"cwd": "project", "project_id": "project-alpha"})
        self.assertEqual(listed.count, 1)


if __name__ == "__main__":
    unittest.main()
