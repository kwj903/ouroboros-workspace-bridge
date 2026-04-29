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

    def test_yolo_rejects_blocked_bundles(self) -> None:
        record = bundle_record(risk="blocked")

        self.assertFalse(approval_modes.should_auto_approve(record, "yolo"))

    def test_yolo_rejects_sensitive_paths(self) -> None:
        record = bundle_record(risk="high", steps=[{"type": "write_file", "risk": "medium", "path": ".env"}])

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
