# Multi-Agent Task Workflow Operator Guide

This guide describes the current Phase 3 end-to-end operating model for splitting a large request into task-scoped worktrees, running workers in parallel, inspecting their outputs, and integrating approved work back into the source project through the local review flow.

The workflow is intentionally review-gated. Task worktrees isolate worker changes, but source-project integration still happens only through an approved pending command bundle.

## Current Scope

Implemented:

- Task-scoped metadata using `task_id`, `project_id`, and `workspace_mode="task-workspace"`.
- Runtime task workspace records.
- Explicit git worktree creation under the runtime directory.
- Approved `task-workspace` bundle routing into the ready worktree.
- Read-only worktree inspection.
- Read-only merge preflight.
- Merge queue record storage.
- Approved source integration staging through `workspace_propose_task_worktree_merge_and_wait`.
- Non-destructive archive helpers for task workspace and merge queue records.
- Read-only orchestrator summary through `workspace_task_orchestration_summary`.

Not implemented:

- Automatic task splitting.
- Automatic worker session creation.
- Automatic source merge without local review.
- Automatic post-merge tests or commits.
- Physical deletion of task worktree directories.
- A full interactive merge queue UI with conflict resolution.

## Roles

Use one orchestrator session and one or more worker sessions.

- Orchestrator: decomposes work, assigns stable `task_id` values, creates task worktrees, inspects results, runs merge preflight, queues merges, proposes approved source integration, and archives records.
- Worker: works only on one `task_id` and uses proposal tools with `workspace_mode="task-workspace"` so approved bundles apply in that task worktree.
- Local operator: reviews `/pending` proposals and approves only focused, expected changes.

## Naming Rules

Use stable and explicit identifiers.

- `task_id`: short, filesystem-safe task identifier, for example `phase3j-doc-guide` or `fix-runner-path-map`.
- `project_id`: stable project identifier shared by orchestrator and worker sessions.
- `cwd`: source repository path relative to `WORKSPACE_ROOT`, for example `.` or `my-terminal-tool`.
- `workspace_mode`: `task-workspace` for worker changes that must apply inside a task worktree. Use `direct` for source integration proposals and ordinary single-user workflows.

Do not reuse the same `task_id` for unrelated work. A task workspace key is derived from `task_id`, `project_id`, and `source_cwd`.

## End-to-End Runbook

### 1. Orchestrator Decomposes The Work

Create a short task list before starting workers.

For each task, record:

- `task_id`
- goal
- source `cwd`
- expected files or modules
- test target
- conflict risk with other tasks
- worker prompt

Prefer independent tasks. Avoid assigning two workers the same files unless the conflict is deliberate and the orchestrator plans to resolve it manually.

### 2. Orchestrator Creates A Task Workspace

For each task:

1. Call `workspace_create_task_worktree(task_id, cwd, project_id)`.
2. Confirm the result has `status="worktree"` and `worktree_status="ready"`.
3. Send the worker the `task_id`, `cwd`, `project_id`, and exact constraints.

`workspace_prepare_task_workspace` can create bookkeeping records, but worker apply routing requires a ready git worktree. Prefer `workspace_create_task_worktree` for operational task starts.

### 3. Worker Session Prompt Template

Use this template when opening a worker session:

```text
You are working in the same project through Workspace Bridge.

Task:
- task_id: <TASK_ID>
- project_id: <PROJECT_ID>
- source cwd: <CWD>
- workspace_mode: task-workspace

Goal:
<ONE TASK GOAL>

Scope:
- Work only on this task.
- Do not merge changes back into the source project.
- Do not use direct-mode proposal tools for task changes.
- Use proposal wrappers with metadata:
  task_id=<TASK_ID>
  project_id=<PROJECT_ID>
  workspace_mode=task-workspace
- Keep changes focused.
- Run only relevant tests.
- Report changed files, verification, and remaining risk.

Use these public proposal wrappers as appropriate:
- workspace_propose_command_and_wait
- workspace_propose_file_write_and_wait
- workspace_propose_file_replace_and_wait
- workspace_propose_patch_and_wait

Do not call merge queue or archive tools. The orchestrator owns inspect, preflight, enqueue, source merge proposal, and archive.
```

