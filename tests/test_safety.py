from __future__ import annotations

import unittest
from pathlib import Path

import server


class WorkspacePathSafetyTests(unittest.TestCase):
    def test_resolve_workspace_root(self) -> None:
        self.assertEqual(server._resolve_workspace_path("."), server.WORKSPACE_ROOT)

    def test_rejects_absolute_path(self) -> None:
        with self.assertRaises(ValueError):
            server._resolve_workspace_path("/tmp")

    def test_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            server._resolve_workspace_path("../outside")

    def test_rejects_blocked_directory(self) -> None:
        with self.assertRaises(PermissionError):
            server._resolve_workspace_path(".ssh/config")

    def test_rejects_secret_like_file(self) -> None:
        with self.assertRaises(PermissionError):
            server._resolve_workspace_path("project/.env")


class PatchPathSafetyTests(unittest.TestCase):
    def test_clean_patch_path_removes_git_prefix(self) -> None:
        self.assertEqual(server._clean_patch_path("a/README.md"), "README.md")
        self.assertEqual(server._clean_patch_path("b/server.py"), "server.py")

    def test_clean_patch_path_allows_dev_null(self) -> None:
        self.assertIsNone(server._clean_patch_path("/dev/null"))

    def test_clean_patch_path_rejects_unsafe_paths(self) -> None:
        with self.assertRaises(ValueError):
            server._clean_patch_path("../README.md")
        with self.assertRaises(ValueError):
            server._clean_patch_path("/tmp/README.md")
        with self.assertRaises(PermissionError):
            server._clean_patch_path(".git/config")

    def test_extract_patch_paths(self) -> None:
        patch = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-old
+new
"""
        self.assertEqual(server._extract_patch_paths(patch), ["README.md"])

    def test_validate_patch_paths_rejects_secrets(self) -> None:
        with self.assertRaises(PermissionError):
            server._validate_patch_paths(server.PROJECT_ROOT, [".env"])


class OperationIdTests(unittest.TestCase):
    def test_explicit_operation_id(self) -> None:
        self.assertEqual(server._normalize_operation_id("abc-123_ok"), "abc-123_ok")

    def test_rejects_invalid_operation_id(self) -> None:
        with self.assertRaises(ValueError):
            server._normalize_operation_id("bad id with spaces")


if __name__ == "__main__":
    unittest.main()
