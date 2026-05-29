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

```text
UNIT Phase4WriteEntry

PURPOSE:
  Enforce entry conditions before dispatching write-capable author.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md loaded before dispatch
  NOTE: Pre-dispatch fail-stop and Mode B degradation rules in
    {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md

  REQUIRE Phase 3 confirmation (yes) received before executing author selection
  FORBID dispatching write-capable author directly from orchestrator

  REQUIRE AUTHOR_PLAN_OFFER_RESOLVED is set by
    workflows/generate/phase-1.5-author-plan.md
  IF AUTHOR_PLAN_OFFER_RESOLVED unset:
    FAIL-STOP
    ROUTE back to workflows/generate/phase-1.5-author-plan.md

  IF AUTHOR_PLAN_OFFER_RESOLVED is terminal cancellation state
    (cancelled_by_stop_token | cancelled_planner_failure | cancelled_partial_write):
    FAIL-STOP immediately
    FORBID dispatching write-capable author
    FORBID synthesizing single-author fallback payload
    LEAVE target files untouched

RULES:
  - MUST NOT dispatch write-capable author before Phase 3 yes
  - MUST NOT create files before confirmation
  - MUST NOT create incomplete or placeholder files
  - Open, load, and follow {cf-studio-path}/.core/skills/studio/protocol.md § Agent-safe invocation
    for no-auto-approval rule (--yes/-y/--force forbidden unless user explicitly
    requested non-interactive behavior)
```

## Author Selection and Dispatch

```text
UNIT Phase4AuthorSelectionDispatch

PURPOSE:
  Two-step canonical write/fix dispatch path for Phase 4 and Phase 5.

DO:
  STEP 1: DISPATCH read-only selector cf-generate-author with full author payload
  STEP 2: PARSE returned author_selection JSON block
  STEP 3: VERIFY selected_author is exactly one of:
    cf-generate-author-junior
    cf-generate-author-middle
    cf-generate-author-senior
    cf-generate-author-lead
    cf-generate-coder-casual
    cf-generate-coder-smart
    cf-generate-prompt-engineer-casual
    cf-generate-prompt-engineer-smart
  STEP 4: KEEP CF_PHASE_GATE = armed while dispatching selector
           SET CF_PHASE_GATE = released_for_dispatch IMMEDIATELY before
             dispatching selected write-capable author
           DISPATCH selected write-capable author with author_selection.dispatch_payload
           RESET CF_PHASE_GATE = armed IMMEDIATELY on return
             (on manifest, escalation, error, or no-response)
           NOTE: gate MUST NOT remain at released_for_dispatch across turns

  IF INLINE_FALLBACK == true:
    WHEN executing author/coder/migrator contract inline:
    SET CF_PHASE_GATE = released_for_inline_write IMMEDIATELY before inline write block
    RESET CF_PHASE_GATE = armed IMMEDIATELY after inline write block completes
      (both on success AND on failure)

  IF selector output is missing, malformed, names unregistered author,
     or changes payload semantics:
    FAIL-STOP
    ASK user before proceeding
    NOTE: selector is the only agent allowed to choose author tier/domain;
          orchestrator MUST NOT silently bypass it

  IF payload comes from AUTHOR_EXECUTION_PLAN task:
    INCLUDE planner fields in selector dispatch:
      author_plan_task_id, planner_recommended_author, planner_parallel_group,
      planner_dependencies, planner_acceptance_criteria
    NOTE: selector may honor or override recommendation; MUST record decision
          in author_selection.reasons

RULES:
  - MUST NOT left CF_PHASE_GATE in released_for_dispatch across turns
  - MUST reset CF_PHASE_GATE = armed immediately after inline write block
    on both success and failure
```

## Planned Multi-Author Dispatch

```text
UNIT Phase4PlannedMultiAuthorDispatch

PURPOSE:
  Execute AUTHOR_EXECUTION_PLAN when non-null instead of single all-path payload.

DO:
  IF AUTHOR_EXECUTION_PLAN is non-null:
    RE-VALIDATE plan before dispatch:
      - every task's recommended_author is one of registered author workers
      - every Phase 4 target_paths entry covered by at least one task
      - tasks in same parallel_group have disjoint target_paths
      - no parallel group has more than one task with updates_artifacts_toml=true
      - each parallel_groups[].depends_on group has completed before its group runs

    FOR each parallel group in dependency order:
      FOR each task in group:
        CONSTRUCT task-scoped mode=create payload:
          - start from Phase 4 Create Payload
          - replace target_paths with task's target_paths
          - preserve full approved inputs UNLESS task declares input_keys;
            when input_keys present, include only those keys plus global keys
            required by template/rules
          - add planner metadata fields for selector/author worker
        EXECUTE § Author Selection and Dispatch
        NOTE: read-only selector runs with CF_PHASE_GATE=armed;
              gate opens only immediately before selector-returned write-capable
              author is dispatched; resets immediately after each author return

      IF INLINE_FALLBACK == false:
        tasks in same group MAY be dispatched in parallel
      IF INLINE_FALLBACK == true:
        run tasks sequentially in listed order
        EMIT one-line warning that planned parallelism degraded to sequential inline execution

    AFTER each group:
      MERGE manifests: concatenate paths_written, union ids_assigned,
        OR artifacts_toml_updated, concatenate findings_not_fixable if present

    IF any planned task fails:
      STOP remaining groups
      LEAVE already-written files untouched
      SURFACE failing task id and author
      ROUTE to workflows/generate/error-handling.md

  IF AUTHOR_EXECUTION_PLAN is null (continuation no-plan states:
     declined | auto_skipped_no_author_plan_flag | auto_skipped_rules_disabled):
    BUILD one Phase 4 Create Payload covering all target paths
    EXECUTE § Author Selection and Dispatch once
```

