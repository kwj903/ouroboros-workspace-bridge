# Update Info

Version: 0.4.1

For live local version and git state, run:

```bash
uv run woojae version
```

## Recent Commits

Recent Commits is a generated snapshot. Run `uv run python scripts/update_version_info.py` before releases or documentation refreshes.

- a5f8040 Document Pydantic schema usability improvements
- 4399287 Add typed preparation result schemas
- b536e61 Type transport and recovery tool results
- ecb53f3 Improve Pydantic result schema metadata
- 2e9e3de refactor: centralize proposal wait config
- 82700cc fix-ci-path-handling
- 5c873ed merge cleanup-update
- cfc17d0 feat: finalize cleanup management UI
- 5521e88 feat: add storage cleanup management UI
- 8ea7903 feat: paginate bundle history view
- ca620f1 feat: add runtime cleanup policy core
- 1f87c13 docs: plan runtime storage cleanup management
- c92edcf chore: release v0.4.0
- e01c213 docs: record task orchestration release checkpoint
- 64f7d10 feat: orchestrate safe task merge proposals
- 9260afb feat: surface validation result hints in dashboard
- dbdd81f feat: add task validation result hints
- 0fa580c feat: stage task validation command proposals
- 61029c8 feat: show cleanup readiness in task dashboard
- 69f1ebd feat: add approved task worktree cleanup execution

## How to Update Existing Installation

```bash
uv run woojae update
```

Preview the update steps without changing files:

```bash
uv run woojae update --dry-run
```

After MCP tool or schema changes, refresh or reconnect the ChatGPT custom MCP connector.
