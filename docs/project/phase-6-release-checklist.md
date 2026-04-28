# Phase 6 Release Checklist

Phase 6 closes the local session management workflow for Workspace Terminal Bridge.

## Release status

- Status: ready to close Phase 6
- Branch: `main`
- Last known clean worktree check: `git status --short --branch` returned `## main`
- Final documentation commit before this checklist: `6f317ca Document final supervisor workflow`
- Final applied bundle before this checklist: `cmd-20260427-180950-659072fa`

## Completed scope

### Local session supervisor

- `scripts/dev_session.sh start` starts the review server, MCP server, and ngrok in the background.
- Supervisor-managed process metadata is stored outside the repository under `~/.mcp_terminal_bridge/my-terminal-tool/processes`.
- Each managed service has a pid file and log file.
- Re-running `scripts/dev_session.sh start` reuses live managed processes instead of starting duplicates.
- `scripts/dev_session.sh status` reports pid, alive state, log path, and TCP reachability where applicable.
- `scripts/dev_session.sh doctor` checks required local tools, key environment state, and supervisor-managed service status.
- `scripts/dev_session.sh logs [review|mcp|ngrok]` tails managed service logs.
- `scripts/dev_session.sh stop` stops the full supervisor-managed session in reverse service order.

### Service control commands

- `scripts/dev_session.sh start-service [mcp|ngrok]`
- `scripts/dev_session.sh stop-service [mcp|ngrok]`
- `scripts/dev_session.sh restart [mcp|ngrok]`
- `scripts/dev_session.sh restart-session`

The review service is intentionally not exposed as an individual start/stop/restart target from the UI because it is the UI process itself.

### Review UI process management

- `/servers?tab=processes` shows supervisor process state for `review`, `mcp`, and `ngrok`.
- The process table shows pid, alive state, managed/stale state, reachability, endpoint, log file, and pid file.
- Long file paths are shortened visually while preserving the full path in the title attribute.
- MCP and ngrok show state-aware controls:
  - running: Stop / Restart
  - stopped or stale: Start
- The review service is displayed as terminal-only control.
- Successful MCP/ngrok start, stop, and restart operations show success notices.
- Full session stop and restart go through confirmation pages.

### Full session restart fix

- The UI-triggered full session restart previously stopped the review process but did not start the session again.
- Root cause: the restart helper was launched inside the review process group and was killed together with the review process.
- Fix: `schedule_full_session_restart()` launches the helper with `subprocess.Popen(..., start_new_session=True)`.
- Manual verification confirmed that review, MCP, and ngrok return with new PIDs after full session restart.

### Secret handling

- `MCP_ACCESS_TOKEN`, Bearer tokens, and `NGROK_AUTHTOKEN` are not printed in helper output or failure views.
- Failure screens mask sensitive stdout/stderr patterns.
- Runtime session secrets live outside the repository in `~/.mcp_terminal_bridge/my-terminal-tool/session.env`.
- The repository should not contain token values in README, logs, `.env`, fixtures, or screenshots.

## Verification completed before closing Phase 6

The final supervisor workflow bundle completed the following checks successfully:

- `bash -n scripts/dev_session.sh`
- `uv run python -m unittest discover -s tests`
- `uv run python scripts/smoke_check.py`
- `git diff --check`

The unit test suite reported 102 passing tests.

## Manual release checks

Before tagging or announcing Phase 6 as done, run the following commands from the repository root:

```bash
scripts/dev_session.sh status
scripts/dev_session.sh doctor
```

Expected high-level result:

- `review` is managed and reachable on the configured review host/port.
- `mcp` is managed and reachable on the configured MCP host/port.
- `ngrok` is managed and has a current log path.
- `doctor` reports `uv` as installed.
- Missing optional tools such as `terminal-notifier` are warnings, not release blockers.
- Token values are never printed.

For a full restart verification:

```bash
scripts/dev_session.sh status
scripts/dev_session.sh restart-session
# wait for the helper to stop and start the session
scripts/dev_session.sh status
```

Expected result:

- `review`, `mcp`, and `ngrok` have new PIDs after restart.
- `review` and `mcp` become reachable again.
- The restart helper log is available under the process directory.

## Known limitations

- The review UI does not individually stop or restart itself.
- Full session stop/restart can temporarily disconnect the browser page because the review server is part of the session.
- ngrok public reachability still depends on local ngrok configuration and account state.
- Remote MCP smoke checks require a valid `MCP_ACCESS_TOKEN` and public ngrok endpoint.
- `terminal-notifier` is optional; without it, clickable macOS notifications are unavailable.

## Recovery path

If the local session behaves unexpectedly:

```bash
scripts/dev_session.sh status
scripts/dev_session.sh logs review
scripts/dev_session.sh logs mcp
scripts/dev_session.sh logs ngrok
scripts/dev_session.sh restart-session
```

If `restart-session` does not recover the session:

```bash
scripts/dev_session.sh stop
scripts/dev_session.sh start
scripts/dev_session.sh status
```

If MCP tool schemas changed:

```bash
scripts/dev_session.sh restart mcp
```

Then refresh the MCP connection in the ChatGPT app.

## Recommended next phase

Phase 7 should focus on stability and operability rather than adding broad new capabilities immediately.

Good candidates:

- Add regression tests for full-session restart scheduling and sensitive output masking.
- Split long README content into focused docs under `docs/`.
- Add a concise troubleshooting guide for stuck bundles, stale pid files, and ngrok failures.
- Improve `/servers?tab=processes` UX around stale pid files and restart helper logs.
- Add a lightweight release checklist command or doc index once more release notes exist.
