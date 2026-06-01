# Update Info

Version: 0.3.1

For live local version and git state, run:

```bash
uv run woojae version
```

## Recent Commits

Recent Commits is a generated snapshot. Run `uv run python scripts/update_version_info.py` before releases or documentation refreshes.

- 928ea86 docs: add multi-agent task orchestration plan
- 9aba4f7 Refactor limits for GPT-5.5 context
- 2c489b0 사용제한 풀기 update
- d8a3eab .env.* rm
- b83ff2b docs: record refactor stabilization updates
- 4a07231 chore: clean up ruff baseline imports
- a0d6704 refactor: extract review audit helpers
- b1818fe refactor: extract review server state helpers
- 240bb05 refactor: extract stage bundle helpers
- 3261fbf chore: add ruff as dev dependency
- 4e16fd9 refactor: extract MCP intent helpers
- f601e2b Merge pull request #1 from kwj903/codex/refactor-public-tool-surface
- 772fc60 .gitignore update
- e201361 docs: refresh update info snapshot
- 82b6e58 docs: document MCP helper refactor workflow
- e3846ba chore: stop tracking graphify outputs
- 5d64d09 Merge branch 'refactor/server-readonly-tools'
- 1138304 chore: update graphify output
- b4943f1 refactor: extract status MCP tool helpers
- 82aec40 chore: update graphify output

## How to Update Existing Installation

```bash
uv run woojae update
```

Preview the update steps without changing files:

```bash
uv run woojae update --dry-run
```

After MCP tool or schema changes, refresh or reconnect the ChatGPT custom MCP connector.
