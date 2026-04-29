# Update Info

Version: 0.1.0

For live local version and git state, run:

```bash
uv run woojae version
```

## Recent Commits

Recent Commits is a generated snapshot. Run `uv run python scripts/update_version_info.py` before releases or documentation refreshes.

- 1954b91 Share watcher logic across review modes
- 6ef7baa Add restart-session CLI command and connection docs
- ae6f208 Add approval mode controls
- d9eafed Add stage-and-wait bundle tools
- ae113bd Add optional MCP token generation in setup
- 46b7b02 Set workspace root in CI
- 1259dcd Align bilingual user docs
- e124f34 Document platform support
- ce0f8ec Add non-commercial license metadata
- 70665bf Document contribution license
- a1cfa62 Document non-commercial license
- ec8d961 Adopt non-commercial license
- 668b50c Update README repository URL
- 1d3f43e Organize bilingual user docs
- f1503ef Show Ouroboros logo in README
- 5bafdce Add Ouroboros brand assets
- 2634482 Add repository hygiene docs and CI
- e1c73fa Add configurable workspace root and woojae CLI
- b87660e Document payload ref usage thresholds
- 62ff809 Link ChatGPT project instructions guide from README

## How to Update Existing Installation

```bash
git pull origin main
uv sync
uv run woojae restart-session
uv run woojae status
```

After MCP tool or schema changes, refresh or reconnect the ChatGPT custom MCP connector.
