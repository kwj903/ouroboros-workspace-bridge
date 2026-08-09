# Troubleshooting

This guide covers common local operation failures for Ouroboros Workspace Bridge.

Use these checks from the repository root:

```bash
cd ouroboros-workspace-bridge
```

## First checks

Start with the current supervisor state.

```bash
uv run terminalbridge status
uv run terminalbridge doctor
```

Expected high-level result:

- `review` has an alive managed process and is reachable.
- `mcp` has an alive managed process and is reachable.
- In ngrok mode, `ngrok` is managed. In Cloudflare mode, `cloudflared` is managed. In generic external mode, the connector is reported as manually managed.
- `uv` is installed.
- Token values are not printed.

## First-run success checklist

Use this checklist after the first setup:

1. `uv run terminalbridge status` shows review and mcp reachable.
2. `http://127.0.0.1:8790/pending` opens locally.
3. `uv run terminalbridge copy-url` or `uv run terminalbridge mcp-url` returns the expected MCP URL information.
4. The ChatGPT custom app uses the current MCP server URL.
5. Asking ChatGPT for a brief overview of the target workspace directory creates a bundle. In Normal it should usually remain `pending`; Safe Auto/YOLO may move it to `running` or a terminal state immediately.
6. Resolve the bundle according to the active approval mode and confirm a terminal result in review/history.
7. After connector refresh/reconnect, confirm the default MCP surface is the canonical 31-tool set reported by `workspace_info`.

If one step fails, troubleshoot that step first instead of repeating the full setup.

## Review UI is unreachable

Symptoms:

- `http://127.0.0.1:8790/pending` does not load.
- `/servers` or `/history` does not respond.
- The review service is stale or missing in `status` output.

Check:

```bash
uv run terminalbridge status
uv run woojae logs review
```

Recover:

```bash
uv run terminalbridge restart
```

If that does not recover the UI:

```bash
uv run terminalbridge stop
uv run terminalbridge start
uv run terminalbridge status
```

## MCP server is unreachable

Symptoms:

- ChatGPT MCP calls fail.
- `/servers?tab=processes` shows MCP reachable as `no`.
- `uv run terminalbridge status` shows `mcp alive=no` or `reachable=no`.

Check:

```bash
uv run terminalbridge status
uv run woojae logs mcp
```

Recover:

```bash
uv run woojae restart mcp
uv run terminalbridge status
```

If `server.py` or MCP tool schemas changed, refresh the MCP connection in the ChatGPT app after restart.

## Connection drops after restarting the session from ChatGPT

Symptoms:

- ChatGPT creates a session restart bundle such as `uv run terminalbridge restart`, then the MCP connection drops.
- The review UI may still show that restart bundle in pending, rejected, or failed history.

This is usually an expected side effect. When the MCP server restarts itself, the active ChatGPT tool connection can be interrupted.

Recommended recovery:

```bash
uv run terminalbridge status
uv run terminalbridge start
# or
uv run terminalbridge restart
```

Then refresh the MCP connection in the ChatGPT app and confirm the connection with a read-only tool such as `workspace_transport_probe` or `workspace_git_status`.

Recommended operating rule:

- Restart the full local session from a terminal when possible; the selected managed ngrok or Cloudflare connector is included automatically.
- Avoid restarting the server through a ChatGPT tool proposal unless you are intentionally debugging the restart flow.
- A rejected or failed restart bundle may be an already-processed history item. Check `/history` and the bundle status together.

## Cloudflare or external domain is not connected

Symptoms:

- `PUBLIC_ACCESS_MODE=external` is configured, but the public endpoint does not reach the local MCP server.
- `uv run terminalbridge status` shows review and MCP healthy while ChatGPT cannot connect.

Check:

```bash
uv run terminalbridge doctor
uv run terminalbridge status
uv run terminalbridge logs mcp
uv run terminalbridge logs cloudflared
uv run terminalbridge mcp-url
```

For managed Cloudflare mode, confirm that the user's config path and tunnel name are correct and that `cloudflared` is alive. For generic external mode, start the proxy or connector separately. In both cases, route the public hostname only to `http://127.0.0.1:8787`, keep the review UI private, and stop replica connectors on other computers. See [Public access modes](public-access.md).

## ngrok is not connected

Symptoms:

- Public MCP endpoint does not work.
- ChatGPT cannot reach the local MCP server through the ngrok URL.
- ngrok log shows tunnel or account errors.

Check:

```bash
uv run terminalbridge status
uv run woojae logs ngrok
```

Recover:

```bash
uv run woojae restart ngrok
uv run terminalbridge status
```

