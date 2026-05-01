# Changelog

This project uses a lightweight changelog format inspired by Keep a Changelog.

## 0.2.0

### Added

- Stage-and-wait bundle tools for local approval flows.
- Approval mode UI with Normal, Safe Auto, and YOLO modes.
- Shared watcher logic across the embedded review-server watcher and standalone watcher.
- `woojae restart-session` for restarting the full local review, MCP, and ngrok session.
- Detailed ChatGPT custom MCP connector documentation.
- Configurable `WORKSPACE_ROOT` support.
- `woojae` CLI for setup, start, status, logs, URL copy, and session management.
- ngrok fixed-domain and temporary URL mode support.
- Non-commercial license metadata.
- Bilingual Korean and English user documentation.

### Changed

- The default ChatGPT mutation flow now uses `workspace_stage_*_and_wait` proposal tools that create local `/pending` review items instead of directly applying changes.
- Action and command proposal wrappers enforce one action or one command step per call.
- Submit-first tools, signed-intent preparation tools, and direct operation/trash tools are hidden from the default public MCP schema.
- File action bundles snapshot target files before apply and roll back action changes on failure.
- Risky local operations continue to route through approval bundles by default.
- Review UI and watcher behavior remain local-first and approval-oriented.
- Version numbers are manually bumped for releases; they are not automatically bumped on every push.
- Update info is a generated snapshot from git metadata, while `woojae version` shows live local commit and dirty state.

### Verified

- `uv run python -m unittest discover -s tests`
- `uv run python scripts/update_version_info.py --check`
- `git diff --check`

## 0.1.0

- Initial public repository metadata and local MCP bridge workflow.
