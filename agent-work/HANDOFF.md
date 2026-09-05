---
lifecycle_schema: 1
kind: handoff
active_task: null
status: idle
updated_at: 2026-09-05
---

# Handoff

## Current goal

No active Task. Project-work lifecycle documents are aligned and the repository is ready for the next persistent Task.

## Completed in this state

- Reworked `AGENTS.md` into a compact authority/startup/invariant map with progressive disclosure.
- Converted CURRENT into the sole schema-backed active pointer and left it `idle` after completion.
- Added this canonical bounded HANDOFF snapshot; legacy `agent-work/handoffs/` files remain cold history.
- Updated `agent-work/README.md` with lifecycle roles, metadata, completion transaction, promotion boundaries, and compatibility rules.
- Added ADR-0002 for the durable lifecycle decision.
- Added and completed `TASK-2026-09-001` as the migration evidence record.
- Preserved existing historical Tasks/decisions/handoffs and the established `docs/project/` Plan/spec structure.

## Last validation

- Direct lifecycle validation: passed for 6 documents, including final newline, trailing whitespace, local Markdown links, and validating-state metadata consistency before completion.
- `git diff --check`: passed for the tracked repository tree.
- `git check-ignore -v`: confirmed `AGENTS.md` and `agent-work/` remain excluded by `.git/info/exclude`; no force-add or tracking change was made.
- `uv run terminalbridge status`: passed before the migration; review, MCP, and cloudflared were alive and the public endpoint returned the expected HTTP 401 challenge.

## Protected / pre-existing state

- `AGENTS.md` and `agent-work/` are local operating documents under the current `.git/info/exclude` configuration.
- Existing completed Task/decision/handoff records remain historical provenance.
- Public MCP/runtime behavior was not changed by this docs-only migration.

## Blockers / decisions

- none

## Next action

Start from `agent-work/CURRENT.md`. For the next non-trivial persistent change, create or activate one Task and point CURRENT to it before implementation.
