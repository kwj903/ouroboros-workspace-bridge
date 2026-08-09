# Development Workflow

This guide is for maintaining and extending Workspace Terminal Bridge itself.

For end-user local session operation, see `docs/en/local-session.md` or `docs/ko/local-session.md`.

## Working principles

Workspace Terminal Bridge can modify local files and run local commands. Keep every change small and reviewable.

Preferred flow:

1. Inspect current state.
2. Read the relevant files.
3. Stage one small proposal bundle.
4. Inspect the returned bundle status.
5. In Normal mode, approve locally if it is `pending`; in Safe Auto/YOLO, it may already be `running` or terminal.
6. Wait/poll until the prior bundle reaches a clear terminal result.
7. Verify with one command at a time.
8. Commit only after verification.

Do not mix file edits, tests, and commits in the same bundle.

The default public mutation path uses purpose-specific proposal wrapper tools:

```text
workspace_propose_file_replace_and_wait
workspace_propose_file_write_and_wait
workspace_propose_command_and_wait
workspace_propose_patch_and_wait
workspace_propose_git_commit_and_wait
workspace_propose_git_push_and_wait
```

The canonical default public MCP surface contains 31 tools and is defined in `terminal_bridge/public_tools.py`; `workspace_info`, smoke checks, and schema tests share that manifest. Generic stage/submit tools, signed-intent preparation helpers, and direct operation/trash functions may remain in the implementation for internal or advanced compatibility, but they are hidden from the default public MCP schema.

## Read-only inspection

Use read-only tools freely before changing files.

Common checks:

```text
workspace_git_status
workspace_search_text
workspace_read_file
workspace_read_many_files
workspace_command_bundle_status
workspace_list_command_bundles
```

Start most maintenance tasks with:

```text
workspace_git_status
```

Then inspect files before staging any mutation bundle.

## File edit proposals

Use `workspace_propose_file_replace_and_wait` or `workspace_propose_file_write_and_wait` for small file edits.

Typical use cases:

- write one new file
- replace one small text block
- append one small section through a targeted replacement

Rules:

- One file edit purpose per proposal.
- Do not include tests in the same proposal.
- Do not include git add or commit in the same proposal.
- The proposal does not directly edit project files. Normal requires manual review; Safe Auto/YOLO may authorize execution automatically.
- File action apply captures target file snapshots before execution and rolls back action changes on failure.
- Treat `pending` and `running` as active states and continue only after the terminal result is clear.

Large content can be stored first with `workspace_stage_text_payload`, then referenced by `content_ref`, `old_text_ref`, or `new_text_ref` through the internal bundle path when needed.

## Command proposals

Use `workspace_propose_command_and_wait` for one local command at a time.

Examples:

```bash
uv run python -m unittest discover -s tests
uv run python scripts/smoke_check.py
git diff --check
```

Rules:

- One command per proposal.
- Do not use long `bash -lc` chains.
- Do not combine unit tests, smoke checks, and commits.
- The proposal does not directly execute commands. The local approval policy authorizes the bundle: Normal is manual, Safe Auto/YOLO may auto-authorize.
- Treat `pending` and `running` as active states and check/wait for a terminal bundle result.

If a verification sequence becomes long, create a small `scripts/check_*.sh` or `scripts/check_*.py` file first, then run that script as a single command proposal.

## Patch proposals

Patch proposals are useful for code changes that are easier to review as a unified diff.

Recommended flow:

1. Generate a unified diff.
2. Prefer small patches when possible.
3. Create the patch proposal with `workspace_propose_patch_and_wait`.
4. Inspect the returned status; review/approve manually only when Normal leaves it `pending`.
5. Wait/poll while it is `pending` or `running`.
6. Inspect the terminal result and resulting diff.
7. Run verification commands.

The runner performs path safety checks, `git apply --check`, backup, and `git apply` during approval.

## Commit flow

Commit only after the change is applied and verified.

Recommended flow:

