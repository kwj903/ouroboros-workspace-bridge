from __future__ import annotations

import unittest

from scripts import update_version_info


class UpdateVersionInfoTests(unittest.TestCase):
    def test_normalize_for_check_ignores_only_recent_commits(self) -> None:
        first = """# Update Info

Version: 0.2.0

For live local version and git state, run:

```bash
uv run woojae version
```

## Recent Commits

Recent Commits is a generated snapshot. Run `uv run python scripts/update_version_info.py` before releases or documentation refreshes.

- aaa1111 First commit

## How to Update Existing Installation

```bash
git pull origin main
uv sync
uv run woojae restart-session
uv run woojae status
```

After MCP tool or schema changes, refresh or reconnect the ChatGPT custom MCP connector.
"""
        second = first.replace("- aaa1111 First commit", "- bbb2222 Second commit\n- ccc3333 Third commit")

        self.assertEqual(update_version_info.normalize_for_check(first), update_version_info.normalize_for_check(second))

    def test_normalize_for_check_detects_version_changes(self) -> None:
        first = update_version_info.render_update_info()
        second = first.replace("Version: 0.2.0", "Version: 9.9.9")

        self.assertNotEqual(update_version_info.normalize_for_check(first), update_version_info.normalize_for_check(second))

    def test_normalize_for_check_detects_update_command_changes(self) -> None:
        first = update_version_info.render_update_info()
        second = first.replace("uv run woojae status", "uv run woojae doctor")

        self.assertNotEqual(update_version_info.normalize_for_check(first), update_version_info.normalize_for_check(second))


if __name__ == "__main__":
    unittest.main()
