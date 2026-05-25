---
name: generate-phase-4-write
description: "Invoke when Phase 3 confirmation is received and the approved author payload must be dispatched to write or fix target files."
purpose: Generate Phase 4 — dispatch author(mode=create), persist manifest, echo Written block
loaded_by: workflows/generate.md
version: 1.0
---

## Phase 4: Write

<!-- toc -->

- [Phase 4: Write](#phase-4-write)
- [Author Selection and Dispatch](#author-selection-and-dispatch)
- [Planned Multi-Author Dispatch](#planned-multi-author-dispatch)
- [Phase 4 Create Payload](#phase-4-create-payload)
- [Escalation Handling](#escalation-handling)

<!-- /toc -->

Requires: `workflows/shared/inline-fallback-probe.md` before any `cf-*` sub-agent dispatch. Pre-dispatch fail-stop and Mode B degradation rules are defined in `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`.

Only after Phase 3 confirmation (`yes`), execute the author selection flow
below with a `mode=create` payload. Do not dispatch a write-capable author
directly from the orchestrator.

Prerequisite: `AUTHOR_PLAN_OFFER_RESOLVED` MUST be set by
`workflows/generate/phase-1.5-author-plan.md`. If unset, fail-stop and route
back to `workflows/generate/phase-1.5-author-plan.md` so its state contract and
offer/dispatch modules can re-run.

Only the continuation states from
`workflows/generate/phase-1.5/state-contract.md` may enter Phase 4:
`memory`, `disk`, `declined`, `auto_skipped_no_author_plan_flag`, and
`auto_skipped_rules_disabled`.

If `AUTHOR_PLAN_OFFER_RESOLVED` is a terminal cancellation state
(`cancelled_by_stop_token`, `cancelled_planner_failure`,
`cancelled_partial_write`), fail-stop immediately: do NOT dispatch a
write-capable author, do NOT synthesize a single-author fallback payload, and
leave target files untouched.

## Author Selection and Dispatch

This block is the canonical write/fix dispatch path for Phase 4 and Phase 5.
It is intentionally two-step:

1. Dispatch read-only selector `cf-generate-author` with the full
   author payload.
2. Parse the returned `author_selection` JSON block.
3. Verify `selected_author` is exactly one of:
   - `cf-generate-author-junior`
   - `cf-generate-author-middle`
   - `cf-generate-author-senior`
   - `cf-generate-author-lead`
   - `cf-generate-coder-casual`
   - `cf-generate-coder-smart`
   - `cf-generate-prompt-engineer-casual`
   - `cf-generate-prompt-engineer-smart`
4. Keep CF_PHASE_GATE=armed while dispatching the selector. Set
   CF_PHASE_GATE=released_for_dispatch only immediately before dispatching the
   selected write-capable author.
   Dispatch that selected write-capable author with
   `author_selection.dispatch_payload`.
   Reset CF_PHASE_GATE=armed immediately on return — manifest, escalation,
   error, or no-response. The gate MUST NOT remain at released_for_dispatch
   across turns.
   When `INLINE_FALLBACK=true` and the orchestrator is executing the author/
   coder/migrator contract inline (in lieu of sub-agent dispatch), MUST set
   `CF_PHASE_GATE=released_for_inline_write` IMMEDIATELY before the inline
   write block (see SKILL.md § Phase-Skip Gate). MUST reset
   `CF_PHASE_GATE=armed` IMMEDIATELY after the inline write block
   completes — both on success AND on failure.

If the selector output is missing, malformed, names an unregistered author, or
changes the payload semantics, fail-stop and ask the user before proceeding.
The selector is the only agent allowed to choose the author tier/domain; the
orchestrator must not silently bypass it.

When the payload comes from an `AUTHOR_EXECUTION_PLAN` task, include the
planner fields (`author_plan_task_id`, `planner_recommended_author`,
`planner_parallel_group`, `planner_dependencies`, `planner_acceptance_criteria`)
in the selector dispatch. The selector may honor or override the recommendation,
but it must record the decision in `author_selection.reasons`.

## Planned Multi-Author Dispatch

If `AUTHOR_EXECUTION_PLAN` is non-null, Phase 4 executes the plan instead of the
single all-path author payload:

1. Re-validate the plan before dispatch:
   - every task's `recommended_author` is one of the registered author workers
   - every Phase 4 `target_paths` entry is covered by at least one task
   - tasks in the same `parallel_group` have disjoint `target_paths`
   - no parallel group contains more than one task with `updates_artifacts_toml=true`
   - each `parallel_groups[].depends_on` group has completed before its group runs
2. For each parallel group in dependency order, construct one task-scoped
   `mode=create` payload per task:
   - start from the Phase 4 Create Payload below
   - replace `target_paths` with the task's `target_paths`
   - preserve the full approved `inputs` unless the task declares `input_keys`;
     when `input_keys` is present, include only those keys plus any global keys
     required by the template/rules
   - add planner metadata fields for the selector/author worker
3. For each task payload, execute § Author Selection and Dispatch. The
   read-only selector dispatch runs with CF_PHASE_GATE=armed. The gate opens
   only inside that section, immediately before the selector-returned
   write-capable author is dispatched, and resets immediately after each
   author return — whether the author returns a manifest, an
   AUTHOR_ESCALATION_REQUIRED payload, fails, or does not respond.
4. If `INLINE_FALLBACK=false`, tasks in the same group MAY be dispatched in
   parallel. If `INLINE_FALLBACK=true`, run the tasks sequentially in listed
   order and emit a one-line warning that planned parallelism degraded to
   sequential inline execution.
5. Merge all returned manifests after each group: concatenate
   `paths_written`, union `ids_assigned`, OR `artifacts_toml_updated`, and
   concatenate `findings_not_fixable` if present.

If any planned task fails, stop the remaining groups, keep already-written
files untouched, surface the failing task id and author, and route to
`workflows/generate/error-handling.md`.

If `AUTHOR_EXECUTION_PLAN` is null because `AUTHOR_PLAN_OFFER_RESOLVED` is one
of the continuation no-plan states (`declined`,
`auto_skipped_no_author_plan_flag`, `auto_skipped_rules_disabled`), build one
Phase 4 Create Payload covering all target paths and execute § Author Selection
and Dispatch once.

## Phase 4 Create Payload

Inputs: see "Inputs (dispatched-prompt contract)" in
`{cf-studio-path}/.core/skills/studio/agents/cf-generate-author-worker.md`
(mandatory vs optional listed there). Orchestrator-supplied values for this
dispatch:

- `mode` = `"create"`; `kind`, `name`, `rules_mode`, `system` from earlier phases
- `template_path`, `example_path`, `kit_rules_path` resolved from `rules.md`
- `checklist_path` included only when STRICT explicitly requires checklist pre-write
- `design_artifact_path` code mode only
- `target_paths` = the full list of output paths for this generation (single-path artifacts pass a one-element array; multi-file artifacts pass the full list and the author writes them atomically in one dispatch — the agent's `target_paths` input is an array by contract)
- `inputs` = the approved inputs from Phase 1 / Phase 3 — constructed from the collector's `proposed_inputs` JSON block (emitted alongside the human-facing Inputs markdown; open, load, and follow `cf-generate-collector.md` Output contract) with user edits merged in. Keys are the template's H2 section names (normalized); values are the approved defaults.
- optional planner metadata when dispatched from a planned task: `author_plan_task_id`, `planner_task_title`, `planner_recommended_author`, `planner_parallel_group`, `planner_dependencies`, `planner_acceptance_criteria`
- `git_commit_mode` = `GIT_COMMIT_MODE` (one of `"commit"`, `"stage"`, `"none"`; MUST be included)
- `contributing_guide` = `CONTRIBUTING_GUIDE` (path + key directives object, or `null`; MUST be included)
- `git_constraint` = the mode-matched constraint block (see below; MUST be included verbatim in the dispatch)

Git constraint blocks by mode (include exactly one matching the current `GIT_COMMIT_MODE`):
- `commit`: "You MAY `git add` files you wrote and create one commit at the end. Follow the CONTRIBUTING guide (provided) for commit message format. MUST NOT `git push`, `git reset`, `git rebase`, `git stash`, `git checkout --`."
- `stage`:  "You MAY `git add` files you wrote. MUST NOT `git commit`, `git push`, `git reset`, `git rebase`, `git stash`, `git checkout --`."
- `none`:   "MUST NOT run `git commit`, `git push`, `git reset`, `git rebase`, `git stash`, `git checkout --`, or `git add`. Leave changes as uncommitted, unstaged working-tree edits only."

The selected author updates `{cf-studio-path}/config/artifacts.toml`
when a new artifact path is introduced, creates directories as needed, writes
the file(s), and verifies content. It returns a `✓ Written` markdown block plus
a `manifest` JSON block.

Persist `manifest.paths_written` for Phase 5. Echo the `✓ Written` lines to the user verbatim.

## Escalation Handling

If the selected author returns `AUTHOR_ESCALATION_REQUIRED`, write nothing from
that result. Parse its `recommended_author` and `reason`, then rerun the
read-only selector at most once with the original payload plus
`escalation_context`:

```json
{
  "previous_selected_author": "<first selector-returned author>",
  "recommended_author": "<author-reported recommendation>",
  "author_escalation_reason": "<author-reported reason>"
}
```

The selector remains the routing authority. Dispatch only the second
selector-returned `selected_author`, after verifying it is one of the registered
write-capable author agents listed above, differs from the first selected
author, and records the escalation reason in `author_selection.reasons`. Keep
CF_PHASE_GATE=armed while rerunning the selector; open
CF_PHASE_GATE=released_for_dispatch only immediately before dispatching the
second selector-returned write-capable author, then reset it immediately on
return. If the second author also escalates, or if the selector returns the
same author or an invalid author, reset `CF_PHASE_GATE=armed` BEFORE surfacing
the multi-escalation error to the user; the gate MUST NOT remain in
`released_for_dispatch` across turns per SKILL.md § Phase-Skip Gate.
Then fail-stop and surface the reason to the user.

**MUST NOT** dispatch any write-capable author before Phase 3 `yes`. **MUST
NOT** create files before confirmation, create incomplete files, or create
placeholder files. Open, load, and follow `skills/studio/protocol.md` §
Agent-safe invocation for the no-auto-approval rule (`--yes`/`-y`/`--force`
forbidden unless the user explicitly requested non-interactive behavior).
