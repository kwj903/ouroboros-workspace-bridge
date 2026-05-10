# Update Info

Version: 0.3.1

For live local version and git state, run:

```bash
uv run woojae version
```

## Recent Commits

Recent Commits is a generated snapshot. Run `uv run python scripts/update_version_info.py` before releases or documentation refreshes.

- 82b6e58 docs: document MCP helper refactor workflow
- e3846ba chore: stop tracking graphify outputs
- 5d64d09 Merge branch 'refactor/server-readonly-tools'
- 1138304 chore: update graphify output
- b4943f1 refactor: extract status MCP tool helpers
- 82aec40 chore: update graphify output
- 43c8615 refactor: extract command bundle MCP helpers
- 54d1457 refactor: extract proposal MCP tool helpers
- 033f8a0 refactor: extract readonly MCP tool helpers
- 1ccc968 chore: ignore graphify outputs
- 5c26c9c Fix update info test expectation
- 5ed6768 Improve README setup helper documentation
- a046f6f Add update command for existing installs
- 0a21bcb Add setup UI onboarding helper
- 7f1558d Clarify README onboarding flow
- f405349 Improve first-run onboarding docs
- 259cd65 Add pending review UI guide
- 1730f54 Add ChatGPT app setup guide
- add45b7 Improve README landing quick start
- 07c1b90 Add Korean README language switch

## How to Update Existing Installation

```bash
uv run woojae update
```

Preview the update steps without changing files:

```bash
uv run woojae update --dry-run
```

After MCP tool or schema changes, refresh or reconnect the ChatGPT custom MCP connector.
