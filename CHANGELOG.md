# Changelog

This project uses a lightweight changelog format inspired by Keep a Changelog.

## Unreleased

## 0.6.0 - 2026-08-07

### Changed

- Concurrent ChatGPT sessions and other AI clients now use one direct workspace execution path with logical `task_id`, `client_id`, `session_id`, and `project_id` metadata for request identity, bundle/handoff filtering, and result separation.
- Public proposal schemas describe `session_id` as the conversation separation key and no longer expose the retired `workspace_mode` routing option.
- YOLO now acts as an approval all-pass mode: every valid pending bundle is submitted to the runner without requiring a manual approval click, including bundles labeled `blocked` or touching sensitive-path patterns.
- Automatic approval modes now resume eligible bundles that were already pending when the review watcher starts instead of treating all pre-existing pending bundles as already seen.

### Removed

- Removed the task-workspace/worktree orchestrator, merge queue, worktree merge/preflight, task validation/cleanup lifecycle, Worktree Task management UI, and their public MCP tools. Historical runtime records are not deleted, but new work no longer creates or routes through them.
- Removed the legacy task-workspace operator plans now that concurrent work is separated by logical metadata instead of physical Git worktrees.

### Fixed

- The pending watcher no longer consumes a bundle permanently when it observes the JSON file while it is still being written; unreadable/incomplete records are retried on a later poll.
- YOLO no longer falls back to a manual review notification when the automatic runner invocation itself fails; execution failures remain failures rather than approval prompts.

## 0.5.0 - 2026-08-03

### Added

- New `terminalbridge` operator CLI for complete `setup`, `start`, `stop`, `restart`, `status`, `logs`, `doctor`, onboarding, and connector-URL workflows.
- Managed Cloudflare Tunnel profile using each installation's own public URL, cloudflared config path, tunnel name, executable, account, domain, and credentials.
- Explicit `--mode ngrok|cloudflare|external` switching while preserving provider-specific configuration for later reuse.
- Safe cloudflared PID, log, and process-metadata tracking under the private runtime process directory.
- Bilingual documentation for user-owned ngrok, managed Cloudflare, generic external connectors, and single-active-computer handoff.

### Changed

- Normal complete-stack operation now uses `uv run terminalbridge ...`; the existing `uv run woojae ...` CLI remains the low-level Bridge supervisor and compatibility interface.
- Review UI full-session stop and restart actions now include the selected managed public connector through the operator layer.
- Setup and setup UI distinguish ngrok, managed Cloudflare, and generic external profiles.
- User-facing examples use neutral placeholder domains instead of a maintainer-specific endpoint.
- Release version updated to `0.5.0` without changing the public MCP tool schema.

### Security

- No maintainer token, public domain, tunnel ID, Cloudflare credential, account-specific config, or local absolute path is used as a working product default.
- Managed cloudflared shutdown verifies the executable, config path, and tunnel name before termination; stale or reused PID tracking is removed without killing an unrelated process.
- Remote smoke checks use an in-process MCP client with a Bearer header, reject token-bearing URL arguments, and no longer place the connector token in subprocess argv.
- The review UI remains loopback-only and shared-domain connectors must remain active on only one computer at a time.

## 0.4.3 - 2026-08-02

### Added

- Provider-neutral `external` public access mode for user-managed HTTPS domains and tunnels while keeping ngrok as the default.
- Validated `PUBLIC_MCP_URL` configuration with safe hostname extraction, token encoding, and redacted URL output.
- Mode-aware setup UI, review UI status, supervisor controls, diagnostics, and bilingual public access documentation.
- Regression coverage for external settings persistence, ngrok-to-external lifecycle transitions, UI rendering, URL validation, and shared-domain operation.

### Changed

- The supervisor starts review and MCP only in external mode and continues to manage review, MCP, and ngrok in the default ngrok mode.
- Full session stop and restart always clean up managed ngrok state before starting the services active for the selected mode.
- MCP transport host/origin allowlists now use the hostname selected from either `NGROK_HOST` or `PUBLIC_MCP_URL`.
- Remote smoke checks now derive their endpoint through the shared public-access helper instead of assuming ngrok.
- Release version updated to `0.4.3` without changing the public MCP tool schema.

### Fixed

- Windows physical-host tests no longer inherit an existing external public-access session when validating the legacy ngrok URL helper.
- Task-workspace command routing tests now invoke the active Python interpreter instead of assuming a `python3` launcher exists on Windows.
- Review, bundle-runner, and Git worktree subprocess capture tolerates mixed UTF-8/local-codepage output on non-UTF-8 Windows system locales without reader-thread decode failures.
- Review and MCP PID files whose endpoints are no longer reachable are treated as stale, preventing Windows PID reuse from blocking restart or terminating an unrelated process.

### Security

- External URLs must use HTTPS and cannot contain credentials, query strings, fragments, or access tokens.
- The review UI remains localhost-only, and documentation requires only one shared-domain connector to be active at a time.
- External tunnel credentials remain outside repository and runtime session configuration.

## 0.4.2 - 2026-07-23

### Added

- GitHub Actions coverage for Ubuntu, macOS, and Windows, including platform-specific Bash and PowerShell syntax checks.
- CI bootstrap actions use current Node 24-based checkout, Python, and uv action releases.
- Windows regression coverage for non-destructive process status probing and cross-platform supervisor command construction.

### Changed

- Review UI process controls now invoke the shared Python CLI entrypoint instead of a Bash-only wrapper.
- Approved command execution now uses one shared cross-platform safe environment builder with OS-specific virtualenv paths and Windows process-launch variables.
- User-facing process-management instructions now use the platform-neutral `uv run woojae ...` command form.
- The smoke check allows enough time for the expanded cross-platform unit suite to complete on hosted CI runners.
- Bundle staging and intent tests now isolate runtime storage so a running local watcher cannot apply test bundles.

### Fixed

- Windows status checks no longer call `os.kill(pid, 0)`, which can terminate the target process on Windows; the supervisor now uses a read-only Win32 process query.
- Full-session stop and restart actions from the review UI now work without requiring Bash on Windows.
- Detached full-session stop/restart commands can finish PID cleanup after terminating the review service on every platform.
- PATH fallback construction now uses the current OS path separator and `.venv/Scripts` on Windows.
- Legacy `session.env` parsing preserves Windows drive paths and backslashes.
- Patch path validation recognizes unsafe absolute and traversal paths in both POSIX and Windows syntax.
- Review UI runtime paths use stable forward-slash display formatting across platforms.
- `woojae version` now reports a clean Git worktree as `dirty: no` instead of `unknown`.

## 0.4.1 - 2026-06-06

### Added

- Runtime storage cleanup management UI under Management > Storage Cleanup, including editable cleanup policy, preview/apply actions, backup-inclusive cleanup, and guarded clear-history flow.
- Count-based cleanup policy support for bundle history, tool calls, handoffs, and text payload records.
- History/results pagination with bounded default rendering and filter-preserving navigation for large bundle histories.
- Management > Worktree Task management page that separates actual Git task branch/worktree state from Workspace Bridge task record history, with direct cleanup controls for user-managed task branches, worktrees, and archived records.

### Changed

- Improved public MCP result schema usability with concise field descriptions and named Pydantic result models for transport probe, recovery, and intent preparation tools; public tool names and JSON response fields remain unchanged, while direct Python callers now receive typed model instances.
- Public MCP proposal wait defaults are now centralized in `terminal_bridge/config.py`, with the default wait increased to 300 seconds and the maximum wait increased to 900 seconds for long approved local tasks.
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
