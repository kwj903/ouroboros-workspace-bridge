# Development Workflow

This guide is for maintaining and extending Workspace Terminal Bridge itself.

For end-user local session operation, see `docs/en/local-session.md` or `docs/ko/local-session.md`.

## Working principles

Workspace Terminal Bridge can modify local files and run local commands. Keep every change small and reviewable.

Preferred flow:

1. Inspect current state.
2. Read the relevant files.
3. Stage one small proposal bundle.
4. Approve locally in the review UI.
5. Check bundle status.
6. Verify with one command at a time.
7. Commit only after verification.

Do not mix file edits, tests, and commits in the same bundle.

The default public mutation path is the stage-and-wait proposal flow:

```text
workspace_stage_action_bundle_and_wait
workspace_stage_command_bundle_and_wait
workspace_stage_patch_bundle_and_wait
workspace_stage_commit_bundle_and_wait
```

Submit-first tools, signed-intent preparation tools, and direct operation/trash tools may remain in the implementation for internal or advanced workflows, but they are hidden from the default public MCP schema.

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

## Action bundles

Use `workspace_stage_action_bundle_and_wait` for small file edits.

Typical use cases:

- write one new file
- replace one small text block
- append one small section

Rules:

- One action per proposal bundle.
- Do not include tests in the same bundle.
- Do not include git add or commit in the same bundle.
- The proposal does not directly edit project files; files change only after local approval.
- File action apply captures target file snapshots before execution and rolls back action changes on failure.
- Check bundle status after approval.

Large content should be stored first with `workspace_stage_text_payload`, then referenced by `content_ref`, `old_text_ref`, or `new_text_ref`.

## Command bundles

Use `workspace_stage_command_bundle_and_wait` for one local command at a time.

Examples:

```bash
uv run python -m unittest discover -s tests
uv run python scripts/smoke_check.py
git diff --check
```

Rules:

- One command step per proposal bundle.
- Do not use long `bash -lc` chains.
- Do not combine unit tests, smoke checks, and commits.
- The proposal does not directly execute commands; commands run only after local approval.
- Check command bundle status after approval.

If a verification sequence becomes long, create a small `scripts/check_*.sh` or `scripts/check_*.py` file first, then run that script as a single command bundle.

## Patch bundles

Patch bundles are useful for code changes that are easier to review as a unified diff.

Recommended flow:

1. Generate a unified diff.
2. Store large patch text with `workspace_stage_text_payload`.
3. Stage the patch with `workspace_stage_patch_bundle_and_wait`.
4. Review and approve in the local review UI.
5. Check bundle status.
6. Inspect the resulting diff.
7. Run verification commands.

The runner performs path safety checks, `git apply --check`, backup, and `git apply` during approval.

## Commit flow

Commit only after the change is applied and verified.

Recommended flow:

1. Check `workspace_git_status`.
2. Confirm only expected files changed.
3. Run the needed verification commands.
4. Stage a commit-only bundle with `workspace_stage_commit_bundle_and_wait`.
5. Approve locally.
6. Check bundle status.
7. Confirm final `workspace_git_status` is clean.

Do not use `precheck_commands` in commit proposals. Verification should happen before the commit proposal as separate command bundles.

## Text payload refs

`workspace_stage_text_payload` is an advanced fallback for long content, not the default editing path.

## Internal module map

The large entrypoint files should stay thin enough to review:

- `server.py` owns MCP tool registration and high-level orchestration.
- `terminal_bridge/mcp_runtime.py` owns runtime directory setup, audit logging, tool-call journal wrapping, and command-bundle stage result conversion.
- `scripts/command_bundle_review_server.py` owns local review HTTP routes.
- `terminal_bridge/review_layout.py` owns the shared review UI shell, navigation, and CSS.
- `terminal_bridge/review_intents.py` owns signed intent token import parsing for the local review UI.

When adding new behavior, prefer placing pure helpers in `terminal_bridge/` and keeping entrypoint files focused on wiring.

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

## Task/session records

Long maintenance work can be tracked through task tools.

Useful tools:

```text
workspace_task_start
workspace_task_status
workspace_task_log_step
workspace_task_update_plan
workspace_task_finish
workspace_list_tasks
```

Use task records for multi-step efforts such as major refactors, new MCP tools, or UI workflow changes.

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
scripts/dev_session.sh restart mcp
```

After MCP schema changes, refresh the MCP connection in the ChatGPT app.

## Restart requirements

Restart only what is needed.

- README/docs only: no MCP restart needed.
- Review UI or watcher only: restart review session if manually testing UI behavior.
- `server.py` or MCP tool schema: restart MCP and refresh the ChatGPT app.
- ngrok configuration: restart ngrok.
- confusing local process state: use `scripts/dev_session.sh restart-session`.

## Safety model summary

Workspace Terminal Bridge uses several guardrails:

- workspace root is constrained under the configured `WORKSPACE_ROOT`
- path traversal is blocked
- sensitive directories and secret-like files are blocked
- direct mutation, submit-first, signed-intent, and direct operation/trash tools are hidden by default
- file changes are staged through local approval bundles
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
