---
name: analyze-phase-2.5-reviewer-plan
description: "Invoke when building the reviewer execution plan (methodology × path partition) for parallel Phase 3 dispatch."
purpose: Analyze Phase 2.5 — build a reviewer execution plan so Phase 3 can dispatch reviewer sub-agents in parallel across methodology × path-partition; mandatory when SUB_AGENT_SESSION_APPROVED=true.
loaded_by: workflows/analyze.md
version: 1.0
---

# Phase 2.5: Reviewer Plan

<!-- toc -->

- [State](#state)
- [Applicability](#applicability)
- [Storage Choice](#storage-choice)
- [Planner Dispatch](#planner-dispatch)
- [Disk Mode Rendering](#disk-mode-rendering)
- [Handoff](#handoff)

<!-- /toc -->

## State

This phase runs after Phase 2 (Deterministic Gate) and before Phase 3
(Semantic Review). It decomposes the analyze task into reviewer sub-agent
tasks partitioned by methodology and path so Phase 3 can dispatch them in
parallel.

Set `PLANNER_RETRY_COUNT = 0` on entry to this phase.

Set `REVIEWER_PLAN_RESOLVED` to exactly one of:

- `memory`
- `disk`
- `cancelled_partial_cache`
- `auto_skipped_inline_fallback`
- `auto_skipped_no_methodology`
- `auto_skipped_explain_mode`

Set `REVIEWER_EXECUTION_PLAN` to the parsed `reviewer_plan` JSON when
`REVIEWER_PLAN_RESOLVED` is `memory` or `disk`; otherwise set it to `null`.
Set `REVIEWER_PLAN_CACHE_DIR` only when disk-mode cache rendering completes
successfully.

## Applicability

Auto-skip this phase (set `REVIEWER_PLAN_RESOLVED=auto_skipped_*`,
`REVIEWER_EXECUTION_PLAN=null`) when any of these conditions holds:

- `INLINE_FALLBACK=true` — no native sub-agent dispatch is available, so
  partitioning across reviewers offers no parallelism win; Phase 3 uses its
  non-planned per-methodology dispatch path.
- `EXPLAIN_MODE=true` — storytelling phases replace Phase 3 entirely.
- No semantic methodology flag is active (gate is `PASS` and no flag set).

Otherwise this phase is mandatory and `REVIEWER_PLAN_RESOLVED` MUST end up
`memory`, `disk`, or the terminal recovery state `cancelled_partial_cache`.

## Storage Choice

Ask the user:

Why this input is needed: the storage mode determines whether the reviewer plan persists through context compaction; a memory plan is lost if compaction occurs before Phase 3 completes.

```text
Reviewer plan (mandatory — sub-agents approved): pick storage.

I will partition this analyze run into reviewer sub-tasks (by methodology
and path) so they can run in parallel in Phase 3.

Reply `enter` or `memory` for in-memory plan (default), or `disk` to also
save a Markdown plan pack under
`{cf-studio-path}/.cache/analyze-plans/`.

Choose disk to inspect the plan as Markdown files and resume the analysis in a new chat using the saved plan; memory keeps it in-context only (NOT resumable after context compaction).
```

Reply parsing:

| User input | Meaning |
|---|---|
| empty / `enter` / `memory` / `1` | Set `REVIEWER_PLAN_RESOLVED=memory`; run Planner Dispatch. Note: a memory plan is NOT recoverable if the context is compacted before Phase 3 completes — choose disk if the session may be long or context-heavy. |
| `disk` / `save` / `2` | Set `REVIEWER_PLAN_RESOLVED=disk`; run Planner Dispatch + Disk Mode Rendering |
| stop token | Open and follow `workflows/shared/stop-token-policy.md`; cancel without proceeding |
| `no` / `skip` / `3` | Reject with `Decomposition is mandatory while sub-agents are approved. Reply enter/memory or disk.` and ask again |
| anything else | Reject with `Reply not recognized. Expected enter/memory or disk.` and ask again |

Choosing `disk` is approval to write only the plan cache files described in
Disk Mode Rendering. It is NOT approval to run any reviewer or write any
artifact.

## Planner Dispatch

Requires: `workflows/shared/inline-fallback-probe.md` before any
`cf-*` sub-agent dispatch. Pre-dispatch fail-stop and Mode B
degradation rules are defined in
`{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`.

Dispatch read-only sub-agent `cf-analyze-planner` with the JSON
contract documented in
`{cf-studio-path}/.core/skills/studio/agents/cf-analyze-planner.md`.
Orchestrator-supplied values:

- `plan_mode` = `"memory"` or `"disk"` from the user's reply
- `target_type`, `mode`, `kind`, `rules_mode`, `system`
- `kit_rules_path`, `checklist_path`, `template_path`, `example_path`,
  `design_artifact_path`
- `target_paths` = the resolved analyze target set
- `code_targets` = Phase 0 typed code targets from `diff_scope.changed_files`
  when `CHANGE_REVIEW=true`, else `target_paths` filtered to code paths
- `prompt_targets` = Phase 0 typed prompt targets from
  `diff_scope.changed_files` when `CHANGE_REVIEW=true`, else `target_paths`
  filtered to prompt/workflow/instruction paths
- `cross_refs` = related cross-reference paths
- `diff_scope` = Phase 0 diff scope or `null`
- `methodology_flags` = current values of `PROMPT_REVIEW`,
  `PROMPT_BUG_REVIEW`, `CODE_BUG_REVIEW`, `CONSISTENCY_REVIEW`,
  `ARTIFACT_REVIEW`, `CODE_REVIEW`
- `available_reviewers` = the reviewer sub-agents registered in
  `workflows/analyze/phase-3-semantic.md`
- `size_estimate_lines` = the Phase 0.1 estimate

Parse the marker `<!-- reviewer_plan -->` and the following JSON block.

Field names per {cf-studio-path}/.core/skills/studio/agents/cf-analyze-planner.md § Output schema.

Validate:

- every active methodology has at least one task
- the union of `path_partition` for each methodology covers every applicable
  input path
- partitions for the same methodology are disjoint
- every `reviewer` matches its task's `methodology`
- every `parallel_groups[].task_ids` entry names an existing task
- every `parallel_groups[].depends_on` reference names an earlier group

If validation fails, fail-stop and ask the user whether to rerun the planner
or stop with the validation errors. Do not clear the plan into a fallback path
after sub-agent decomposition was selected. Do not set
`REVIEWER_PLAN_RESOLVED=auto_skipped_inline_fallback` after planner dispatch
has already failed validation.

If the planner returns `checkpoint.type=PARTIAL_CHECKPOINT`, treat as
planner-validation failure: ask the user whether to rerun the planner or stop
with the validation errors. Do not set
`REVIEWER_PLAN_RESOLVED=auto_skipped_inline_fallback` after planner dispatch
has already failed or returned partial coverage.

**Planner retry cap** — `PLANNER_RETRY_MAX = 2`:

- Increment `PLANNER_RETRY_COUNT` (starts at `0`) each time the user chooses
  rerun after a validation failure or `PARTIAL_CHECKPOINT` return.
- When `PLANNER_RETRY_COUNT >= PLANNER_RETRY_MAX`, do NOT offer rerun again.
  Fail-stop with:
  ```
  Planner returned PARTIAL_CHECKPOINT twice in this run — manual intervention required. Stopping.
  ```
  Then route the user to Storage Choice to select `disk` for offline inspection,
  or suggest switching to `/cf-plan` for manual decomposition.

## Disk Mode Rendering

When `REVIEWER_PLAN_RESOLVED=disk`, render the validated
`REVIEWER_EXECUTION_PLAN` to:

Only when `REVIEWER_PLAN_RESOLVED=disk`: set `CF_PHASE_GATE=released_for_orchestrator_write` with scope `{cf-studio-path}/.cache/analyze-plans/{slug}-{ISO}/**` immediately before writing these cache files.

```text
{cf-studio-path}/.cache/analyze-plans/{slug}-{ISO}/index.md
{cf-studio-path}/.cache/analyze-plans/{slug}-{ISO}/plan.json
{cf-studio-path}/.cache/analyze-plans/{slug}-{ISO}/reviewers/{reviewer}.md
{cf-studio-path}/.cache/analyze-plans/{slug}-{ISO}/tasks/{task_id}.md
```

`index.md` summarises the partitioning and lists the parallel groups in
execution order. `plan.json` is the exact parsed `REVIEWER_EXECUTION_PLAN`.
Each `reviewers/{reviewer}.md` file lists the tasks assigned to that
reviewer. Each task file contains task title, methodology, reviewer,
`path_partition`, namespace prefix, parallel group, dependencies, rationale,
and acceptance criteria.

After writing cache files, set `REVIEWER_PLAN_CACHE_DIR` to the directory
path and emit:

```text
Reviewer plan saved: {REVIEWER_PLAN_CACHE_DIR}
```

Reset CF_PHASE_GATE=armed immediately after the named writes complete or fail.

If any cache file write fails: emit a structured error block listing files that
were written and files that failed. Do not silently proceed with a partial
cache. Offer:

```text
Partial cache write failure. Some reviewer-plan cache files could not be written.

Written: {list of successfully written files, one per line, or "none"}
Failed:  {list of files that failed with error reason, one per line}

How do you want to proceed?

| Option | Action |
|---|---|
| 1 | Retry disk mode — re-attempt the failed writes |
| 2 | Continue in memory mode — discard the partial cache files and proceed with `REVIEWER_EXECUTION_PLAN` in-context |
| 3 | Cancel reviewer-plan caching and stop before Phase 3 (`REVIEWER_PLAN_RESOLVED=cancelled_partial_cache`) |

Suggested: 1

Reply `1`, `2`, or `3`.
```

On `1`: re-attempt only the failed writes; do not re-write already successful
files. If the retry still fails, re-emit the menu.

On `2`: set `REVIEWER_PLAN_RESOLVED=memory`, discard any partially written
cache files, clear `REVIEWER_PLAN_CACHE_DIR`, and proceed to Phase 3 with
`REVIEWER_EXECUTION_PLAN` in-context.

On `3`: set `REVIEWER_PLAN_RESOLVED=cancelled_partial_cache`, set
`REVIEWER_PLAN_CACHE_DIR=null`, reset `CF_PHASE_GATE=armed`, and stop the
current analyze sub-flow without entering Phase 3.

A stop token at this recovery prompt is equivalent to option `3`.

## Handoff

After `REVIEWER_PLAN_RESOLVED` is set, proceed to
`workflows/analyze/phase-3-semantic.md`.

Phase 3 MUST NOT run while `REVIEWER_PLAN_RESOLVED` is unset. If a later
phase sees it unset, fail-stop and route back to this file's Storage Choice.
If `REVIEWER_PLAN_RESOLVED=cancelled_partial_cache`, stop the current analyze
sub-flow and do not dispatch any semantic reviewers.
