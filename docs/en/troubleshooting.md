# Troubleshooting

This guide covers common local operation failures for Ouroboros Workspace Bridge.

Use these checks from the repository root:

```bash
cd ouroboros-workspace-bridge
```

## First checks

Start with the current supervisor state.

```bash
uv run woojae status
uv run woojae doctor
```

Expected high-level result:

- `review` has an alive managed process and is reachable.
- `mcp` has an alive managed process and is reachable.
- `ngrok` has a managed process and a current log path.
- `uv` is installed.
- Token values are not printed.

## Review UI is unreachable

Symptoms:

- `http://127.0.0.1:8790/pending` does not load.
- `/servers` or `/history` does not respond.
- The review service is stale or missing in `status` output.

Check:

```bash
uv run woojae status
uv run woojae logs review
```

Recover:

```bash
uv run woojae restart-session
```

If that does not recover the UI:

```bash
uv run woojae stop
uv run woojae start
uv run woojae status
```

## MCP server is unreachable

Symptoms:

- ChatGPT MCP calls fail.
- `/servers?tab=processes` shows MCP reachable as `no`.
- `uv run woojae status` shows `mcp alive=no` or `reachable=no`.

Check:

```bash
uv run woojae status
uv run woojae logs mcp
```

Recover:

```bash
uv run woojae restart mcp
uv run woojae status
```

If `server.py` or MCP tool schemas changed, refresh the MCP connection in the ChatGPT app after restart.

## ngrok is not connected

Symptoms:

- Public MCP endpoint does not work.
- ChatGPT cannot reach the local MCP server through the ngrok URL.
- ngrok log shows tunnel or account errors.

Check:

```bash
uv run woojae status
uv run woojae logs ngrok
```

Recover:

```bash
uv run woojae restart ngrok
uv run woojae status
```

If ngrok still fails, check that the ngrok account/session is valid. `NGROK_HOST` is optional for temporary URL mode, but `uv run woojae copy-url` requires a configured fixed host.

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
uv run woojae doctor
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

## PID file is stale

Symptoms:

- `status` shows `alive=stale`.
- Process table shows stale state.
- The service is not actually running, but a pid file remains.

Check:

```bash
uv run woojae status
```

Recover by restarting the service or full session:

```bash
uv run woojae restart mcp
uv run woojae restart ngrok
```

For review-related stale state, prefer full session recovery:

```bash
uv run woojae restart-session
```

## Full session restart did not recover

Symptoms:

- The review page disconnects and does not return.
- review, MCP, or ngrok do not come back with new PIDs.

Check:

```bash
uv run woojae status
uv run woojae logs review
uv run woojae logs mcp
uv run woojae logs ngrok
```

Recover:

```bash
uv run woojae stop
uv run woojae start
uv run woojae status
```

The full session restart helper log is stored under the process directory shown by `uv run woojae status`.

## ChatGPT app MCP connection needs refresh

Refresh the ChatGPT app MCP connection when:

- `server.py` changed.
- MCP tool schemas changed.
- `MCP_ACCESS_TOKEN` changed.
- the public ngrok host changed.

Recommended order:

```bash
uv run woojae restart mcp
uv run woojae status
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
uv run woojae status
uv run woojae doctor
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