If the worker needs to make a git commit or push, stop and return control to the orchestrator. The current operating model expects source integration to be handled centrally.

### 4. Worker Makes Task-Scoped Changes

The worker proposes changes with:

- `workspace_mode="task-workspace"`
- the assigned `task_id`
- the shared `project_id`
- the source `cwd`

After local `/pending` approval, the runner applies that bundle in the task worktree. The source bundle record keeps the source `cwd`, while the runner result includes `workspace_routing` metadata that shows the actual worktree apply cwd.

Workers should verify in the task worktree through task-scoped command proposals. The orchestrator should not assume a worker's chat summary is sufficient; it should inspect the worktree.

### 5. Orchestrator Inspects A Finished Task

When the worker reports completion:

1. Call `workspace_task_orchestration_summary(project_id)` to see all task workspace and merge queue records for the project.
2. Call `workspace_inspect_task_worktree(task_id, cwd, project_id)` for the finished task.
3. Review `dirty`, `changed_file_count`, `git_status_short`, `diff_stat`, and `changed_files`.
4. If `dirty=false`, archive or reassign the task. There is nothing to merge.
5. If the changed files are unexpected, ask the worker to explain or revise before preflight.

Inspection is read-only and does not modify the source project.

### 6. Orchestrator Runs Merge Preflight

Call `workspace_merge_preflight_task_worktree(task_id, cwd, project_id)`.

Use these fields:

- `ready_to_merge`: whether the task is eligible for merge queue.
- `conflict_risk`: `low`, `medium`, or `high`.
- `recommended_action`: next operational step.
- `source_head_changed`: whether source `HEAD` moved since the task worktree was created.
- `source_dirty`: whether the source workspace has local changes.
- `overlapping_files`: files changed by both source and task worktree.

If `source_dirty=true`, clean the source workspace first. If `overlapping_files` is non-empty, do manual conflict review before enqueueing.

### 7. Orchestrator Enqueues A Merge

If preflight says the task is ready:

1. Call `workspace_enqueue_task_worktree_merge(task_id, cwd, project_id)`.
2. Confirm queue `status="queued"` and review `changed_files`, `conflict_risk`, and `source_head_sha`.
3. Optionally call `workspace_merge_queue_status(task_id, cwd, project_id)`, `workspace_list_merge_queue(project_id)`, or `workspace_task_orchestration_summary(project_id)`.

Queue records are bookkeeping. Enqueueing does not apply changes to the source project.

### 8. Orchestrator Stages Source Integration For Approval

Call `workspace_propose_task_worktree_merge_and_wait(task_id, cwd, project_id)`.

This creates a pending command bundle. It does not run inside ChatGPT. The local operator must review and approve it in `/pending`.

On approved execution, the command validates:

- queue entry is `queued`
- source `HEAD` still matches the queued `source_head_sha`
- source workspace is clean
- task worktree path is valid and under runtime task workspaces
- task worktree has a diff
- `git apply --check` passes before applying

After success, the queue record transitions to `merged`. The source project now has working-tree changes from the task worktree; run source-level tests and decide whether to create a source commit through the normal review-gated workflow.

### 9. Orchestrator Archives Runtime Records

After a task is merged, abandoned, or superseded:

1. Call `workspace_archive_merge_queue_entry(task_id, cwd, project_id, reason=...)` if a queue record exists.
2. Call `workspace_archive_task_workspace(task_id, cwd, project_id, reason=...)`.

Archive is non-destructive. It updates runtime records to `status="archived"` and preserves record files and worktree directories. It does not delete source files or remove worktrees.

## Parallel Session Operating Rules

Use these rules when multiple chat sessions or multiple webapps are active:

- One orchestrator owns task assignment and merge order.
- Every worker gets exactly one `task_id`.
- Workers must use `workspace_mode="task-workspace"` for task changes.
- Workers do not enqueue, merge, archive, commit, or push.
- The source workspace should stay clean while workers are active.
- Do not approve broad direct-mode file edits while task worktrees are being prepared for merge.
- Before enqueueing any task, run merge preflight against the current source `HEAD`.
- Re-run preflight if source `HEAD` changes after inspection or enqueue.
- Merge one task at a time unless the source changes are proven independent.
- Keep `/pending` review items focused; do not combine task merge, tests, commits, and pushes in one approval.
- Use metadata filters or task ids when reviewing pending/history lists to avoid approving the wrong task.

