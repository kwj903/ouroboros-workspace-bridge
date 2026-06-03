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
- Compact read-only task orchestration summary rendering in the `/pending` review UI.
- Conflict handling dashboard indicators and operator runbook for high-risk task worktree merges.
- Post-merge validation metadata recording through `workspace_record_task_validation` and `workspace_task_validation_status`.
- Source-level validation command proposal staging through `workspace_propose_task_validation_command_and_wait`.
- Read-only validation command result hints through `workspace_task_validation_result_hint`.
- Read-only physical cleanup candidate preview through `workspace_task_cleanup_preview`.
- Locally approved task worktree cleanup proposal and execution through `workspace_propose_task_cleanup_and_wait`.
- Cleanup readiness, risk, blockers, validation, queue, and workspace status badges in the `/pending` task orchestration dashboard.
- Validation result hint badges in the `/pending` task orchestration dashboard.

Not implemented:

- Automatic task splitting.
- Automatic worker session creation.
- Automatic source merge without local review.
- Automatic post-merge test execution or commits.
- Automatic `validation_status` updates after validation command execution.
- Automatic task worktree cleanup without local review.
- Manual runtime directory deletion outside the recorded cleanup path.
- A full interactive merge queue UI with conflict resolution.
- A dashboard button that directly creates cleanup proposals.
- A dashboard button that records validation status.

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

### 9. Orchestrator Stages Source-Level Validation For Approval

After the source integration proposal is approved and applied, stage the relevant source-level validation command from the orchestrator:

```text
workspace_propose_task_validation_command_and_wait(task_id, argv, cwd, project_id)
```

This creates a pending command bundle in `/pending`. It does not run in ChatGPT. The local operator must review and approve it before the command runs.

The tool checks that the merge queue record exists and has `status="merged"`. The command runs in the source project `cwd` with `workspace_mode="direct"` metadata. If the source project is dirty, the proposal metadata marks `source_dirty=true`, `validation_risk="high"`, and `validation_blockers=["source_dirty"]` so the operator can treat the validation as high risk. This phase does not automatically interpret stdout/stderr or record `validation_status`.

### 10. Orchestrator Records Post-Merge Validation

After the validation command has run, ask for a read-only result hint:

```text
workspace_task_validation_result_hint(task_id, cwd, project_id)
```

You can also pass `bundle_id` directly when you already know the validation command bundle id:

```text
workspace_task_validation_result_hint(bundle_id="cmd-...")
```

The hint summarizes the linked command bundle, including command argv, exit code, stdout/stderr previews, a conservative `inferred_status` candidate, and suggested `workspace_record_task_validation(...)` input values. `exit_code=0` is only a `passed` candidate, non-zero exit code is only a `failed` candidate, and pending or missing results remain `unknown`. The hint is read-only; it does not run commands, edit source files, update merge queue records, or set validation metadata.

Review the hint and record the human-reviewed outcome. This phase records what the operator observed; it does not rerun commands automatically.

Use `workspace_record_task_validation(task_id, cwd, project_id, validation_status, validation_commands, validation_summary, validated_by, client_id, session_id)` to update the merge queue record.

Recommended statuses:

- `unknown`: no validation has been recorded yet.
- `pending`: validation is planned or running outside the tool.
- `passed`: validation completed successfully.
- `failed`: validation completed and found a problem.

Use `workspace_task_validation_status(task_id, cwd, project_id)` to read the latest validation metadata. Recording validation only updates runtime metadata; it does not run commands, edit source files, apply patches, archive records, or create commits.

The `/pending` task orchestration dashboard also shows a compact read-only validation hint for each task when available:

- recorded `validation_status`
- latest validation command bundle id
- conservative inferred status candidate
- recommended next action
- whether a suggested manual record input is available

Use the dashboard as a guide only. The guided flow is: approve/run the validation command, inspect `workspace_task_validation_result_hint(...)`, call `workspace_record_task_validation(...)` manually with the operator-reviewed outcome, then refresh `/pending` to confirm the recorded validation status. The dashboard does not record validation status and does not run validation commands.

### 11. Orchestrator Archives Runtime Records

After a task is merged, abandoned, or superseded:

1. Call `workspace_archive_merge_queue_entry(task_id, cwd, project_id, reason=...)` if a queue record exists.
2. Call `workspace_archive_task_workspace(task_id, cwd, project_id, reason=...)`.

