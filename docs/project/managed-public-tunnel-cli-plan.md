# Managed Public Tunnel CLI Plan

## Goal

Add a user-facing `terminalbridge` command that operates the existing Workspace Terminal Bridge through one consistent interface while preserving the lower-level `woojae` supervisor and existing ngrok behavior.

The command must support:

- `terminalbridge start`
- `terminalbridge stop`
- `terminalbridge restart`
- `terminalbridge status`
- `terminalbridge logs`
- `terminalbridge setup`
- explicit `--mode ngrok|cloudflare|external` selection

## Architecture

The implementation keeps one shared Bridge core:

- Review UI
- MCP server
- access-token authentication
- workspace and runtime configuration
- proposal and approval workflow

Only the public connector differs:

- `ngrok`: existing `woojae` supervisor manages review, MCP, and ngrok.
- `cloudflare`: `woojae` manages review and MCP; the new operator layer manages the user's own `cloudflared` process.
- `external`: `woojae` manages review and MCP while the operator manages a proxy or tunnel outside this project.

`PUBLIC_ACCESS_MODE` remains `ngrok|external` for compatibility. A separate provider setting distinguishes managed Cloudflare from generic external mode.

## User-owned configuration

No operator-specific infrastructure may be bundled or selected by default. Each installation owns its own values:

- `MCP_ACCESS_TOKEN`
- `NGROK_HOST` and ngrok account configuration
- `PUBLIC_MCP_URL`
- external tunnel provider
- Cloudflare config path
- Cloudflare tunnel name
- optional cloudflared executable path
- `WORKSPACE_ROOT`

The repository must not include a real token, tunnel credential, tunnel ID, operator domain as a forced default, or user-specific absolute path.

## Settings

Add compatible session fields:

- `EXTERNAL_TUNNEL_PROVIDER=manual|cloudflare`
- `CLOUDFLARED_CONFIG_PATH`
- `CLOUDFLARED_TUNNEL_NAME`
- `CLOUDFLARED_BIN`

Existing session files without these fields load as `manual` external management.

## Process ownership

The Cloudflare connector uses the existing runtime process directory with separate files:

- `cloudflared.pid`
- `cloudflared.log`
- `cloudflared.process.json`

Before reusing or terminating a PID, the operator verifies that it still belongs to the configured cloudflared executable. A stale or reused PID file is removed without terminating an unrelated process.

## Lifecycle rules

### Start

- Apply an explicit `--mode` selection when supplied and persist the selected profile.
- Prevent simultaneous managed ngrok and Cloudflare connectors.
- Start the Bridge services first.
- Wait for Review and MCP readiness.
- In Cloudflare mode, start cloudflared from the user's config and tunnel name.
- Report endpoint reachability without exposing the token.

### Stop

- Stop managed cloudflared first.
- Stop all `woojae` services, including stale ngrok state.
- Preserve configuration for later switching.

### Status

Show:

- selected operator mode
- Review and MCP state
- ngrok state
- cloudflared state
- redacted public endpoint
- public endpoint reachability

### Logs

Expose bounded logs for review, MCP, ngrok, cloudflared, or all services.

## Compatibility

- `uv run woojae ...` remains available and keeps its current low-level semantics.
- Existing ngrok installations require no migration.
- Existing external installations remain manual unless the user selects Cloudflare management.
- Public MCP tool schema does not change.
- Review UI remains loopback-only.

## Cross-platform requirements

- macOS and Linux use detached process groups.
- Windows uses the existing safe process-launch behavior and supports a user-supplied absolute cloudflared executable path.
- Path expansion and persistence must work across POSIX and Windows.
- Tests must not depend on the operator's live domain, credentials, tunnel, or local runtime files.

## Verification

- focused operator CLI and process-management tests
- existing CLI, public-access, and session-supervisor tests
- full unit suite
- smoke check
- Ruff and compile checks
- Bash and PowerShell syntax checks where available
- update-info and diff checks
- live Mac handoff from separately started cloudflared to `terminalbridge start`
- existing endpoint authentication and MCP initialize check
- ngrok compatibility check without exposing credentials
