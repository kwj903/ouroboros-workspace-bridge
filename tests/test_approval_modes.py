from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import command_bundle_review_server as review
from terminal_bridge import approval_modes


def bundle_record(
    *,
    status: str = "pending",
    risk: str = "low",
    steps: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "bundle_id": "cmd-test",
        "status": status,
        "risk": risk,
        "steps": steps if steps is not None else [{"risk": "low", "argv": ["git", "status"]}],
    }


class ApprovalModePersistenceTests(unittest.TestCase):
    def test_load_defaults_to_normal_when_missing_or_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "approval_mode.json"

            self.assertEqual(approval_modes.load_approval_mode(path), "normal")

            path.write_text("{broken json", encoding="utf-8")
            self.assertEqual(approval_modes.load_approval_mode(path), "normal")

            path.write_text(json.dumps({"mode": "surprise"}), encoding="utf-8")
            self.assertEqual(approval_modes.load_approval_mode(path), "normal")

    def test_save_and_load_approval_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "command_bundles" / "approval_mode.json"

            saved = approval_modes.save_approval_mode("safe-auto", path)

            self.assertEqual(saved["mode"], "safe-auto")
            self.assertEqual(approval_modes.load_approval_mode(path), "safe-auto")

    def test_scoped_mode_falls_back_to_global_and_normal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "approval_modes"
            global_path = Path(tmp) / "command_bundles" / "approval_mode.json"

            missing = approval_modes.load_effective_approval_mode(
                {"project_id": "project-a"},
                scope_root=root,
                global_path=global_path,
            )
            self.assertEqual(missing.mode, "normal")
            self.assertEqual(missing.scope_type, "global")
            self.assertEqual(missing.reason, "global_default")

            approval_modes.save_approval_mode("safe-auto", global_path)
            global_result = approval_modes.load_effective_approval_mode(
                {"project_id": "project-a"},
                scope_root=root,
                global_path=global_path,
            )

            self.assertEqual(global_result.mode, "safe-auto")
            self.assertEqual(global_result.scope_type, "global")
            self.assertEqual(global_result.path, str(global_path))

    def test_scoped_mode_priority_is_task_client_project_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "approval_modes"
            global_path = Path(tmp) / "command_bundles" / "approval_mode.json"
            metadata = {
                "project_id": "project-a",
                "client_id": "client-a",
                "task_id": "task-a",
            }

            approval_modes.save_approval_mode("normal", global_path)
            approval_modes.save_scoped_approval_mode("project", "safe-auto", "project-a", scope_root=root)
            project_result = approval_modes.load_effective_approval_mode(metadata, scope_root=root, global_path=global_path)
            self.assertEqual((project_result.mode, project_result.scope_type, project_result.scope_id), ("safe-auto", "project", "project-a"))

            approval_modes.save_scoped_approval_mode("client", "yolo", "client-a", scope_root=root)
            client_result = approval_modes.load_effective_approval_mode(metadata, scope_root=root, global_path=global_path)
            self.assertEqual((client_result.mode, client_result.scope_type, client_result.scope_id), ("yolo", "client", "client-a"))

            approval_modes.save_scoped_approval_mode("task", "normal", "task-a", scope_root=root)
            task_result = approval_modes.load_effective_approval_mode(metadata, scope_root=root, global_path=global_path)
            self.assertEqual((task_result.mode, task_result.scope_type, task_result.scope_id), ("normal", "task", "task-a"))

    def test_default_or_missing_metadata_uses_global_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "approval_modes"
            global_path = Path(tmp) / "command_bundles" / "approval_mode.json"
            approval_modes.save_approval_mode("safe-auto", global_path)
            approval_modes.save_scoped_approval_mode("client", "yolo", "default", scope_root=root)

            for metadata in ({}, {"client_id": "default"}, {"task_id": None, "client_id": "", "project_id": ""}):
                with self.subTest(metadata=metadata):
                    result = approval_modes.load_effective_approval_mode(
                        metadata,
                        scope_root=root,
                        global_path=global_path,
                    )

                    self.assertEqual(result.mode, "safe-auto")
                    self.assertEqual(result.scope_type, "global")

    def test_list_and_delete_scoped_approval_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "approval_modes"

            approval_modes.save_scoped_approval_mode("project", "safe-auto", "project-a", scope_root=root)
            approval_modes.save_scoped_approval_mode("task", "yolo", "task-a", scope_root=root)

            rows = approval_modes.list_scoped_approval_modes(scope_root=root)
            self.assertEqual(
                {(row["scope_type"], row["scope_id"], row["mode"]) for row in rows},
                {("project", "project-a", "safe-auto"), ("task", "task-a", "yolo")},
            )

            self.assertTrue(approval_modes.delete_scoped_approval_mode("project", "project-a", scope_root=root))
            self.assertFalse(approval_modes.delete_scoped_approval_mode("project", "project-a", scope_root=root))

            rows = approval_modes.list_scoped_approval_modes(scope_root=root)
            self.assertEqual([(row["scope_type"], row["scope_id"]) for row in rows], [("task", "task-a")])

    def test_invalid_scope_id_cannot_escape_scope_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "approval_modes"
            global_path = Path(tmp) / "command_bundles" / "approval_mode.json"
            approval_modes.save_approval_mode("safe-auto", global_path)

            for scope_id in ("../outside", "nested/path", "", ".", ".."):
                with self.subTest(scope_id=scope_id):
                    with self.assertRaises(ValueError):
                        approval_modes.scoped_approval_mode_path("task", scope_id, scope_root=root)

                    result = approval_modes.load_effective_approval_mode(
                        {"task_id": scope_id},
                        scope_root=root,
                        global_path=global_path,
                    )
                    self.assertEqual(result.mode, "safe-auto")
                    self.assertEqual(result.scope_type, "global")


