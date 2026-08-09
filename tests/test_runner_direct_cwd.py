from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import command_bundle_runner as runner
from terminal_bridge import handoffs


class RunnerDirectCwdTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.workspace = root / "workspace"
        self.project = self.workspace / "project"
        self.project.mkdir(parents=True)
        self.runtime = root / "runtime"
        self.original_paths = {
            "WORKSPACE_ROOT": runner.WORKSPACE_ROOT,
            "RUNTIME_ROOT": runner.RUNTIME_ROOT,
            "COMMAND_BUNDLES_DIR": runner.COMMAND_BUNDLES_DIR,
            "PENDING_DIR": runner.PENDING_DIR,
            "RUNNING_DIR": runner.RUNNING_DIR,
            "APPLIED_DIR": runner.APPLIED_DIR,
            "REJECTED_DIR": runner.REJECTED_DIR,
            "FAILED_DIR": runner.FAILED_DIR,
            "INTERRUPTED_DIR": runner.INTERRUPTED_DIR,
            "BACKUP_DIR": runner.BACKUP_DIR,
            "TEXT_PAYLOAD_DIR": runner.TEXT_PAYLOAD_DIR,
        }
        self.original_handoff_dir = handoffs.HANDOFF_DIR
        runner.WORKSPACE_ROOT = self.workspace
        runner.RUNTIME_ROOT = self.runtime
        runner.COMMAND_BUNDLES_DIR = self.runtime / "command_bundles"
        runner.PENDING_DIR = runner.COMMAND_BUNDLES_DIR / "pending"
        runner.RUNNING_DIR = runner.COMMAND_BUNDLES_DIR / "running"
        runner.APPLIED_DIR = runner.COMMAND_BUNDLES_DIR / "applied"
        runner.REJECTED_DIR = runner.COMMAND_BUNDLES_DIR / "rejected"
        runner.FAILED_DIR = runner.COMMAND_BUNDLES_DIR / "failed"
        runner.INTERRUPTED_DIR = runner.COMMAND_BUNDLES_DIR / "interrupted"
        runner.BACKUP_DIR = self.runtime / "backups"
        runner.TEXT_PAYLOAD_DIR = self.runtime / "text_payloads"
        handoffs.HANDOFF_DIR = self.runtime / "handoffs"
        for directory in runner.bundle_dirs():
            directory.mkdir(parents=True)

    def tearDown(self) -> None:
        for name, value in self.original_paths.items():
            setattr(runner, name, value)
        handoffs.HANDOFF_DIR = self.original_handoff_dir
        self.tmp.cleanup()

    def write_pending(self, bundle_id: str) -> None:
        runner.write_json(
            runner.PENDING_DIR / f"{bundle_id}.json",
            {
                "version": 1,
                "bundle_id": bundle_id,
                "title": "Direct cwd",
                "cwd": "project",
                "status": "pending",
                "risk": "low",
                "approval_required": True,
                "steps": [
                    {
                        "type": "command",
                        "name": "status",
                        "argv": ["git", "status"],
                        "risk": "low",
                    }
                ],
            },
        )

    def test_apply_uses_one_resolved_workspace_cwd_and_emits_no_routing_identity(self) -> None:
        bundle_id = "cmd-direct-cwd"
        self.write_pending(bundle_id)
        observed_cwds: list[Path] = []

        def apply_step(cwd: Path, _step: dict[str, object]) -> dict[str, object]:
            observed_cwds.append(cwd)
            return {
                "type": "command",
                "name": "status",
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "truncated": False,
            }

        with (
            mock.patch.object(runner, "preview", return_value=None),
            mock.patch.object(runner, "apply_step", side_effect=apply_step),
        ):
            applied = runner.apply_bundle(bundle_id, yes=True)

        record = json.loads(
            (runner.APPLIED_DIR / f"{bundle_id}.json").read_text(encoding="utf-8")
        )
        self.assertTrue(applied)
        self.assertEqual(observed_cwds, [self.project.resolve()])
        self.assertEqual(record["result"]["cwd"], "project")
        self.assertNotIn("workspace_routing", record["result"])
        for retired_name in (
            "RunnerWorkspace",
            "_ACTIVE_RUNNER_WORKSPACE",
            "resolve_runner_workspace",
            "resolve_bundle_apply_cwd",
            "_map_source_path_for_apply",
        ):
            self.assertFalse(hasattr(runner, retired_name), retired_name)

    def test_legacy_record_keeps_historical_routing_output_readable(self) -> None:
        bundle_id = "cmd-legacy-routing"
        legacy = {
            "bundle_id": bundle_id,
            "status": "pending",
            "result": {
                "ok": True,
                "workspace_routing": {
                    "workspace_mode": "task-workspace",
                    "source_cwd": "project",
                    "actual_cwd": ".agent-workspaces/task-1",
                },
            },
        }
        runner.write_json(runner.APPLIED_DIR / f"{bundle_id}.json", legacy)

        path, loaded = runner.find_bundle(bundle_id)

        self.assertEqual(path.parent, runner.APPLIED_DIR)
        self.assertEqual(loaded["status"], "applied")
        self.assertEqual(
            loaded["result"]["workspace_routing"]["workspace_mode"], "task-workspace"
        )

    def test_patch_execution_uses_bundle_cwd_not_legacy_step_routing(self) -> None:
        observed_cwds: list[Path] = []

        def run_git_apply(
            cwd: Path,
            _args: list[str],
            _patch: str,
            _timeout_seconds: int = 30,
        ) -> dict[str, object]:
            observed_cwds.append(cwd)
            return {
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "truncated": False,
            }

        with (
            mock.patch.object(runner, "step_patch_paths", return_value=[]),
            mock.patch.object(runner, "validate_patch_paths", return_value=None),
            mock.patch.object(runner, "run_git_apply", side_effect=run_git_apply),
        ):
            result = runner.apply_patch_step(
                self.project.resolve(),
                {
                    "name": "Legacy patch",
                    "patch": "legacy patch text",
                    "cwd": ".agent-workspaces/retired",
                },
            )

        self.assertEqual(observed_cwds, [self.project.resolve(), self.project.resolve()])
        self.assertEqual(result["cwd"], "project")


if __name__ == "__main__":
    unittest.main()