1. Check `workspace_git_status`.
2. Confirm only expected files changed.
3. Run the needed verification commands.
4. Create a commit-only proposal with `workspace_propose_git_commit_and_wait`.
5. Inspect the returned status and review manually only if Normal leaves it `pending`.
6. Wait/poll until the commit bundle reaches a terminal state.
7. Confirm final `workspace_git_status` is clean.

Do not use `precheck_commands` in commit proposals. Verification should happen before the commit proposal as separate command bundles.

## Text payload refs

`workspace_stage_text_payload` is an advanced fallback for long content, not the default editing path.

## Internal module map

The large entrypoint files should stay thin enough to review:

- `server.py` owns FastMCP registration, public wrapper signatures/annotations, validation, and thin adapters.
- `terminal_bridge/public_tools.py` owns the canonical 31-tool default public manifest and annotation policy helpers.
- `terminal_bridge/bundles.py` is the canonical filesystem store for atomic JSON persistence, generation signaling, request-key indexing, claim, transition, reject, and finalization.
- `terminal_bridge/bundle_service.py` owns cohesive stage/find/status/list/cancel orchestration over the canonical store.
- `terminal_bridge/mcp_tools/readonly.py` owns read-only inspection helper implementations used by public MCP wrappers.
- `terminal_bridge/mcp_tools/proposals.py` owns proposal step/action construction and async proposal delegation helpers.
- `terminal_bridge/mcp_tools/bundles.py` owns async wait/stage-and-wait helpers and delegates store-facing status/list work through `BundleService` where appropriate.
- `terminal_bridge/mcp_tools/status.py` owns runtime status, audit, handoff, operation, backup/trash list, and git status/diff helper implementations.
- `terminal_bridge/mcp_runtime.py` owns runtime directory setup plus sync/async-aware audit and tool-call journal wrapping.
- `scripts/command_bundle_review_server.py` owns local review HTTP routes, generation-based long polling, and approval-mode UI behavior.
- `scripts/command_bundle_runner.py` owns validated execution in one resolved workspace cwd plus snapshot/backup/rollback and terminal finalization.
- `terminal_bridge/review_layout.py` owns the shared review UI shell, navigation, and CSS.
- `terminal_bridge/review_intents.py` owns signed intent token import parsing for the local review UI.

When adding new behavior, prefer placing pure helpers in `terminal_bridge/` or `terminal_bridge/mcp_tools/` and keeping entrypoint files focused on wiring. Public MCP tool names, decorators, signatures, and schemas should remain stable unless the change is explicitly a schema change.

## Graphify workflow

This repository may be treated as graphify-enabled when local `graphify-out/graph.json` or `graphify-out/GRAPH_REPORT.md` exists.

Recommended internal workflow for structural refactors:

```bash
graphify update .
```

Use Graphify output to narrow impact analysis, then confirm changes against source files and tests. `graphify-out/` is a local analysis artifact by default. If it is temporarily tracked to carry analysis across local branches, remove it from the Git index again before public push:

```bash
git rm -r --cached graphify-out
```

Keep these ignore rules active before publishing:

```gitignore
graphify-out/
.graphify_*
```

Do not use payload refs for short edits such as README link updates, small paragraph replacements, import lines, config tweaks, or test snippets. For short edits, put `content`, `old_text`, or `new_text` directly in a single action bundle.

Use payload refs when content is long enough to make the tool call JSON heavy or fragile.

Recommended thresholds:

- 2KB or less: do not use payload refs
- 2KB to 8KB: prefer a direct single action bundle when practical
- 8KB or more: consider payload refs
- 20KB or more, or large patches: prefer payload refs

Supported fields:

```text
content_ref
old_text_ref
new_text_ref
patch_ref
```

Runtime location:

```text
~/.mcp_terminal_bridge/my-terminal-tool/text_payloads
```

Payload refs reduce large JSON tool calls and make review UI behavior more stable for large edits. They also add an extra tool call, so using them for short edits can increase the chance of interrupted responses.

