---
cf: true
type: workflow-phase
name: plan-phase-4-finalize
description: "Invoke when cf-plan enters Phase 4 to validate the completed plan, report the result, offer next-steps, and emit the new-chat startup prompt when the user chooses execution handoff."
loaded_by: workflows/plan.md
version: 1.0
---

# Phase 4: Finalize Plan

<!-- toc -->

- [4.1 Validate Plan Before Handoff (MANDATORY)](#41-validate-plan-before-handoff-mandatory)
- [4.2 Report Plan & Offer Next Steps](#42-report-plan--offer-next-steps)
- [New-Chat Startup Prompt](#new-chat-startup-prompt)

<!-- /toc -->

```pdsl
UNIT Phase4Init

PURPOSE:
  Define entry conditions and status model for Phase 4.

WHEN:
  User selected option [1] or [3] in Phase 3.2A
  AND all phase-* files were produced in Phase 3.3

RULES:
  - MUST NOT enter Phase 4 if user selected option [2] or [4] at brief checkpoint
  - MUST NOT emit "Plan created" if run stopped after brief generation or produced only downstream prompts

STATE:
  plan.toml status fields:
    phases[].status: pending | in_progress | done | failed
    plan.execution_status: aggregate phase execution state (independent of lifecycle handling)
    plan.lifecycle_status: plan-file lifecycle state (independent of whether all phases complete)

CONTINUE Phase4StatusMapping
```

```pdsl
UNIT Phase4StatusMapping

PURPOSE:
  Apply the correct execution_status to plan.toml based on current phase states.

DO:
  IF all phases pending:
    SET plan.execution_status = "not_started"
  IF user chose option [4] at brief checkpoint:
    SET plan.execution_status = "briefs_only"
  IF user chose option [2] (only prompts emitted):
    SET plan.execution_status = "prompts_emitted"
  IF any phase in_progress OR done/pending mix:
    SET plan.execution_status = "in_progress"
  IF any phase failed:
    SET plan.execution_status = "failed"
  IF all phases done:
    SET plan.execution_status = "done"

NOTES:
  plan.lifecycle_status may still be ready/partial/in_progress/manual_action_required
  even when plan.execution_status = "done".
```

## 4.1 Validate Plan Before Handoff (MANDATORY)

```pdsl
UNIT Phase4SelfValidation

PURPOSE:
  Self-validate the complete plan against the plan-checklist before offering handoff.

DO:
  OPEN {cf-studio-path}/.core/requirements/plan-checklist.md
  SELF-VALIDATE against plan-checklist.md

  EMIT:
    ═══════════════════════════════════════════════
    Plan Self-Validation: {task-slug}
    ───────────────────────────────────────────────
    | Category                  | Status    |
    |---------------------------|-----------|
    | 1. Structural              | PASS/FAIL |
    | 2. Interactive Questions   | PASS/FAIL |
    | 3. Rules Coverage          | PASS/FAIL |
    | 4. Context Completeness    | PASS/FAIL |
    | 5. Phase Independence      | PASS/FAIL |
    | 6. Budget Compliance       | PASS/FAIL |
    | 7. Lifecycle & Handoff     | PASS/FAIL |
    Overall: PASS/FAIL
    ═══════════════════════════════════════════════

  IF any category FAIL:
    LIST issues
    OFFER to fix them

RULES:
  - MUST run self-validation before generating the startup prompt or offering execution handoff
```

## 4.2 Report Plan & Offer Next Steps

```pdsl
UNIT Phase4ReportPlan

PURPOSE:
  Report plan creation and present the appropriate next-steps menu.

WHEN:
  All validation categories PASS

DO:
  EMIT:
    Plan created: {cf-studio-path}/.plans/{task-slug}/
      Phases: {N}
      Files: {file_count}
      Lifecycle: {lifecycle}

  EMIT:
    Delegation prompt:
      I have a Constructor Studio execution plan ready at:
        {cf-studio-path}/.plans/{task-slug}

      Please delegate this plan to ralphex using Constructor Studio's native delegation flow.

  IF SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false:
    EMIT:
      Native execution options available:
        This plan can be delegated to ralphex using Constructor Studio's native delegation feature.
        Command: {cfs_cmd} delegate "{cf-studio-path}/.plans/{task-slug}"

      Native phase execution prompt:
        I have a Constructor Studio execution plan ready at:
          {cf-studio-path}/.plans/{task-slug}/plan.toml

        Please execute the next phase using Constructor Studio's native phase runner.

    EMIT_MENU Phase4NextStepsNative
    WAIT user.reply
    STOP_TURN

  ELSE:
    EMIT:
      Same-chat native phase execution is not currently available in this run.
      If the user later asks to execute a phase in this chat, re-run
      `workflows/shared/inline-fallback-probe.md` first. Offer native phase-runner
      execution only if that re-probe resolves to `SUB_AGENT_SESSION_APPROVED=true`
      and `INLINE_FALLBACK=false`; otherwise keep to validation/review/handoff paths.

    EMIT_MENU Phase4NextStepsFallback
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST emit "Plan created" only after Phase 3.4 PASS confirms plan.toml, every brief-*, and every compiled phase-* file already exist on disk
  - MUST wait for user choice before generating any startup prompt

MENU Phase4NextStepsNative:
  TITLE: What would you like to do next? (native execution available)
  PREAMBLE:
    The plan passed self-validation. Choose your next action:
  OPTIONS:
    1 -> CONTINUE Phase4AnalyzePlan
         (Suggested default before execution — verify the plan thoroughly with Invoke skill `cf-analyze`)
    2 -> CONTINUE Phase4NativePhaseDispatch
         (Start executing the first phase now in this chat with the native phase runner)
    3 -> CONTINUE Phase4EmitStartupPrompt
         (Generate a handoff prompt for a separate execution chat)
    4 -> CONTINUE Phase4ReviewPlanFiles
         (Inspect the plan files manually before deciding what to do next)
    5 -> CONTINUE Phase4ModifyPlan
         (Rework the plan structure or contents before execution)
  PREAMBLE_REPLY: Reply with `1`, `2`, `3`, `4`, or `5`.
  INVALID:
    EMIT "Reply with 1, 2, 3, 4, or 5."
    WAIT user.reply
    STOP_TURN

MENU Phase4NextStepsFallback:
  TITLE: What would you like to do next? (native execution unavailable)
  PREAMBLE:
    The plan passed self-validation. Choose your next action:
  OPTIONS:
    1 -> CONTINUE Phase4AnalyzePlan
         (Suggested default before execution — verify the plan thoroughly with Invoke skill `cf-analyze`)
    2 -> CONTINUE Phase4EmitStartupPrompt
         (Generate a handoff prompt for a separate execution chat)
    3 -> CONTINUE Phase4ReviewPlanFiles
         (Inspect the plan files manually before deciding what to do next)
    4 -> CONTINUE Phase4ModifyPlan
         (Rework the plan structure or contents before execution)
  PREAMBLE_REPLY: Reply with `1`, `2`, `3`, or `4`.
  INVALID:
    EMIT "Reply with 1, 2, 3, or 4."
    WAIT user.reply
    STOP_TURN
```

```pdsl
UNIT Phase4AnalyzePlan

PURPOSE:
  Route the completed plan into analyze review after the user chooses
  validation from the Phase 4 next-steps menu.

DO:
  CONTINUE workflows/analyze.md
  WITH:
    target_paths = ["{cf-studio-path}/.plans/{task-slug}/plan.toml"]
    cross_refs = ["{cf-studio-path}/.plans/{task-slug}/phase-*.md"]
    work_request = "Validate the completed execution plan before execution."
```

```pdsl
UNIT Phase4ReviewPlanFiles

PURPOSE:
  Show the concrete plan files to inspect and wait for the user's next action.

DO:
  EMIT "Review plan files at {cf-studio-path}/.plans/{task-slug}/. Reply with `execute`, `handoff`, `validate`, or a specific file/change request."
  WAIT user.reply
  STOP_TURN
```

```pdsl
UNIT Phase4ModifyPlan

PURPOSE:
  Route requested plan modifications back to the plan workflow instead of
  ending after advice text.

DO:
  EMIT "Describe the plan change you want: add/remove phases, adjust scope, or update specific phase files."
  WAIT user.reply
  STOP_TURN
```

## New-Chat Startup Prompt

```pdsl
UNIT Phase4NativePhaseDispatch

PURPOSE:
  Dispatch the phase runner for native same-chat phase execution (option [2] native menu).

DO:
  OPEN {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
  RE-RUN inline-fallback-probe.md immediately before dispatch
    (do NOT trust the earlier menu state; INLINE_FALLBACK is re-derived per workflow run)

  IF re-probe stops for approval:
    STOP_TURN

  IF re-probe resolves to INLINE_FALLBACK == true:
    EMIT "Same-chat native execution is unavailable for this turn."
    FALL BACK to Phase4NextStepsFallback choices
    STOP_TURN

  IF SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false:
    SET CF_PHASE_GATE = released_for_dispatch
    DISPATCH {cf-studio-path}/.core/skills/studio/agents/cf-phase-runner.md
      with payload:
        plan_dir = "{cf-studio-path}/.plans/{task-slug}/"
        target_phase = 1
        git_commit_mode = GIT_COMMIT_MODE
        contributing_guide = CONTRIBUTING_GUIDE
        git_constraint = mode-matched constraint block from workflows/generate/phase-4-write.md § Git constraint blocks
    ACCEPT only concise execution summary defined by the agent contract
    SET CF_PHASE_GATE = armed  (immediately after phase-runner returns — success, error, or no-response)

RULES:
  - MUST NOT dispatch without a successful re-probe of inline-fallback-probe.md
  - MUST set CF_PHASE_GATE = released_for_dispatch immediately before dispatch
  - MUST reset CF_PHASE_GATE = armed immediately after dispatch returns
  - Dispatch payload MUST include plan_dir, target_phase, git_commit_mode, contributing_guide, and git_constraint
```

```pdsl
UNIT Phase4EmitStartupPrompt

PURPOSE:
  Emit the new-chat startup prompt for execution handoff
  ([3] in native-available menu, [2] in native-unavailable menu).

DO:
  EMIT exactly the following inside a single fenced code block:

    I have a Constructor Studio execution plan ready at:
      {cf-studio-path}/.plans/{task-slug}/plan.toml

    Please read the plan manifest, then execute Phase 1.
    The phase file is self-contained — follow its instructions exactly.
    After completion, report results and generate the prompt for Phase 2.

RULES:
  - MUST wrap startup prompt in a single fenced code block
  - MUST NOT mix explanatory text into that code fence
```
