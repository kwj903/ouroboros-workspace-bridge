# Local Session Guide

This guide is for users who want to run Ouroboros Workspace Bridge locally and connect it to ChatGPT.

For project maintenance notes, release checklists, and development plans, see `docs/project/`.

## Start from the repository root

```bash
cd ouroboros-workspace-bridge
```

## Recommended session flow

Use `uv run terminalbridge ...` for normal setup and complete connection-stack operation. `uv run woojae ...` and `scripts/dev_session.*` remain low-level compatibility and debugging interfaces.

Run the initial setup when configuring a checkout for the first time:

```bash
uv run terminalbridge setup
```

This writes private runtime settings outside the repository. During setup, choose the public access mode, the allowed `WORKSPACE_ROOT`, and the default help language. Existing shell environment values such as `PUBLIC_ACCESS_MODE`, `PUBLIC_MCP_URL`, `WORKSPACE_ROOT`, `MCP_ACCESS_TOKEN`, `NGROK_HOST`, and `WOOJAE_HELP_LANG` take precedence over values loaded from runtime `session.env`. See [Public access modes](public-access.md).

Use `uv run woojae help` for project-specific command help. Use `uv run woojae help --lang ko` for Korean help, or save `Help language` as `ko` during setup.

Check the local environment:

```bash
uv run woojae doctor
```

Start the full local session:

```bash
uv run terminalbridge start
```

This starts review and MCP in the background. In `ngrok` mode it also starts the user's ngrok connector. In managed `cloudflare` mode it starts the user's configured `cloudflared` connector. In generic `external` mode the public connector remains manually managed. Process metadata is stored outside the repository under:

```text
~/.mcp_terminal_bridge/my-terminal-tool/processes
```

Check service status:

```bash
uv run terminalbridge status
```

Open the review UI:

```bash
uv run terminalbridge open
```

Stop the full session when finished:

```bash
uv run terminalbridge stop
```

## Runtime environment

If `MCP_ACCESS_TOKEN` is missing, create a private runtime env file:

