# Phase 7 Plan

Phase 7 should build on the completed Phase 6 local session supervisor work. The goal is to improve stability, observability, and operator confidence before adding larger new capabilities.

## Goal

Make Workspace Terminal Bridge easier to operate, debug, and recover when local sessions, command bundles, or review UI flows get stuck.

## Guiding principles

- Keep local control explicit and reviewable.
- Prefer small, testable changes over broad rewrites.
- Do not expose secrets in UI, logs, bundle output, diagnostics, or docs.
- Keep Workspace Terminal Bridge tool calls small by using scripts, payload refs, and short bundles.
- Preserve the current safe workflow: inspect first, stage changes, approve locally, verify, then commit.

## Recommended scope

### 1. Regression tests for Phase 6 behavior

Add targeted tests for the behaviors that were fixed or stabilized during Phase 6.

Candidate tests:

- Full session restart scheduling launches a detached helper.
- Sensitive stdout/stderr masking covers `access_token`, Bearer tokens, `MCP_ACCESS_TOKEN`, and `NGROK_AUTHTOKEN` patterns.
- Process table rendering keeps full paths in `title` while displaying short filenames.
- MCP/ngrok controls render the correct Start, Stop, and Restart buttons by state.
- Review service renders as terminal-only and cannot be individually controlled from the UI.

Success criteria:

- Existing 102 tests continue to pass.
- New tests focus on pure helper/rendering behavior where possible.
- No live process control is required in unit tests.

### 2. Troubleshooting guide

Create a short operator guide for common failure modes.

Candidate file:

```text
docs/troubleshooting.md
```

Recommended sections:

- Review UI is unreachable.
- MCP server is unreachable.
- ngrok is not connected.
- Bundle is stuck in pending/applied/failed state.
- PID file is stale.
- Full session restart did not recover.
- ChatGPT app MCP connection needs refresh.
- A tool call appeared to fail but may have already staged a bundle.

Success criteria:

- Each failure mode has commands to check status, logs, and bundle state.
- Commands are short enough to copy safely.
- Recovery steps prefer `scripts/dev_session.sh status`, `logs`, `restart`, `restart-session`, and `stop/start`.

### 3. README decomposition

The README now covers product overview, security, session operations, bundle workflows, testing, and troubleshooting. It may become easier to maintain if long operational sections move into focused docs.

Candidate docs:

```text
docs/local-session.md
docs/command-bundles.md
docs/security.md
docs/troubleshooting.md
```

Success criteria:

- README remains the entrypoint.
- Detailed workflows move to docs without losing important warnings.
- Existing command examples remain accurate.
- Secret handling warnings stay visible in README.

### 4. Process management UX polish

Improve the `/servers?tab=processes` page after the Phase 6 functionality is stable.

Candidate improvements:

- Add a visible restart helper log link or path.
- Add clearer stale PID guidance.
- Add a copyable CLI command block for each service row.
- Add timestamps for last known pid/log update if available.
- Keep destructive full session controls behind confirmation pages.

Success criteria:

- The page remains read-first and low-risk.
- UI controls do not attempt to individually control the review process.
- Failure output continues to be masked.

### 5. Release workflow hardening

Add a small repeatable release checklist flow.

Candidate improvements:

- Add `docs/release-process.md`.
- Add a lightweight checklist command or script only if it does not duplicate existing smoke checks.
- Standardize final verification commands for docs-only, UI-only, and server/tool-schema changes.

Success criteria:

- A release can be closed from clean `main` with documented commands.
- Docs-only changes do not require unnecessary MCP restart.
- MCP schema changes explicitly require MCP restart and ChatGPT app refresh.

## Suggested execution order

### Phase 7A: Safety regression tests

Focus on the behaviors most likely to regress:

1. Sensitive output masking.
2. Detached full session restart scheduling.
3. Process control button rendering.
4. Terminal-only review service behavior.

Recommended verification:

```bash
uv run python -m unittest discover -s tests
git diff --check
```

### Phase 7B: Troubleshooting docs

Add `docs/troubleshooting.md` after the tests clarify expected behavior.

Recommended verification:

```bash
git diff --check
```

### Phase 7C: README split

Move detailed operational content gradually. Avoid rewriting the whole README in one change.

Recommended verification:

```bash
git diff --check
```

### Phase 7D: Process UX polish

Make one UI improvement at a time and verify rendering helpers through tests.

Recommended verification:

```bash
uv run python -m unittest discover -s tests
uv run python scripts/smoke_check.py
git diff --check
```

## Out of scope for early Phase 7

Avoid these until stability and docs are stronger:

- Large UI rewrites.
- New direct mutation tools.
- Background automation outside the current local approval workflow.
- Major authentication redesign.
- Broad command allowlist expansion.

## Current recommended next task

Start with Phase 7A and add regression tests for the Phase 6 fixes.

Initial target:

- Add or extend review UI helper tests for sensitive output masking and process control rendering.
- Add a small test around full session restart scheduling if it can be tested without starting real services.

This keeps Phase 7 grounded in the most valuable safety guarantees from Phase 6.
