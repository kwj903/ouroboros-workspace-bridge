---
lifecycle_schema: 1
kind: task
id: TASK-2026-09-001
status: completed
plan: null
depends_on: []
code_intelligence: none
---

# TASK-2026-09-001 Align project work documents with agent-project lifecycle

## Goal

Align the repository's project-work documentation with the canonical agent-project lifecycle while preserving established repository structure and historical provenance.

## Scope

- Make `AGENTS.md` a concise authority/startup/invariant map.
- Convert `agent-work/CURRENT.md` into the sole schema-backed active pointer.
- Add one canonical bounded `agent-work/HANDOFF.md`.
- Update `agent-work/README.md` with progressive-disclosure, completion-transaction, and compatibility rules.
- Record the durable migration decision in ADR-0002.
- Preserve existing Task, decision, historical handoff, and `docs/project/` plan paths.

## Non-goals

- No source/runtime/public MCP behavior changes.
- No bulk conversion or renaming of historical Task/handoff documents.
- No duplicate `agent-work/plans/` tree solely for schema conformity.
- No commit or push unless separately requested.

## Relevant authority

- [AGENTS.md](../../AGENTS.md)
- [Agent work lifecycle](../README.md)
- [ADR-0001](../decisions/ADR-0001-agent-work-document-system.md)
- [ADR-0002](../decisions/ADR-0002-agent-project-lifecycle.md)
- LLM-WIKI `knowledge.skills.agent-project-lifecycle`
- LLM-WIKI `knowledge.skills.agent-project-lifecycle.schemas-v1`

## Completion criteria

- [x] CURRENT becomes a narrow sole pointer instead of a completed-history report.
- [x] Canonical bounded HANDOFF exists and legacy handoffs are explicitly cold history.
- [x] AGENTS startup uses progressive disclosure rather than mandatory broad preloading.
- [x] Existing `docs/project/` plans and historical agent-work documents remain compatible.
- [x] Durable lifecycle adoption is recorded in a decision document.
- [x] `git diff --check` passes for the tracked repository tree.
- [x] Local Markdown links in the changed lifecycle documents resolve.
- [x] CURRENT, Task, and HANDOFF lifecycle metadata are designed for a final consistent idle transition.

## Progress

Completed. The repository now follows the canonical hot-document lifecycle while retaining its existing stable project-plan and historical document structure.

## Evidence

- Pre-change project snapshot: branch `main`, clean tracked worktree, synchronized with `origin/main`.
- LLM-WIKI canonical lifecycle skill and schema v1 reference were read before editing.
- `uv run terminalbridge status` passed before editing: review/MCP/cloudflared were alive and the public endpoint returned the expected unauthenticated HTTP 401 challenge.
- Lifecycle validator passed for 6 changed documents: final newline, trailing whitespace, local Markdown links, and validating-state CURRENT/Task/HANDOFF consistency.
- `git diff --check` exited 0 for the tracked repository tree.
- `git check-ignore -v` confirmed that `AGENTS.md` and `agent-work/` are local operating documents excluded by `.git/info/exclude`; no force-add or Git tracking change was made.

## Limitations / blockers

- These lifecycle documents are intentionally outside normal Git status/diff visibility under the current local exclude configuration. Their content was validated directly rather than through a tracked Git diff.
- none otherwise

## Next action

None for this Task. CURRENT and HANDOFF should be left in `idle` until a new persistent Task is activated.
