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

```text
UNIT Phase15OfferDispatch

PURPOSE:
  Present mandatory or optional author-plan offer based on sub-agent approval state.

WHEN:
  SUB_AGENT_SESSION_APPROVED == true
  AND INLINE_FALLBACK == false
  AND auto_skip_condition == false

DO:
  EMIT exactly:
---
Author plan (mandatory — sub-agents approved): pick storage.

I will decompose this generate task into author-worker sub-tasks, assign each
to a specialist sub-agent, and group them for parallel dispatch in Phase 4.

Reply `enter` or `memory` for in-memory plan (default), or `disk` to also save
a Markdown plan pack under `{cf-studio-path}/.cache/generate-plans/`.

Choose `disk` if the session may be long or context may compact (plan survives compaction); choose `memory` for short sessions (no disk I/O, plan is in-context only).
---
  WAIT user.reply
  STOP_TURN

MENU MandatoryOfferMenu:
  TITLE: Mandatory author-plan storage choice
  OPTIONS:
    empty | memory | 1 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = memory
      CONTINUE PlannerDispatch
    disk | save | 2 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = disk
      CONTINUE PlannerDispatch
      THEN LOAD {cf-studio-path}/.core/workflows/generate/phase-1.5/disk-mode.md
    stop_token ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_by_stop_token
      SET CF_PHASE_GATE = armed
      LOAD {cf-studio-path}/.core/workflows/shared/stop-token-policy.md
      STOP current generate sub-flow
      FORBID entering Phase 3 or Phase 4
    no | skip | 3 ->
      EMIT "Decomposition is mandatory while sub-agents are approved. Reply enter/memory or disk."
      WAIT user.reply
      STOP_TURN
  INVALID:
    EMIT "Reply not recognized. Expected enter/memory or disk."
    WAIT user.reply
    STOP_TURN
```

```text
UNIT Phase15OptionalOffer

PURPOSE:
  Present optional author-plan offer when mandatory branch is not active and
  no auto-skip condition already resolved the state.

WHEN:
  NOT (SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false)
  AND auto_skip_condition == false

DO:
  EMIT exactly:
---
Want a lightweight author plan before the final summary?

I can decompose this generate task into author-worker tasks, recommend which
author should handle each task, and mark which tasks can run in parallel.

Suggested: `memory` (or `enter`) for short sessions; `disk` for sessions that may be long or context-heavy.

Reply `enter` or `memory` for an in-memory plan (default), `disk` to also save
a Markdown plan pack under `{cf-studio-path}/.cache/generate-plans/`, or
`no` to skip the author plan.
---
  WAIT user.reply
  STOP_TURN

MENU OptionalOfferMenu:
  TITLE: Optional author-plan storage choice
  OPTIONS:
    empty | memory | 1 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = memory
      CONTINUE PlannerDispatch
    disk | save | 2 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = disk
      CONTINUE PlannerDispatch
      THEN LOAD {cf-studio-path}/.core/workflows/generate/phase-1.5/disk-mode.md
    no | skip | 3 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = declined
      SET AUTHOR_EXECUTION_PLAN = null
      CONTINUE Phase3
    stop_token ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_by_stop_token
      SET CF_PHASE_GATE = armed
      LOAD {cf-studio-path}/.core/workflows/shared/stop-token-policy.md
      STOP current generate sub-flow
      FORBID entering Phase 3 or Phase 4
  INVALID:
    EMIT "Reply not recognized. Expected enter/memory, disk, or no."
    WAIT user.reply
    STOP_TURN

RULES:
  - Choosing disk approves ONLY plan-cache files described in disk-mode.md;
    it is NOT approval to write target artifact/code files;
    Phase 3 yes is still required before Phase 4
```

## Planner Dispatch

```text
UNIT Phase15PlannerDispatch

PURPOSE:
  Dispatch cf-generate-planner and validate returned plan.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md loaded before dispatch
  NOTE: Pre-dispatch fail-stop and Mode B degradation rules in
    {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md

  DISPATCH cf-generate-planner (read-only) with JSON contract from
    {cf-studio-path}/.core/skills/studio/agents/cf-generate-planner.md
  WITH orchestrator-supplied values:
    plan_mode = "memory" or "disk" from user's reply
    work_request = original generate request / approved statement of what must be done
    target_type, mode, kind, name, rules_mode, system
    template_path, example_path, kit_rules_path, checklist_path
    design_artifact_path (code mode only, otherwise null)
    target_paths = full list of paths expected to be written in Phase 4
    inputs = approved Phase 1 proposed_inputs with user edits merged in
    findings = [] in create mode (Phase 5 fix loops do not use this offer gate)
    brainstorm_decisions = Phase 0.7 decisions or {}
    open_questions = Phase 0.7 open questions or []
    available_authors = registered write-capable author worker agents from
      {cf-studio-path}/.core/workflows/generate/phase-4-write.md § Author Selection and Dispatch

  PARSE marker "<!-- author_plan -->" and following JSON block

  VALIDATE:
    - every task's recommended_author is one of the registered author worker agents
    - work_request is present, non-empty, and preserves what the user asked to do
    - every target path is covered by at least one task
    - tasks in the same parallel_group have disjoint target_paths
    - no parallel group contains more than one task with updates_artifacts_toml=true
    - every parallel_groups[].task_ids entry names an existing task

  IF validation fails:
    EMIT_MENU PlannerValidationFailureMenu
    WAIT user.reply
    STOP_TURN

MENU PlannerValidationFailureMenu:
  TITLE: Planner validation failed: {reason}.
  OPTIONS:
    1 ->
      NOTE: Suggested — most validation failures are transient; a rerun resolves them.
      RE-DISPATCH cf-generate-planner with same inputs
      RE-VALIDATE returned plan
    2 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = declined
      SET AUTHOR_EXECUTION_PLAN = null
      CONTINUE Phase3
      NOTE: Only valid declined exit in the mandatory-decompose branch
    3 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_planner_failure
      SET AUTHOR_EXECUTION_PLAN = null
      SET CF_PHASE_GATE = armed
      STOP current generate sub-flow
      FORBID entering Phase 3 or Phase 4
  stop_token ->
    SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_planner_failure
    SET AUTHOR_EXECUTION_PLAN = null
    STOP without entering Phase 3 or Phase 4
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN
```
