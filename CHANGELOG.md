# Changelog

This project uses a lightweight changelog format inspired by Keep a Changelog.

## Unreleased

### Added

- Runtime storage cleanup management UI under Management > Storage Cleanup, including editable cleanup policy, preview/apply actions, backup-inclusive cleanup, and guarded clear-history flow.
- Count-based cleanup policy support for bundle history, tool calls, handoffs, and text payload records.
- History/results pagination with bounded default rendering and filter-preserving navigation for large bundle histories.
- Management > Worktree Task management page that separates actual Git task branch/worktree state from Workspace Bridge task record history, with direct cleanup controls for user-managed task branches, worktrees, and archived records.

### Changed

- Storage cleanup and Worktree Task management UI text is now Korean-first where it is user-facing.
- Task orchestration history is no longer shown inline on the main pending dashboard; the pending page links to the dedicated Worktree Task management page.

### Fixed

- CI path safety checks now treat workspace-relative development paths lexically so `.venv/bin/python` symlinks on GitHub Actions runners are not incorrectly classified as escaping `WORKSPACE_ROOT`.

## 0.4.0 - 2026-06-03

### Added

- Public MCP handoff lookup tool `workspace_get_handoff_for_bundle` for retrieving a specific bundle's handoff without relying on the global latest handoff stream.
- Metadata filters on `workspace_list_command_bundles` and `workspace_list_handoffs` for task, client, session, project, and workspace mode scoped listing.
- Review UI metadata badges and basic query filters for pending/history bundle lists.
- Project-specific `woojae help` command with English and Korean command descriptions.
- Setup-time `Help language` preference stored in runtime session settings.
- Purpose-specific public proposal tools: `workspace_propose_command_and_wait`, `workspace_propose_file_write_and_wait`, `workspace_propose_file_replace_and_wait`, `workspace_propose_patch_and_wait`, `workspace_propose_git_commit_and_wait`, and `workspace_propose_git_push_and_wait`.
- Optional proposal metadata inputs (`task_id`, `client_id`, `session_id`, `project_id`, `workspace_mode`) for direct-mode proposal routing and filtering.
- Scoped approval mode storage and effective lookup for project, client, and task-specific Safe Auto/YOLO settings.
- Task workspace runtime record foundation with public MCP helpers `workspace_prepare_task_workspace`, `workspace_task_workspace_status`, and `workspace_list_task_workspaces`.
- Public MCP helper `workspace_create_task_worktree` for explicitly creating a git worktree-backed task workspace under the runtime directory.
- Public MCP helper `workspace_inspect_task_worktree` for read-only task worktree status and diff inspection before merge queue integration.
- Public MCP helper `workspace_merge_preflight_task_worktree` for read-only task worktree merge readiness and conflict-risk inspection before merge queue integration.
- Public MCP helpers `workspace_enqueue_task_worktree_merge`, `workspace_merge_queue_status`, and `workspace_list_merge_queue` for merge queue record foundation without source-project apply.
- Public MCP helper `workspace_propose_task_worktree_merge_and_wait` for staging a locally approved source apply command from a queued task worktree merge.
- Public MCP helpers `workspace_archive_task_workspace` and `workspace_archive_merge_queue_entry` for non-destructive task workspace and queue record archiving.
- Operator guide for the end-to-end multi-session task workspace workflow, including worker prompts, merge review flow, and recovery checklists.
- Public MCP helper `workspace_task_orchestration_summary` for a read-only orchestrator overview of task workspace and merge queue records.
- Review UI task orchestration dashboard section on `/pending` for a compact read-only view of task workspace and merge queue summary records.
- Conflict handling operator guidance for source dirty state, source HEAD drift, overlapping files, queue/task record mismatch, requeue, and worker rework flows.
- Public MCP helpers `workspace_record_task_validation` and `workspace_task_validation_status` for recording and reading post-merge validation metadata on merge queue records.
- Public MCP helper `workspace_task_cleanup_preview` for read-only physical task worktree cleanup candidate detection.
- Public MCP helper `workspace_propose_task_cleanup_and_wait` for staging a locally approved task worktree cleanup command for ready archived task workspaces.
- Public MCP helper `workspace_propose_task_validation_command_and_wait` for staging a locally approved source-level validation command for merged task worktree results.
- Public MCP helper `workspace_task_validation_result_hint` for read-only validation command bundle result summaries and suggested manual validation record inputs.
- Public MCP helper `workspace_prepare_safe_task_merge_and_wait` for inspect/preflight/queue/proposal safe task merge orchestration without direct source apply.

### Changed

- The bundle watcher now resolves approval mode per pending bundle using metadata scope priority before falling back to the existing global mode.
- Review UI bundle cards now show the effective approval mode and scope used for that bundle.
- Review UI pending settings include a scoped approval override form and a saved scoped override list with delete actions.
- Proposal metadata now accepts `workspace_mode="task-workspace"` when a `task_id` is provided, preparing the metadata foundation for isolated task workspaces.
- Review UI bundle cards now show task workspace status, path, branch, and base ref for `workspace_mode="task-workspace"` bundles when available.
- Approved `task-workspace` bundles now apply inside their ready git worktree while preserving direct-mode runner behavior and source bundle `cwd` records.
- Review UI task workspace badges now include clean/dirty state, changed file count, and a compact diff stat summary when inspection is available.
- Task worktree preflight now reports source HEAD drift, source dirty state, overlapping file changes, conflict risk, and a recommended next action without modifying the source project.
- Task orchestration summary and `/pending` dashboard now surface source dirty, source HEAD drift, overlapping files, and operator attention indicators from merge queue records.
- Task orchestration summary and `/pending` dashboard now show post-merge validation status from merge queue records.
- `/pending` task orchestration dashboard now shows cleanup readiness, risk, blockers, recommended cleanup action, validation status, queue status, and workspace status from the read-only cleanup preview.
- `/pending` task orchestration dashboard now shows read-only validation result hints, including latest validation bundle id, inferred status candidate, next action, and manual record suggestion availability.
- Operator documentation now includes a primary orchestrator happy path for the task-workspace merge, validation, archive, and cleanup release checkpoint.
- User documentation now explains help language selection, `WOOJAE_HELP_LANG`, and Korean help usage.
- Default public MCP tool guidance now favors small proposal wrapper tools while keeping the generic bundle functions internally available.
- Refactored MCP tool helper implementations out of `server.py` into `terminal_bridge/mcp_tools/` modules while preserving public MCP tool names, wrappers, signatures, schemas, approval flow, and runner behavior.
- Refactored `server.py` internals for workspace tool list construction, MCP intent helpers, and stage bundle record construction without changing public MCP schemas or approval behavior.
- Refactored review server internals by extracting bundle state helpers and audit loading/sanitization helpers while preserving route, rendering, and approval behavior.
- Added `ruff` as a dev dependency, documented exploratory touched-file linting, and cleaned the targeted `server.py` / review server import baseline.
- Restored `graphify-out/` and `.graphify_*` ignore rules before public push preparation.
- Relaxed YOLO hard-block classification to keep only workspace escapes, exact `.env`, `.git`, `.aws`, `.gnupg`, and destructive disk/admin executables blocked while routing risky development commands through approval risk levels.
- Increased GPT-5.5-oriented workspace read, command, payload, stdout/stderr, and preview limits while centralizing limit values in `terminal_bridge/config.py`.

### Verified

- `uv run python -m unittest discover -s tests`
- `uv run python scripts/smoke_check.py`
- `uv run ruff check server.py`
- `uv run ruff check scripts/command_bundle_review_server.py`
- `git diff --check`

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
