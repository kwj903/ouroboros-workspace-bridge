# Local Session Guide

This guide is for users who want to run Workspace Terminal Bridge locally and connect it to ChatGPT.

For project maintenance notes, release checklists, and development plans, see `docs/project/`.

## Start from the repository root

```bash
cd ~/workspace/Custom-Tools/GPT-Tools/my-terminal-tool
```

## Recommended session flow

Check the local environment first:

```bash
scripts/dev_session.sh doctor
```

Start the full local session:

```bash
scripts/dev_session.sh start
```

This starts the review server, MCP server, and ngrok in the background. Process metadata is stored outside the repository under:

```text
~/.mcp_terminal_bridge/my-terminal-tool/processes
```

Check service status:

```bash
scripts/dev_session.sh status
```

Stop the full session when finished:

```bash
scripts/dev_session.sh stop
```

## Runtime environment

If `MCP_ACCESS_TOKEN` or `NGROK_HOST` is missing, create a private runtime env file:

```bash
scripts/dev_session.sh configure
```

The generated file is stored outside the repository:

```text
~/.mcp_terminal_bridge/my-terminal-tool/session.env
```

Expected permission:

```text
600
```

Token values must not be committed, printed in docs, or pasted into logs.

## Review UI

Open the pending bundle dashboard:

```text
http://127.0.0.1:8790/pending
```

Useful pages:

```text
http://127.0.0.1:8790/history
http://127.0.0.1:8790/servers
http://127.0.0.1:8790/servers?tab=processes
```

The review UI is used to approve staged action and command bundles. It is intentionally separate from ChatGPT so local file changes and commands remain user-approved.

## Process controls

Use the helper script for local process control.

```bash
scripts/dev_session.sh status
scripts/dev_session.sh start-service mcp
scripts/dev_session.sh stop-service mcp
scripts/dev_session.sh restart mcp
scripts/dev_session.sh start-service ngrok
scripts/dev_session.sh stop-service ngrok
scripts/dev_session.sh restart ngrok
scripts/dev_session.sh restart-session
scripts/dev_session.sh logs review
scripts/dev_session.sh logs mcp
scripts/dev_session.sh logs ngrok
```

The review process is not individually controlled from the UI because it is the UI process itself. For review-related recovery, use full session restart or stop/start.

## ChatGPT MCP connection

The ChatGPT app MCP URL format is:

```text
https://<NGROK_HOST>/mcp?access_token=<TOKEN>
```

Do not write the real token value in README, docs, logs, fixtures, or screenshots.

Refresh the ChatGPT app MCP connection when:

- `server.py` changed.
- MCP tool schemas changed.
- `MCP_ACCESS_TOKEN` changed.
- `NGROK_HOST` changed.
- the MCP server was restarted after a schema change.

Recommended refresh flow:

```bash
scripts/dev_session.sh restart mcp
scripts/dev_session.sh status
```

Then refresh the MCP connection in the ChatGPT app.

## Manual fallback commands

Use these only for fallback or debugging.

Run review server in foreground:

```bash
scripts/dev_session.sh review
```

Run MCP server only:

```bash
scripts/run_server.sh
```

Run ngrok only:

```bash
scripts/run_ngrok.sh
```

## Notifications and watcher behavior

The review server includes an embedded watcher for pending bundles. By default it opens the pending dashboard once and sends macOS notifications when available.

Install clickable macOS notifications:

```bash
brew install terminal-notifier
```

Useful watcher options:

```bash
BUNDLE_REVIEW_EMBEDDED_WATCHER=0 scripts/dev_session.sh review
BUNDLE_WATCH_NOTIFICATION_CLICK_ACTION=open scripts/dev_session.sh review
BUNDLE_WATCH_OPEN_MODE=none scripts/dev_session.sh review
```

Default notification target is `/pending`. Use bundle-specific notification targets only when debugging review flow behavior.

## Safe bundle workflow

ChatGPT should stage local changes as small bundles. The usual user flow is:

1. Inspect the pending bundle in the review UI.
2. Approve only if the bundle is small, expected, and safe.
3. Wait for the bundle to apply.
4. Ask ChatGPT to check `workspace_command_bundle_status`.
5. Continue to the next small step.

Avoid approving bundles that mix unrelated work such as file edits, tests, and commits in one request.

## Troubleshooting

For common recovery steps, see:

```text
docs/user/troubleshooting.md
```
