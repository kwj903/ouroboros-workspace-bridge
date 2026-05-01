# Update Info

Version: 0.3.1

For live local version and git state, run:

```bash
uv run woojae version
```

## Recent Commits

Recent Commits is a generated snapshot. Run `uv run python scripts/update_version_info.py` before releases or documentation refreshes.

- 890ce7c Clean up companion flow and relax bundle limits
- 18c9442 Refactor MCP and review server helpers
- 21708cc Add local pending action intents
- a10a7a3 Add ChatGPT companion workflow prototype
- 20dd5d4 Fix review UI horizontal overflow
- 5adb855 Add bundle handoff queue
- 25b799a Collapse intent inbox in review UI
- 0afd266 Add intent inbox to review UI
- 510f9f3 Show bundle handoff summaries in review UI
- 37814d3 Polish intent workflow and check handling
- 8ec0505 Import intents into pending review UI
- 905085e Add read-only intent review flow
- 469bfc7 Add transport probe tool
- d68f8ef Add submit-first command bundle tools
- ccc5877 Add request key dedupe for command bundles
- f09bd37 Add tool call journal
- e04225b Add recovery snapshot tool
- 944856c Hide primitive stage tools from MCP schema
- 1331602 Add version and update info tooling
- 1954b91 Share watcher logic across review modes

## How to Update Existing Installation

```bash
git pull origin main
uv sync
uv run woojae restart-session
uv run woojae status
```

After MCP tool or schema changes, refresh or reconnect the ChatGPT custom MCP connector.
