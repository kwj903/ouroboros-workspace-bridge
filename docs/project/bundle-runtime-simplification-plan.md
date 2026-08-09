# Bundle Runtime Simplification Plan

## Implementation status

Completed on 2026-08-10. Phases 1-3 are implemented and live-verified against the managed Workspace Terminal Bridge stack. The final source passes the full unit suite, local smoke, version-info check, `git diff --check`, Graphify rebuild, full Ruff, exact 31-tool remote MCP contract, and live mutation-annotation checks. The pre-existing user-owned `TASK-123` pending bundle remains pending and was not replayed during the controlled restart.

Post-completion backup contract correction: new command-bundle file mutations use the same canonical `RUNTIME_ROOT/backups/<backup_id>/manifest.json` writer as direct compatibility paths. `backup_id` is the authoritative persistent identifier, while legacy `RUNTIME_ROOT/command_bundle_file_backups/` data is retained unchanged as historical/read-only runtime state. Action snapshots remain a separate in-memory rollback mechanism for partial bundle failure.

## Goal

Simplify Workspace Terminal Bridge's approval-gated mutation runtime without weakening its core product invariants:

- local mutations remain review-gated by default;
- purpose-specific `workspace_propose_*_and_wait` tools remain the default public mutation path;
- Normal, Safe Auto, and YOLO remain supported;
- execution-time validation, snapshots/backups, rollback, logical session metadata, and bundle-specific handoffs remain supported;
- historical runtime records remain readable even when new records use a simpler lifecycle.

The target is a smaller and more deterministic bundle lifecycle with fewer polling loops, fewer duplicate state implementations, and explicit execution ownership.

## Baseline problems

The current runtime spreads one mutation across `server.py`, bundle helpers, a watcher, a review HTTP server, a runner subprocess, JSON state moves, handoff generation, and MCP-side polling. Review found these concrete risks:

1. A pending bundle has no atomic execution claim, so concurrent approval paths can race and execute it more than once.
2. JSON writes and bundle state transitions use direct writes/copy-then-delete patterns that are vulnerable to torn or duplicated state after interruption.
3. `*_and_wait` status polling is synchronous and can hold MCP execution threads for long periods.
4. Review UI long-poll revision checks and request-key deduplication repeatedly scan the entire bundle history.
5. Runner failure can be persisted as `failed` while its process still exits successfully, allowing watchers to misclassify execution.
6. Public-tool annotations and smoke-test expectations have drifted from the actual 31-tool runtime contract.
7. v0.6.0 removed worktree routing, but identity routing/facade layers still remain in the runner and server.
8. CLI/session lifecycle code has duplicated command surfaces that should eventually share one implementation.

## Design principles

- Prefer one canonical lifecycle implementation over distributed compatibility wrappers.
- Prefer atomic filesystem primitives before adding a database.
- Keep JSON runtime records for portability and inspectability unless measured scale requires stronger storage.
- Make `pending`, `running`, and terminal states explicit.
- Do not auto-replay interrupted `running` work without an explicit recovery decision.
- Derive handoff/audit/tool-call summaries from canonical state; they must not become execution authority.
- Preserve public MCP compatibility where practical; when a schema change is intentional, verify it against one canonical manifest.
- Keep historical-record normalization separate from new-record creation.

## Target lifecycle

```text
proposal
   |
   v
pending -- atomic claim --> running
   |                         |
   | reject                  +--> applied
   v                         +--> failed
rejected                     +--> interrupted
```

Only the process that successfully claims `pending -> running` may execute side effects. Finalization must atomically publish the terminal record. A stale `running` record is treated as interrupted/needs-review rather than silently replayed.

## Phase 1 — Correctness and execution ownership

### 1. Atomic JSON storage

Introduce one reusable atomic JSON writer for runtime state:

- write to a same-directory temporary file;
- flush and fsync when practical;
- publish with `os.replace()`;
- preserve current JSON formatting/encoding contracts;
- replace duplicate direct JSON writers in bundle execution paths.

### 2. Atomic bundle claim/finalize

Add canonical bundle-store operations:

- `claim_pending_bundle(bundle_id)` performs an atomic `pending -> running` ownership transfer;
- store execution metadata such as execution id, pid, and start timestamp when useful;
- `finalize_bundle(...)` atomically transitions `running -> applied|failed|interrupted`;
- competing claims must fail without executing the bundle;
- lookup/list/status functions must understand `running` and historical records without it.

### 3. Runner/watch correctness

- runner must claim before any mutation;
- runner failure must produce a non-zero process exit code;
- watcher/UI execution paths must determine success from canonical terminal state, not only subprocess exit code;
- restart recovery must not automatically replay stale running records;
- add race/interruption regression tests.

### Phase 1 acceptance criteria

- concurrent runner attempts execute one bundle at most once;
- torn JSON writes are not observable under normal interruption boundaries;
- failed bundle execution cannot be reported as auto-applied;
- old bundle JSON remains readable;
- full unit suite passes.

## Phase 2 — Performance and waiting model

### 1. Remove full-history revision polling

Replace `command_bundle_revision()` full JSON parsing on every long-poll iteration with a compact generation/change signal. Use an opaque UUID-style token published with atomic replace rather than a numeric read-modify-write counter, avoiding lost increments between concurrent writers:

