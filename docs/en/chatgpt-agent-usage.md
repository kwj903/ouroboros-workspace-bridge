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
- Do not create a new mutation bundle while another related bundle is pending.

## Bundle Rules

- `workspace_stage_action_bundle_and_wait.actions.length` must be 1.
- `workspace_stage_command_bundle_and_wait.steps.length` must be 1.
- Do not mix file edits, tests, git add, or git commit in one bundle.
- Do not mix tests or precheck commands into a commit proposal.
- After staging a bundle, report the bundle ID and wait for user approval.
- After approval, check bundle status before continuing.

## Payload Refs

Use `workspace_stage_text_payload` only for large content:

- long new files
- long documentation replacements
- long unified diff patches
- long old_text/new_text replacements

Do not use payload refs for short edits such as README links, import lines, small paragraphs, or config tweaks.

Suggested threshold:

- 2KB or less: direct action bundle
- 2KB to 8KB: direct action bundle when practical
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
3. Stage exactly one action bundle.
4. Tell the user the bundle ID and review UI location.
5. Wait for approval.
6. Check bundle status.
7. Check git status.

Verification workflow:

1. Stage exactly one command bundle.
2. Wait for approval.
3. Check bundle status.
4. Continue with the next verification only after the prior result is clear.

Commit workflow:

1. Confirm expected changes with git status.
2. Confirm verification is complete.
3. Stage a commit-only bundle.
4. Wait for approval.
5. Check bundle status.
6. Confirm final git status.

## Response Rules

After creating a bundle, always report:

- bundle ID
- review location
- what to check after approval
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
