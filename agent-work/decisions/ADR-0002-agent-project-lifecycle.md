---
lifecycle_schema: 1
kind: decision
id: ADR-0002
status: accepted
decided: 2026-09-05
---

# ADR-0002 Adopt the agent-project lifecycle hot-document contract

## Context

ADR-0001 established a useful separation between stable project documentation and repository-local agent work state. Over time, however, the current-state documents drifted from their intended roles:

- `CURRENT.md` retained the full result and validation history of an already completed Task.
- handoff files were session-specific historical artifacts rather than one bounded current resume snapshot.
- fresh-session onboarding preloaded several stable documents even when they were not needed for the active work.
- Task formats evolved organically, making a bulk format rewrite risky and low-value.

The canonical LLM-WIKI `knowledge.skills.agent-project-lifecycle` skill defines a compatible model: repository truth first, one sole CURRENT pointer, progressive disclosure, evidence-based completion, a fresh HANDOFF snapshot, stable-path Task records, and no forced migration of useful legacy history.

## Decision

Adopt that lifecycle model with the smallest repository-compatible changes:

- `AGENTS.md` is a stable map and operating contract, not a work log or full manual.
- `agent-work/CURRENT.md` is the sole active-work pointer and is rewritten when active state changes.
- `agent-work/HANDOFF.md` is the one canonical fresh-agent resume snapshot and is rewritten rather than appended.
- `agent-work/tasks/` keeps stable-path Task records. New persistent Tasks use lifecycle schema v1 metadata; historical Tasks are not bulk-renamed or reformatted solely for consistency.
- `agent-work/handoffs/` remains as cold historical provenance and is not part of normal startup context.
- `docs/project/` remains this repository's established stable Plan/spec/architecture area. A duplicate `agent-work/plans/` tree is not created merely to match a generic template.
- Graphify remains on-demand code intelligence: it narrows scope but never replaces source/tests/runtime verification.
- LLM-WIKI supplies reusable lifecycle workflow and durable cross-project knowledge, but volatile current repository state remains local.
- Task completion includes synchronized Task evidence, HANDOFF rewrite, and CURRENT transition to the next executable Task, a decision gate, or `idle`.

## Consequences

- Fresh sessions can restore active work from a much smaller hot context.
- Completed Task evidence stays in Task/history documents instead of bloating CURRENT.
- Interrupted work gets one clear resume snapshot instead of ambiguous session handoff history.
- Existing historical documents remain useful and stable; migration churn is limited to documents that affect current operation.
- Deterministic lifecycle checks can be added later using the narrow frontmatter fields without forcing semantic data into YAML.

## Alternatives considered

- Bulk-convert every historical Task and handoff to schema v1: rejected because it creates high churn without improving current-context restoration.
- Move all stable plans from `docs/project/` into a new `agent-work/plans/`: rejected because the existing plan authority is already established and linked across the repository.
- Keep the old CURRENT-as-completion-report model: rejected because it makes completed history the default startup context and leaves no unambiguous idle/current state.

## References

- [ADR-0001](ADR-0001-agent-work-document-system.md)
- [Agent work lifecycle](../README.md)
- [Current pointer](../CURRENT.md)
- [Canonical handoff](../HANDOFF.md)
- LLM-WIKI `knowledge.skills.agent-project-lifecycle`
- LLM-WIKI `knowledge.skills.agent-project-lifecycle.schemas-v1`