## Phase 4 Create Payload

```text
UNIT Phase4CreatePayload

PURPOSE:
  Define the dispatched-prompt inputs for the create payload.

DO:
  SUPPLY to selected author:
    mode = "create"
    kind, name, rules_mode, system (from earlier phases)
    template_path, example_path, kit_rules_path (resolved from rules.md)
    checklist_path (included ONLY when STRICT explicitly requires pre-write)
    design_artifact_path (code mode only)
    target_paths = full list of output paths (array by contract)
    inputs = approved inputs from Phase 1 / Phase 3 (from collector's
      proposed_inputs JSON with user edits merged; keys are template H2
      section names normalized; values are approved defaults)
    (OPTIONAL when dispatched from planned task):
      author_plan_task_id, planner_task_title, planner_recommended_author,
      planner_parallel_group, planner_dependencies, planner_acceptance_criteria
    git_commit_mode = GIT_COMMIT_MODE (MUST be included)
    contributing_guide = CONTRIBUTING_GUIDE (MUST be included; null when not found)
    git_constraint = exactly one matching block:
      commit: "You MAY `git add` files you wrote and create one commit at the end.
               Follow the CONTRIBUTING guide (provided) for commit message format.
               MUST NOT `git push`, `git reset`, `git rebase`, `git stash`,
               `git checkout --`."
      stage:  "You MAY `git add` files you wrote. MUST NOT `git commit`,
               `git push`, `git reset`, `git rebase`, `git stash`,
               `git checkout --`."
      none:   "MUST NOT run `git commit`, `git push`, `git reset`, `git rebase`,
               `git stash`, `git checkout --`, or `git add`. Leave changes as
               uncommitted, unstaged working-tree edits only."

RULES:
  - git_commit_mode MUST be included
  - contributing_guide MUST be included (null when not found)
  - git_constraint MUST be included verbatim matching current GIT_COMMIT_MODE

NOTES:
  The selected author updates {cf-studio-path}/config/artifacts.toml when a
  new artifact path is introduced, creates directories as needed, writes
  file(s), and verifies content. Returns a Written markdown block plus
  a manifest JSON block.
  MUST persist manifest.paths_written for Phase 5.
  MUST echo Written lines to user verbatim.
  Open, load, and follow {cf-studio-path}/.core/skills/studio/agents/cf-generate-collector.md Output contract for
  proposed_inputs JSON block shape.
```

## Escalation Handling

```text
UNIT Phase4EscalationHandling

PURPOSE:
  Handle AUTHOR_ESCALATION_REQUIRED returns from selected author.

DO:
  IF selected author returns AUTHOR_ESCALATION_REQUIRED:
    WRITE nothing from that result
    PARSE recommended_author and reason
    KEEP CF_PHASE_GATE = armed while rerunning selector
    RERUN read-only selector AT MOST ONCE with original payload plus:
      escalation_context = {
        "previous_selected_author": "<first selector-returned author>",
        "recommended_author": "<author-reported recommendation>",
        "author_escalation_reason": "<author-reported reason>"
      }
    DISPATCH ONLY second selector-returned selected_author
    VERIFY it is one of registered write-capable author agents (see above list)
    VERIFY it differs from first selected author
    VERIFY escalation reason is recorded in author_selection.reasons
    OPEN CF_PHASE_GATE = released_for_dispatch IMMEDIATELY before dispatching
    RESET CF_PHASE_GATE = armed IMMEDIATELY on return

    IF second author also escalates:
      RESET CF_PHASE_GATE = armed BEFORE surfacing error
      FAIL-STOP and surface reason to user
    IF selector returns same author or invalid author:
      RESET CF_PHASE_GATE = armed BEFORE surfacing error
      FAIL-STOP and surface reason to user

RULES:
  - MUST NOT dispatch write-capable author before Phase 3 yes
  - MUST reset CF_PHASE_GATE = armed BEFORE surfacing multi-escalation error;
    gate MUST NOT remain in released_for_dispatch across turns per
    SKILL.md § Phase-Skip Gate
```
