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


if __name__ == "__main__":
    unittest.main()
