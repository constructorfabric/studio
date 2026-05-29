---
name: generate-phase-1-collect
description: "Invoke when the generate workflow enters Phase 1 to dispatch the collector sub-agent, manage the edit-iteration loop, and await final input approval."
purpose: Generate Phase 1 — collector dispatch contract, edit-iteration loop, COLLECTOR_MAX_ITER handling
loaded_by: workflows/generate.md
version: 1.0
---

<!-- toc -->

- [Phase 1: Collect Information](#phase-1-collect-information)

<!-- /toc -->

## Phase 1: Collect Information

```text
UNIT Phase1CollectInformation

PURPOSE:
  Dispatch collector sub-agent, manage edit-iteration loop, await final approval.

DO:
  REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before dispatch
  DISPATCH cf-generate-collector with JSON contract from
    {cf-studio-path}/.core/skills/studio/agents/cf-generate-collector.md
  WITH orchestrator-supplied values:
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
    NOTE: stored_proposed_inputs is the ONLY authoritative Phase 1 state for Phase 4

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
      MERGE user modifications into stored_proposed_inputs
      RE-DISPATCH cf-generate-collector with:
        same full Inputs field set (kind, name, rules_mode, system,
        template_path, example_path, kit_rules_path, open_questions
        all carried over unchanged)
        ONLY pre_resolved_inputs updated to merged stored_proposed_inputs
      RECEIVE refreshed Inputs block
      REPLACE stored_proposed_inputs with refreshed proposed_inputs JSON
      DECREMENT COLLECTOR_MAX_ITER budget
      IF COLLECTOR_MAX_ITER exhausted:
        STOP
        EMIT BLOCKED status with partial Inputs block
        STOP_TURN
      ELSE:
        CONTINUE Phase1EditLoop

RULES:
  - MUST show Inputs markdown to user verbatim
  - MUST persist returned JSON as stored_proposed_inputs
  - MUST replace stored_proposed_inputs on every collector return before showing
    next edit/approval prompt
  - MUST use final approved stored_proposed_inputs in Phase 4 (not earlier display copy)
  - MUST NOT skip questions, assume answers, or proceed without explicit approve all
  - MUST stop and surface BLOCKED on COLLECTOR_MAX_ITER exhaustion — MUST NOT
    auto-proceed to Phase 3
  - MUST NOT enter Phase 3 until AUTHOR_PLAN_OFFER_RESOLVED is set by Phase 1.5
  - COLLECTOR_MAX_ITER defaults to 5; mirrors Phase 5 MAX_ITER default
  - Collector MUST propose specific answers and use project context
  - Orchestrator MUST require final confirmation
```
