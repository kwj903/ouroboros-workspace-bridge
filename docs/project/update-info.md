# Update Info

Version: 0.3.1

For live local version and git state, run:

```bash
uv run woojae version
```

## Recent Commits

Recent Commits is a generated snapshot. Run `uv run python scripts/update_version_info.py` before releases or documentation refreshes.

- cea43ec Update docs for proposal wrapper workflow
- 22af817 Avoid reopening browser during session restart
- 2f9fd50 Add purpose-specific proposal wrapper tools
- a0d69bd Refresh update info snapshot
- 06a8da6 Document localized CLI help workflow
- ff9c364 Persist CLI help language preference
- 224defc Add localized CLI help command
- 147c350 Improve public README and issue templates
- bca50d1 Add runtime storage management commands
- dda6993 Release 0.3.0 cross-platform session support
- 3e48144 Fix process table layout overflow
- 48cc1a8 Release 0.2.0
- 890ce7c Clean up companion flow and relax bundle limits
- 18c9442 Refactor MCP and review server helpers
- 21708cc Add local pending action intents
- a10a7a3 Add ChatGPT companion workflow prototype
- 20dd5d4 Fix review UI horizontal overflow
- 5adb855 Add bundle handoff queue
- 25b799a Collapse intent inbox in review UI
- 0afd266 Add intent inbox to review UI
- 510f9f3 Show bundle handoff summaries in review UI

## How to Update Existing Installation

```bash
git pull origin main
uv sync
uv run woojae restart-session
uv run woojae status
```

After MCP tool or schema changes, refresh or reconnect the ChatGPT custom MCP connector.