- mutation/transition paths update one generation token atomically;
- review long-poll observes the generation token;
- full bundle rows are reloaded only after a detected change or when a page explicitly requests them;
- reuse loaded rows inside one request.

### 2. Bound deduplication cost and semantics

- avoid scanning every historical terminal bundle for every proposal;
- dedupe strongly across active `pending`/`running` work;
- define a bounded terminal retry/idempotency window if compatibility requires it;
- preserve session metadata participation in request identity;
- add explicit tests for retry-after-applied/failed/rejected behavior.

Use a compact filesystem request-key slot/index rather than SQLite unless later evidence shows the filesystem contract has become more complex than a small database. The canonical bundle JSON remains authoritative; request-key slots are rebuildable derived state. Preserve terminal idempotent replay by default and require an explicit retry identity when a caller intentionally wants a new attempt for an already-final request.

### 3. Non-blocking wait behavior

- remove synchronous `time.sleep()` from public long-wait MCP paths;
- use async waiting or thread offload compatible with FastMCP;
- keep explicit status tools for clients that prefer submit-then-poll;
- preserve `*_and_wait` public convenience semantics.

### Phase 2 acceptance criteria

- review event checks no longer parse the entire bundle history every 0.5 seconds;
- proposal dedupe cost is not linear in all historical terminal bundles for the normal path;
- one pending approval wait does not block unrelated MCP calls;
- existing review UI and public proposal UX still work.

## Phase 3 — Structural cleanup

### 1. Bundle service/store ownership

Move bundle lifecycle logic out of the giant MCP façade into cohesive runtime modules. The desired responsibility split is:

```text
server.py
  MCP registration, schemas, annotations, thin adapters

BundleService
  propose, status, wait, cancel, claim, execute/finalize coordination

BundleStore
  atomic persistence, state lookup/listing, request-key index/generation

Runner
  execution-time validation, snapshot/rollback, command/action execution
```

Avoid building a generalized framework; extract only boundaries proven by the current bundle workflow.

### 2. Remove v0.6.0 worktree-routing identity layers

For new execution paths remove unnecessary identity mappings such as duplicated source/apply roots and identity path mapping. Preserve legacy record parsing only at compatibility boundaries.

### 3. Public tool contract single source of truth

Create one canonical public-tool manifest used by:

- MCP registration/introspection expectations;
- `workspace_info().tools`;
- smoke tests/schema regressions.

Tests should verify exact default public-tool equality, not a stale subset.

### 4. MCP annotations

Align annotations with actual side effects. Proposal/cancel/payload-stage operations that mutate runtime state or may auto-execute in YOLO must not advertise themselves as pure read-only operations.

### 5. Hidden/direct compatibility cleanup

- reduce no-op hidden façade layers where they only add call depth;
- keep low-level Python capabilities needed by runner/tests/operator code;
- keep direct mutation tools out of the default public MCP schema;
- do not remove the optional direct-tool compatibility switch without explicit migration evidence.

### 6. CLI command-tree consolidation

Keep the distinct meanings of `terminalbridge` and `woojae`: `terminalbridge` remains the operator-facing full connection-stack command, while `woojae` retains lower-level session/update/diagnostic commands. Consolidate only duplicated implementation primitives (URL/open/version/setup helpers and managed connector primitives) rather than merging the two command trees or entry points. Do not change documented user commands unnecessarily.

### Phase 3 acceptance criteria

- bundle lifecycle has one canonical service/store implementation;
- `server.py` no longer owns duplicated bundle-state behavior;
- obsolete worktree identity routing is removed from new execution;
- public tool manifest, `workspace_info`, smoke check, and tests agree exactly;
- both CLI entry points preserve supported behavior with shared implementation where feasible;
- full unit/smoke/ruff/diff checks pass.

## Complexity that must remain

The following mechanisms provide real product value and are not cleanup targets:

- purpose-specific review-gated proposal wrappers;
- execution-time path/command validation;
- snapshot, backup, and rollback for partial action failures;
- `task_id`, `client_id`, `session_id`, and `project_id` logical metadata;
- bundle-specific handoffs and bounded audit/tool-call observability;
- explicit Normal / Safe Auto / YOLO approval modes.

## Verification strategy

Each phase should run focused tests first, followed by the full suite at integration checkpoints. Final validation target:

```bash
uv run python -m unittest discover -s tests
uv run ruff check .
uv run python scripts/smoke_check.py
uv run python scripts/update_version_info.py --check
git diff --check
uv run graphify update . --force
```

If public MCP registration or annotations change, restart the managed MCP/review stack and refresh the ChatGPT connector before live schema verification.

## Migration and compatibility

- No historical runtime JSON should be deleted as part of this refactor.
- Existing `command_bundle_file_backups/` payloads remain historical runtime data; new persistent file backups are written only through the canonical `backups/` manifest store.
- Readers normalize legacy records without `running`, generation, or new execution metadata.
- New records should not emit retired worktree routing fields.
- Public mutation remains bundle/review-first by default.
- Any public schema change must be documented in the task record and CHANGELOG/user docs when operator-visible.
