from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from inspect import signature
from pathlib import Path
from typing import Any, get_args, get_type_hints
from unittest import mock
from uuid import uuid4

import server
from scripts import command_bundle_runner
from terminal_bridge import (
    bundle_serialization,
    cli,
    commands,
    config,
    operations,
    patches,
    payloads,
    safety,
    tasks,
)
from terminal_bridge.models import CommandBundleAction, CommandBundleStep


def _field_metadata_value(function: Any, parameter_name: str, metadata_name: str) -> object:
    annotation = get_type_hints(function, include_extras=True)[parameter_name]
    for annotation_arg in get_args(annotation):
        metadata = getattr(annotation_arg, "metadata", None)
        if metadata is None:
            continue
        for item in metadata:
            if hasattr(item, metadata_name):
                return getattr(item, metadata_name)
    raise AssertionError(f"{function.__name__}.{parameter_name} has no {metadata_name} metadata")


class ConfigLimitTests(unittest.TestCase):
    def test_gpt55_limit_constants(self) -> None:
        self.assertEqual(config.MAX_READ_CHARS, 320_000)
        self.assertEqual(config.MAX_WRITE_CHARS, 400_000)
        self.assertEqual(config.MAX_TREE_ENTRIES, 800)
        self.assertEqual(config.MAX_STDOUT_CHARS, 120_000)
        self.assertEqual(config.MAX_STDERR_CHARS, 80_000)
        self.assertEqual(config.TEXT_PAYLOAD_CHUNK_MAX_CHARS, 64_000)
        self.assertEqual(config.TEXT_PAYLOAD_MAX_TOTAL_CHARS, 2_000_000)
        self.assertEqual(config.MAX_EXEC_ARG_CHARS, 64_000)
        self.assertEqual(config.MAX_EXEC_ARGV_TOTAL_CHARS, 256_000)
        self.assertEqual(config.MAX_EXEC_ARGV_ITEMS, 80)
        self.assertEqual(config.MAX_READ_MANY_FILE_CHARS, 160_000)
        self.assertEqual(config.MAX_READ_MANY_TOTAL_CHARS, 800_000)
        self.assertEqual(config.MAX_FIND_ENTRIES, 800)
        self.assertEqual(config.MAX_SEARCH_MATCHES, 800)
        self.assertEqual(config.MAX_SEARCH_FILE_BYTES, 1_000_000)
        self.assertEqual(config.MAX_DIFF_PREVIEW_CHARS, 120_000)
        self.assertEqual(config.DEFAULT_DIFF_PREVIEW_CHARS, 20_000)
        self.assertEqual(config.MAX_COMMAND_TIMEOUT_SECONDS, 900)
        self.assertEqual(config.MIN_BUNDLE_WAIT_SECONDS, 1)
        self.assertEqual(config.DEFAULT_BUNDLE_WAIT_SECONDS, 300)
        self.assertEqual(config.MAX_BUNDLE_WAIT_SECONDS, 900)
        self.assertEqual(config.MIN_BUNDLE_POLL_INTERVAL_SECONDS, 0.2)
        self.assertEqual(config.DEFAULT_BUNDLE_POLL_INTERVAL_SECONDS, 1.0)
        self.assertEqual(config.MAX_BUNDLE_POLL_INTERVAL_SECONDS, 5.0)

    def test_runner_limit_constants_are_imported_from_config(self) -> None:
        self.assertEqual(command_bundle_runner.MAX_STDOUT_CHARS, config.MAX_STDOUT_CHARS)
        self.assertEqual(command_bundle_runner.MAX_STDERR_CHARS, config.MAX_STDERR_CHARS)
        self.assertEqual(
            command_bundle_runner.TEXT_PAYLOAD_MAX_TOTAL_CHARS,
            config.TEXT_PAYLOAD_MAX_TOTAL_CHARS,
        )


class TruncateHelperTests(unittest.TestCase):
    def test_truncate_preserves_short_text(self) -> None:
        for truncate in (server._truncate, patches._truncate, command_bundle_runner.truncate):
            with self.subTest(truncate=truncate.__module__):
                text, truncated = truncate("short text", 80)

                self.assertEqual(text, "short text")
                self.assertFalse(truncated)

    def test_truncate_preserves_head_tail_and_marker(self) -> None:
        text = "HEAD-" + ("x" * 100) + "-TAIL"

        for truncate in (server._truncate, patches._truncate, command_bundle_runner.truncate):
            with self.subTest(truncate=truncate.__module__):
                result, truncated = truncate(text, 80)

                self.assertTrue(truncated)
                self.assertLessEqual(len(result), 80)
                self.assertTrue(result.startswith("HEAD-"))
                self.assertTrue(result.endswith("-TAIL"))
                self.assertIn("truncated 30 chars", result)


