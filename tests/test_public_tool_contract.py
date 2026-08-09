from __future__ import annotations

import unittest

import server
from terminal_bridge.public_tools import (
    DEFAULT_PUBLIC_MCP_TOOLS,
    DIRECT_MUTATION_MCP_TOOLS,
    PUBLIC_MUTATION_TOOL_ANNOTATIONS,
)


class PublicToolContractTests(unittest.TestCase):
    def test_default_manifest_matches_registration_and_workspace_info_exactly(self) -> None:
        self.assertFalse(server.MCP_EXPOSE_DIRECT_MUTATION_TOOLS)
        registered = {tool.name for tool in server.mcp._tool_manager.list_tools()}
        expected = set(DEFAULT_PUBLIC_MCP_TOOLS)

        self.assertEqual(registered, expected)
        self.assertEqual(tuple(server.workspace_info().tools), DEFAULT_PUBLIC_MCP_TOOLS)
        self.assertEqual(len(DEFAULT_PUBLIC_MCP_TOOLS), 31)
        self.assertTrue(expected.isdisjoint(DIRECT_MUTATION_MCP_TOOLS))

    def test_public_mutation_annotations_match_runtime_side_effects(self) -> None:
        registered = {tool.name: tool for tool in server.mcp._tool_manager.list_tools()}

        for name, expected in PUBLIC_MUTATION_TOOL_ANNOTATIONS.items():
            with self.subTest(tool=name):
                annotations = registered[name].annotations
                self.assertIsNotNone(annotations)
                assert annotations is not None
                actual = {
                    "readOnlyHint": annotations.readOnlyHint,
                    "destructiveHint": annotations.destructiveHint,
                    "idempotentHint": annotations.idempotentHint,
                    "openWorldHint": annotations.openWorldHint,
                }
                self.assertEqual(actual, expected)

    def test_public_bundle_descriptions_match_current_approval_and_lifecycle_semantics(self) -> None:
        registered = {tool.name: tool for tool in server.mcp._tool_manager.list_tools()}
        proposal_names = (
            "workspace_propose_command_and_wait",
            "workspace_propose_file_write_and_wait",
            "workspace_propose_file_replace_and_wait",
            "workspace_propose_patch_and_wait",
            "workspace_propose_git_commit_and_wait",
            "workspace_propose_git_push_and_wait",
        )

        for name in proposal_names:
            with self.subTest(tool=name):
                description = registered[name].description or ""
                self.assertIn("Normal requires manual review", description)
                self.assertIn("Safe Auto or YOLO", description)
                self.assertNotIn("only after the user approves", description)

        wait_description = registered["workspace_wait_command_bundle_status"].description or ""
        self.assertIn("pending/running", wait_description)
        self.assertIn("terminal state", wait_description)

        list_description = registered["workspace_list_command_bundles"].description or ""
        for state in ("pending", "running", "applied", "rejected", "failed", "interrupted"):
            self.assertIn(state, list_description)


if __name__ == "__main__":
    unittest.main()