## Orchestrator Summary View

Use `workspace_task_orchestration_summary(project_id)` as the first dashboard-style check during orchestration.

Each entry connects task workspace and merge queue records by `project_id`, `source_cwd`, and `task_id`. It includes:

- task workspace status, worktree status, branch, and path
- merge queue status, conflict risk, and recommended action
- changed file count when a queue record captured it
- archived state across task workspace or queue records
- anomaly flags, including queue records whose task workspace record is missing

The summary is read-only. It does not inspect git diffs live, run preflight, enqueue merges, archive records, or apply source changes. Use detailed tools when an entry needs action.

## Recovery And Troubleshooting

Use this checklist before retrying.

### Worker Changes Applied To Source Unexpectedly

- Inspect the bundle metadata and runner result.
- If `workspace_mode` was `direct`, the worker used the wrong mode.
- If `workspace_mode` was `task-workspace`, check `result.workspace_routing.actual_cwd`.
- Stop the worker and reassign with the prompt template.

### Task Workspace Missing Or Not Ready

- Call `workspace_task_workspace_status(task_id, cwd, project_id)`.
- If `status` is `missing` or `created`, call `workspace_create_task_worktree`.
- If archived, use a new `task_id` or intentionally recreate the workflow.

### Worker Has No Changes

- Call `workspace_inspect_task_worktree`.
- If `dirty=false`, ask the worker whether the task was already complete or whether proposals were never approved.
- Check `/pending`, applied bundle history, and `workspace_routing`.

### Preflight Refuses Merge

- If `source_dirty=true`, clean or commit/stash source changes.
- If `overlapping_files` is non-empty, inspect both source and task changes manually.
- If `source_head_changed=true` with medium risk, decide whether to enqueue anyway or rebase/recreate the task worktree in a later workflow.
- If `recommended_action="no_changes"`, archive or reassign the task.

### Queue Status Is Not Queued

- Call `workspace_merge_queue_status`.
- If `missing`, rerun preflight then enqueue.
- If `merged`, do not apply again.
- If `archived`, use a new task or explicitly restart the workflow.

### Approved Merge Proposal Fails

- Read the failed bundle result.
- Common causes: source `HEAD` changed, source workspace dirty, task diff disappeared, or `git apply --check` failed.
- Rerun inspect and preflight.
- If source changed, enqueue a fresh queue record after resolving the condition.

### Runtime Records Need Cleanup

- Use archive helpers first.
- Do not manually delete runtime records while sessions are active.
- Physical worktree removal is not part of the current public workflow.

## Operator Checklist

Before worker starts:

- Source workspace is clean.
- Task has unique `task_id`.
- Orchestrator created a ready worktree.
- Worker prompt includes `workspace_mode=task-workspace`.

Before merge queue:

- Worker reports done.
- Inspect shows expected changed files.
- Preflight says `ready_to_merge=true`.
- Source workspace is clean.

Before approving source integration:

- Pending item title matches the task.
- Queue entry is `queued`.
- Diff and changed files are expected.
- You are ready for source working-tree changes.

After approved source integration:

- Queue status is `merged`.
- Source tests have been proposed and approved or run locally.
- Source commit is created through normal review-gated flow if desired.
- Queue and task workspace records are archived with a useful reason.

## Phase Map

- Phase 3-A: task-workspace metadata mode.
- Phase 3-B: runtime task workspace record foundation.
- Phase 3-C: explicit git worktree creation.
- Phase 3-D: approved task-workspace bundle routing to ready worktrees.
- Phase 3-E: read-only task worktree inspection.
- Phase 3-F: read-only merge preflight and conflict risk inspection.
- Phase 3-G: merge queue records.
- Phase 3-H: locally approved source integration staging.
- Phase 3-I: non-destructive archive helpers.
- Phase 3-J: this end-to-end multi-session workflow and operator guide.
- Phase 3-K: read-only orchestrator dashboard summary across task workspace and merge queue records.

Remaining future work includes automatic task decomposition, richer interactive merge queue UI, explicit conflict resolution workflow, post-merge test/result tracking, commit flow integration, and physical worktree cleanup.
