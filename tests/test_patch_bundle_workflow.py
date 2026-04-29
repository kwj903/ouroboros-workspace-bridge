from __future__ import annotations

import hashlib
import asyncio
import json
import os
import shutil
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import server
from scripts import command_bundle_runner as runner
from terminal_bridge import config, payloads, safety, tool_calls


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
    "workspace_submit_command_bundle",
    "workspace_submit_action_bundle",
    "workspace_submit_patch_bundle",
    "workspace_submit_commit_bundle",
    "workspace_command_bundle_status",
    "workspace_wait_command_bundle_status",
    "workspace_stage_command_bundle_and_wait",
    "workspace_stage_action_bundle_and_wait",
    "workspace_stage_patch_bundle_and_wait",
    "workspace_stage_commit_bundle_and_wait",
    "workspace_list_command_bundles",
    "workspace_cancel_command_bundle",
}

INTENT_TOOLS = {
    "workspace_prepare_check_intent",
    "workspace_prepare_commit_current_changes_intent",
    "workspace_prepare_dev_session_intent",
}

RECOVERY_TOOLS = {
    "workspace_recover_last_activity",
    "workspace_transport_probe",
}

PRIMITIVE_STAGE_TOOLS = {
    "workspace_stage_command_bundle",
    "workspace_stage_action_bundle",
    "workspace_stage_commit_bundle",
    "workspace_stage_patch_bundle",
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


def command_bundle_file_count() -> int:
    return sum(1 for directory in server._command_bundle_dirs() if directory.exists() for _ in directory.glob("cmd-*.json"))


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
        self.assertTrue(INTENT_TOOLS.issubset(tools))
        self.assertTrue(RECOVERY_TOOLS.issubset(tools))
        self.assertFalse(PRIMITIVE_STAGE_TOOLS.intersection(tools))

    def test_recover_last_activity_returns_snapshot(self) -> None:
        tools = set(server.workspace_info().tools)

        self.assertIn("workspace_recover_last_activity", tools)

        result = server.workspace_recover_last_activity(cwd=safety._relative(config.PROJECT_ROOT))

        self.assertIsInstance(result, dict)
        self.assertIn("git_status", result)
        self.assertIn("latest_bundles", result)
        self.assertIn("latest_audit_events", result)
        self.assertIn("diagnosis", result)

    def test_transport_probe_returns_compact_snapshot_with_git_status(self) -> None:
        tools = set(server.workspace_info().tools)

        self.assertIn("workspace_transport_probe", tools)
        self.assertFalse(PRIMITIVE_STAGE_TOOLS.intersection(tools))

        result = server.workspace_transport_probe(cwd=safety._relative(config.PROJECT_ROOT), include_git_status=True)

        self.assertIs(result["ok"], True)
        self.assertIn("server_time", result)
        self.assertIn("pid", result)
        self.assertIn("workspace_root", result)
        self.assertIn("runtime_root", result)
        self.assertIn("latest_tool_call_count", result)
        self.assertIn("latest_bundle_count", result)
        self.assertIn("diagnosis", result)
        self.assertIsInstance(result["git_status"], dict)

    def test_transport_probe_can_skip_git_status(self) -> None:
        result = server.workspace_transport_probe(include_git_status=False)

        self.assertIs(result["ok"], True)
        self.assertIsNone(result["git_status"])

    def test_intent_tools_are_read_only_public_tools(self) -> None:
        with open(server.__file__, encoding="utf-8") as handle:
            source = handle.read()

        for tool_name in INTENT_TOOLS:
            self.assertIn(tool_name, server.workspace_info().tools)
            function_index = source.index(f"def {tool_name}(")
            decorator_block = source[max(0, function_index - 260) : function_index]
            self.assertIn('"readOnlyHint": True', decorator_block)
            self.assertIn('"destructiveHint": False', decorator_block)
            self.assertIn('"idempotentHint": True', decorator_block)
            self.assertIn('"openWorldHint": False', decorator_block)


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


class CommitBundleStagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle_ids: list[str] = []
        self.original_audit = server._audit
        server._audit = lambda *args, **kwargs: None

    def tearDown(self) -> None:
        server._audit = self.original_audit

        for bundle_id in self.bundle_ids:
            for status in ("pending", "applied", "rejected", "failed"):
                server._command_bundle_path(bundle_id, status).unlink(missing_ok=True)

    def project_cwd(self) -> str:
        return safety._relative(config.PROJECT_ROOT)

    def test_stages_commit_bundle_with_default_prechecks(self) -> None:
        result = server.workspace_stage_commit_bundle(
            cwd=self.project_cwd(),
            paths=["README.md"],
            message="Test commit bundle",
        )
        self.bundle_ids.append(result.bundle_id)

        bundle_path = server._command_bundle_path(result.bundle_id, "pending")
        record = json.loads(bundle_path.read_text(encoding="utf-8"))
        steps = record["steps"]

        self.assertEqual(result.status, "pending")
        self.assertEqual(result.risk, "medium")
        self.assertTrue(result.approval_required)
        self.assertEqual(result.command_count, 6)
        self.assertEqual(steps[0]["argv"], ["git", "status", "--short", "--branch"])
        self.assertEqual(steps[1]["argv"], ["git", "diff", "--check"])
        self.assertEqual(steps[2]["argv"], ["git", "add", "--", "README.md"])
        self.assertEqual(steps[2]["risk"], "medium")
        self.assertEqual(steps[3]["argv"], ["git", "commit", "-m", "Test commit bundle"])
        self.assertEqual(steps[3]["risk"], "medium")

    def test_stages_commit_bundle_with_custom_low_risk_precheck(self) -> None:
        result = server.workspace_stage_commit_bundle(
            cwd=self.project_cwd(),
            paths=["README.md"],
            message="Test custom precheck",
            precheck_commands=[
                server.CommandBundleStep(
                    name="custom status",
                    argv=["git", "status", "--short"],
                    timeout_seconds=15,
                )
            ],
        )
        self.bundle_ids.append(result.bundle_id)

        bundle_path = server._command_bundle_path(result.bundle_id, "pending")
        record = json.loads(bundle_path.read_text(encoding="utf-8"))

        self.assertEqual(result.command_count, 5)
        self.assertEqual(record["steps"][0]["name"], "custom status")

    def test_rejects_multiline_commit_message(self) -> None:
        with self.assertRaises(ValueError):
            server.workspace_stage_commit_bundle(
                cwd=self.project_cwd(),
                paths=["README.md"],
                message="bad\nmessage",
            )

    def test_rejects_unsafe_commit_path(self) -> None:
        with self.assertRaises(ValueError):
            server.workspace_stage_commit_bundle(
                cwd=self.project_cwd(),
                paths=["../outside.md"],
                message="Bad path",
            )


class CommandBundleDedupeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle_ids: list[str] = []
        self.original_audit = server._audit
        self.original_tool_call_dir = tool_calls.TOOL_CALL_DIR
        self.tmp_tool_calls = None
        server._audit = lambda *args, **kwargs: None

    def tearDown(self) -> None:
        server._audit = self.original_audit
        tool_calls.TOOL_CALL_DIR = self.original_tool_call_dir
        if self.tmp_tool_calls is not None:
            self.tmp_tool_calls.cleanup()

        for bundle_id in self.bundle_ids:
            for status in ("pending", "applied", "rejected", "failed"):
                server._command_bundle_path(bundle_id, status).unlink(missing_ok=True)

    def project_cwd(self) -> str:
        return safety._relative(config.PROJECT_ROOT)

    def use_temp_tool_calls(self) -> None:
        import tempfile
        from pathlib import Path

        self.tmp_tool_calls = tempfile.TemporaryDirectory()
        tool_calls.TOOL_CALL_DIR = Path(self.tmp_tool_calls.name)

    def test_command_bundle_duplicate_returns_same_bundle_without_new_file(self) -> None:
        title = f"Dedupe command {uuid4().hex[:8]}"
        steps = [server.CommandBundleStep(name="status", argv=["git", "status", "--short"])]
        before_count = command_bundle_file_count()

        first = server.workspace_stage_command_bundle(title=title, cwd=self.project_cwd(), steps=steps)
        self.bundle_ids.append(first.bundle_id)
        after_first_count = command_bundle_file_count()
        second = server.workspace_stage_command_bundle(title=title, cwd=self.project_cwd(), steps=steps)
        after_second_count = command_bundle_file_count()

        self.assertEqual(first.bundle_id, second.bundle_id)
        self.assertEqual(after_first_count, before_count + 1)
        self.assertEqual(after_second_count, after_first_count)

        _, record = server._find_command_bundle(first.bundle_id)
        self.assertTrue(str(record["request_key"]).startswith("sha256:"))
        self.assertEqual(record["request_key_version"], 1)
        self.assertIsNone(record["duplicate_of"])

    def test_action_bundle_duplicate_returns_same_bundle_without_new_file(self) -> None:
        title = f"Dedupe action {uuid4().hex[:8]}"
        path = f"tmp-dedupe-action-{uuid4().hex[:8]}.txt"
        actions = [
            server.CommandBundleAction(
                name="write",
                type="write_file",
                path=path,
                content="dedupe action content",
            )
        ]
        before_count = command_bundle_file_count()

        first = server.workspace_stage_action_bundle(title=title, cwd=self.project_cwd(), actions=actions)
        self.bundle_ids.append(first.bundle_id)
        after_first_count = command_bundle_file_count()
        second = server.workspace_stage_action_bundle(title=title, cwd=self.project_cwd(), actions=actions)
        after_second_count = command_bundle_file_count()

        self.assertEqual(first.bundle_id, second.bundle_id)
        self.assertEqual(after_first_count, before_count + 1)
        self.assertEqual(after_second_count, after_first_count)

    def test_patch_bundle_duplicate_returns_same_bundle_and_key_omits_patch_text(self) -> None:
        patch_path = f"tmp-dedupe-patch-{uuid4().hex[:8]}.txt"
        patch = new_file_patch(patch_path, "dedupe patch body should not be in request key")
        before_count = command_bundle_file_count()

        first = server.workspace_stage_patch_bundle(title="Dedupe patch", cwd=self.project_cwd(), patch=patch)
        self.bundle_ids.append(first.bundle_id)
        after_first_count = command_bundle_file_count()
        second = server.workspace_stage_patch_bundle(title="Dedupe patch", cwd=self.project_cwd(), patch=patch)
        after_second_count = command_bundle_file_count()

        self.assertEqual(first.bundle_id, second.bundle_id)
        self.assertEqual(after_first_count, before_count + 1)
        self.assertEqual(after_second_count, after_first_count)

        _, record = server._find_command_bundle(first.bundle_id)
        self.assertNotIn("dedupe patch body", str(record["request_key"]))
        self.assertEqual(record["request_key_version"], 1)

    def test_commit_bundle_duplicate_returns_same_bundle_without_new_file(self) -> None:
        message = f"Dedupe commit {uuid4().hex[:8]}"
        before_count = command_bundle_file_count()

        first = server.workspace_stage_commit_bundle(
            cwd=self.project_cwd(),
            paths=["README.md"],
            message=message,
        )
        self.bundle_ids.append(first.bundle_id)
        after_first_count = command_bundle_file_count()
        second = server.workspace_stage_commit_bundle(
            cwd=self.project_cwd(),
            paths=["README.md"],
            message=message,
        )
        after_second_count = command_bundle_file_count()

        self.assertEqual(first.bundle_id, second.bundle_id)
        self.assertEqual(after_first_count, before_count + 1)
        self.assertEqual(after_second_count, after_first_count)

    def test_wrapper_benefits_from_stage_dedupe(self) -> None:
        title = f"Dedupe wrapper {uuid4().hex[:8]}"
        steps = [server.CommandBundleStep(name="status", argv=["git", "status", "--short"])]

        first = server.workspace_stage_command_bundle_and_wait(
            title=title,
            cwd=self.project_cwd(),
            steps=steps,
            timeout_seconds=1,
            poll_interval_seconds=0.2,
        )
        self.bundle_ids.append(first.bundle_id)
        second = server.workspace_stage_command_bundle_and_wait(
            title=title,
            cwd=self.project_cwd(),
            steps=steps,
            timeout_seconds=1,
            poll_interval_seconds=0.2,
        )

        self.assertEqual(first.bundle_id, second.bundle_id)

    def test_submit_tools_return_stage_results_and_dedupe(self) -> None:
        command_title = f"Submit command {uuid4().hex[:8]}"
        command_steps = [server.CommandBundleStep(name="status", argv=["git", "status", "--short"])]
        command_first = server.workspace_submit_command_bundle(
            title=command_title,
            cwd=self.project_cwd(),
            steps=command_steps,
        )
        self.bundle_ids.append(command_first.bundle_id)
        command_second = server.workspace_submit_command_bundle(
            title=command_title,
            cwd=self.project_cwd(),
            steps=command_steps,
        )

        action_title = f"Submit action {uuid4().hex[:8]}"
        action_path = f"tmp-submit-action-{uuid4().hex[:8]}.txt"
        action_first = server.workspace_submit_action_bundle(
            title=action_title,
            cwd=self.project_cwd(),
            actions=[
                server.CommandBundleAction(
                    name="write",
                    type="write_file",
                    path=action_path,
                    content="submit action content",
                )
            ],
        )
        self.bundle_ids.append(action_first.bundle_id)

        patch_path = f"tmp-submit-patch-{uuid4().hex[:8]}.txt"
        patch_first = server.workspace_submit_patch_bundle(
            title="Submit patch",
            cwd=self.project_cwd(),
            patch=new_file_patch(patch_path),
        )
        self.bundle_ids.append(patch_first.bundle_id)

        commit_message = f"Submit commit {uuid4().hex[:8]}"
        commit_first = server.workspace_submit_commit_bundle(
            cwd=self.project_cwd(),
            paths=["README.md"],
            message=commit_message,
        )
        self.bundle_ids.append(commit_first.bundle_id)

        self.assertIsInstance(command_first, server.CommandBundleStageResult)
        self.assertIsInstance(action_first, server.CommandBundleStageResult)
        self.assertIsInstance(patch_first, server.CommandBundleStageResult)
        self.assertIsInstance(commit_first, server.CommandBundleStageResult)
        self.assertEqual(command_first.bundle_id, command_second.bundle_id)

    def test_submit_tool_creates_tool_call_journal_record(self) -> None:
        self.use_temp_tool_calls()
        title = f"Submit journal {uuid4().hex[:8]}"

        result = server.workspace_submit_command_bundle(
            title=title,
            cwd=self.project_cwd(),
            steps=[server.CommandBundleStep(name="status", argv=["git", "status", "--short"])],
        )
        self.bundle_ids.append(result.bundle_id)

        records = tool_calls.list_tool_calls()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["tool_name"], "workspace_submit_command_bundle")
        self.assertEqual(records[0]["status"], "completed")
        self.assertEqual(records[0]["result_summary"]["bundle_id"], result.bundle_id)


class IntentFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle_ids: list[str] = []
        self.original_audit = server._audit
        self.original_intent_secret_file = server.INTENT_SECRET_FILE
        self.original_intent_import_dir = server.INTENT_IMPORT_DIR
        self.original_changed_paths = server._intent_changed_paths
        self.original_tool_call_dir = tool_calls.TOOL_CALL_DIR
        self.original_mcp_host = server.MCP_HOST
        self.original_bundle_review_host = os.environ.get("BUNDLE_REVIEW_HOST")
        self.tmp = None
        server._audit = lambda *args, **kwargs: None

    def tearDown(self) -> None:
        server._audit = self.original_audit
        server.INTENT_SECRET_FILE = self.original_intent_secret_file
        server.INTENT_IMPORT_DIR = self.original_intent_import_dir
        server._intent_changed_paths = self.original_changed_paths
        tool_calls.TOOL_CALL_DIR = self.original_tool_call_dir
        server.MCP_HOST = self.original_mcp_host
        if self.original_bundle_review_host is None:
            os.environ.pop("BUNDLE_REVIEW_HOST", None)
        else:
            os.environ["BUNDLE_REVIEW_HOST"] = self.original_bundle_review_host
        if self.tmp is not None:
            self.tmp.cleanup()

        for bundle_id in self.bundle_ids:
            for status in ("pending", "applied", "rejected", "failed"):
                server._command_bundle_path(bundle_id, status).unlink(missing_ok=True)

    def use_temp_runtime_bits(self) -> None:
        import tempfile
        from pathlib import Path

        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        server.INTENT_SECRET_FILE = root / "intent_secret"
        server.INTENT_IMPORT_DIR = root / "intent_imports"
        tool_calls.TOOL_CALL_DIR = root / "tool_calls"

    def project_cwd(self) -> str:
        return safety._relative(config.PROJECT_ROOT)

    def token_from_intent(self, result: dict[str, object]) -> str:
        return str(result["local_review_url"]).split("token=", 1)[1]

    def test_prepare_intents_do_not_create_command_bundle_files_and_tokens_validate(self) -> None:
        self.use_temp_runtime_bits()
        before_count = command_bundle_file_count()

        check_intent = server.workspace_prepare_check_intent(cwd=self.project_cwd(), check="git_status")
        commit_intent = server.workspace_prepare_commit_current_changes_intent(
            cwd=self.project_cwd(),
            message="Intent commit",
            include_untracked=False,
        )
        dev_intent = server.workspace_prepare_dev_session_intent(cwd=self.project_cwd(), action="status")
        after_count = command_bundle_file_count()

        self.assertEqual(after_count, before_count)
        for item, intent_type in (
            (check_intent, "check"),
            (commit_intent, "commit_current_changes"),
            (dev_intent, "dev_session"),
        ):
            self.assertTrue(item["ok"])
            self.assertEqual(item["intent_type"], intent_type)
            self.assertIn("local_review_url", item)
            self.assertIn("local_pending_url", item)
            self.assertIn("expires_at", item)
            self.assertIn("diagnosis", item)
            self.assertIn("pending bundle UI", str(item["diagnosis"]))
            payload = server._validate_intent_token(self.token_from_intent(item))
            self.assertEqual(payload["intent_type"], intent_type)

    def test_intent_local_urls_use_loopback_for_wildcard_hosts(self) -> None:
        self.use_temp_runtime_bits()
        server.MCP_HOST = "0.0.0.0"
        os.environ["BUNDLE_REVIEW_HOST"] = "0.0.0.0"

        intent = server.workspace_prepare_check_intent(cwd=self.project_cwd(), check="git_status")

        self.assertTrue(str(intent["local_review_url"]).startswith("http://127.0.0.1:"))
        self.assertTrue(str(intent["local_pending_url"]).startswith("http://127.0.0.1:"))

    def test_invalid_and_expired_intent_tokens_are_rejected(self) -> None:
        self.use_temp_runtime_bits()
        expired_payload = {
            "intent_type": "check",
            "cwd": self.project_cwd(),
            "params": {"check": "git_status"},
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
            "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "nonce": "expired",
        }
        expired = server._sign_intent_payload(expired_payload)

        with self.assertRaises(ValueError):
            server._validate_intent_token("bad-token")
        with self.assertRaises(ValueError):
            server._validate_intent_token(expired)

    def test_preview_endpoint_previews_valid_intent_without_creating_bundle(self) -> None:
        self.use_temp_runtime_bits()
        intent = server.workspace_prepare_check_intent(cwd=self.project_cwd(), check="git_status")
        token = self.token_from_intent(intent)
        before_count = command_bundle_file_count()

        response = asyncio.run(server._preview_intent_endpoint(SimpleNamespace(query_params={"token": token})))
        after_count = command_bundle_file_count()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(after_count, before_count)
        self.assertIn(b"Intent review", response.body)
        self.assertIn(b"git_status", response.body)

    def test_review_endpoint_imports_intent_and_redirects_to_pending_ui(self) -> None:
        self.use_temp_runtime_bits()
        events: list[tuple[str, dict[str, object]]] = []
        server._audit = lambda event, **data: events.append((event, data))
        server._intent_changed_paths = lambda cwd, include_untracked: ["README.md"]
        message = f"Intent import {uuid4().hex[:8]}"
        intent = server.workspace_prepare_commit_current_changes_intent(
            self.project_cwd(),
            message=message,
            include_untracked=False,
        )
        token = self.token_from_intent(intent)

        response = asyncio.run(server._review_intent_endpoint(SimpleNamespace(query_params={"token": token})))

        self.assertEqual(response.status_code, 303)
        location = response.headers["location"]
        self.assertIn("/pending?bundle_id=", location)
        bundle_id = location.rsplit("bundle_id=", 1)[1]
        self.bundle_ids.append(bundle_id)

        record = server._read_json(server._command_bundle_path(bundle_id, "pending"))
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["title"], f"Commit: {message}")
        self.assertFalse(server._command_bundle_path(bundle_id, "applied").exists())
        self.assertTrue(any(event == "intent_imported" and data["bundle_id"] == bundle_id for event, data in events))
        fallback_html = server._intent_approved_html(server._command_bundle_stage_result(server._command_bundle_path(bundle_id, "pending"), record))
        self.assertIn("Copyable JSON summary", fallback_html)
        self.assertIn("workspace_wait_command_bundle_status", fallback_html)

        recovery = server.workspace_recover_last_activity(cwd=self.project_cwd())
        latest_ids = {str(item.get("bundle_id")) for item in recovery["latest_bundles"]}
        self.assertIn(bundle_id, latest_ids)

    def test_review_endpoint_is_idempotent_for_same_intent_url(self) -> None:
        self.use_temp_runtime_bits()
        server._intent_changed_paths = lambda cwd, include_untracked: ["README.md"]
        intent = server.workspace_prepare_commit_current_changes_intent(
            self.project_cwd(),
            message=f"Intent duplicate {uuid4().hex[:8]}",
            include_untracked=False,
        )
        token = self.token_from_intent(intent)
        before_count = command_bundle_file_count()

        first = asyncio.run(server._review_intent_endpoint(SimpleNamespace(query_params={"token": token})))
        after_first_count = command_bundle_file_count()
        second = asyncio.run(server._review_intent_endpoint(SimpleNamespace(query_params={"token": token})))
        after_second_count = command_bundle_file_count()

        self.assertEqual(first.status_code, 303)
        self.assertEqual(second.status_code, 303)
        self.assertEqual(after_first_count, before_count + 1)
        self.assertEqual(after_second_count, after_first_count)
        self.assertEqual(first.headers["location"], second.headers["location"])
        self.bundle_ids.append(first.headers["location"].rsplit("bundle_id=", 1)[1])

    def test_clean_worktree_commit_intent_approval_refuses_no_changes(self) -> None:
        self.use_temp_runtime_bits()
        server._intent_changed_paths = lambda cwd, include_untracked: []
        intent = server.workspace_prepare_commit_current_changes_intent(
            cwd=self.project_cwd(),
            message="No changes",
            include_untracked=False,
        )
        token = self.token_from_intent(intent)

        response = asyncio.run(server._review_intent_endpoint(SimpleNamespace(query_params={"token": token})))

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"No changes to commit", response.body)


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
