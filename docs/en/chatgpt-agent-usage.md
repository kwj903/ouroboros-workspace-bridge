# ChatGPT Agent Instructions

This document is a practical project-instructions template for using Ouroboros Workspace Bridge safely from ChatGPT.

Copy the block below into your ChatGPT project instructions.

## Project Instructions

```md
# Project Instructions: Ouroboros Workspace Bridge

The main local development bridge is Ouroboros Workspace Bridge. It lets ChatGPT inspect projects under the configured WORKSPACE_ROOT and stage local changes through approval bundles.

## Safety Rules

- Never print, store, or summarize real tokens, API keys, bearer tokens, ngrok authtokens, or .env values.
- Treat WORKSPACE_ROOT as the only allowed local file boundary.
- Prefer read-only inspection before every mutation.
- Use approval bundles for file writes, command execution, patch apply, git add, and git commit.
- Do not use direct unsafe local file or shell operations.
- Do not create a new related mutation bundle while the prior one is still `pending` or `running`.

## Proposal Rules

- Prefer purpose-specific public proposal tools: `workspace_propose_file_replace_and_wait`, `workspace_propose_file_write_and_wait`, `workspace_propose_command_and_wait`, `workspace_propose_patch_and_wait`, `workspace_propose_git_commit_and_wait`, and `workspace_propose_git_push_and_wait`.
- Use one proposal per file edit, command, patch, commit, or push.
- Do not mix file edits, tests, git add, git commit, or push in one proposal.
- Do not mix tests or precheck commands into a commit proposal.
- After creating a proposal, report the bundle ID and current status.
- If it is `pending` in Normal mode, wait for user review in the local UI. If it is `running`, poll/wait for a terminal state. Safe Auto or YOLO may already return a terminal result without a manual approval click.
- Continue only after the prior bundle status is clear.

## Session Identity and Retry

For concurrent chats, provide stable logical metadata when the public wrapper exposes it:

- `client_id`: stable caller/platform name.
- `session_id`: distinct stable id for each concurrent chat; this is the primary separation key.
- `task_id`: optional logical work-unit id.
- `project_id`: stable logical project id.
- `retry_id`: reuse the same value for an idempotent retry, or provide a new value only when one deliberate new attempt is required after a final result.

These values separate request/history identity; they do not create a worktree or change the filesystem target.

## Payload Refs

Use `workspace_stage_text_payload` only for large content:

- long new files
- long documentation replacements
- long unified diff patches
- long old_text/new_text replacements

Do not use payload refs for short edits such as README links, import lines, small paragraphs, or config tweaks.

Suggested threshold:

- 2KB or less: direct purpose-specific proposal
- 2KB to 8KB: direct purpose-specific proposal when practical
- 8KB or more: consider payload refs
- 20KB or more, or large patches: prefer payload refs

## Standard Workflow

Read-only inspection:

- `workspace_git_status`
- `workspace_read_file`
- `workspace_read_many_files`
- `workspace_search_text`
- `workspace_command_bundle_status`
- `workspace_list_command_bundles`

File edit workflow:

1. Check git status.
2. Read the relevant files.
3. Create exactly one file proposal with `workspace_propose_file_replace_and_wait` or `workspace_propose_file_write_and_wait`.
4. Report the bundle ID, review UI location, and returned status.
5. If `pending`, wait for manual review when Normal is active; if `running`, wait/poll for a terminal state; if already final, inspect the result directly.
6. Check bundle status when needed.
7. Check git status.

Verification workflow:

1. Create exactly one command proposal with `workspace_propose_command_and_wait`.
2. Inspect the returned status: `pending` means review is still required, `running` means execution is active, and a terminal state can be handled immediately.
3. Check/wait for bundle status when needed.
4. Continue with the next verification only after the prior result is clear.

Commit workflow:

1. Confirm expected changes with git status.
2. Confirm verification is complete.
3. Create a commit-only proposal with `workspace_propose_git_commit_and_wait`.
4. Inspect the returned status and wait only while it is `pending`/`running`.
5. Check the terminal bundle result.
6. Confirm final git status.

## Response Rules

After creating a bundle, always report:

- bundle ID
- current status
- review location when relevant
- whether manual review is still required or the bundle is already running/final
- what to inspect if it fails

Keep every local mutation small, explicit, and reviewable.
```

## Approval Checklist

Before approving a bundle in the local review UI, check:

- Is there exactly one purpose?
- Is there exactly one action or command step?
- Are only expected files touched?
- Is there no real secret value?
- Are tests and commits separated from file edits?