If ngrok still fails, check that the ngrok account/session is valid. `NGROK_HOST` is optional for temporary URL mode, but `uv run terminalbridge copy-url` requires a configured fixed host.

## Bundle is stuck in pending

Symptoms:

- A bundle remains visible in the review UI.
- ChatGPT says a bundle was created but the next step is unclear.

Check in the review UI:

```text
http://127.0.0.1:8790/pending
http://127.0.0.1:8790/history
```

From ChatGPT, inspect with:

```text
workspace_list_command_bundles
workspace_command_bundle_status <bundle_id>
```

Recover:

- Approve the bundle if it is expected and safe.
- Reject/cancel the bundle if it is too large, mixes unrelated actions, or was created by mistake.
- After approval or rejection, check bundle status again before creating another mutation bundle.

## Desktop notification does not appear

Notification helpers are optional. If desktop notifications are unavailable, the review UI and bundle approval flow still work.

```bash
uv run terminalbridge doctor
```

- macOS: `terminal-notifier` enables clickable notifications; `osascript` can be used as a fallback when configured.
- Linux: `notify-send` sends desktop notifications when available. URL opening uses `xdg-open` or Python browser fallback.
- Windows: PowerShell/BurntToast is attempted when available. Failure does not stop the watcher.

## Bundle failed

Symptoms:

- Review UI shows a failed bundle.
- `workspace_command_bundle_status` returns `failed`.

Check:

```text
workspace_command_bundle_status <bundle_id>
```

Then inspect:

- failed step name
- exit code
- stdout/stderr
- rollback or backup information if present

Recover:

1. Do not immediately create another large bundle.
2. Check `git status`.
3. Fix one cause at a time with a single-action bundle.
4. Re-run only the failed verification command first.

## Runtime data keeps growing

Symptoms:

- `~/.mcp_terminal_bridge/my-terminal-tool` keeps growing.
- Old bundle, tool call, backup, or trash records accumulate.
- It is unclear where runtime data is stored.

Check:

```bash
uv run woojae paths
uv run woojae storage
uv run woojae cleanup --dry-run
```

Recover:

- Inspect `cleanup --dry-run` output first.
- Run `uv run woojae cleanup --apply` only after confirming the candidates are safe.
- Add `--include-backups` only when you also want backups and trash considered as cleanup candidates.
- `session.json`, `session.env`, `intent_hmac_secret`, pending bundles, and pid files are protected.

## PID file is stale

Symptoms:

- `status` shows `alive=stale`.
- Process table shows stale state.
- The service is not actually running, but a pid file remains.

Check:

```bash
uv run terminalbridge status
```

Recover by restarting the service or full session:

```bash
uv run woojae restart mcp
uv run woojae restart ngrok
```

For review-related stale state, prefer full session recovery:

```bash
uv run terminalbridge restart
```

## Full session restart did not recover

Symptoms:

- The review page disconnects and does not return.
- review, MCP, or ngrok do not come back with new PIDs.

Check:

```bash
uv run terminalbridge status
uv run woojae logs review
uv run woojae logs mcp
uv run woojae logs ngrok
```

Recover:

```bash
uv run terminalbridge stop
uv run terminalbridge start
uv run terminalbridge status
```

The full session restart helper log is stored under the process directory shown by `uv run terminalbridge status`.

## ChatGPT app MCP connection needs refresh

Refresh the ChatGPT app MCP connection when:

- `server.py` changed.
- MCP tool schemas changed.
- `MCP_ACCESS_TOKEN` changed.
- the public ngrok host changed.

Recommended order:

```bash
uv run woojae restart mcp
uv run terminalbridge status
```

Then refresh the MCP connection in the ChatGPT app.

## Tool call appeared to fail but may have staged a bundle

Symptoms:

- ChatGPT response stopped or showed an error.
- The local review UI still shows a new pending bundle.
- A tool call looked interrupted.

Check before retrying:

```text
workspace_list_command_bundles
workspace_git_status
```

If a new bundle exists:

- inspect its status
- approve only if it is safe and expected
- reject/cancel if it is too large or mixed multiple concerns

Do not repeat the same large request. Split the next attempt into smaller bundles.

## Safe recovery checklist

When unsure, use this order:

```bash
uv run terminalbridge status
uv run terminalbridge doctor
uv run woojae logs review
uv run woojae logs mcp
uv run woojae logs ngrok
```

Then from ChatGPT, check:

```text
workspace_list_command_bundles
workspace_git_status
```

Only after the current state is clear should you create the next small bundle.
