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
  AUTHOR_PLAN_OFFER_RESOLVED:
    unresolved
    | memory
    | disk
    | auto_skipped_no_author_plan_flag
    | auto_skipped_rules_disabled
    | cancelled_by_stop_token
    | cancelled_planner_failure
    | cancelled_partial_write

  AUTHOR_EXECUTION_PLAN: parsed author_plan JSON | null
  AUTHOR_PLAN_APPROVED: false | true  default: false  scope: workflow_run
  AUTHOR_PLAN_CACHE_DIR: directory path | null (only when AUTHOR_PLAN_OFFER_RESOLVED=disk
    AND cache render completed successfully)
  auto_skip_condition: true | false
    derived from invoke_flag == "--no-author-plan"
    OR kind_rules.author_plan == "disabled"

RULES:
  Continuation states:
    memory | disk | auto_skipped_no_author_plan_flag |
    auto_skipped_rules_disabled

  Terminal cancellation states:
    cancelled_by_stop_token | cancelled_planner_failure | cancelled_partial_write

  Unresolved state:
    unresolved means Phase 1.5 has not completed and MUST NOT enter Phase 3,
    Phase 4, or any author dispatch.

  AUTHOR_EXECUTION_PLAN:
    - MUST be set to parsed author_plan JSON ONLY when
      AUTHOR_PLAN_OFFER_RESOLVED is memory or disk
    - MUST be null otherwise

  AUTHOR_PLAN_APPROVED:
    - MUST remain false until the validated author_plan has been shown to the
      user and the user explicitly approves it through AuthorPlanApprovalMenu
    - Phase 3 and Phase 4 MUST NOT run from a planner-produced
      AUTHOR_EXECUTION_PLAN while AUTHOR_PLAN_APPROVED != true

  AUTHOR_PLAN_CACHE_DIR:
    - MUST be set ONLY when AUTHOR_PLAN_OFFER_RESOLVED=disk AND cache
      render completed successfully
    - MUST NOT be claimed unless successfully written subset is explicitly
      reported to the user when disk-mode cache writes fail

  Auto-skip conditions:
    - user passed --no-author-plan in the invocation
    - KIND's rules.md explicitly sets author_plan = "disabled"
```

## Mandatory-Decompose Branch

```pdsl
UNIT Phase15MandatoryDecomposeBranch

PURPOSE:
  Define behavior when SUB_AGENT_SESSION_APPROVED=true AND INLINE_FALLBACK=false
  AND no auto-skip condition applies.

WHEN:
  SUB_AGENT_SESSION_APPROVED == true
  AND INLINE_FALLBACK == false
  AND auto_skip_condition == false

RULES:
  - Initial user choice is ONLY plan storage (memory vs disk)
  - FORBID direct user-decline from the offer itself
  - auto_skipped_* states are unreachable in this branch
  - Planner dispatch is unconditional
  - AUTHOR_EXECUTION_PLAN is expected non-null on successful planner exit, but
    MUST_NOT be executed until the user approves the displayed plan
  - Planner-failure recovery MUST NOT continue to Phase 3 without a valid
    AUTHOR_EXECUTION_PLAN; recovery choices are rerun or terminal cancellation
```

## Downstream Requirements

```pdsl
UNIT Phase15DownstreamRequirements

PURPOSE:
  Enforce Phase 3 / Phase 4 entry guards based on AUTHOR_PLAN_OFFER_RESOLVED.

RULES:
  - Phase 3 and Phase 4 MUST only run when AUTHOR_PLAN_OFFER_RESOLVED
    is a continuation state
  - When AUTHOR_EXECUTION_PLAN is non-null from planner dispatch, Phase 3 and
    Phase 4 additionally require AUTHOR_PLAN_APPROVED == true
  - When target_paths includes instruction-file targets
    (`workflows/**`, `requirements/**`, any `AGENTS.md`,
    `skills/**/SKILL.md`, `skills/**/agents/*.md`, and equivalent
    prompt/agent contracts), continuation authorizes only planner/author
    dispatch continuation; it does NOT authorize controller-local patching
  - IF a later phase observes a terminal cancellation state:
    MUST fail-stop without dispatching write-capable author
    MUST leave target files untouched
  - Plan-cache files written under disk mode are not target-file writes;
    cleanup/resume handling defined by disk-mode.md and error-handling.md
```
