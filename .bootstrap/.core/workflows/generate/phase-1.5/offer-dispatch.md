---
cf: true
type: workflow-fragment
parent: workflows/generate/phase-1.5-author-plan.md
description: Mandatory/optional author-plan offer plus planner dispatch and validation for Generate Phase 1.5.
---

<!-- toc -->

- [Offer](#offer)
- [Planner Dispatch](#planner-dispatch)

<!-- /toc -->

## Offer

When `SUB_AGENT_SESSION_APPROVED=true` AND `INLINE_FALLBACK=false` AND no
auto-skip condition applies, use this **mandatory storage-choice offer**:

```text
Author plan (mandatory — sub-agents approved): pick storage.

I will decompose this generate task into author-worker sub-tasks, assign each
to a specialist sub-agent, and group them for parallel dispatch in Phase 4.

Reply `enter` or `memory` for in-memory plan (default), or `disk` to also save
a Markdown plan pack under `{cf-studio-path}/.cache/generate-plans/`.

Choose `disk` if the session may be long or context may compact (plan survives compaction); choose `memory` for short sessions (no disk I/O, plan is in-context only).
```

Reply parsing in the mandatory branch:

| User input | Meaning |
|---|---|
| empty / `memory` / `1` | Set `AUTHOR_PLAN_OFFER_RESOLVED=memory`; run Planner Dispatch |
| `disk` / `save` / `2` | Set `AUTHOR_PLAN_OFFER_RESOLVED=disk`; run Planner Dispatch, then open and follow `workflows/generate/phase-1.5/disk-mode.md` |
| stop token | Set `AUTHOR_PLAN_OFFER_RESOLVED=cancelled_by_stop_token`; reset `CF_PHASE_GATE=armed`; open and follow `workflows/shared/stop-token-policy.md`; stop the current generate sub-flow without entering Phase 3 or Phase 4 |
| `no` / `skip` / `3` | Reject with `Decomposition is mandatory while sub-agents are approved. Reply enter/memory or disk.` and ask again |
| anything else | Reject with `Reply not recognized. Expected enter/memory or disk.` and ask again |

When the mandatory branch is not active and no auto-skip condition resolved the
state already, ask:

```text
Want a lightweight author plan before the final summary?

I can decompose this generate task into author-worker tasks, recommend which
author should handle each task, and mark which tasks can run in parallel.

Suggested: `memory` (or `enter`) for short sessions; `disk` for sessions that may be long or context-heavy.

Reply `enter` or `memory` for an in-memory plan (default), `disk` to also save
a Markdown plan pack under `{cf-studio-path}/.cache/generate-plans/`, or
`no` to skip the author plan.
```

Reply parsing in the optional branch:

| User input | Meaning |
|---|---|
| empty / `memory` / `1` | Set `AUTHOR_PLAN_OFFER_RESOLVED=memory`; run Planner Dispatch |
| `disk` / `save` / `2` | Set `AUTHOR_PLAN_OFFER_RESOLVED=disk`; run Planner Dispatch, then open and follow `workflows/generate/phase-1.5/disk-mode.md` |
| `no` / `skip` / `3` | Set `AUTHOR_PLAN_OFFER_RESOLVED=declined`; set `AUTHOR_EXECUTION_PLAN=null`; proceed to Phase 3 |
| stop token | Set `AUTHOR_PLAN_OFFER_RESOLVED=cancelled_by_stop_token`; reset `CF_PHASE_GATE=armed`; open and follow `workflows/shared/stop-token-policy.md`; stop the current generate sub-flow without entering Phase 3 or Phase 4 |
| anything else | Reject with `Reply not recognized. Expected enter/memory, disk, or no.` and ask again |

Choosing `disk` approves only the plan-cache files described in
`workflows/generate/phase-1.5/disk-mode.md`. It is not approval to write the
target artifact/code files; Phase 3 `yes` is still required before Phase 4.

## Planner Dispatch

Requires: `workflows/shared/inline-fallback-probe.md` before any
`cf-*` sub-agent dispatch. Pre-dispatch fail-stop and Mode B
degradation rules are defined in
`{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`.

Dispatch read-only sub-agent `cf-generate-planner` with the JSON
contract documented in
`{cf-studio-path}/.core/skills/studio/agents/cf-generate-planner.md`.
Orchestrator-supplied values:

- `plan_mode` = `"memory"` or `"disk"` from the user's reply
- `target_type`, `mode`, `kind`, `name`, `rules_mode`, `system`
- `template_path`, `example_path`, `kit_rules_path`, `checklist_path`
- `design_artifact_path` for code mode, otherwise `null`
- `target_paths` = the full list of paths expected to be written in Phase 4
- `inputs` = the approved Phase 1 `proposed_inputs` with user edits merged in
- `findings` = `[]` in create mode; Phase 5 fix loops do not use this offer gate
- `brainstorm_decisions` = Phase 0.7 decisions or `{}`
- `open_questions` = Phase 0.7 open questions or `[]`
- `available_authors` = the registered write-capable author worker agents from
  `workflows/generate/phase-4-write.md` § Author Selection and Dispatch

Parse the marker `<!-- author_plan -->` and the following JSON block. Validate:

- every task's `recommended_author` is one of the registered author worker agents
- every target path is covered by at least one task
- tasks in the same `parallel_group` have disjoint `target_paths`
- no parallel group contains more than one task with `updates_artifacts_toml=true`
- every `parallel_groups[].task_ids` entry names an existing task

If validation fails, emit:

```text
Planner validation failed: {reason}.

| Option | Action |
|---|---|
| 1 | Rerun planner — try decomposition again with the same inputs |
| 2 | Skip author plan — proceed to Phase 3 with AUTHOR_PLAN_OFFER_RESOLVED=declined |
| 3 | Cancel — stop the generate workflow now (AUTHOR_PLAN_OFFER_RESOLVED=cancelled_planner_failure) |

Suggested: 1 because most validation failures are transient (incomplete plan, missing field) and a rerun resolves them.

Reply `1`, `2`, or `3`.
```

On `1`: re-dispatch `cf-generate-planner` with the same inputs and
re-validate the returned plan.

On `2`: set `AUTHOR_PLAN_OFFER_RESOLVED=declined`,
`AUTHOR_EXECUTION_PLAN=null`, and proceed to Phase 3. This recovery path is the
only valid `declined` exit in the mandatory-decompose branch.

On `3`: set `AUTHOR_PLAN_OFFER_RESOLVED=cancelled_planner_failure`,
`AUTHOR_EXECUTION_PLAN=null`, reset `CF_PHASE_GATE=armed`, and stop the current
generate sub-flow without entering Phase 3 or Phase 4.

A stop token at the planner-validation recovery prompt is equivalent to
option `3`: set `AUTHOR_PLAN_OFFER_RESOLVED=cancelled_planner_failure`, keep
`AUTHOR_EXECUTION_PLAN=null`, and stop without entering Phase 3 or Phase 4.
