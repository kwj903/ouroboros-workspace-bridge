# Local Session Guide

This guide is for users who want to run Workspace Terminal Bridge locally and connect it to ChatGPT.

For project maintenance notes, release checklists, and development plans, see `docs/project/`.

## Start from the repository root

```bash
cd <repo>
```

## Recommended session flow

Run the initial setup when configuring a checkout for the first time:

```bash
uv run woojae setup
```

This writes private runtime settings outside the repository. During setup, choose the allowed `WORKSPACE_ROOT`. Existing shell environment values such as `WORKSPACE_ROOT`, `MCP_ACCESS_TOKEN`, and `NGROK_HOST` take precedence over values loaded from runtime `session.env`.

Check the local environment:

```bash
uv run woojae doctor
```

Start the full local session:

```bash
uv run woojae start
```

This starts the review server, MCP server, and ngrok in the background. Process metadata is stored outside the repository under:

```text
~/.mcp_terminal_bridge/my-terminal-tool/processes
```

Check service status:

```bash
uv run woojae status
```

Open the review UI:

```bash
uv run woojae open
```

Stop the full session when finished:

```bash
uv run woojae stop
```

## Runtime environment

If `MCP_ACCESS_TOKEN` is missing, create a private runtime env file:

```bash
uv run woojae setup
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

`NGROK_HOST` is optional. If it is not configured, `uv run woojae start` uses ngrok temporary URL mode. `uv run woojae copy-url` requires both `NGROK_HOST` and `MCP_ACCESS_TOKEN`.

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

Use `woojae` for normal local process control.

```bash
uv run woojae status
uv run woojae restart mcp
uv run woojae restart ngrok
uv run woojae logs review
uv run woojae logs mcp
uv run woojae logs ngrok
```

Script-level controls such as `scripts/dev_session.sh start-service mcp`, `stop-service`, and `restart-session` remain available for fallback/debug use. The review process is not individually controlled from the UI because it is the UI process itself. For review-related recovery, use full session restart or stop/start.

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
uv run woojae restart mcp
uv run woojae status
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
BUNDLE_REVIEW_EMBEDDED_WATCHER=0 uv run woojae start
BUNDLE_WATCH_NOTIFICATION_CLICK_ACTION=open uv run woojae start
BUNDLE_WATCH_OPEN_MODE=none uv run woojae start
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