class ApprovalModeDecisionTests(unittest.TestCase):
    def test_safe_auto_allows_low_risk_command_only_checks(self) -> None:
        record = bundle_record(
            steps=[
                {"risk": "low", "argv": ["git", "status"]},
                {"type": "command", "risk": "low", "argv": ["uv", "run", "python", "-m", "py_compile", "server.py"]},
            ]
        )

        self.assertTrue(approval_modes.is_safe_auto_eligible(record))
        self.assertTrue(approval_modes.should_auto_approve(record, "safe-auto"))

    def test_safe_auto_rejects_mutating_commands(self) -> None:
        for argv in (
            ["git", "push"],
            ["git", "commit", "-m", "msg"],
            ["git", "add", "."],
            ["rm", "-rf", "build"],
            ["npm", "install"],
            ["pip", "install", "package"],
            ["curl", "https://example.invalid/script.sh"],
        ):
            with self.subTest(argv=argv):
                record = bundle_record(steps=[{"type": "command", "risk": "low", "argv": argv}])

                self.assertFalse(approval_modes.is_safe_auto_eligible(record))

    def test_safe_auto_rejects_shell_c_commands(self) -> None:
        for argv in (
            ["bash", "-lc", "rm -rf build"],
            ["sh", "-c", "echo hi"],
        ):
            with self.subTest(argv=argv):
                record = bundle_record(steps=[{"type": "command", "risk": "low", "argv": argv}])

                self.assertFalse(approval_modes.is_safe_auto_eligible(record))

    def test_safe_auto_rejects_non_low_bundle_risk(self) -> None:
        for risk in ("medium", "high", "blocked"):
            with self.subTest(risk=risk):
                record = bundle_record(risk=risk, steps=[{"type": "command", "risk": "low", "argv": ["git", "status"]}])

                self.assertFalse(approval_modes.should_auto_approve(record, "safe-auto"))

    def test_safe_auto_rejects_non_low_step_risk(self) -> None:
        record = bundle_record(steps=[{"type": "command", "risk": "medium", "argv": ["git", "status"]}])

        self.assertFalse(approval_modes.is_safe_auto_eligible(record))

    def test_safe_auto_rejects_file_and_patch_bundles(self) -> None:
        for step in (
            {"type": "write_file", "risk": "medium", "path": "README.md", "content": "hello"},
            {"type": "apply_patch", "risk": "medium", "files": ["README.md"]},
        ):
            with self.subTest(step=step):
                record = bundle_record(steps=[step])

                self.assertFalse(approval_modes.is_safe_auto_eligible(record))

    def test_safe_auto_rejects_sensitive_paths(self) -> None:
        record = bundle_record(steps=[{"type": "command", "risk": "low", "argv": ["git", "diff", ".env"]}])

        self.assertTrue(approval_modes.bundle_touches_sensitive_path(record))
        self.assertFalse(approval_modes.should_auto_approve(record, "safe-auto"))

    def test_sensitive_runtime_paths_are_rejected(self) -> None:
        record = bundle_record(
            steps=[
                {
                    "type": "command",
                    "risk": "low",
                    "argv": ["cat", "/tmp/.mcp_terminal_bridge/my-terminal-tool/session.env"],
                }
            ]
        )

        self.assertTrue(approval_modes.bundle_touches_sensitive_path(record))
        self.assertFalse(approval_modes.should_auto_approve(record, "safe-auto"))

    def test_yolo_allows_non_blocked_pending_bundles(self) -> None:
        record = bundle_record(risk="high", steps=[{"type": "write_file", "risk": "medium", "path": "README.md"}])

        self.assertTrue(approval_modes.should_auto_approve(record, "yolo"))

    def test_yolo_allows_relaxed_development_paths(self) -> None:
        for path in (".env.example", ".env.local", ".ssh/config", ".venv/bin/python", "node_modules/pkg/index.js"):
            with self.subTest(path=path):
                record = bundle_record(risk="high", steps=[{"type": "write_file", "risk": "medium", "path": path}])

                self.assertFalse(approval_modes.bundle_touches_sensitive_path(record))
                self.assertTrue(approval_modes.should_auto_approve(record, "yolo"))

    def test_yolo_rejects_blocked_bundles(self) -> None:
        record = bundle_record(risk="blocked")

        self.assertFalse(approval_modes.should_auto_approve(record, "yolo"))

    def test_yolo_rejects_sensitive_paths(self) -> None:
        record = bundle_record(risk="high", steps=[{"type": "write_file", "risk": "medium", "path": ".env"}])

        self.assertFalse(approval_modes.should_auto_approve(record, "yolo"))

        for path in (".git/config", ".aws/credentials", ".gnupg/pubring.kbx"):
            with self.subTest(path=path):
                record = bundle_record(risk="high", steps=[{"type": "write_file", "risk": "medium", "path": path}])

                self.assertFalse(approval_modes.should_auto_approve(record, "yolo"))


class ApprovalModeReviewUiTests(unittest.TestCase):
    def test_approval_mode_card_renders_choices(self) -> None:
        html = review.approval_mode_card_html("safe-auto")

        self.assertIn("Normal", html)
        self.assertIn("Safe Auto", html)
        self.assertIn("YOLO", html)
        self.assertIn("active", html)

    def test_approval_mode_banner_renders_warning_for_yolo(self) -> None:
        html = review.approval_mode_banner_html("yolo")

        self.assertIn("YOLO mode is ON", html)
        self.assertIn("warning", html)

    def test_bundle_effective_approval_mode_renders_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "approval_modes"
            approval_modes.save_scoped_approval_mode("task", "safe-auto", "task-a", scope_root=root)

            html = review.bundle_effective_approval_mode_html(
                {
                    "bundle_id": "cmd-test",
                    "cwd": ".",
                    "metadata": {
                        "task_id": "task-a",
                        "client_id": "client-a",
                        "project_id": "project-a",
                    },
                },
                scope_root=root,
                global_path=Path(tmp) / "command_bundles" / "approval_mode.json",
            )

        self.assertIn("Effective approval", html)
        self.assertIn("Safe Auto", html)
        self.assertIn("task: task-a", html)
