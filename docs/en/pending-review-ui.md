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

## Approval mode

Start with **Normal** mode.

| Mode | Meaning |
| --- | --- |
| Normal | Manual review for every pending bundle. |
| Safe Auto | Conservative handling for simple low-risk checks. |
| YOLO | Faster mode for short trusted sessions only. |

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
Check only the current project's git status.
```

When the expected bundle appears, inspect it in the review UI and approve it.

## Latest handoff / Copy for ChatGPT

This area shows the latest local result or text that can be copied back into ChatGPT. It is useful when continuing a longer workflow.

## Related docs

- [Quickstart](quickstart.md)
- [Connect as a ChatGPT custom app](chatgpt-app-setup.md)
- [Recommended local workflow](workflow.md)
- [Troubleshooting](troubleshooting.md)
