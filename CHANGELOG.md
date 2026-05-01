# Changelog

This project uses a lightweight changelog format inspired by Keep a Changelog.

## 0.3.1

### Added

- Runtime storage inspection commands: `woojae paths`, `woojae storage`, and `woojae cleanup`.
- Conservative cleanup dry-run/apply workflow with protected session secrets, pending bundles, and pid files.
- Runtime storage tests covering protected files, pending bundles, symlink exclusion, backup/trash opt-in, and dry-run behavior.

### Changed

- Runtime data management documentation now explains storage inspection, dry-run cleanup, and backup/trash cleanup opt-in behavior.
- `cleanup --older-than-days` now rejects non-positive values.

### Verified

- `uv run python -m compileall -q server.py terminal_bridge scripts`
- `env PYTHONPATH=. uv run --with pytest pytest`

## 0.3.0

### Added

- Cross-platform Python session supervisor for macOS, Linux, and Windows local workflows.
- Windows PowerShell install and dev-session wrappers.
- OS-specific desktop notification support for macOS, Linux, and Windows with safe fallbacks.
- OS-specific installation and quickstart documentation.

### Changed

- Official local workflow now centers on `uv run woojae ...`, with shell scripts kept as compatibility wrappers.
- Increased workspace read limits for larger code and documentation reviews.
- Review watcher and review UI notification wording is now OS-neutral.
- `woojae doctor` reports platform-specific optional notification, browser-open, and clipboard helpers.

### Verified

- `uv run python -m compileall -q server.py terminal_bridge scripts`
- `env PYTHONPATH=. uv run --with pytest pytest`

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