If a response stops after creating a payload ref, do not retry the same request immediately. First check:

```text
workspace_list_command_bundles
workspace_git_status
```

A payload ref by itself does not modify project files.

## Task tracking and session identity

The removed public task/worktree tool family is no longer part of the current MCP contract. Development work on this repository is tracked in the repository-local `agent-work/` documents instead:

```text
agent-work/CURRENT.md
agent-work/tasks/
agent-work/decisions/
agent-work/handoffs/
```

For runtime proposal identity across concurrent ChatGPT sessions, use logical metadata on the public proposal wrappers:

```text
client_id
session_id
task_id
project_id
retry_id
```

`session_id` is the primary concurrent-chat separation key. These values affect request/history identity and filtering; they do not create task worktrees, merge queues, or alternate execution roots.

## Verification levels

Choose the smallest useful verification for the change.

Docs-only change:

```bash
git diff --check
```

Script or shell helper change:

```bash
bash -n scripts/dev_session.sh
git diff --check
```

Python helper or review UI change:

```bash
uv run python -m unittest discover -s tests
uv run python scripts/smoke_check.py
git diff --check
```

MCP tool or server schema change:

```bash
uv run python -m unittest discover -s tests
uv run python scripts/smoke_check.py
git diff --check
uv run terminalbridge restart
```

For a schema/annotation change, also run remote smoke when configured and verify that the live connector exposes the canonical tool set.

After MCP schema changes, refresh the MCP connection in the ChatGPT app.

## Restart requirements

Restart only what is needed.

- README/docs only: no MCP restart needed.
- Review UI or watcher only: restart the managed stack when manually validating live behavior, or use the low-level `woojae` service controls only for focused diagnosis.
- `server.py` or MCP tool schema/annotations: use `uv run terminalbridge restart`, then refresh/reconnect the ChatGPT app if the client caches schema.
- Public connector configuration: use `uv run terminalbridge restart` so the selected ngrok/Cloudflare/external mode stays coherent.
- Confusing local process state: use `uv run terminalbridge status`, `uv run terminalbridge doctor`, then `uv run terminalbridge restart` if needed.

## Safety model summary

Workspace Terminal Bridge uses several guardrails:

- workspace root is constrained under the configured `WORKSPACE_ROOT`
- path traversal is blocked
- sensitive directories and secret-like files are blocked
- direct mutation, submit-first, signed-intent, and direct operation/trash tools are hidden by default
- file changes are staged through local approval bundles; Normal is manual while Safe Auto/YOLO can authorize eligible bundles automatically
- public action proposals enforce one action per call
- public command proposals enforce one command step per call
- file action bundles snapshot target files before apply and roll back action changes on failure
- patch bundles validate paths, run `git apply --check`, and back up touched files before apply
- backups are created for file-changing operations
- audit, tool-call, bundle, and handoff records are stored under runtime data

Direct mutation tools should only be exposed for local debugging with explicit environment configuration.

## Secret handling

Never print or commit these values:

- API keys
- access tokens
- Bearer tokens
- `MCP_ACCESS_TOKEN`
- `NGROK_AUTHTOKEN`
- `.env` values

Failure views, logs, docs, tests, and screenshots should not contain real secret values.

## Recovery after a failed or interrupted tool call

If a tool call appears to fail or the ChatGPT response stops:

1. Do not repeat the same large request.
2. Check recent bundles.
3. Check the specific bundle status if an ID is known.
4. Check git status.
5. If a pending bundle exists, inspect and approve only if it is expected and safe.
6. Otherwise reject/cancel and retry with a smaller bundle.

Useful checks:

```text
workspace_list_command_bundles
workspace_command_bundle_status <bundle_id>
workspace_git_status
```

## Related docs

```text
docs/en/local-session.md
docs/en/troubleshooting.md
docs/ko/local-session.md
docs/ko/troubleshooting.md
docs/project/phase-6-release-checklist.md
docs/project/phase-7-plan.md
```
