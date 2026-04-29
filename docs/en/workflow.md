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

2. Submit a bundle for local approval.

   Preferred public bundle tools:

   ```text
   workspace_submit_command_bundle
   workspace_submit_action_bundle
   workspace_submit_patch_bundle
   workspace_submit_commit_bundle
   ```

   These tools create pending bundle records and return quickly. They do not apply project changes by themselves.

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
2. Submit-first bundle tools
3. Local pending review UI approval
4. Handoff queue
5. Read-only signed intent tools as fallback or convenience
6. `workspace_stage_*_and_wait` tools only as legacy or convenience fallback
7. Primitive stage tools must remain hidden from the public MCP schema

The `workspace_stage_*_and_wait` wrappers keep one ChatGPT tool call open while polling for local approval. Their approval/status wait timeout is capped at 45 seconds. Prefer submit-first tools plus handoff/status checks for routine work.

## Signed Intent Fallback

Read-only signed intent tools remain available:

```text
workspace_prepare_check_intent
workspace_prepare_commit_current_changes_intent
workspace_prepare_dev_session_intent
```

They return a signed `local_review_url`. Opening the URL from the local browser imports the intent into the same pending bundle approval flow.

The advanced Intent Inbox on `/pending` accepts either:

- a full `local_review_url`
- a raw signed intent token

The import is idempotent. Re-importing the same token redirects to the same bundle when the bundle is still available.

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
- Submit-first bundle tools create pending bundles without applying changes.
- Pending bundles can be approved or rejected in the local pending review UI.
- A YOLO-applied bundle is still visible at `/pending?bundle_id=<bundle_id>`.
- The bundle-focused page shows `Copy for ChatGPT` JSON.
- `workspace_next_handoff` returns the latest handoff after local execution.
- Primitive stage tools are absent from `workspace_info().tools`.
- JSON companion imports to `/intents/import` are rejected.
- `bash scripts/check_all.sh` exits `0` when local checks pass and `npx` is missing.