Archive is non-destructive. It updates runtime records to `status="archived"` and preserves record files and worktree directories. It does not delete source files or remove worktrees.

### 12. Orchestrator Previews Physical Cleanup Candidates

Use `workspace_task_cleanup_preview(project_id)` after source integration, validation recording, and archive steps to find runtime task worktrees that may be safe candidates for an explicit cleanup proposal.

This preview is read-only. It does not delete directories, run `git worktree remove`, update runtime records, apply patches, or modify the source project.

A task is marked `cleanup_ready=true` only when the preview can conservatively verify all of these conditions:

- the task workspace record exists and is archived
- the merge queue record exists and is `merged` or `archived`
- validation status is `passed`
- the task workspace path is under the runtime task workspace root
- the task workspace path is a git worktree
- `git status --short` in the task worktree is clean

If any condition fails, the preview returns `cleanup_ready=false`, `cleanup_risk`, `cleanup_blockers`, and `recommended_action`. Treat `cleanup_ready=true` as a prerequisite for staging the approval-gated cleanup proposal, not as automatic cleanup.

The `/pending` task orchestration dashboard mirrors this preview with compact cleanup badges:

- `cleanup ready`
- `cleanup risk`
- `cleanup blockers`
- `cleanup action`
- `cleanup validation`
- `cleanup queue`
- `cleanup workspace`

When an entry shows `cleanup ready: yes`, `cleanup risk: low`, and `cleanup action: ready_for_physical_cleanup_review`, the next orchestrator call is:

```text
workspace_propose_task_cleanup_and_wait(task_id, cwd, project_id)
```

The dashboard does not create this proposal directly. The orchestrator must call the wrapper, and the local operator must approve the generated `/pending` item before `git worktree remove` runs.

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

The `/pending` review UI also renders this summary as a compact read-only section. It distinguishes workspace-only, queue-only, and joined workspace+queue entries, and highlights anomalies such as queue records whose task workspace record is missing.

Each entry connects task workspace and merge queue records by `project_id`, `source_cwd`, and `task_id`. It includes:

- task workspace status, worktree status, branch, and path
- merge queue status, conflict risk, and recommended action
- changed file count when a queue record captured it
- source dirty, source HEAD drift, overlapping file, and operator attention indicators when a queue record captured merge preflight fields
- post-merge validation status, commands, summary, timestamp, and operator metadata when recorded
- cleanup preview readiness, risk, blocker count/main blocker, recommended cleanup action, validation status, queue status, and workspace status when cleanup preview data is available
- archived state across task workspace or queue records
- anomaly flags, including queue records whose task workspace record is missing

The summary is read-only. It does not inspect git diffs live, run preflight, enqueue merges, archive records, or apply source changes. Use detailed tools when an entry needs action.

## Conflict Handling Runbook

Use this runbook when `workspace_merge_preflight_task_worktree`, `workspace_task_orchestration_summary`, or the `/pending` dashboard shows `conflict_risk="high"`, `attention: conflict review`, `source dirty`, `head drift`, `overlap: ...`, or an anomaly.

### Source Dirty

`source_dirty=true` means the source repository has local working-tree changes. Do not enqueue or approve task merge proposals while this is true.

1. Inspect the source workspace changes outside the task worktree.
2. Decide whether they should be committed, reverted, stashed, or turned into their own reviewed proposal.
3. Return the source workspace to the intended clean state.
4. Rerun `workspace_merge_preflight_task_worktree(task_id, cwd, project_id)`.
5. Enqueue only if preflight reports `ready_to_merge=true`.

### Source HEAD Drift

`source_head_changed=true` means the source `HEAD` moved after the task worktree was created. This may still be mergeable, but it needs explicit review.

1. Review what changed in the source branch since the task worktree `base_sha`.
2. If changed files do not overlap and preflight recommends `merge_queue_with_source_head_check`, enqueue may be acceptable.
3. If the drift is broad, ask the worker to recreate or refresh the task worktree in a later workflow.
4. Re-run preflight immediately before enqueueing because the approved source merge command will reject stale queue records.

### Overlapping Files

`overlapping_files` means source changes and task worktree changes touched the same paths.

1. Treat the task as high risk.
2. Inspect the task diff with `workspace_inspect_task_worktree`.
3. Inspect the source changes for each overlapping path.
4. Do not use automatic merge/rebase/apply to resolve this in the current workflow.
5. Ask the worker to revise the task, or manually create a new task that incorporates the current source state.
6. Rerun preflight after the worker revision.

