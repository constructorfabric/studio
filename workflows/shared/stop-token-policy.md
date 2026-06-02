---
name: stop-token-policy
description: "Invoke when loading the canonical stop-token (stop/enough/done) routing policy applicable to every workflow prompt."
purpose: Canonical stop-token (stop/enough/done) routing for every workflow prompt
loaded_by: workflows/generate.md, workflows/analyze.md, workflows/plan.md, workflows/workspace.md, workflows/workspace/phase-1-discover.md, workflows/workspace/phase-2-configure.md, workflows/workspace/phase-3-generate.md, workflows/workspace/phase-4-validate.md, workflows/workspace/next-steps.md
version: 1.0
---

<!-- toc -->

- [Stop-Token Policy (canonical)](#stop-token-policy-canonical)
- [Plan Workflow Stop Tokens](#plan-workflow-stop-tokens)
- [Workspace Workflow Stop Tokens](#workspace-workflow-stop-tokens)

<!-- /toc -->

## Stop-Token Policy (canonical)

```pdsl
UNIT StopTokenPolicy

PURPOSE:
  Define canonical stop-token routing for every workflow prompt.
  This unit is the single source of truth; other workflow files reference
  this path instead of restating. Existing per-phase stop-token mentions
  are non-normative reminders only.

INPUT:
  stop_token: "stop" | "enough" | "done"
    match: case-insensitive, exact-match — NOT as substring of a longer reply

WHEN:
  user reply matches stop_token at any user-input prompt

DO:
  CONTINUE StopTokenRouter

RULES:
  - MUST match stop tokens case-insensitively and exactly
    (not as substrings of a longer reply)
```

```pdsl
UNIT StopTokenRouter

PURPOSE:
  Route to the safest exit for the phase that emitted the prompt.

WHEN:
  stop_token received

DO:
  IF prompt is from workflows/generate/phase-0.7/round-loop.md
  OR workflows/generate/phase-0.7/wrap-handoff.md (brainstorm round loop or wrap-up):
    SET state.topic_current = None
    CARRY current state.decisions forward
    SET unanswered questions = open_questions
    CONTINUE workflows/generate/phase-1-collect.md with whatever was already approved

  IF prompt is from workflows/generate/phase-5/phase-5.3-findings.md
  (all-mechanical fast-path announcement, before auto-fix dispatch):
    TREAT AS workflows/generate/phase-5/phase-5.4-approval.md option 4
    SKIP auto-fix dispatch
    SET remaining_findings = all_findings
    SET loop_exit = "manual-handoff"
    CONTINUE workflows/generate/phase-6/index.md

  IF prompt is from workflows/generate/phase-5/phase-5.2-semantic.md
  (inline-mode reduce: warning prompt):
    CANCEL Phase 5 before any validator/reviewer/author dispatch for that review-loop run
    IF manifest.paths_written is non-empty:
      LEAVE written files untouched
      END generate run with Pre-Review Warning Handoff block
        (workflows/generate/phase-5/phase-5.2-semantic.md sanctioned pre-review warning terminal path)
    ELSE:
      RETURN control to user without proceeding to Phase 6

  IF prompt is from workflows/generate/phase-1.5/offer-dispatch.md
  (storage-choice prompts):
    SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_by_stop_token
    SKIP Phase 3 / Phase 4
    STOP current generate sub-flow

  IF prompt is from workflows/generate/phase-1.5/offer-dispatch.md
  (planner-validation recovery prompt):
    SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_planner_failure
    SKIP Phase 3 / Phase 4
    STOP current generate sub-flow

  IF prompt is from workflows/generate/phase-1.5/disk-mode.md
  (partial-cache recovery prompt):
    SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_partial_write
    SKIP Phase 3 / Phase 4
    STOP current generate sub-flow

  IF prompt is from workflows/generate/phase-5/phase-5.4-approval.md
  (mixed-iteration approval gate):
    TREAT AS option 4
    SET remaining_findings = all_findings ∪ carry_forward
    SET loop_exit = "manual-handoff"
    CONTINUE workflows/generate/phase-6/index.md

  IF prompt is from any other generate prompt:
    (covers: workflows/generate/phase-0.2-review-loop-cfg.md,
     workflows/generate/phase-5/index.md § Pre-Phase-Setup,
     workflows/generate/phase-0.5-clarify.md,
     workflows/generate/phase-0.7/offer.md,
     workflows/generate/phase-1-collect.md,
     workflows/generate/phase-3-summary.md,
     workflows/generate/phase-6/index.md menus,
     Review-Loop Iteration Cap Prompt)
    CANCEL current sub-flow with a one-line acknowledgement
    LEAVE any already-written files untouched
    RETURN control to user without proceeding further
```

## Plan Workflow Stop Tokens

```pdsl
UNIT PlanStopTokenRouter

PURPOSE:
  Route stop tokens received at plan workflow prompts.

WHEN:
  stop_token received at a workflows/plan.md prompt

DO:
  IF prompt is raw-input materialization [y/n]:
    EMIT "Raw-input materialization declined — stop and re-run with smaller input or approve Invoke skill `cf-plan` materialization when ready"
    STOP (valid completion state, no further routing)

  IF prompt is decomposition [y/n]:
    EMIT "Decomposition declined — rework the phase boundaries and re-run Invoke skill `cf-plan` when ready"
    STOP (valid completion state, no further routing)

  IF prompt is Phase 3.2A brief-checkpoint [1]–[4]:
    TREAT AS option [4]
    SET plan.execution_status = "briefs_only"
    STOP after brief package

  IF prompt is Phase 4.2 next-steps [1]–[5]:
    CANCEL current next-step sub-flow
    LEAVE already-written files untouched
    RETURN control to user without proceeding further

  IF prompt is workflows/plan/plan-lifecycle.md lifecycle selection [1]–[4]:
    TREAT AS option [4] (Manual)
    DEFER lifecycle decision to post-execution

ON_ERROR:
  unrecognized_prompt_origin ->
    EMIT "Stop received — no matching route; returning control to user."
    STOP_TURN
```

## Workspace Workflow Stop Tokens

```pdsl
UNIT WorkspaceStopTokenRouter

PURPOSE:
  Route stop tokens received at workspace workflow prompts.

WHEN:
  stop_token received at a workflows/workspace.md prompt

DO:
  IF prompt is Phase 1 zero-results menu [1]–[3]
  (workflows/workspace/phase-1-discover.md):
    TREAT AS [3] (stop workspace setup)
    PRESERVE scan results in state
    END cleanly; no files written

  IF prompt is Phase 1 repo-selection prompt
  (workflows/workspace/phase-1-discover.md):
    CANCEL workspace setup immediately
    DO NOT carry any provisional selection into Phase 2

  IF prompt is Phase 1 standalone-vs-inline decision prompt:
    CANCEL workspace setup; no files written

  IF prompt is Phase 2 approval prompt
  (workflows/workspace/phase-2-configure.md):
    CANCEL before writing workspace config; no files written

  IF prompt is Phase 3 CLI failure recovery [1]–[3]
  (workflows/workspace/phase-3-generate.md):
    TREAT AS [3] (abort)
    LEAVE whatever partial state exists for user inspection

  IF prompt is Phase 4 validation decision point
  (workflows/workspace/phase-4-validate.md):
    CANCEL validation
    REPORT partial result

  IF prompt is post-setup next-steps menu
  (workflows/workspace/next-steps.md):
    SILENT exit; no further menus

ON_ERROR:
  unrecognized_prompt_origin ->
    EMIT "Stop received — no matching route; returning control to user."
    STOP_TURN
```
