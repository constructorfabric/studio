---
cf: true
type: workflow-fragment
parent: workflows/generate/phase-1.5-author-plan.md
description: Canonical state contract for Generate Phase 1.5 author-plan offer resolution, continuation states, and terminal cancellation states.
---

# Generate Phase 1.5: State Contract

```pdsl
UNIT Phase15StateContract

PURPOSE:
  Define canonical AUTHOR_PLAN_OFFER_RESOLVED values, state families,
  and derived state variables.

STATE:
  - SET AUTHOR_PLAN_OFFER_RESOLVED:
    unresolved
    | memory
    | disk
    | inline
    | skipped_by_user
    | auto_skipped_no_author_plan_flag
    | auto_skipped_rules_disabled
    | cancelled_by_stop_token
    | cancelled_planner_failure
    | cancelled_partial_write

  - SET AUTHOR_EXECUTION_PLAN: parsed author_plan JSON | null
  - SET AUTHOR_PLAN_APPROVED: false | true  default: false  scope: workflow_run
  - SET AUTHOR_PLAN_CACHE_DIR: directory path | null (only when AUTHOR_PLAN_OFFER_RESOLVED=disk
    AND cache render completed successfully)
  - SET auto_skip_condition: true | false
    derived from invoke_flag == "--no-author-plan"
    OR kind_rules.author_plan == "disabled"

RULES:
  - ALWAYS Continuation states:
    memory | disk | inline | skipped_by_user |
    auto_skipped_no_author_plan_flag | auto_skipped_rules_disabled

  - ALWAYS Terminal cancellation states:
    cancelled_by_stop_token | cancelled_planner_failure | cancelled_partial_write

  - ALWAYS Unresolved state:
    unresolved means Phase 1.5 has not completed and NEVER enter Phase 3,
    Phase 4, or any author dispatch.

  - ALWAYS AUTHOR_EXECUTION_PLAN:
    - ALWAYS be set to parsed author_plan JSON ONLY when
      AUTHOR_PLAN_OFFER_RESOLVED is memory, disk, or inline
    - ALWAYS be null otherwise

  - ALWAYS AUTHOR_PLAN_APPROVED:
    - ALWAYS remain false until the validated author_plan has been shown to the
      user and the user explicitly approves it through AuthorPlanApprovalMenu
    - ALWAYS Phase 3 and Phase 4 NEVER run from a planner-produced
      AUTHOR_EXECUTION_PLAN while AUTHOR_PLAN_APPROVED != true

  - ALWAYS AUTHOR_PLAN_CACHE_DIR:
    - ALWAYS be set ONLY when AUTHOR_PLAN_OFFER_RESOLVED=disk AND cache
      render completed successfully
    - NEVER be claimed unless successfully written subset is explicitly
      reported to the user when disk-mode cache writes fail

  - ALWAYS Auto-skip conditions:
    - ALWAYS user passed --no-author-plan in the invocation
    - ALWAYS KIND's rules.md explicitly sets author_plan = "disabled"
```

## Mandatory-Decompose Branch

```pdsl
UNIT Phase15MandatoryDecomposeBranch

PURPOSE:
  Define behavior when SUB_AGENT_SESSION_APPROVED=true AND INLINE_FALLBACK=false
  AND no auto-skip condition applies.

WHEN:
  - REQUIRE SUB_AGENT_SESSION_APPROVED == true
  - AND INLINE_FALLBACK == false
  - AND auto_skip_condition == false

RULES:
  - ALWAYS Initial user choice resolves planning mode: memory, disk, inline, skip, or stop
  - ALWAYS `skip` is an explicit user-decline of planner decomposition and continues
    through the single-author flow
  - ALWAYS auto_skipped_* states are unreachable in this branch
  - ALWAYS Planner dispatch is required only for memory/disk choices
  - ALWAYS Inline choice builds the same AUTHOR_EXECUTION_PLAN in-controller without
    dispatching cf-generate-planner
  - ALWAYS AUTHOR_EXECUTION_PLAN is expected non-null on successful planner exit, but
    NEVER be executed until the user approves the displayed plan
  - ALWAYS Planner-failure recovery NEVER continue to Phase 3 without a valid
    AUTHOR_EXECUTION_PLAN; recovery choices are rerun or terminal cancellation
```

## Downstream Requirements

```pdsl
UNIT Phase15DownstreamRequirements

PURPOSE:
  Enforce Phase 3 / Phase 4 entry guards based on AUTHOR_PLAN_OFFER_RESOLVED.

RULES:
  - ALWAYS Phase 3 and Phase 4 ALWAYS only run when AUTHOR_PLAN_OFFER_RESOLVED
    is a continuation state
  - ALWAYS When AUTHOR_EXECUTION_PLAN is non-null from planner dispatch or inline
    planning, Phase 3 and Phase 4 additionally require AUTHOR_PLAN_APPROVED == true
  - ALWAYS When target_paths includes instruction-file targets
    (`workflows/**`, `requirements/**`, any `AGENTS.md`,
    `skills/**/SKILL.md`, `skills/**/agents/*.md`, and equivalent
    prompt/agent contracts), continuation authorizes only planner/author
    dispatch continuation; it does NOT authorize controller-local patching
  - ALWAYS IF a later phase observes a terminal cancellation state:
    ALWAYS fail-stop without dispatching write-capable author
    ALWAYS leave target files untouched
  - ALWAYS Plan-cache files written under disk mode are not target-file writes;
    cleanup/resume handling defined by disk-mode.md and error-handling.md
```
