# Agent Work Lifecycle

This directory stores repository-local execution state for persistent AI-assisted work. It is intentionally separate from [docs/project/](../docs/project/), which remains the stable home for project plans, architecture notes, release/update documents, and long-term development references.

The lifecycle is designed for progressive disclosure:

```text
AGENTS.md
→ CURRENT.md
→ active Task / linked Plan
→ HANDOFF.md only when resume context is needed
→ linked source/tests/spec/ADR on demand
```

Completed history is retained, but it is not default startup context.

## Canonical Roles

```text
agent-work/
├── README.md
├── CURRENT.md
├── HANDOFF.md
├── tasks/
├── decisions/
└── handoffs/     # retained legacy/cold handoff artifacts
```

- [CURRENT.md](CURRENT.md): the sole active-work pointer. It contains only current goal, next action, blockers/decision gate, and relevant authority.
- [HANDOFF.md](HANDOFF.md): a bounded fresh-agent resume snapshot. Rewrite it when state changes; do not append session history.
- [tasks/](tasks/): stable-path Task records. New persistent Tasks should use lifecycle frontmatter plus goal, scope, completion criteria, progress, evidence, limitations, and next action.
- [decisions/](decisions/): durable architecture/product decisions. Do not create an ADR for routine implementation choices.
- [handoffs/](handoffs/): historical handoff artifacts retained for provenance. They are cold history and should be searched only when specifically needed.
- [docs/project/](../docs/project/): this repository's established stable Plan/spec/architecture area. Reuse it instead of creating a duplicate `agent-work/plans/` tree solely for format uniformity.

## Startup Protocol

1. Check Git status and relevant runtime/process state.
2. Read [../AGENTS.md](../AGENTS.md).
3. Read [CURRENT.md](CURRENT.md).
4. If CURRENT names an active Task, read that Task.
5. If the Task links a Plan/spec/ADR, read only what the current work requires.
6. Read [HANDOFF.md](HANDOFF.md) only for interrupted/resumed work that needs a resume snapshot.
7. Use Graphify on demand for non-trivial code structure, dependency, or impact questions, then verify against source/tests/runtime.

Do not preload completed Tasks, old handoffs, Graphify reports, or all stable project docs.

## Lifecycle Metadata

New or migrated lifecycle documents use narrow YAML frontmatter for machine-checkable state. Existing historical Tasks do not need bulk renames or metadata-only churn.

Recommended status vocabulary:

- CURRENT: `idle`, `ready`, `in_progress`, `validating`, `blocked`, `decision_required`
- Task: `planned`, `ready`, `in_progress`, `validating`, `blocked`, `decision_required`, `completed`, `cancelled`
- Decision: `proposed`, `accepted`, `superseded`, `rejected`

Stable file paths are preferred. Completion normally changes metadata/state rather than moving files between active/completed directories.

## Task Protocol

For a non-trivial persistent Task:

1. Confirm CURRENT and the Task goal.
2. Preserve unrelated or pre-existing changes.
3. Inspect only the source/context needed for the work.
4. Make the smallest coherent implementation slice.
5. Run the smallest sufficient validation.
6. Record actual evidence, limitations, blockers, and next action in the Task.
7. Complete the documentation transaction before reporting completion.

Do not update Task docs after every file read or trivial observation.

## Completion Transaction

A Task is complete only when its completion criteria have evidence.

Then, as one logical transaction:

1. Set the Task to `completed` and record concise evidence.
2. Update a stable Plan/ADR/spec only when a durable outcome changed.
3. Rewrite [HANDOFF.md](HANDOFF.md) as the fresh current snapshot.
4. Select the next executable Task if one already exists in scope and has no decision gate.
5. Rewrite [CURRENT.md](CURRENT.md) to that Task, a decision-required state, or `idle`.
6. Re-check cross-file consistency.

Do not auto-expand scope merely because a new idea was discovered.

## Promotion Boundaries

Promote information only when it becomes durable:

- stable architecture or project plan → [docs/project/](../docs/project/)
- user-facing behavior → [docs/en/](../docs/en/) and [docs/ko/](../docs/ko/)
- operator-visible change → [CHANGELOG.md](../CHANGELOG.md)
- release/update metadata → [docs/project/update-info.md](../docs/project/update-info.md)
- cross-project reusable workflow or long-term environment knowledge → LLM-WIKI, when it is not just volatile repository state

## Compatibility

This repository predates lifecycle schema v1 and contains valuable historical Task/handoff documents. Preserve them unless a concrete migration benefit justifies change.

`AGENTS.md` and `agent-work/` are currently excluded by `.git/info/exclude`. They are local operating state, so normal `git status`/`git diff` will not report changes here. Do not force-add or alter that exclusion unless the user explicitly asks to track these documents.

Do not:

- rename old Tasks only to match a template
- turn old handoff files into startup context
- copy completed history into CURRENT/HANDOFF/AGENTS
- treat LLM-WIKI as a replacement for actual repository/source/runtime truth
