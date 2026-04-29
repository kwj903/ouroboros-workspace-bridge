from __future__ import annotations

import unittest

import server
from terminal_bridge.models import CommandBundleStageResult


def fake_result(title: str = "fake") -> CommandBundleStageResult:
    return CommandBundleStageResult(
        bundle_id="cmd-test",
        title=title,
        cwd=".",
        status="pending",
        risk="low",
        approval_required=True,
        path="/tmp/cmd-test.json",
        review_hint="preview",
        command_count=1,
    )


class CompanionActionIntentStagingTests(unittest.TestCase):
    def test_run_script_uses_command_bundle_not_action_bundle(self) -> None:
        original_command = server.workspace_stage_command_bundle
        original_action = server.workspace_stage_action_bundle
        calls: list[object] = []

        def fake_command_bundle(*, title, cwd, steps):
            calls.append({"title": title, "cwd": cwd, "steps": steps})
            return fake_result(title)

        def fail_action_bundle(*args, **kwargs):
            raise AssertionError("run_script must not use workspace_stage_action_bundle")

        try:
            server.workspace_stage_command_bundle = fake_command_bundle
            server.workspace_stage_action_bundle = fail_action_bundle

            result = server._approve_intent(
                {
                    "intent_type": "run_script",
                    "cwd": ".",
                    "params": {
                        "title": "Run script smoke",
                        "script": "echo ok",
                        "timeout_seconds": 7,
                    },
                    "nonce": "a" * 24,
                }
            )

            self.assertEqual(result.bundle_id, "cmd-test")
            self.assertEqual(len(calls), 1)
            step = calls[0]["steps"][0]
            self.assertEqual(step.argv, ["bash", "-lc", "echo ok"])
            self.assertEqual(step.timeout_seconds, 7)
        finally:
            server.workspace_stage_command_bundle = original_command
            server.workspace_stage_action_bundle = original_action


if __name__ == "__main__":
    unittest.main()


class CompanionWriteFileIntentStagingTests(unittest.TestCase):
    def test_write_file_uses_patch_bundle_not_action_bundle(self) -> None:
        original_patch = server.workspace_stage_patch_bundle
        original_action = server.workspace_stage_action_bundle
        calls: list[object] = []

        def fake_patch_bundle(*, title, cwd, patch=None, patch_ref=None):
            calls.append({"title": title, "cwd": cwd, "patch": patch, "patch_ref": patch_ref})
            return fake_result(title)

        def fail_action_bundle(*args, **kwargs):
            raise AssertionError("write_file must not use workspace_stage_action_bundle")

        try:
            server.workspace_stage_patch_bundle = fake_patch_bundle
            server.workspace_stage_action_bundle = fail_action_bundle

            result = server._approve_intent(
                {
                    "intent_type": "write_file",
                    "cwd": ".",
                    "params": {
                        "title": "Write smoke",
                        "path": "tmp/companion-write-smoke.txt",
                        "content": "write-ok\\n",
                        "overwrite": True,
                        "create_parent_dirs": True,
                    },
                    "nonce": "b" * 24,
                }
            )

            self.assertEqual(result.bundle_id, "cmd-test")
            self.assertEqual(len(calls), 1)
            self.assertIn("diff --git", calls[0]["patch"])
            self.assertIn("write-ok", calls[0]["patch"])
        finally:
            server.workspace_stage_patch_bundle = original_patch
            server.workspace_stage_action_bundle = original_action
