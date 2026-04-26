from __future__ import annotations

import shutil
import unittest
from uuid import uuid4

from terminal_bridge import (
    bundle_serialization,
    commands,
    config,
    operations,
    patches,
    payloads,
    safety,
    tasks,
)
from terminal_bridge.models import CommandBundleAction, CommandBundleStep


class RefactoredSafetyHelperTests(unittest.TestCase):
    def test_resolves_workspace_paths(self) -> None:
        self.assertEqual(safety._resolve_workspace_path("."), config.WORKSPACE_ROOT)

        project_rel = config.PROJECT_ROOT.relative_to(config.WORKSPACE_ROOT)
        self.assertEqual(safety._resolve_workspace_path(str(project_rel)), config.PROJECT_ROOT)

    def test_rejects_unsafe_workspace_paths(self) -> None:
        with self.assertRaises(ValueError):
            safety._resolve_workspace_path("/tmp")

        with self.assertRaises(ValueError):
            safety._resolve_workspace_path("../outside")

        with self.assertRaises(PermissionError):
            safety._resolve_workspace_path(".env")

    def test_relative_workspace_root(self) -> None:
        self.assertEqual(safety._relative(config.WORKSPACE_ROOT), ".")


class RefactoredCommandHelperTests(unittest.TestCase):
    def test_validate_exec_argv(self) -> None:
        with self.assertRaises(ValueError):
            commands._validate_exec_argv([])

        self.assertEqual(
            commands._validate_exec_argv(["git", "status", "--short"]),
            ["git", "status", "--short"],
        )

    def test_classifies_exec_commands(self) -> None:
        risk, _reason = commands._classify_exec_command(
            config.PROJECT_ROOT,
            ["git", "status", "--short"],
        )
        self.assertEqual(risk, "low")

        risk, reason = commands._classify_exec_command(config.PROJECT_ROOT, ["sudo", "ls"])
        self.assertEqual(risk, "blocked")
        self.assertIn("sudo", reason)

        risk, _reason = commands._classify_exec_command(config.PROJECT_ROOT, ["git", "push"])
        self.assertIn(risk, {"medium", "high"})


class RefactoredPayloadHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload_ids: list[str] = []

    def tearDown(self) -> None:
        for payload_id in self.payload_ids:
            shutil.rmtree(payloads._text_payload_dir(payload_id), ignore_errors=True)

    def _payload_id(self) -> str:
        payload_id = f"txt-refactored-helper-{uuid4().hex[:8]}"
        self.payload_ids.append(payload_id)
        return payload_id

    def test_stages_one_complete_payload_chunk(self) -> None:
        payload_id = self._payload_id()

        result = payloads._stage_text_payload_chunk(
            payload_id=payload_id,
            chunk_index=0,
            total_chunks=1,
            text="single chunk",
        )

        self.assertTrue(result.complete)
        self.assertEqual(result.total_chars, len("single chunk"))

    def test_stages_two_payload_chunks(self) -> None:
        payload_id = self._payload_id()

        first = payloads._stage_text_payload_chunk(
            payload_id=payload_id,
            chunk_index=0,
            total_chunks=2,
            text="hello ",
        )
        second = payloads._stage_text_payload_chunk(
            payload_id=payload_id,
            chunk_index=1,
            total_chunks=2,
            text="world",
        )

        self.assertFalse(first.complete)
        self.assertTrue(second.complete)
        self.assertEqual(second.total_chars, len("hello world"))

    def test_serializes_text_payload_ref_field(self) -> None:
        payload_id = self._payload_id()
        payloads._stage_text_payload_chunk(
            payload_id=payload_id,
            chunk_index=0,
            total_chunks=1,
            text="payload ref text",
        )

        field = payloads._serialize_text_payload_field(
            action_name="write payload",
            field_name="content",
            inline_value=None,
            ref_value=payload_id,
        )

        self.assertEqual(field["content_ref"], payload_id)
        self.assertEqual(field["content_chars"], len("payload ref text"))
        self.assertEqual(field["content_chunks"], 1)

    def test_rejects_inline_and_ref_together(self) -> None:
        with self.assertRaises(ValueError):
            payloads._serialize_text_payload_field(
                action_name="bad payload",
                field_name="content",
                inline_value="inline",
                ref_value="txt-ref",
            )


class RefactoredBundleSerializationHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload_ids: list[str] = []

    def tearDown(self) -> None:
        for payload_id in self.payload_ids:
            shutil.rmtree(payloads._text_payload_dir(payload_id), ignore_errors=True)

    def _complete_payload(self, text: str) -> str:
        payload_id = f"txt-refactored-bundle-{uuid4().hex[:8]}"
        self.payload_ids.append(payload_id)
        payloads._stage_text_payload_chunk(
            payload_id=payload_id,
            chunk_index=0,
            total_chunks=1,
            text=text,
        )
        return payload_id

    def test_serializes_low_risk_command_step(self) -> None:
        steps, risk, approval_required = bundle_serialization._serialize_command_steps(
            config.PROJECT_ROOT,
            [
                CommandBundleStep(
                    name="git status",
                    argv=["git", "status", "--short"],
                    timeout_seconds=30,
                )
            ],
        )

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["argv"], ["git", "status", "--short"])
        self.assertEqual(risk, "low")
        self.assertFalse(approval_required)

    def test_serializes_write_file_action_with_content_ref(self) -> None:
        payload_id = self._complete_payload("bundle content ref")

        actions, risk, approval_required = bundle_serialization._serialize_action_steps(
            config.PROJECT_ROOT,
            [
                CommandBundleAction(
                    name="write ref",
                    type="write_file",
                    path="tmp-refactored-helper.md",
                    content_ref=payload_id,
                    overwrite=True,
                )
            ],
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "write_file")
        self.assertTrue(str(actions[0]["path"]).endswith("tmp-refactored-helper.md"))
        self.assertEqual(actions[0]["content_ref"], payload_id)
        self.assertEqual(actions[0]["content_chars"], len("bundle content ref"))
        self.assertEqual(actions[0]["content_chunks"], 1)
        self.assertEqual(risk, "medium")
        self.assertTrue(approval_required)

    def test_rejects_unsafe_bundle_file_action_paths(self) -> None:
        with self.assertRaises(ValueError):
            bundle_serialization._resolve_bundle_file_action_path(
                config.PROJECT_ROOT,
                "../outside.md",
            )

        with self.assertRaises(PermissionError):
            bundle_serialization._resolve_bundle_file_action_path(config.PROJECT_ROOT, ".env")


class RefactoredPatchHelperTests(unittest.TestCase):
    def test_extract_patch_paths_for_new_file(self) -> None:
        patch = """diff --git a/tmp-refactored-patch.md b/tmp-refactored-patch.md
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/tmp-refactored-patch.md
@@ -0,0 +1 @@
+hello patch
"""

        self.assertEqual(
            patches._extract_patch_paths(patch),
            ["tmp-refactored-patch.md"],
        )

    def test_clean_patch_path_rejects_unsafe_paths(self) -> None:
        with self.assertRaises(ValueError):
            patches._clean_patch_path("../outside.md")

        with self.assertRaises(PermissionError):
            patches._clean_patch_path(".git/config")


class RefactoredTaskHelperTests(unittest.TestCase):
    def test_normalizes_task_id(self) -> None:
        self.assertEqual(tasks._normalize_task_id("  task-refactor-ok  "), "task-refactor-ok")

    def test_rejects_invalid_task_id(self) -> None:
        with self.assertRaises(ValueError):
            tasks._normalize_task_id("bad task id")

    def test_task_path_uses_task_dir(self) -> None:
        path = tasks._task_path("task-refactor-ok")

        self.assertEqual(path.parent, config.TASK_DIR)
        self.assertEqual(path.name, "task-refactor-ok.json")


class RefactoredOperationHelperTests(unittest.TestCase):
    def test_normalizes_operation_id(self) -> None:
        self.assertEqual(
            operations._normalize_operation_id("  op-refactor-ok  "),
            "op-refactor-ok",
        )

    def test_rejects_invalid_operation_id(self) -> None:
        with self.assertRaises(ValueError):
            operations._normalize_operation_id("bad operation id")

    def test_model_to_dict_handles_dict_and_fallback(self) -> None:
        value = {"ok": True}

        self.assertIs(operations._model_to_dict(value), value)
        self.assertEqual(operations._model_to_dict("fallback"), {"value": "fallback"})


if __name__ == "__main__":
    unittest.main()
