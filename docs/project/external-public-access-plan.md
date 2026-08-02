# External Public Access Plan

## Status

- Status: approved for implementation
- Date: 2026-08-02
- Target branch: `external-public-access`
- Primary endpoint for operator validation: `https://terminalbridge.woojae.dev/mcp`
- Related task: `agent-work/tasks/2026-08-external-public-access.md`

## Purpose

Allow Ouroboros Workspace Bridge to keep its existing ngrok workflow while also supporting a user-managed public domain and tunnel or reverse proxy. The bridge must remain usable on macOS, Linux, and Windows through the same `uv run woojae ...` commands.

The first operator deployment will use:

```text
https://terminalbridge.woojae.dev/mcp?access_token=<TOKEN>
```

The public domain is a stable entrypoint. The active computer runs the local MCP server and a separately managed external tunnel. Only one computer should run the shared tunnel at a time.

## Goals

1. Preserve existing ngrok behavior and settings without migration requirements.
2. Add an `external` public access mode for user-managed domains.
3. Keep the review UI localhost-only.
4. Reuse the existing MCP access-token middleware.
5. Generate and redact the correct public MCP URL in CLI and review UI surfaces.
6. Make service lifecycle transitions safe when switching between ngrok and external modes.
7. Validate behavior on Ubuntu, macOS, Windows CI, then on a physical Windows notebook.

## Non-goals

- Managing Cloudflare accounts, API tokens, tunnel credentials, DNS records, or tunnel installation inside this project.
- Replacing ngrok with Cloudflare-specific code.
- Running the same shared domain against multiple computers simultaneously.
- Exposing the review UI publicly.
- Replacing query-token authentication with OAuth in this task.
- Changing the public MCP tool schema.

## Architecture decision

Public access is selected through a small provider-neutral configuration contract:

```text
PUBLIC_ACCESS_MODE=ngrok|external
PUBLIC_MCP_URL=https://terminalbridge.woojae.dev/mcp
```

`ngrok` remains the default. `external` means the bridge manages only the review and MCP processes; the operator manages the external tunnel separately.

### Runtime topology

ngrok mode:

```text
ChatGPT -> ngrok -> 127.0.0.1:8787/mcp
```

external mode:

```text
ChatGPT -> terminalbridge.woojae.dev -> external tunnel/proxy -> 127.0.0.1:8787/mcp
```

Review UI in both modes:

```text
http://127.0.0.1:8790/pending
```

## Configuration contract

### New settings

- `PUBLIC_ACCESS_MODE`
  - Allowed values: `ngrok`, `external`
  - Default: `ngrok`
  - Invalid values fail with an actionable configuration error.
- `PUBLIC_MCP_URL`
  - Required only in `external` mode.
  - Canonical form includes the `/mcp` path and excludes credentials, query parameters, and fragments.
  - HTTPS is required for non-local public endpoints.

### Existing settings retained

- `NGROK_HOST`
- `NGROK_BASE_URL`
- `MCP_ACCESS_TOKEN`
- `WORKSPACE_ROOT`
- existing local host and port settings

### Compatibility and precedence

1. Explicit process environment values remain highest priority.
2. Runtime `session.json` values are next.
3. Legacy `session.env` values remain supported.
4. Missing `PUBLIC_ACCESS_MODE` resolves to `ngrok`.
5. Existing installations containing only `NGROK_HOST` continue unchanged.
6. Switching back from `external` to `ngrok` does not require reconstructing previous ngrok settings.

## Public URL handling

Introduce a focused pure helper module, tentatively `terminal_bridge/public_access.py`, responsible for:

- mode normalization and validation;
- external URL normalization and validation;
- public hostname extraction;
- public base endpoint selection;
- final tokenized URL construction;
- redacted URL construction.

Validation must reject:

- non-HTTPS public URLs;
- embedded username or password;
- query strings or fragments in `PUBLIC_MCP_URL`;
- an access token embedded in configuration;
- missing hostnames;
- paths other than the canonical MCP endpoint unless intentionally normalized to `/mcp`.

The access token must be URL-encoded when composing the final connector URL and must never be printed unredacted.

## Service lifecycle

Keep all known service names for compatibility:

```text
review, mcp, ngrok
```

Add a mode-aware active-service selector:

- ngrok mode: `review`, `mcp`, `ngrok`
- external mode: `review`, `mcp`

Important transition rule:

- `start_session` starts only active services.
- `stop_session` always attempts to stop every managed service, including ngrok.
- `restart_session` stops every managed service, then starts only active services.

This prevents a stale ngrok process from surviving a change from ngrok to external mode.

Low-level commands such as `restart ngrok` remain available for compatibility, but in external mode they should fail or report disabled status clearly rather than silently launching ngrok against the external configuration.

## Server transport security

Transport host and origin allowlists must be derived from the selected public endpoint:

- ngrok mode: continue using the normalized ngrok hostname;
- external mode: use the hostname parsed from `PUBLIC_MCP_URL`.

Local loopback hosts remain allowed. Arbitrary hosts remain rejected by DNS rebinding protection.

