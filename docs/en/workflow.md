# Recommended Local Workflow

This workflow is the default path for using Ouroboros Workspace Bridge from ChatGPT.

The default goal is to avoid ChatGPT MCP tool calls for routine local work. ChatGPT should write an ordinary assistant message containing an `ouroboros-intent` fenced block, and the browser companion should import that intent through local HTTP.

## Normal Local Work

1. ChatGPT does not call an MCP tool.

2. ChatGPT prints an ordinary assistant message with an execution intent block.

   The preferred prototype UX uses the local browser companion at:

   ```text
   browser/ouroboros-companion.user.js
   ```

   The companion watches the ChatGPT page for `ouroboros-intent` fenced blocks that include `intent_kind: "run"`.

3. The companion POSTs the JSON intent to local HTTP:

   ```text
   http://127.0.0.1:8790/intents/import
   ```

4. The local review server validates the intent and imports it as a pending command bundle.

5. The companion opens or focuses the existing pending review UI.

   Useful routes:

   ```text
   /pending
   /pending?bundle_id=<bundle_id>
   /review-intent?token=...
   /review-intent/preview?token=...
   /intents/import
   ```

6. Approve the bundle in the local UI, or let the configured approval mode handle it.

   YOLO and Safe Auto modes do not change the recommended ChatGPT path. They only affect local approval behavior.

7. Use the bundle-focused page to review the final status.

   `/pending?bundle_id=<bundle_id>` shows `pending`, `applied`, `failed`, and `rejected` records. It includes a compact `Copy for ChatGPT` JSON block.

8. After execution, `/handoffs/latest` or the handoff queue returns the result to the companion.

9. The companion prepares a ChatGPT composer message with the handoff. It does not auto-submit by default.

10. The user sends the prepared message, and ChatGPT continues from the result.

## Continuation Priority

Use this order after local approval or execution:

1. Companion handoff from `/handoffs/latest`
2. `workspace_next_handoff`
3. Copied `Copy for ChatGPT` JSON from the bundle page
4. `workspace_list_handoffs`
5. `workspace_recover_last_activity` only for debugging or interrupted calls

`workspace_recover_last_activity` is still useful when a tool call may not have reached the MCP server, but it is no longer the normal continuation path.

## Tool Priority

Preferred tool order:

1. Normal assistant-message `ouroboros-intent` block plus local companion
2. Local pending UI approval
3. Handoff queue
4. Read-only signed intent tools as fallback or convenience
5. Submit-first tools only when a durable MCP ack is explicitly needed
6. `workspace_stage_*_and_wait` tools only as legacy or convenience fallback
7. Primitive stage tools must remain hidden from the public MCP schema

Fallback tool order:

1. Read-only signed intent flow plus local pending UI
2. Handoff queue
3. Submit-first tools
4. `workspace_stage_*_and_wait` tools only as legacy or convenience fallback
5. Primitive stage tools must remain hidden from the public MCP schema

Public submit-first tools are not the default path because ChatGPT web may show an MCP approval modal for the tool call itself. They are still useful when you explicitly need a direct durable bundle ack:

```text
workspace_submit_command_bundle
workspace_submit_action_bundle
workspace_submit_patch_bundle
workspace_submit_commit_bundle
```

Avoid using long-running wait wrappers as the primary path. They keep one ChatGPT tool call open longer than needed.

## Local Companion Prototype

The first companion prototype is a userscript:

```text
browser/ouroboros-companion.user.js
```

Install it with a userscript manager such as Tampermonkey.

What it does:

- watches ChatGPT pages for fenced code blocks using the language name `ouroboros-intent`
- POSTs valid intent JSON to `http://127.0.0.1:8790/intents/import`
- opens or focuses `http://127.0.0.1:8790/pending?bundle_id=<bundle_id>`
- polls `http://127.0.0.1:8790/handoffs/latest`
- prepares a ChatGPT composer message with `bundle_id`, `status`, `ok`, `next`, `stdout_tail`, and `stderr_tail`
- copies the handoff message to the clipboard if composer filling is not available

Execution intent block:

````md
```ouroboros-intent
{
  "version": 1,
  "intent_kind": "run",
  "intent_type": "check",
  "cwd": "Custom-Tools/GPT-Tools/my-terminal-tool",
  "params": {
    "check": "git_status"
  }
}
```
````

For documentation or explanation examples, prefer a plain `json` fence instead of `ouroboros-intent`. The companion imports only blocks with `intent_kind: "run"`, so explanatory JSON without that field is ignored.

What it does not do:

- it does not bypass local pending approval
- it does not auto-submit ChatGPT messages by default
- it does not import arbitrary code blocks
- it does not import explanatory JSON that lacks `intent_kind: "run"`
- it does not require the manual Intent Inbox in normal use

Security notes:

- it talks only to `http://127.0.0.1:8790`
- keep `autoSubmit` disabled unless you deliberately change the script for local testing
- approve or reject the imported bundle in the local review UI as usual

## Intent Inbox

The Intent Inbox on `/pending` is an advanced fallback.

Use it when the companion is unavailable, or when you are using the fallback read-only signed intent tools and ChatGPT returned a `local_review_url`. Paste either:

- the full local URL, or
- the raw intent token

The import remains idempotent. Re-importing the same intent redirects to the same bundle.

Read-only signed intent tools remain available as fallback or convenience tools:

```text
workspace_prepare_check_intent
workspace_prepare_commit_current_changes_intent
workspace_prepare_dev_session_intent
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
- The local companion imports an `ouroboros-intent` block with `intent_kind: "run"` without manual copy/paste.
- An explanatory `json` block or `ouroboros-intent` block without `intent_kind: "run"` is not imported.
- A read-only check intent imports into the pending UI.
- A YOLO-applied bundle is still visible at `/pending?bundle_id=<bundle_id>`.
- The bundle-focused page shows `Copy for ChatGPT` JSON.
- `workspace_next_handoff` returns the latest handoff after local execution.
- `bash scripts/check_all.sh` exits `0` when local checks pass and `npx` is missing.

### Supported companion run intents

The companion JSON import path currently accepts these executable `intent_type` values:

- `check`
- `commit_current_changes`
- `dev_session`

Use `json` fences for explanatory examples. Use an `ouroboros-intent` fence only for a real execution request, and include `intent_kind: "run"` so the companion can distinguish it from documentation text.
