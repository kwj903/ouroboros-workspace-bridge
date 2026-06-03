# Use the pending review UI

This guide explains the local review screen opened after `uv run woojae start`.

```text
http://127.0.0.1:8790/pending
```

![pending review UI screen](../project/pending-review-ui.png)

## Purpose

The pending review UI is where you review local work proposed by ChatGPT before it is applied.

```text
ChatGPT request
  -> Local MCP bridge
  -> Pending bundle
  -> User review
  -> Apply or skip
```

## Left navigation

| Menu | Purpose |
| --- | --- |
| Approval | Review current pending bundles. |
| History / Results | See past bundle results. |
| Manage | Check local server and session state. |

Most first-time users only need the **Approval** page.

## Storage cleanup

Use **Manage > Storage Cleanup** to inspect and prune runtime data that accumulates during long-running local use.

- Review runtime storage size and history counts.
- Tune retention counts and age thresholds.
- Preview cleanup candidates before applying cleanup.
- Run default cleanup or backup-inclusive cleanup.
- Clear eligible history through a guarded confirmation flow.

Pending bundles, session settings, secrets, and active pid files are preserved by cleanup actions.

## Worktree Task management

Use **Manage > Worktree Task management** to separate actual Git state from Workspace Bridge task records.

- The actual Git state card reads the current branch, `task/*` branches, and task worktrees directly from the repository.
- Remaining task branches and task worktrees can be deleted from the management UI after explicit checkbox confirmation.
- Archived Worktree Task history is audit metadata; it does not necessarily mean a branch or worktree still exists.

## Approval mode

Start with **Normal** mode.

| Mode | Meaning |
| --- | --- |
| Normal | Manual review for every pending bundle. |
| Safe Auto | Conservative handling for simple low-risk command checks. |
| YOLO | Auto-approves pending bundles unless they are hard-blocked. Use it only for trusted development sessions. |

YOLO is intentionally more flexible for local development. The hard-blocked set is narrow:

- Still hard-blocked: paths outside `WORKSPACE_ROOT`, exact `.env`, `.git`, `.aws`, `.gnupg`, `sudo`, `su`, `dd`, `mkfs`, `diskutil`.
- Not hard-blocked for development flow: `.env.example`, `.env.local`, `.ssh`, `.venv`, `node_modules`, `ssh`, `scp`, `sftp`, `rsync`, shell `-c/-lc`, package install/sync commands, and ordinary git operations.
- Non-blocked work may still be labeled `medium` or `high` risk. YOLO may auto-approve those bundles, while Safe Auto remains conservative.

If a red warning is shown, it usually means the current approval mode is less conservative. Switch back to **Normal** unless you intentionally changed it.

## Empty pending list

If the page says there are no pending bundles, that is usually normal. It means no new local work is waiting for review.

If you expected a bundle, check the session:

```bash
uv run woojae status
```

Also confirm that the ChatGPT app is using the current MCP server URL.

## Before approving

Approve only work that matches your request. Check the files, commands, and scope. Reject anything unexpected or too large to review comfortably.

## First test

After connecting the app, try a harmless request first.

```text
Use this workspace directory: /path/to/your/project
Show me a brief overview of this directory's structure and tell me what kind of project it looks like.
```

When the expected bundle appears, inspect it in the review UI and approve it.

## Latest handoff / Copy for ChatGPT

This area shows the latest local result or text that can be copied back into ChatGPT. It is useful when continuing a longer workflow.

## Related docs

- [Quickstart](quickstart.md)
- [Connect as a ChatGPT custom app](chatgpt-app-setup.md)
- [Recommended local workflow](workflow.md)
- [Troubleshooting](troubleshooting.md)