### Queue And Task Record Mismatch

Queue-only entries or `missing_task_workspace_record` anomalies mean runtime bookkeeping is inconsistent.

1. Call `workspace_task_workspace_status(task_id, cwd, project_id)`.
2. Call `workspace_merge_queue_status(task_id, cwd, project_id)`.
3. If the task workspace was archived or removed intentionally, archive the stale queue entry with a clear reason.
4. If the queue record is stale, rerun inspect and preflight before creating a fresh queue record.
5. Do not approve source integration for queue-only anomalies.

### Requeue After Preflight Failure

When preflight fails, do not reuse old assumptions.

1. Resolve the cause shown by `recommended_action`.
2. Rerun `workspace_inspect_task_worktree`.
3. Rerun `workspace_merge_preflight_task_worktree`.
4. If a stale queue record exists, archive it first.
5. Call `workspace_enqueue_task_worktree_merge` only after the latest preflight is ready.
6. Create a fresh approved merge proposal with `workspace_propose_task_worktree_merge_and_wait`.

### Worker Rework Request

When a worker needs to revise a task:

1. Keep the same `task_id` only if the task worktree remains valid and the scope is unchanged.
2. Give the worker the exact conflict signal: source dirty, head drift, overlapping files, missing task record, or stale queue.
3. Tell the worker not to enqueue, archive, merge, commit, or push.
4. Require the worker to continue using `workspace_mode="task-workspace"`.
5. After the worker reports completion, restart the orchestrator flow at inspect, then preflight, then enqueue.

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

### Post-Merge Validation Fails

- Record the failure with `workspace_record_task_validation(..., validation_status="failed", validation_commands=[...], validation_summary=...)`.
- Keep the queue and task workspace records unarchived until the operator decides whether to request worker rework, create a follow-up task, or revert manually.
- Do not record `passed` until the latest source-level validation has actually succeeded.
- If a worker needs to fix the failure, send the exact validation command and failure summary, and restart the orchestrator flow at inspect after the worker reports completion.

### Validation Command Proposal Fails Or Is Rejected

- Confirm the task's merge queue record is still `merged` with `workspace_merge_queue_status`.
- If the wrapper reports a missing or unmerged queue record, do not use a generic direct command proposal as a substitute; rerun the merge workflow checks first.
- If the proposal metadata includes `source_dirty=true`, approve only when the dirty source state is the expected post-merge state you intend to validate.
- After an approved command finishes, call `workspace_task_validation_result_hint(...)`, review the suggested status and stdout/stderr previews, then call `workspace_record_task_validation` manually.

### Runtime Records Need Cleanup

- Use archive helpers first.
- Preview cleanup candidates with `workspace_task_cleanup_preview(project_id)`.
- Only entries with `cleanup_ready=true` should be sent to `workspace_propose_task_cleanup_and_wait(task_id, cwd, project_id)`.
- Approve the generated `/pending` item only after confirming the task was merged, source validation passed, and the task workspace was archived.
- Do not manually edit runtime records while sessions are active.
- If cleanup proposal execution fails, inspect the bundle result, rerun `workspace_task_cleanup_preview`, and preserve the task worktree until blockers are understood.

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
- Source tests have been proposed with `workspace_propose_task_validation_command_and_wait` and approved, or run locally by the operator.
- Validation command output has been reviewed.
- Validation status is recorded as `passed` or `failed` on the merge queue record with `workspace_record_task_validation`.
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
- Phase 3-L: review UI rendering foundation for the task orchestration summary.
- Phase 3-M: conflict handling workflow foundation with dashboard indicators and operator runbook.
- Phase 3-N: post-merge validation tracking foundation on merge queue records and dashboard summaries.
- Phase 3-O1: read-only physical cleanup preview and candidate detection foundation.
- Phase 3-O2: locally approved task worktree cleanup proposal and execution foundation.
- Phase 3-O3: `/pending` cleanup readiness dashboard and operator UX guidance.
- Phase 3-P1: merged task source-level validation command proposal foundation.
- Phase 3-P2: read-only validation command result hint and guided recording foundation.
- Phase 3-P3: `/pending` validation result hint dashboard and guided recording UX foundation.

Remaining future work includes automatic task decomposition, richer interactive merge queue controls, automatic conflict resolution support, automatic validation status recording, automatic validation command execution, and commit flow integration.