class ServerSchemaLimitTests(unittest.TestCase):
    def test_read_tree_search_schema_limits_use_config(self) -> None:
        self.assertEqual(_field_metadata_value(server.workspace_read_file, "limit", "le"), config.MAX_READ_CHARS)
        self.assertEqual(_field_metadata_value(server.workspace_tree, "max_entries", "le"), config.MAX_TREE_ENTRIES)
        self.assertEqual(
            _field_metadata_value(server.workspace_project_snapshot, "max_entries", "le"),
            config.MAX_TREE_ENTRIES,
        )
        self.assertEqual(_field_metadata_value(server.workspace_find_files, "max_entries", "le"), config.MAX_FIND_ENTRIES)
        self.assertEqual(
            _field_metadata_value(server.workspace_search_text, "max_matches", "le"),
            config.MAX_SEARCH_MATCHES,
        )
        self.assertEqual(
            _field_metadata_value(server.workspace_search_text, "max_file_bytes", "le"),
            config.MAX_SEARCH_FILE_BYTES,
        )
        self.assertEqual(
            _field_metadata_value(server.workspace_read_many_files, "limit_per_file", "le"),
            config.MAX_READ_MANY_FILE_CHARS,
        )
        self.assertEqual(
            _field_metadata_value(server.workspace_read_many_files, "total_limit", "le"),
            config.MAX_READ_MANY_TOTAL_CHARS,
        )

    def test_command_payload_and_diff_schema_limits_use_config(self) -> None:
        self.assertEqual(
            _field_metadata_value(server.workspace_propose_command_and_wait, "argv", "max_length"),
            config.MAX_EXEC_ARGV_ITEMS,
        )
        self.assertEqual(
            _field_metadata_value(server.workspace_propose_command_and_wait, "command_timeout_seconds", "le"),
            config.MAX_COMMAND_TIMEOUT_SECONDS,
        )
        self.assertEqual(
            _field_metadata_value(server.workspace_propose_command_and_wait, "timeout_seconds", "le"),
            config.MAX_BUNDLE_WAIT_SECONDS,
        )
        self.assertEqual(
            signature(server.workspace_propose_command_and_wait).parameters["timeout_seconds"].default,
            config.DEFAULT_BUNDLE_WAIT_SECONDS,
        )
        self.assertEqual(
            _field_metadata_value(server.workspace_propose_command_and_wait, "poll_interval_seconds", "le"),
            config.MAX_BUNDLE_POLL_INTERVAL_SECONDS,
        )
        self.assertEqual(
            signature(server.workspace_propose_command_and_wait).parameters["poll_interval_seconds"].default,
            config.DEFAULT_BUNDLE_POLL_INTERVAL_SECONDS,
        )
        self.assertEqual(
            _field_metadata_value(server.workspace_exec, "timeout_seconds", "le"),
            config.MAX_COMMAND_TIMEOUT_SECONDS,
        )
        self.assertEqual(
            _field_metadata_value(server.workspace_apply_patch, "diff_max_chars", "le"),
            config.MAX_DIFF_PREVIEW_CHARS,
        )
        self.assertEqual(
            signature(server.workspace_apply_patch).parameters["diff_max_chars"].default,
            config.DEFAULT_DIFF_PREVIEW_CHARS,
        )
        self.assertEqual(
            _field_metadata_value(server.workspace_stage_text_payload, "text", "max_length"),
            config.TEXT_PAYLOAD_CHUNK_MAX_CHARS,
        )


class ConfigWorkspaceRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.original_runtime_root = config.DEFAULT_RUNTIME_ROOT
        self.original_runtime_root_env = os.environ.get("MCP_TERMINAL_BRIDGE_RUNTIME_ROOT")
        self.original_workspace_root = os.environ.get("WORKSPACE_ROOT")

    def tearDown(self) -> None:
        config.DEFAULT_RUNTIME_ROOT = self.original_runtime_root
        if self.original_runtime_root_env is None:
            os.environ.pop("MCP_TERMINAL_BRIDGE_RUNTIME_ROOT", None)
        else:
            os.environ["MCP_TERMINAL_BRIDGE_RUNTIME_ROOT"] = self.original_runtime_root_env
        if self.original_workspace_root is None:
            os.environ.pop("WORKSPACE_ROOT", None)
        else:
            os.environ["WORKSPACE_ROOT"] = self.original_workspace_root
        self.tmp.cleanup()

    def test_shell_workspace_root_overrides_session_env(self) -> None:
        root = Path(self.tmp.name)
        session_root = root / "runtime"
        shell_workspace = root / "shell-workspace"
        session_workspace = root / "session-workspace"
        session_root.mkdir()
        shell_workspace.mkdir()
        session_workspace.mkdir()
        (session_root / "session.env").write_text(
            f"export WORKSPACE_ROOT={session_workspace}\n",
            encoding="utf-8",
        )

        config.DEFAULT_RUNTIME_ROOT = session_root
        os.environ["WORKSPACE_ROOT"] = str(shell_workspace)

        self.assertEqual(config._resolve_workspace_root(), shell_workspace.resolve())

    def test_session_env_workspace_root_is_used_as_fallback(self) -> None:
        root = Path(self.tmp.name)
        session_root = root / "runtime"
        session_workspace = root / "session-workspace"
        session_root.mkdir()
        session_workspace.mkdir()
        (session_root / "session.env").write_text(
            f"export WORKSPACE_ROOT={session_workspace}\n",
            encoding="utf-8",
        )

        config.DEFAULT_RUNTIME_ROOT = session_root
        os.environ.pop("WORKSPACE_ROOT", None)

        self.assertEqual(config._resolve_workspace_root(), session_workspace.resolve())

    def test_custom_runtime_root_session_env_is_used_as_fallback(self) -> None:
        root = Path(self.tmp.name)
        runtime_root = root / "custom-runtime"
        session_workspace = root / "session-workspace"
        runtime_root.mkdir()
        session_workspace.mkdir()
        (runtime_root / "session.env").write_text(
            f"export WORKSPACE_ROOT={session_workspace}\n",
            encoding="utf-8",
        )

        os.environ["MCP_TERMINAL_BRIDGE_RUNTIME_ROOT"] = str(runtime_root)
        os.environ.pop("WORKSPACE_ROOT", None)

        self.assertEqual(config._resolve_workspace_root(), session_workspace.resolve())

    def test_rejects_dangerous_workspace_root(self) -> None:
        os.environ["WORKSPACE_ROOT"] = "/"

        with self.assertRaises(ValueError):
            config._resolve_workspace_root()


class CliEnvHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.original_runtime_root = os.environ.get("MCP_TERMINAL_BRIDGE_RUNTIME_ROOT")
        self.original_ngrok_host = os.environ.get("NGROK_HOST")
        self.original_ngrok_base_url = os.environ.get("NGROK_BASE_URL")
        self.original_token = os.environ.get("MCP_ACCESS_TOKEN")

    def tearDown(self) -> None:
        for name, value in (
            ("MCP_TERMINAL_BRIDGE_RUNTIME_ROOT", self.original_runtime_root),
            ("NGROK_HOST", self.original_ngrok_host),
            ("NGROK_BASE_URL", self.original_ngrok_base_url),
            ("MCP_ACCESS_TOKEN", self.original_token),
        ):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.tmp.cleanup()

    def test_cli_uses_shell_env_before_session_env_for_host(self) -> None:
        runtime_root = Path(self.tmp.name)
        (runtime_root / "session.env").write_text(
            "export NGROK_HOST=session.example.invalid\n",
            encoding="utf-8",
        )
        os.environ["MCP_TERMINAL_BRIDGE_RUNTIME_ROOT"] = str(runtime_root)
        os.environ["NGROK_HOST"] = "shell.example.invalid"

        self.assertEqual(cli.configured_ngrok_host(), "shell.example.invalid")

    def test_cli_mcp_url_redacted_preview_does_not_include_token(self) -> None:
        os.environ["NGROK_HOST"] = "example.invalid"
        os.environ["MCP_ACCESS_TOKEN"] = "secret-token-value"

        self.assertEqual(
            cli.mcp_url("<redacted>"),
            "https://example.invalid/mcp?access_token=<redacted>",
        )


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

    def test_allows_former_dev_blocked_workspace_paths(self) -> None:
        for path in (
            ".env.example",
            ".env.local",
            ".ssh/config",
            ".venv/bin/python",
            "node_modules/pkg/index.js",
            "__pycache__/module.pyc",
        ):
            with self.subTest(path=path):
                self.assertEqual(safety._resolve_workspace_path(path), config.WORKSPACE_ROOT / path)

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

    def test_validate_exec_argv_allows_larger_shell_body(self) -> None:
        body = "printf 'ok'\\n" + ("x" * 2000)

        self.assertEqual(
            commands._validate_exec_argv(["bash", "-lc", body]),
            ["bash", "-lc", body],
        )

    def test_validate_exec_argv_uses_config_limits(self) -> None:
        commands._validate_exec_argv(["x"] * config.MAX_EXEC_ARGV_ITEMS)
        with self.assertRaisesRegex(ValueError, "too many items"):
            commands._validate_exec_argv(["x"] * (config.MAX_EXEC_ARGV_ITEMS + 1))

        max_arg = "x" * config.MAX_EXEC_ARG_CHARS
        self.assertEqual(commands._validate_exec_argv([max_arg]), [max_arg])
        with self.assertRaisesRegex(ValueError, "item is too long"):
            commands._validate_exec_argv(["x" * (config.MAX_EXEC_ARG_CHARS + 1)])

        exact_total = ["x" * config.MAX_EXEC_ARG_CHARS] * (
            config.MAX_EXEC_ARGV_TOTAL_CHARS // config.MAX_EXEC_ARG_CHARS
        )
        self.assertEqual(commands._validate_exec_argv(exact_total), exact_total)
        with self.assertRaisesRegex(ValueError, "argv is too large"):
            commands._validate_exec_argv([*exact_total, "x"])

    def test_classifies_large_shell_body_without_path_scanning_body(self) -> None:
        risk, reason = commands._classify_exec_command(
            config.PROJECT_ROOT,
            ["bash", "-lc", "cat > tmp/generated.txt <<'EOF'\nhello\nEOF"],
        )

        self.assertEqual(risk, "medium")
        self.assertIn("bash", reason)

    def test_classifies_requested_yolo_relaxed_commands_as_non_blocked(self) -> None:
        cases = (
            ["ssh", "example.local"],
            ["bash", "-lc", "echo hi"],
            ["bash", "-lc", "cat .env.example"],
            ["bash", "-lc", "cat .env.local"],
            ["sh", "-c", "echo hi"],
            ["zsh", "-lc", "echo hi"],
            ["git", "push"],
            ["npm", "install"],
            ["pnpm", "install"],
            ["uv", "sync"],
            ["pip", "install", "package"],
            ["rm", "build/output.txt"],
            ["chmod", "600", "README.md"],
            ["chown", "user", "README.md"],
            ["launchctl", "list"],
            ["osascript", "-e", "return 1"],
            ["killall", "ExampleApp"],
            ["pkill", "ExampleApp"],
            ["curl", "https://example.invalid"],
            ["wget", "https://example.invalid"],
        )

        for argv in cases:
            with self.subTest(argv=argv):
                risk, _reason = commands._classify_exec_command(config.PROJECT_ROOT, list(argv))
                self.assertIn(risk, {"medium", "high"})

    def test_classifies_development_paths_as_non_blocked(self) -> None:
        for path in (
            ".env.example",
            ".env.local",
            ".ssh/config",
            ".venv/bin/python",
            "node_modules/pkg/index.js",
            "__pycache__/module.pyc",
        ):
            with self.subTest(path=path):
                risk, _reason = commands._classify_exec_command(config.PROJECT_ROOT, ["cat", path])
                self.assertNotEqual(risk, "blocked")

    def test_classifies_hard_blocked_paths_and_executables(self) -> None:
        blocked_cases = (
            ["cat", ".env"],
            ["cat", ".git/config"],
            ["cat", ".aws/credentials"],
            ["cat", ".gnupg/pubring.kbx"],
            ["cat", "/tmp/outside-workspace"],
            ["bash", "-lc", "cat .env"],
            ["bash", "-lc", "cat /tmp/outside-workspace"],
            ["sudo", "ls"],
            ["su", "user"],
            ["dd", "if=input", "of=output"],
            ["mkfs", "/dev/disk1"],
            ["diskutil", "list"],
        )

        for argv in blocked_cases:
            with self.subTest(argv=argv):
                risk, _reason = commands._classify_exec_command(config.PROJECT_ROOT, list(argv))
                self.assertEqual(risk, "blocked")

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

    def test_allows_dev_bundle_file_action_paths(self) -> None:
        for path in (".env.example", ".env.local", ".venv/bin/python", "node_modules/pkg/index.js", ".ssh/config"):
            with self.subTest(path=path):
                resolved = bundle_serialization._resolve_bundle_file_action_path(config.PROJECT_ROOT, path)

                self.assertNotEqual(resolved, "")


class CommandBundleRunnerSafetyTests(unittest.TestCase):
    def test_runner_uses_shared_blocked_file_policy(self) -> None:
        self.assertTrue(command_bundle_runner.is_blocked_name(".env"))
        self.assertFalse(command_bundle_runner.is_blocked_name(".env.example"))
        self.assertFalse(command_bundle_runner.is_blocked_name(".env.local"))

    def test_runner_file_paths_allow_dev_locations(self) -> None:
        for path in (".env.example", ".env.local", ".venv/bin/python", "node_modules/pkg/index.js", ".ssh/config"):
            with self.subTest(path=path):
                self.assertEqual(command_bundle_runner.resolve_file_path(path), config.WORKSPACE_ROOT / path)

    def test_runner_rechecks_hard_blocked_command_before_apply(self) -> None:
        with mock.patch("scripts.command_bundle_runner.subprocess.run") as run:
            with self.assertRaises(PermissionError):
                command_bundle_runner.apply_command(
                    config.PROJECT_ROOT,
                    {"name": "sudo", "argv": ["sudo", "ls"], "risk": "high"},
                )

            run.assert_not_called()


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