The current MCP middleware already accepts both:

```text
?access_token=<TOKEN>
Authorization: Bearer <TOKEN>
```

No authentication weakening is permitted. Starting the MCP server without `MCP_ACCESS_TOKEN` must continue to fail closed.

## CLI and setup experience

Existing commands remain stable:

```text
uv run woojae setup
uv run woojae setup-ui
uv run woojae doctor
uv run woojae start
uv run woojae stop
uv run woojae restart-session
uv run woojae status
uv run woojae mcp-url
uv run woojae copy-url
```

Setup behavior:

- Ask for public access mode.
- In ngrok mode, preserve current ngrok guidance and host input.
- In external mode, request and validate `PUBLIC_MCP_URL`; skip ngrok installation warnings.
- Never request Cloudflare credentials.

Status and doctor behavior:

- Show selected public access mode.
- Show only a redacted public endpoint.
- External mode reports that tunnel lifecycle is externally managed.
- External mode does not warn that ngrok is absent.
- Detect invalid external configuration before starting services.

## Review UI and onboarding UI

- ngrok mode keeps existing service controls and diagnostics.
- external mode hides or disables ngrok start/stop/restart controls.
- external mode displays the configured public endpoint without a token.
- external mode warns that only one computer should run the shared tunnel at a time.
- review UI remains bound to loopback and is never included in public tunnel instructions.

## Remote smoke behavior

Remote smoke checks must use a provider-neutral public endpoint:

- ngrok mode derives the endpoint from `NGROK_HOST` or `NGROK_BASE_URL`.
- external mode uses `PUBLIC_MCP_URL`.
- `MCP_ACCESS_TOKEN` is appended with proper URL encoding.
- command output and failures redact token values.

## Implementation phases

### Phase 1 — Task and design baseline

- Add this stable plan.
- Add active task and design decision records.
- Create the implementation branch.
- Run Graphify impact queries and verify source locations.

### Phase 2 — Pure configuration and URL helpers

- Add focused tests first.
- Implement mode and URL parsing.
- Extend session persistence and environment export.
- Preserve legacy configuration behavior.

### Phase 3 — Supervisor lifecycle

- Add active-service selection.
- Make stop/restart transitions mode-safe.
- Add mode-aware status, doctor, URL preview, and clipboard behavior.

### Phase 4 — Server, CLI, and UI integration

- Generalize transport allowed-host handling.
- Update CLI help without breaking command names.
- Update review UI and setup UI.
- Generalize remote smoke scripts.

### Phase 5 — Documentation and release metadata

- Update English and Korean user documentation.
- Update security notes and changelog.
- Update version metadata if this is released as a user-visible feature.

### Phase 6 — Validation and rollout

- Focused unit tests.
- Complete unit and smoke suites.
- Ruff and applicable type checks.
- Bash and PowerShell syntax checks.
- Graphify update and representative query.
- Ubuntu, macOS, and Windows GitHub Actions.
- macOS live external-domain test.
- physical Windows notebook clean-install and domain handoff test.

## Test matrix

### Configuration

- default resolves to ngrok;
- legacy ngrok-only session loads unchanged;
- external settings persist through JSON and legacy env parsing;
- invalid mode fails clearly;
- missing external URL fails clearly;
- unsafe URLs are rejected;
- Windows paths remain unaffected.

### Lifecycle

- ngrok mode starts three services;
- external mode starts two services;
- external mode never requires the ngrok executable;
- switching ngrok to external stops stale ngrok;
- switching external to ngrok starts ngrok normally;
- low-level ngrok commands are explicit in external mode.

### Security and URL output

- external hostname is allowed by transport security;
- unrelated hosts remain rejected;
- unauthorized requests return 401;
- valid query token and Bearer token remain accepted;
- no test, log, UI, or command output leaks the token;
- final URL encoding is correct.

### UI and docs

- external mode does not render active ngrok control buttons;
- ngrok mode retains existing controls;
- status and onboarding instructions match the mode;
- English and Korean examples use placeholders only.

## Physical Windows acceptance test

After merged code is available on GitHub:

1. Clone into a clean Windows checkout.
2. Run `uv sync`, `woojae setup`, and `woojae doctor`.
3. Select external mode and configure `https://terminalbridge.woojae.dev/mcp`.
4. Stop the Mac bridge and Mac tunnel.
5. Start the Windows bridge and the same external tunnel connector.
6. Confirm ChatGPT uses the unchanged connector URL.
7. Verify Windows workspace reads, proposal creation, local approval, command execution, and Git status.
8. Verify browser, clipboard, firewall, and notification behavior.
9. Stop Windows and prove the domain can be returned to Mac without connector reconfiguration.

## Completion criteria

The task is complete when:

- existing ngrok users require no configuration migration;
- external mode works without ngrok installed;
- `terminalbridge.woojae.dev` can target the active Mac or Windows computer without changing the ChatGPT connector URL;
- only one shared-domain tunnel is active at a time;
- all local and CI tests pass;
- no public MCP schema changes were introduced;
- review UI remains localhost-only;
- documentation and active task records match actual behavior.
