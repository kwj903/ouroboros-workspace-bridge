# Workspace Terminal Bridge Agent Operating Contract

## Purpose

This repository implements Workspace Terminal Bridge: a review-gated local MCP bridge for file, terminal, Git, runtime, and operator workflows.

Keep this file as a stable project map. Detailed implementation history, task logs, and long runbooks belong in linked documents rather than this always-loaded entrypoint.

## Authority

Use authority in this order for repository work:

1. Actual source, tests, runtime state, and Git state for implementation truth.
2. [agent-work/CURRENT.md](agent-work/CURRENT.md) as the sole active-work pointer.
3. The active Task and, when present, its linked Plan/spec/ADR as execution authority.
4. [docs/project/](docs/project/) for stable plans, architecture notes, release/update information, and long-term project documentation.
5. LLM-WIKI for reusable workflow and long-term cross-project knowledge, not volatile repository state.

Preserve explicit user instructions and pre-existing user changes.

## Startup

For a fresh session or resumed non-trivial task:

1. Check the current Git state and relevant managed runtime/process state.
2. Read [agent-work/CURRENT.md](agent-work/CURRENT.md).
3. Read only the active Task and Plan linked by CURRENT.
4. Read [agent-work/HANDOFF.md](agent-work/HANDOFF.md) only when interrupted/resumed context needs a fresh resume snapshot.
5. Load linked specs, ADRs, runbooks, source files, and tests on demand.
6. For non-trivial structure, dependency, or impact analysis, use Graphify on demand and verify its guidance against source/tests/runtime.

Do not preload completed tasks, historical handoffs, Graphify reports, or every project document.

## Active Work Documents

[agent-work/README.md](agent-work/README.md) defines the repository-local lifecycle. `AGENTS.md` and `agent-work/` are currently excluded through `.git/info/exclude`, so treat them as local operating documents and do not force-add them to Git unless the user explicitly requests it.

- [agent-work/CURRENT.md](agent-work/CURRENT.md): sole current pointer; rewrite when active work changes; never append history.
- [agent-work/HANDOFF.md](agent-work/HANDOFF.md): bounded fresh-agent resume snapshot; rewrite rather than append.
- [agent-work/tasks/](agent-work/tasks/): stable-path Task records with goal, scope, completion criteria, progress, evidence, blockers, and next action.
- [agent-work/decisions/](agent-work/decisions/): durable architecture/product decisions only.
- [agent-work/handoffs/](agent-work/handoffs/): legacy or intentionally retained historical handoff artifacts; not startup context.
- [docs/project/](docs/project/): existing stable Plan/spec/architecture authority. Do not create a duplicate plan tree solely to match a template.

Tiny one-shot changes do not need lifecycle ceremony unless active state changes.

## Working Invariants

- Do not mark work complete without actual validation evidence.
- Do not let CURRENT, HANDOFF, or AGENTS accumulate completed history.
- Preserve unrelated user or concurrent-session changes.
- Do not auto-commit, push, deploy, publish, or perform destructive remote actions without explicit authorization.
- Keep local mutation review-gated by design.
- Keep the purpose-specific `workspace_propose_*_and_wait` family as the default public change path.
- Keep internal low-level mutation tools out of the default public MCP schema.
- Keep each review item focused on one purpose; do not bundle edits, verification, commits, or pushes together.
- Never expose secret values in output, UI, logs, docs, fixtures, or screenshots.

## Graphify

Use Graphify as an on-demand navigation and impact-analysis accelerator, not as source truth.

For structural code work, debugging, refactoring, shared-contract changes, or cross-module impact analysis:

1. Prefer scoped Graphify query/explain/affected/path operations when useful.
2. Narrow candidate files/symbols.
3. Confirm findings in source/tests/runtime before editing.
4. After executable structure changes, check/update graph freshness when this repository's Graphify workflow is active.

Docs-only work and obvious one-file changes normally do not need Graphify.

## High-Risk Areas

Be especially careful when changing:

- `server.py`: MCP registration, public tool visibility, wrapper schemas, access behavior
- `terminal_bridge/mcp_tools/`: public tool helper behavior
- `terminal_bridge/bundles.py`: bundle records, state, listing, serialization
- `terminal_bridge/handoffs.py`: runtime handoff records and routing
- `terminal_bridge/approval_modes.py`: Normal, Safe Auto, and YOLO behavior
- `scripts/command_bundle_review_server.py`: review UI rendering and approval/reject routes
- `scripts/command_bundle_runner.py`: approved bundle application, rollback, backup, failure behavior
- `terminal_bridge/cli.py` and operator lifecycle modules: service management, cleanup, update, session operations

## Documentation Boundaries

- [agent-work/](agent-work/README.md): active execution state, Task evidence, lifecycle handoff, and durable agent decisions.
- [docs/project/](docs/project/): stable project plans, architecture, release/update, and operator-development references.
- [docs/en/](docs/en/) and [docs/ko/](docs/ko/): user-facing documentation.
- [CHANGELOG.md](CHANGELOG.md): user/operator-visible changes.

Promote durable conclusions into stable docs only when they are no longer transient execution state.

## Validation

Use the smallest sufficient validation:

- Docs-only: `git diff --check` plus link/schema consistency when lifecycle files change.
- Python/tool behavior: `uv run python -m unittest discover -s tests`.
- MCP schema/public workflow: unit tests, `uv run python scripts/smoke_check.py`, and `git diff --check`.
- Shell/installers: syntax checks plus relevant focused smoke/unit checks.

If public MCP schema changes, restart the managed MCP stack as required and refresh/reconnect clients that cache schema.

## Completion

For a non-trivial Task, treat completion as one logical documentation transaction:

1. Verify actual changes against completion criteria.
2. Record concise evidence and limitations in the Task.
3. Update stable Plan/ADR/spec only when the outcome is durable.
4. Rewrite HANDOFF as the current resume snapshot.
5. Rewrite CURRENT to the next executable Task, a decision gate, or `idle`.
6. Re-check cross-file consistency.
7. Commit or push only when explicitly requested.
