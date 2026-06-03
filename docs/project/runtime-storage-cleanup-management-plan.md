# Runtime Storage Cleanup Management Plan

## Status

Planned for the `cleanup-update` branch.

This plan defines the durable product and implementation direction for keeping Workspace Terminal Bridge runtime history usable as bundle records, tool call records, handoffs, payloads, and backups accumulate over time.

## Problem

The local review UI currently records and displays large amounts of operational history:

- command bundle history: `pending`, `applied`, `failed`, and `rejected`
- tool call records
- local handoff records
- command text payload chunks
- operation metadata
- file backups, command bundle file backups, and trash
- process logs and audit logs

The runtime storage is intentionally local-first and reviewable, but long-running use can create thousands of records. That causes two separate problems:

1. The runtime directory grows over time.
2. The history UI becomes noisy and harder to navigate.

The cleanup update must solve both without weakening safety invariants.

## Goals

- Add a Management UI page for storage cleanup.
- Show current runtime storage usage and history counts.
- Add configurable cleanup policy values that users can edit from the UI.
- Support count-based cleanup in addition to existing age-based cleanup.
- Support a guarded "clear eligible history" action.
- Keep cleanup direct from the Management UI, not routed through the `/pending` proposal queue.
- Keep dangerous or live state protected.
- Improve the history/results UI so it does not render thousands of records at once.

## Non-goals

- Do not delete pending approval bundles automatically.
- Do not delete session configuration, session environment, or intent HMAC secrets.
- Do not silently run background cleanup by default.
- Do not use cleanup as a substitute for pagination in the history UI.
- Do not remove auditability for recent operational records.

## Safety invariants

The following must never be removed by ordinary cleanup or clear-history actions:

- `command_bundles/pending/**`
- `session.json`
- `session.env`
- `intent_hmac_secret`
- active process pid files under `processes/*.pid`
- paths outside the configured runtime root
- symlinks that could escape the runtime root

The cleanup implementation must continue to resolve and validate paths before deletion.

## Management UI design

Add a new Management navigation item:

```text
MANAGEMENT
- Overview
- Server
- Processes
- Connections
- Environment
- Local tools
- Diagnostics
- Storage Cleanup
```

Korean label: `저장소 정리`.
English label: `Storage Cleanup`.

The page should live under the existing review server management area, using the same page shell and styling as the other Management pages.

### Page sections

#### 1. Runtime storage summary

Show:

- runtime root path
- total bytes
- total files and directories
- category table/cards for:
  - `command_bundles`
  - `command_bundle_file_backups`
  - `tool_calls`
  - `handoffs`
  - `audit.jsonl`
  - `processes`
  - `operations`
  - `text_payloads`
  - `tasks`
  - `backups`
  - `trash`
  - `intent_imports`

#### 2. History counts

Show counts for:

- pending bundles
- applied bundles
- failed bundles
- rejected bundles
- total bundle history
- tool call records
- handoff records
- operation records
- text payload records

If a count exceeds policy recommendations, show a warning/recommendation card.

#### 3. Cleanup policy settings

Users must be able to edit the default retention policy from the UI.

Initial default policy:

| Key | Default | Meaning |
| --- | ---: | --- |
| `keep_applied` | 1000 | Keep newest applied bundle records. |
| `keep_failed` | 500 | Keep newest failed bundle records. |
| `keep_rejected` | 200 | Keep newest rejected bundle records. |
| `keep_tool_calls` | 2000 | Keep newest tool call records. |
| `keep_handoffs` | 1000 | Keep newest handoff records. |
| `keep_text_payloads` | 500 | Keep newest text payload records when count cleanup is enabled. |
| `older_than_text_payload_days` | 14 | Age threshold for text payloads. |
| `older_than_operations_days` | 30 | Age threshold for operation metadata. |
| `older_than_backups_days` | 30 | Age threshold for backups/trash when included. |
| `include_backups_by_default` | false | Whether ordinary cleanup includes backups/trash. |

Recommended validation:

- Empty input resets to default.
- Negative values are rejected.
- Zero is allowed only for explicit clear-history mode, not ordinary policy saves.
- Low values should show a warning but can be accepted for advanced users.
- Policy save must not require `/pending` approval because it is a Management UI configuration operation.

Policy storage:

```text
~/.mcp_terminal_bridge/my-terminal-tool/cleanup_policy.json
```

The file should be loaded from the runtime root and fall back to defaults if missing or invalid.

#### 4. Cleanup preview

A preview action calculates cleanup candidates without deleting anything.

Preview output should include:

- candidate count by category
- candidate bytes by category
- total estimated reclaimed bytes
- protected item summary
- active policy values used
- whether backups are included
- whether clear-history mode is selected

#### 5. Cleanup actions

Provide these actions:

- `Preview default cleanup`
- `Run default cleanup`
- `Preview cleanup including backups`
- `Run cleanup including backups`
- `Clear eligible history` in a separate dangerous-actions section

Deletion actions should be direct Management UI operations, not `/pending` proposals. They still need an explicit confirmation step.

#### 6. Confirmation UX

Ordinary cleanup confirmation:

```text
This will delete eligible runtime cleanup candidates.
Pending bundles, session config, and secrets will be preserved.
[Cancel] [Run cleanup]
```

Clear eligible history confirmation:

