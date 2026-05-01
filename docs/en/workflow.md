# Recommended Local Workflow

This workflow is the default path for using Ouroboros Workspace Bridge from ChatGPT.

The current default is the bundle-first MCP flow: ChatGPT submits a durable bundle, and the actual file change, command execution, or commit happens only after the local review UI approves it. The earlier browser companion / `ouroboros-intent` prototype is discontinued and should not be documented as the normal path.

## Normal Local Work

1. Inspect the workspace with read-only tools when needed.

   Useful examples:

   ```text
   workspace_git_status
   workspace_read_file
   workspace_search_text
   workspace_project_snapshot
   ```

2. Stage a proposal bundle for local approval.

   Preferred public bundle tools:

   ```text
   workspace_stage_action_bundle_and_wait
   workspace_stage_command_bundle_and_wait
   workspace_stage_patch_bundle_and_wait
   workspace_stage_commit_bundle_and_wait
   ```

   These tools create pending proposal bundles in the local `/pending` review UI and briefly wait for status. ChatGPT does not directly modify project files or directly run commands/git operations. Actual changes happen only after the user approves the proposal in the local browser and the local runner applies it.

   `workspace_stage_action_bundle_and_wait` accepts exactly one action per call. `workspace_stage_command_bundle_and_wait` accepts exactly one command step per call. Split multiple edits, checks, or commits into repeated calls.

   File action bundles can run in non-git directories under `WORKSPACE_ROOT`; they no longer require a `git status` clean-worktree preflight. Rollback for file actions uses file snapshots captured before applying the bundle.

3. Review and approve locally.

   Open the local pending review UI:

   ```text
   /pending
   /pending?bundle_id=<bundle_id>
   ```

   The bundle-focused page shows `pending`, `applied`, `failed`, and `rejected` records. It includes a compact `Copy for ChatGPT` JSON block.

4. Continue from the result.

   Preferred continuation order:

   ```text
   workspace_next_handoff
   workspace_list_handoffs
   Copy for ChatGPT JSON
   workspace_command_bundle_status
   workspace_recover_last_activity
   ```

   Use `workspace_recover_last_activity` for debugging or interrupted calls, not as the normal continuation path.

## Tool Priority

Preferred order:

1. Read-only inspection tools
2. `workspace_stage_*_and_wait` proposal tools
3. Local pending review UI approval
4. Bundle status / recovery tools
5. Handoff tools for advanced continuation or debugging
6. Payload / patch helper tools only when large documents or patches are needed
7. Submit-first, signed intent, and direct operation/trash tools stay hidden from the default public MCP schema

`workspace_stage_*_and_wait` tools are the default public mutation path. They create `/pending` proposals and briefly wait for status. If a proposal remains pending, continue with `workspace_command_bundle_status`, `workspace_wait_command_bundle_status`, or `workspace_recover_last_activity`.

## Signed Intent / Direct Operation Tools

Signed intent preparation tools and direct operation/trash tools are hidden from the default public MCP schema.

```text
workspace_prepare_check_intent
workspace_prepare_commit_current_changes_intent
workspace_prepare_dev_session_intent
workspace_get_operation
workspace_list_operations
workspace_list_trash
```

Their implementations may remain available internally, but they are not exposed in the default ChatGPT connector to reduce tool-selection confusion. The default flow uses `workspace_stage_*_and_wait` proposal tools and the local `/pending` review UI.

The advanced Intent Inbox on `/pending` and the `/intents/import` route may remain available for internal or advanced workflows.

## Discontinued Companion Prototype

The browser companion / `ouroboros-intent` block prototype is no longer part of the supported workflow.

Do not rely on:

```text
browser/ouroboros-companion.user.js
ouroboros-intent fenced blocks
JSON POST imports to /intents/import
```

`/intents/import` is kept for signed token form imports only. JSON companion imports are intentionally rejected.

## UI Routes

Useful local routes:

```text
/pending
/pending?bundle_id=<bundle_id>
/review-intent?token=...
/review-intent/preview?token=...
/intents/import
/handoffs/latest
```

## Handoff Records

When a bundle reaches a final state, the local runner writes a compact handoff record under:

```text
~/.mcp_terminal_bridge/my-terminal-tool/handoffs
```

Each record includes:

```text
handoff_id
bundle_id
status
ok
risk
title
cwd
next
stdout_tail
stderr_tail
created_at
updated_at
```

The tails are compact and token-like values are redacted.

## Local Environment Note

`bash scripts/check_all.sh` runs local checks first.

If remote MCP Inspector checks are configured but `npx` is missing, the script prints:

```text
Remote MCP smoke skipped: npx not found on PATH.
```

This is a successful skip when local checks pass. Install Node.js/npm to enable remote MCP Inspector checks.

## Regression Checklist

Manual checks before considering this workflow healthy:

- `/pending` has no page-level horizontal scroll.
- Intent Inbox is collapsed under the advanced section.
- `workspace_stage_*_and_wait` proposal tools create pending proposal bundles without directly applying changes.
- Pending bundles can be approved or rejected in the local pending review UI.
- A YOLO-applied bundle is still visible at `/pending?bundle_id=<bundle_id>`.
- The bundle-focused page shows `Copy for ChatGPT` JSON.
- `workspace_next_handoff` returns the latest handoff after local execution.
- Primitive stage tools are absent from `workspace_info().tools`.
- JSON companion imports to `/intents/import` are rejected.
- `bash scripts/check_all.sh` exits `0` when local checks pass and `npx` is missing.
