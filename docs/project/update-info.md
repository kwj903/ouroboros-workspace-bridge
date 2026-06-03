# Update Info

Version: 0.4.0

For live local version and git state, run:

```bash
uv run woojae version
```

## Recent Commits

Recent Commits is a generated snapshot. Run `uv run python scripts/update_version_info.py` before releases or documentation refreshes.

- e01c213 docs: record task orchestration release checkpoint
- 64f7d10 feat: orchestrate safe task merge proposals
- 9260afb feat: surface validation result hints in dashboard
- dbdd81f feat: add task validation result hints
- 0fa580c feat: stage task validation command proposals
- 61029c8 feat: show cleanup readiness in task dashboard
- 69f1ebd feat: add approved task worktree cleanup execution
- 5af49ab feat: preview task workspace cleanup readiness
- 68d4057 feat: track task validation results
- 4f6ad76 feat: highlight task orchestration conflict risks
- 635f57e feat: render task orchestration dashboard
- 42163ab feat: add task orchestration summary
- f875e85 docs: add multi-session task workspace operator guide
- f6a9f82 feat: archive task workspace records
- f1eef3e feat: add approved task worktree integration staging
- e99112e feat: add task worktree merge queue records
- 7e5e202 feat: add task worktree merge preflight
- 8bddb61 feat: inspect task worktree changes
- 94bc9a7 feat: route task workspace bundles to worktrees
- e551757 feat: add task worktree creation foundation

## How to Update Existing Installation

```bash
uv run woojae update
```

Preview the update steps without changing files:

```bash
uv run woojae update --dry-run
```

After MCP tool or schema changes, refresh or reconnect the ChatGPT custom MCP connector.
