from __future__ import annotations

import unittest

from terminal_bridge import version


class VersionHelperTests(unittest.TestCase):
    def test_version_summary_handles_unknown_git_data(self) -> None:
        original_git_output = version._git_output

        try:
            version._git_output = lambda _args: None
            summary = version.version_summary()
        finally:
            version._git_output = original_git_output

        self.assertEqual(summary["name"], "Ouroboros Workspace Bridge")
        self.assertEqual(summary["version"], version.__version__)
        self.assertEqual(summary["commit"], "unknown")
        self.assertEqual(summary["branch"], "unknown")
        self.assertEqual(summary["dirty"], "unknown")


if __name__ == "__main__":
    unittest.main()