```bash
uv run terminalbridge setup
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

In `ngrok` mode, `NGROK_HOST` is optional and an unset host uses temporary URL mode. Managed `cloudflare` and generic `external` modes require `PUBLIC_MCP_URL`. Cloudflare additionally requires the user's config path and tunnel name. `uv run terminalbridge copy-url` requires a fixed public endpoint and `MCP_ACCESS_TOKEN`.

## Runtime data management

Settings, logs, approval records, backups, and trash are stored outside the repository in the runtime directory.

```bash
uv run woojae paths
uv run woojae storage
uv run woojae cleanup --dry-run
```

- `paths` prints the project checkout, runtime data, session config, and workspace root paths.
- `storage` prints runtime data usage by category with file counts.
- `cleanup` defaults to dry-run behavior. It deletes files only when `uv run woojae cleanup --apply` is explicitly used.
- `session.json`, `session.env`, `intent_hmac_secret`, pending bundles, and pid files are protected.
- `backups`, `command_bundle_file_backups`, and `trash` are included only when `--include-backups` is passed.

Always inspect `--dry-run` output before applying cleanup.

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

## Update Existing Installation

```bash
cd ouroboros-workspace-bridge
uv run woojae update
```

- `uv run woojae update` stops if local uncommitted changes are present.
- It pulls the current branch with `--ff-only`.
- It runs `uv sync`.
- It restarts review and MCP with the new code, plus ngrok only when `PUBLIC_ACCESS_MODE=ngrok`.
- It prints the final local session status.
- After MCP tool changes, refresh or reconnect the ChatGPT app connector.

Preview the update steps without changing files:

```bash
uv run woojae update --dry-run
```

Skip automatic session restart when you only want to pull and sync:

```bash
uv run woojae update --skip-restart
```

## Process controls

Use `terminalbridge` for normal complete-stack process control and `woojae` for individual Bridge services.

```bash
uv run terminalbridge status
uv run woojae restart mcp
uv run woojae restart ngrok
uv run terminalbridge restart
uv run woojae logs review
uv run woojae logs mcp
uv run woojae logs ngrok
```

Low-level `restart ngrok` and `logs ngrok` apply only to ngrok mode. In Cloudflare and generic external modes, ngrok start/restart is disabled. Use `uv run terminalbridge restart` for the complete selected stack, `uv run terminalbridge logs cloudflared` for managed Cloudflare logs, and manage a generic external connector separately.

The wrapper scripts remain available for compatibility. Prefer `uv run terminalbridge ...` for complete-stack operation and `uv run woojae ...` only for individual-service diagnostics.

macOS/Linux:

```bash
scripts/dev_session.sh status
scripts/dev_session.sh restart-session
```

Windows PowerShell:

```powershell
.\scripts\dev_session.ps1 status
.\scripts\dev_session.ps1 restart-session
```

Low-level controls such as `uv run woojae start-service mcp`, `stop-service`, and `restart-session` remain available for fallback/debug use. The Review UI's full-session actions invoke the operator layer so a managed Cloudflare connector is included. The review process is not individually controlled from its own UI.

## ChatGPT MCP connection

1. Start the local session.

```bash
uv run terminalbridge start
```

2. Open the local review UI.

```bash
uv run terminalbridge open
```

3. Copy the MCP URL.

```bash
uv run terminalbridge copy-url
```

`copy-url` copies the real URL to the clipboard. It uses `pbcopy` on macOS, `xclip` on Linux, and `clip` on Windows when available. `uv run terminalbridge mcp-url` prints only a redacted URL preview. It does not print the token.

The ChatGPT app MCP URL format is:

ngrok mode:

```text
https://<NGROK_HOST>/mcp?access_token=<TOKEN>
```

Cloudflare or generic external mode example:

```text
https://terminalbridge.example.com/mcp?access_token=<TOKEN>
```

Do not write the real token value in README, docs, logs, fixtures, screenshots, chats, or GitHub issues.

4. In ChatGPT, open the app/connector creation UI.

The UI may change, so use the settings, connector, or apps area that allows creating a custom app or custom MCP connector.

5. Fill the app creation form.

- Icon: optional.
- Name: `Ouroboros Workspace Bridge` or `Woojae Workspace Bridge`
- Description: `Local MCP bridge for approved workspace file and command operations.`
- MCP server URL: paste the URL copied by `uv run terminalbridge copy-url`.
- Authentication: choose `No auth` or equivalent if the access token is already included in the MCP URL query string.
- Advanced OAuth settings: leave empty unless the product UI requires otherwise.
- Security warning checkbox: custom MCP servers can access data and tools. Enable it only for your own trusted local bridge after understanding the risk.

If the UI forces OAuth, this bridge may not use that mode. Choose the mode that allows a direct MCP URL without OAuth.

After creating the app, refresh or reconnect the connector. Confirm tools are visible and that the local review page is open:

```text
http://127.0.0.1:8790/pending
```

For a first test, ask ChatGPT to summarize the target workspace directory structure and what kind of project it appears to be. Approve only expected bundles in the local review UI.

To print only a redacted URL preview:

```bash
uv run terminalbridge mcp-url
```

## Temporary ngrok URL Caveat

If `NGROK_HOST` is not configured, `terminalbridge copy-url` may not produce a stable ngrok URL. A temporary ngrok URL can change after restart, so the ChatGPT app MCP URL may need to be updated.

For stable usage, create a reserved ngrok domain and set `NGROK_HOST` during `uv run terminalbridge setup`.

## Approval Mode

- Normal: default, manual approval.
- Safe Auto: low-risk command-only bundles may be auto-approved. Normal or Safe Auto is recommended for regular users.
- YOLO: for trusted short sessions only. Do not leave it on.

Refresh the ChatGPT app MCP connection when:

- `server.py` changed.
- MCP tool schemas changed.
- `MCP_ACCESS_TOKEN` changed.
- `NGROK_HOST` changed.
- the MCP server was restarted after a schema change.

Recommended refresh flow:

```bash
uv run woojae restart mcp
uv run terminalbridge status
```

Then refresh the MCP connection in the ChatGPT app.

## Manual fallback commands

Use these only for fallback or debugging.

Run review server in foreground:

```bash
uv run woojae review
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

The review server includes an embedded watcher for pending bundles. By default it opens the pending dashboard once and sends desktop notifications when platform helpers are available.

Install clickable macOS notifications:

```bash
brew install terminal-notifier
```

Useful watcher options:

```bash
BUNDLE_REVIEW_EMBEDDED_WATCHER=0 uv run terminalbridge start
BUNDLE_WATCH_NOTIFICATION_CLICK_ACTION=open uv run terminalbridge start
BUNDLE_WATCH_OPEN_MODE=none uv run terminalbridge start
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
docs/en/troubleshooting.md
```
