---
cf: true
type: workflow-fragment
parent: workflows/generate/phase-1.5-author-plan.md
description: Mandatory/optional author-plan offer plus planner dispatch and validation for Generate Phase 1.5.
---

# Generate Phase 1.5: Author Plan Offer

```pdsl
UNIT Phase15AutoSkip

PURPOSE:
  Short-circuit Phase 1.5 when an explicit auto-skip condition applies.

WHEN:
  - REQUIRE invoke_flag == "--no-author-plan"
  - OR kind_rules.author_plan == "disabled"

DO:
  - REQUIRE invoke_flag == "--no-author-plan":
    - SET AUTHOR_PLAN_OFFER_RESOLVED = auto_skipped_no_author_plan_flag
    - CONTINUE workflows/generate/phase-3-summary.md
  - REQUIRE kind_rules.author_plan == "disabled":
    - SET AUTHOR_PLAN_OFFER_RESOLVED = auto_skipped_rules_disabled
    - CONTINUE workflows/generate/phase-3-summary.md
```

```pdsl
UNIT Phase15OfferDispatch

PURPOSE:
  Present mandatory author-plan storage choice when sub-agents are approved.

WHEN:
  - REQUIRE SUB_AGENT_SESSION_APPROVED == true
  - AND INLINE_FALLBACK == false
  - AND NOT (invoke_flag == "--no-author-plan" OR kind_rules.author_plan == "disabled")

DO:
  - EMIT exactly:
- RUN ---
- RUN Author plan (mandatory — sub-agents approved): pick storage.

- RUN I will decompose this generate task into author-worker sub-tasks, assign each
- RUN to a specialist sub-agent, and group them for parallel dispatch in Phase 4.

- RUN Reply `enter` or `memory` for in-memory plan (default), or `disk` to also save
- RUN a Markdown plan pack under `{cf-studio-path}/.cache/generate-plans/`.

- RUN Choose `disk` if the session may be long or context may compact; choose `memory`
- RUN for short sessions (no disk I/O, plan is in-context only).
- RUN ---
  - WAIT user.reply
  - STOP_TURN

MENU MandatoryOfferMenu:
  TITLE: Mandatory author-plan storage choice
  OPTIONS:
    1 empty | enter | memory | 1 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = memory
      CONTINUE Phase15PlannerDispatch
    2 disk | save | 2 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = disk
      LOAD {cf-studio-path}/.core/workflows/generate/phase-1.5/disk-mode.md
      CONTINUE Phase15PlannerDispatch
    3 stop | stop_token ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_by_stop_token
      SET CF_PHASE_GATE = armed
      LOAD {cf-studio-path}/.core/workflows/shared/stop-token-policy.md
      STOP current generate sub-flow
      NEVER entering Phase 3 or Phase 4
    4 no | skip | 3 ->
      EMIT "Decomposition is mandatory while sub-agents are approved. Reply enter/memory or disk."
      WAIT user.reply
      STOP_TURN
  INVALID:
    EMIT "Reply not recognized. Expected enter/memory or disk."
    WAIT user.reply
    STOP_TURN
```

```pdsl
UNIT Phase15OptionalOffer

PURPOSE:
  Present required author-plan storage choice when native dispatch is not active.

WHEN:
  - NOT (SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false)
  - AND NOT (invoke_flag == "--no-author-plan" OR kind_rules.author_plan == "disabled")

DO:
  - EMIT exactly:
- RUN ---
- RUN Author plan required before the final summary.

- RUN Native sub-agent dispatch is not active for this run. I must still build an
- RUN author plan before Phase 3.

- RUN Suggested: `memory` (or `enter`) for short sessions; `disk` for long or
- RUN context-heavy sessions.

- RUN Reply `enter` or `memory` for an in-memory plan (default), `disk` to also save
- RUN a Markdown plan pack under `{cf-studio-path}/.cache/generate-plans/`, or
- RUN `stop` to cancel.
- RUN ---
  - WAIT user.reply
  - STOP_TURN

MENU OptionalOfferMenu:
  TITLE: Required author-plan storage choice
  OPTIONS:
    1 empty | enter | memory | 1 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = memory
      CONTINUE Phase15PlannerDispatch
    2 disk | save | 2 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = disk
      LOAD {cf-studio-path}/.core/workflows/generate/phase-1.5/disk-mode.md
      CONTINUE Phase15PlannerDispatch
    3 no | skip | 3 ->
      EMIT "Author planning is required before Phase 3. Reply enter/memory, disk, or stop."
      WAIT user.reply
      STOP_TURN
    4 stop | stop_token ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_by_stop_token
      SET CF_PHASE_GATE = armed
      LOAD {cf-studio-path}/.core/workflows/shared/stop-token-policy.md
      STOP current generate sub-flow
      NEVER entering Phase 3 or Phase 4
  INVALID:
    EMIT "Reply not recognized. Expected enter/memory, disk, or stop."
    WAIT user.reply
    STOP_TURN

RULES:
  - NEVER treat disk selection as authorization for target artifact/code writes
  - ALWAYS Phase 3 confirmation still required before Phase 4 even when disk is chosen
```