```text
This will delete all eligible history records.
Pending bundles, session config, secrets, and active pid files will be preserved.
This cannot be undone.
Type DELETE HISTORY to continue.
```

The server must require the exact confirmation text `DELETE HISTORY` for the clear-history action.

## Cleanup policy semantics

### Ordinary cleanup

Ordinary cleanup combines age-based and count-based candidates.

A file or directory is a candidate if it is either:

- older than the configured age threshold for its category, or
- older than the newest N records that must be preserved for its category.

The candidate list should be de-duplicated before deletion.

### Count-based cleanup

Count-based cleanup applies to:

- `command_bundles/applied`
- `command_bundles/failed`
- `command_bundles/rejected`
- `tool_calls`
- `handoffs`
- `text_payloads`

Ordering should prefer record metadata timestamps when available, with filesystem mtime as fallback. The newest N records are preserved; older records become candidates.

### Clear eligible history

Clear eligible history is an explicit dangerous action. It ignores ordinary keep counts and marks all eligible history as candidates, while still preserving protected/live state.

It should delete candidates from:

- `command_bundles/applied`
- `command_bundles/failed`
- `command_bundles/rejected`
- `tool_calls`
- `handoffs`
- `operations`
- `text_payloads`
- `intent_imports`
- `trash`

Backups should be included only when the user explicitly selects a backup-inclusive mode.

`audit.jsonl` and process logs should initially remain outside clear-history deletion unless a future dedicated log-management policy is added. This avoids accidentally removing the current session's diagnostics.

## CLI design

The existing cleanup commands should keep working:

```bash
uv run woojae cleanup --dry-run
uv run woojae cleanup --apply
uv run woojae cleanup --dry-run --include-backups
uv run woojae cleanup --apply --include-backups
```

Extend cleanup to use the saved cleanup policy by default.

Add optional flags:

```bash
uv run woojae cleanup --dry-run --prune-all-history
uv run woojae cleanup --apply --prune-all-history
uv run woojae cleanup --dry-run --prune-all-history --include-backups
uv run woojae cleanup --apply --prune-all-history --include-backups
```

`--prune-all-history` maps to the Management UI's clear-history preview/apply mode.

## History/results UI improvement

Cleanup reduces stored data, but the history/results UI must also stop rendering excessive records.

Required history UI changes:

- default to the newest 100 records
- support `limit` and `page` query parameters
- preserve status filters and metadata filters while paginating
- show total count and visible range
- keep quick access to recent failed bundles

The top summary cards should continue to show total counts even when the rendered list is limited.

## Suggested endpoint design

Use the existing review server rather than a new process.

Candidate routes:

```text
GET  /manage/storage-cleanup
POST /manage/storage-cleanup/policy
POST /manage/storage-cleanup/preview
POST /manage/storage-cleanup/apply
POST /manage/storage-cleanup/clear-history
```

If the current review server route style prefers non-`/manage` paths, keep route names consistent with the existing Management pages.

## Implementation areas

Likely files:

- `terminal_bridge/runtime_storage.py`
- `terminal_bridge/session_supervisor.py`
- `terminal_bridge/cli.py`
- `scripts/command_bundle_review_server.py`
- `terminal_bridge/bundles.py`
- `terminal_bridge/tool_calls.py` or current tool-call record helpers if present
- `terminal_bridge/handoffs.py`
- tests under `tests/`

## Test expectations

Add tests for:

- default cleanup policy loading and fallback
- cleanup policy save and validation
- count-based command bundle candidate selection
- pending bundle protection
- protected root file protection
- tool call count-based cleanup
- handoff count-based cleanup
- clear-history mode candidate selection
- backup inclusion/exclusion
- direct Management apply requiring confirmation
- clear-history requiring exact `DELETE HISTORY`
- history pagination preserving counts and filters

Minimum verification for the final implementation:

```bash
uv run python -m unittest discover -s tests
uv run python scripts/smoke_check.py
git diff --check
```

For touched Python files, also run targeted ruff checks.

## Parallel work split

The `cleanup-update` branch should act as the orchestrator branch. Worker sessions should be isolated with task workspaces. Each worker should make focused changes and then queue a safe merge back to `cleanup-update`.

Recommended worker tasks:

1. `cleanup-policy-core`
   - Runtime cleanup policy model, persistence, count-based candidates, clear-history candidate mode, CLI integration, core tests.
2. `cleanup-management-ui`
   - Management navigation/page, policy form, preview/apply endpoints, confirmation UX, UI tests.
3. `cleanup-history-pagination`
   - History/results limit/page behavior, query preservation, rendering updates, pagination tests.
4. `cleanup-docs-validation`
   - User/operator docs, CHANGELOG, final verification, release notes preparation after code merges.

Worker tasks should not commit or push independently unless explicitly instructed. Each worker should update its active task document and use the task workspace merge flow for orchestrator review.

## Completion criteria

The cleanup update is complete when:

- Management UI includes Storage Cleanup.
- Users can edit and save cleanup policy values.
- Preview shows cleanup candidates and expected reclaimed size.
- Ordinary cleanup can run directly from Management UI after confirmation.
- Clear eligible history requires `DELETE HISTORY` and preserves protected/live state.
- CLI cleanup uses the same policy semantics.
- History/results UI is paginated and defaults to a bounded list.
- Tests and smoke checks pass.
- Docs and CHANGELOG are updated.
