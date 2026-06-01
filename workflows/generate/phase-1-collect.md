---
name: generate-phase-1-collect
description: "Invoke when the generate workflow enters Phase 1 to dispatch the collector sub-agent, manage the edit-iteration loop, and await final input approval."
purpose: Generate Phase 1 — collector dispatch contract, edit-iteration loop, COLLECTOR_MAX_ITER handling
loaded_by: workflows/generate.md
version: 1.0
---

# Phase 1: Collect Information

```text
UNIT Phase1CollectInformation

PURPOSE:
  Dispatch collector sub-agent, manage edit-iteration loop, await final approval.

STATE:
  COLLECTOR_MAX_ITER: integer  default: 5  scope: phase

DO:
  IF COLLECTOR_MAX_ITER unset:
    SET COLLECTOR_MAX_ITER = 5
  REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before dispatch
  LOAD {cf-studio-path}/.core/skills/studio/agents/cf-generate-collector.md
    as the collector source contract
  SYNTHESIZE final dispatch prompt from the loaded collector contract plus
    SHARED_CONTEXT_PACK and the payload below
  IF collector source contract is not loaded, unreadable, ambiguous, or not
     reflected in the final dispatch prompt:
    FAIL per sub-agent-dispatch.md § Contract-read-and-use gate
    FORBID dispatch
  DISPATCH cf-generate-collector with the synthesized final prompt and
    orchestrator-supplied payload:
    kind = {KIND}
    name = {name}
    rules_mode = {STRICT|RELAXED}
    system = from Phase 0.5
    template_path = resolved from rules.md
    example_path = resolved from rules.md
    kit_rules_path = resolved from rules.md
    pre_resolved_inputs = state.decisions from Phase 0.7 (or {} when skipped)
    open_questions = state.open_questions from Phase 0.7 (or [] when skipped)

  RECEIVE Inputs markdown block (show to user verbatim) + proposed_inputs JSON block
  PERSIST returned JSON as stored_proposed_inputs

  EMIT_MENU Phase1EditLoop
  WAIT user.reply
  STOP_TURN

MENU Phase1EditLoop:
  TITLE: Input approval loop
  OPTIONS:
    approve all ->
      EMIT "Inputs confirmed. Proceeding to author planning..."
      CONTINUE workflows/generate/phase-1.5-author-plan.md
    per-item edits ->
      IF COLLECTOR_MAX_ITER exhausted:
        EMIT BLOCKED status with current stored_proposed_inputs
        STOP_TURN
      MERGE user modifications into stored_proposed_inputs
      LOAD {cf-studio-path}/.core/skills/studio/agents/cf-generate-collector.md
        fresh as the collector source contract for this re-dispatch
      SYNTHESIZE final dispatch prompt from the loaded collector contract plus
        SHARED_CONTEXT_PACK and the updated payload
      IF collector source contract is missing, unreadable, ambiguous, or not
         reflected in the final prompt:
        FAIL per sub-agent-dispatch.md § Contract-read-and-use gate
        FORBID re-dispatch
      RE-DISPATCH cf-generate-collector with the synthesized final prompt and
        updated payload:
        same full Inputs field set (kind, name, rules_mode, system,
        template_path, example_path, kit_rules_path, open_questions
        all carried over unchanged)
        ONLY pre_resolved_inputs updated to merged stored_proposed_inputs
      RECEIVE refreshed Inputs block
      REPLACE stored_proposed_inputs with refreshed proposed_inputs JSON
      DECREMENT COLLECTOR_MAX_ITER
      IF COLLECTOR_MAX_ITER exhausted:
        EMIT refreshed Inputs block
        EMIT BLOCKED status with partial Inputs block
        STOP_TURN
      ELSE:
        EMIT refreshed Inputs block
        CONTINUE Phase1EditLoop

RULES:
  - MUST show Inputs markdown to user verbatim
  - MUST apply sub-agent-dispatch.md § Contract-read-and-use gate before
    initial collector dispatch and every collector re-dispatch
  - MUST persist returned JSON as stored_proposed_inputs
  - MUST replace stored_proposed_inputs on every collector return before showing
    next edit/approval prompt
  - MUST use final approved stored_proposed_inputs in Phase 4 (not earlier display copy)
  - MUST NOT skip questions, assume answers, or proceed without explicit approve all
  - MUST stop and surface BLOCKED on COLLECTOR_MAX_ITER exhaustion
  - MUST NOT auto-proceed to Phase 3 on COLLECTOR_MAX_ITER exhaustion
  - MUST NOT enter Phase 3 until AUTHOR_PLAN_OFFER_RESOLVED is set by Phase 1.5
  - Collector MUST propose specific answers and use project context
  - Orchestrator MUST require final confirmation

NOTES:
  stored_proposed_inputs is the ONLY authoritative Phase 1 state for Phase 4.
  COLLECTOR_MAX_ITER default of 5 mirrors the Phase 5 MAX_ITER default.
```