```pdsl
UNIT Phase15PlannerDispatch

PURPOSE:
  Dispatch cf-generate-planner and validate returned plan.

STATE:
  - SET PLANNER_VALIDATION_RETRY_COUNT: integer  default: 0  scope: workflow_run
  - SET PLANNER_VALIDATION_MAX_RETRIES: integer  default: 2  scope: workflow_run

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md loaded before dispatch
  - REQUIRE {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md loaded
  - LOAD {cf-studio-path}/.core/skills/studio/agents/cf-generate-planner.md
    as the planner source contract
  - RUN SYNTHESIZE final dispatch prompt from planner contract plus
    SHARED_CONTEXT_PACK and the payload below
  - REQUIRE planner source contract is not loaded, unreadable, ambiguous, or not
     reflected in the final dispatch prompt:
    FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
    - NEVER dispatch

  - DISPATCH cf-generate-planner (read-only) with synthesized final prompt
  - RUN including:
    plan_mode = AUTHOR_PLAN_OFFER_RESOLVED ("memory" or "disk")
    work_request = original generate request / approved statement of what must be done
    target_type, mode, kind, name, rules_mode, system
    template_path, example_path, kit_rules_path, checklist_path
    design_artifact_path (code mode only, otherwise null)
    target_paths = full list of paths expected to be written in Phase 4
    inputs = approved Phase 1 proposed_inputs with user edits merged in
    findings = [] in create mode
    brainstorm_decisions = Phase 0.7 decisions or {}
    open_questions = Phase 0.7 open questions or []
    available_authors = registered write-capable author worker agents from
      {cf-studio-path}/.core/workflows/generate/phase-4-write.md § Author Selection and Dispatch

  - RUN PARSE marker "<!-- author_plan -->" and following JSON block
  - REQUIRE marker is missing OR JSON parse fails:
    - SET planner_failure_reason = "missing-or-invalid-author-plan-json"
    - EMIT_MENU PlannerValidationFailureMenu
    - WAIT user.reply
    - STOP_TURN

  - RUN VALIDATE:
    - every task's recommended_author is a registered author worker agent
    - work_request is present, non-empty, preserves what the user asked to do
    - every target path is covered by at least one task
    - tasks in the same parallel_group have disjoint target_paths
    - no parallel group contains more than one task with updates_artifacts_toml=true
    - every parallel_groups[].task_ids entry names an existing task
    - every task.parallel_group is a string id matching an existing parallel_groups[].id
    - every parallel_groups[].depends_on references an earlier group
    - every parallel_groups[] entry includes id, task_ids, depends_on, execution, and reason
    - every parallel_groups[].execution is "parallel" or "sequential"

  - REQUIRE validation passes:
    - SET AUTHOR_EXECUTION_PLAN = parsed author_plan JSON
    - SET AUTHOR_PLAN_APPROVED = false
    - SET PLANNER_VALIDATION_RETRY_COUNT = 0
    - EMIT "Author execution plan prepared. Review and approve it before Phase 3 summary or any author-worker dispatch."
    - EMIT author_plan JSON in full, including tasks, target paths, recommended
      authors, dependencies, parallel groups, storage mode, and acceptance criteria
    - EMIT_MENU AuthorPlanApprovalMenu
    - WAIT user.reply
    - STOP_TURN

  - REQUIRE validation fails:
    - SET planner_failure_reason = validation.errors[] joined with "; "
    - EMIT_MENU PlannerValidationFailureMenu
    - WAIT user.reply
    - STOP_TURN

MENU PlannerValidationFailureMenu:
  TITLE: Planner validation failed: {planner_failure_reason}.
  OPTIONS:
    1 retry ->
      INCREMENT PLANNER_VALIDATION_RETRY_COUNT
      IF PLANNER_VALIDATION_RETRY_COUNT > PLANNER_VALIDATION_MAX_RETRIES:
        EMIT_MENU PlannerValidationFailureTerminalMenu
        WAIT user.reply
        STOP_TURN
      LOAD {cf-studio-path}/.core/skills/studio/agents/cf-generate-planner.md
        as the planner source contract
      SYNTHESIZE final dispatch prompt from planner contract plus
        SHARED_CONTEXT_PACK and the same inputs
      IF planner source contract is not loaded, unreadable, ambiguous, or not
         reflected in the final dispatch prompt:
        FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
        NEVER re-dispatch
      DISPATCH cf-generate-planner with synthesized final prompt
      RE-VALIDATE returned plan
      IF validation passes:
        SET AUTHOR_EXECUTION_PLAN = parsed author_plan JSON
        SET AUTHOR_PLAN_APPROVED = false
        SET PLANNER_VALIDATION_RETRY_COUNT = 0
        EMIT "Author execution plan prepared. Review and approve it before Phase 3 summary or any author-worker dispatch."
        EMIT author_plan JSON in full, including tasks, target paths, recommended
          authors, dependencies, parallel groups, storage mode, and acceptance criteria
        EMIT_MENU AuthorPlanApprovalMenu
        WAIT user.reply
        STOP_TURN
      IF validation fails again:
        EMIT_MENU PlannerValidationFailureMenu
        WAIT user.reply
        STOP_TURN
    2 stop_recoverable ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_planner_failure
      SET AUTHOR_EXECUTION_PLAN = null
      SET CF_PHASE_GATE = armed
      STOP current generate sub-flow
      NEVER entering Phase 3 or Phase 4
    3 stop_hard ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_planner_failure
      SET AUTHOR_EXECUTION_PLAN = null
      STOP_TURN
    4 stop_token ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_planner_failure
      SET AUTHOR_EXECUTION_PLAN = null
      SET CF_PHASE_GATE = armed
      STOP current generate sub-flow
      NEVER entering Phase 3 or Phase 4
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN

MENU PlannerValidationFailureTerminalMenu:
  TITLE: Planner validation failed after {PLANNER_VALIDATION_MAX_RETRIES} retry attempts.
  OPTIONS:
    1 stop ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_planner_failure
      SET AUTHOR_EXECUTION_PLAN = null
      SET CF_PHASE_GATE = armed
      STOP current generate sub-flow
      NEVER entering Phase 3 or Phase 4
    2 stop_token ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_planner_failure
      SET AUTHOR_EXECUTION_PLAN = null
      STOP without entering Phase 3 or Phase 4

MENU AuthorPlanApprovalMenu:
  TITLE: |
    Approve author execution plan?

    Phase 3 summary and write-capable author dispatch will not start until you
    approve this plan. Choose rerun if the task split, target paths, selected
    authors, or dependency order look wrong.
  OPTIONS:
    1 approve ->
      SET AUTHOR_PLAN_APPROVED = true
      CONTINUE Phase15Handoff
    2 rerun ->
      SET AUTHOR_EXECUTION_PLAN = null
      SET AUTHOR_PLAN_APPROVED = false
      CONTINUE Phase15PlannerDispatch
    3 stop ->
      SET AUTHOR_EXECUTION_PLAN = null
      SET AUTHOR_PLAN_APPROVED = false
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_planner_failure
      SET CF_PHASE_GATE = armed
      STOP current generate sub-flow
      NEVER entering Phase 3 or Phase 4
  INVALID:
    EMIT "Reply `1` to approve, `2` to rerun the planner, or `3` to stop."
    WAIT user.reply
    STOP_TURN

RULES:
  - NEVER continue to Phase 3 without a valid AUTHOR_EXECUTION_PLAN
  - NEVER continue to Phase 3 or Phase 4 from a planner-produced
    AUTHOR_EXECUTION_PLAN until AuthorPlanApprovalMenu has displayed the full
    plan and the user selected `1 approve`
  - ALWAYS Planner failure NEVER degrade to no-plan Phase 3 continuation
  - ALWAYS AUTHOR_EXECUTION_PLAN may be null only for explicit Phase15AutoSkip states;
    those states use the single-author Phase 4 path and NEVER claim planned
    parallel dispatch
  - ALWAYS PlannerValidationFailureMenu option `2 stop_recoverable` cancels and arms
    CF_PHASE_GATE for session-level recovery.
  - ALWAYS PlannerValidationFailureMenu option `3 stop_hard` stops this turn without
    entering Phase 3 or Phase 4.
  - ALWAYS AuthorPlanApprovalMenu option `3 stop` cancels and arms CF_PHASE_GATE.

NOTES:
  Pre-dispatch fail-stop and Mode B degradation rules in
  {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md.
```
