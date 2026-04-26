from __future__ import annotations

import hashlib
import json
import shutil
import unittest
from uuid import uuid4

import server
from scripts import command_bundle_runner as runner
from terminal_bridge import config, payloads, safety


DIRECT_RISKY_TOOLS = {
    "workspace_create_directory",
    "workspace_write_file",
    "workspace_append_file",
    "workspace_replace_text",
    "workspace_soft_delete",
    "workspace_move_to_trash",
    "workspace_restore_deleted",
    "workspace_restore_backup",
    "workspace_apply_patch",
    "workspace_git_add",
    "workspace_git_commit",
    "workspace_exec",
    "workspace_run_profile",
}

BUNDLE_TOOLS = {
    "workspace_stage_text_payload",
    "workspace_stage_command_bundle",
    "workspace_stage_action_bundle",
    "workspace_stage_patch_bundle",
    "workspace_command_bundle_status",
    "workspace_list_command_bundles",
    "workspace_cancel_command_bundle",
}


def new_file_patch(path: str, content: str = "hello patch bundle") -> str:
    return f"""diff --git a/{path} b/{path}
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/{path}
@@ -0,0 +1 @@
+{content}
"""


class ToolSurfaceTests(unittest.TestCase):
    def test_workspace_info_default_tool_list_is_bundle_first(self) -> None:
        original = server.MCP_EXPOSE_DIRECT_MUTATION_TOOLS
        server.MCP_EXPOSE_DIRECT_MUTATION_TOOLS = False
        try:
            tools = set(server.workspace_info().tools)
        finally:
            server.MCP_EXPOSE_DIRECT_MUTATION_TOOLS = original

        self.assertFalse(DIRECT_RISKY_TOOLS.intersection(tools))
        self.assertTrue(BUNDLE_TOOLS.issubset(tools))


class PatchBundleStagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle_ids: list[str] = []
        self.payload_ids: list[str] = []
        self.original_audit = server._audit
        server._audit = lambda *args, **kwargs: None

    def tearDown(self) -> None:
        server._audit = self.original_audit

        for bundle_id in self.bundle_ids:
            for status in ("pending", "applied", "rejected", "failed"):
                server._command_bundle_path(bundle_id, status).unlink(missing_ok=True)

        for payload_id in self.payload_ids:
            shutil.rmtree(payloads._text_payload_dir(payload_id), ignore_errors=True)

    def project_cwd(self) -> str:
        return safety._relative(config.PROJECT_ROOT)

    def test_stages_inline_patch_bundle(self) -> None:
        patch_path = f"tmp-patch-bundle-inline-{uuid4().hex[:8]}.txt"
        patch = new_file_patch(patch_path)

        result = server.workspace_stage_patch_bundle(
            title="Inline patch bundle",
            cwd=self.project_cwd(),
            patch=patch,
        )
        self.bundle_ids.append(result.bundle_id)

        bundle_path = server._command_bundle_path(result.bundle_id, "pending")
        record = json.loads(bundle_path.read_text(encoding="utf-8"))
        step = record["steps"][0]

        self.assertEqual(result.status, "pending")
        self.assertEqual(result.risk, "medium")
        self.assertTrue(result.approval_required)
        self.assertEqual(step["type"], "apply_patch")
        self.assertEqual(step["patch"], patch)
        self.assertEqual(step["files"], [patch_path])

    def test_stages_patch_ref_bundle(self) -> None:
        patch_path = f"tmp-patch-bundle-ref-{uuid4().hex[:8]}.txt"
        patch = new_file_patch(patch_path)
        payload_id = f"txt-patch-bundle-{uuid4().hex[:8]}"
        self.payload_ids.append(payload_id)

        payloads._stage_text_payload_chunk(
            payload_id=payload_id,
            chunk_index=0,
            total_chunks=1,
            text=patch,
        )

        result = server.workspace_stage_patch_bundle(
            title="Patch ref bundle",
            cwd=self.project_cwd(),
            patch_ref=payload_id,
        )
        self.bundle_ids.append(result.bundle_id)

        bundle_path = server._command_bundle_path(result.bundle_id, "pending")
        record = json.loads(bundle_path.read_text(encoding="utf-8"))
        step = record["steps"][0]

        self.assertEqual(step["type"], "apply_patch")
        self.assertEqual(step["patch_ref"], payload_id)
        self.assertNotIn("patch", step)
        self.assertEqual(step["files"], [patch_path])

    def test_rejects_invalid_patch_path(self) -> None:
        patch = new_file_patch("../outside.md")

        with self.assertRaises(ValueError):
            server.workspace_stage_patch_bundle(
                title="Bad patch path",
                cwd=self.project_cwd(),
                patch=patch,
            )

    def test_rejects_patch_and_patch_ref_together(self) -> None:
        with self.assertRaises(ValueError):
            server.workspace_stage_patch_bundle(
                title="Bad patch source",
                cwd=self.project_cwd(),
                patch=new_file_patch("tmp-bad-patch-source.txt"),
                patch_ref="txt-bad-ref",
            )

    def test_staging_patch_bundle_does_not_run_git_apply_check(self) -> None:
        patch_path = f"tmp-patch-bundle-no-check-{uuid4().hex[:8]}.txt"
        patch = new_file_patch(patch_path)
        original_run_git_apply = server._run_git_apply_with_stdin
        calls: list[object] = []

        def fail_if_called(*args: object, **kwargs: object) -> object:
            calls.append((args, kwargs))
            raise AssertionError("workspace_stage_patch_bundle should not call git apply --check")

        server._run_git_apply_with_stdin = fail_if_called
        try:
            result = server.workspace_stage_patch_bundle(
                title="No check patch bundle",
                cwd=self.project_cwd(),
                patch=patch,
            )
            self.bundle_ids.append(result.bundle_id)
        finally:
            server._run_git_apply_with_stdin = original_run_git_apply

        self.assertFalse(calls)


class PatchBundleRunnerTests(unittest.TestCase):
    def test_runner_applies_apply_patch_step(self) -> None:
        patch_path = f"tmp-patch-bundle-runner-{uuid4().hex[:8]}.txt"
        target = config.PROJECT_ROOT / patch_path
        patch = new_file_patch(patch_path, "runner apply patch")
        step = {
            "type": "apply_patch",
            "name": "Apply runner patch",
            "cwd": safety._relative(config.PROJECT_ROOT),
            "patch": patch,
            "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
            "files": [patch_path],
            "risk": "medium",
            "reason": "Patch apply requires local approval.",
        }

        try:
            result = runner.apply_step(config.PROJECT_ROOT, step)

            self.assertEqual(result["type"], "apply_patch")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["files"], [patch_path])
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8").strip(), "runner apply patch")
        finally:
            target.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
