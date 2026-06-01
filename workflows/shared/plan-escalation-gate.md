---
name: plan-escalation-gate
description: "Invoke when running the generate Phase 0.1 plan-escalation gate (generate.md only; analyze.md uses its own gate with different thresholds/route)."
purpose: Canonical Phase 0.1 plan-escalation gate for generate.md only; analyze.md uses workflows/analyze/phase-0.1-plan-escalation-gate.md (different thresholds/route).
loaded_by: workflows/generate.md
version: 1.0
---

# Phase 0.1: Plan Escalation Gate

```text
UNIT PlanEscalationGate

PURPOSE:
  Decide whether to hand off to /cf-plan or proceed with native in-workflow
  decomposition based on resolved sub-agent dispatch mode. The estimate is
  informational for this gate.

STATE:
  SUB_AGENT_SESSION_APPROVED: unset | true
    scope: session
  INLINE_FALLBACK: unset | true | false
    scope: workflow_run
  INLINE_FALLBACK_PROBED: false | true
    default: false
    scope: workflow_run
  ESCALATION_ESTIMATE: integer (lines)
    scope: workflow_run

WHEN:
  entering Phase 0.1 of generate workflow

DO:
  SET ESCALATION_ESTIMATE = computed line count

  IF raw-input-overflow rule has already fired for direct prompt/provided-file
  input over 500 lines:
    EMIT raw-input-overflow plan-vs-stop choice (higher precedence — resolve first)
    STOP_TURN

  IF INLINE_FALLBACK_PROBED != true:
    RUN workflows/shared/inline-fallback-probe.md
    CONTINUE PlanEscalationGate (re-evaluate after resolution)

  IF SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false:
    CONTINUE SubAgentDecompositionBypass

  IF INLINE_FALLBACK == unset:
    STOP and surface unresolved INLINE_FALLBACK after inline-fallback-probe.md;
    do not enter NoNativeDispatchPlanHandoff or SubAgentDecompositionBypass.

  IF INLINE_FALLBACK == true OR host.supports_native_subagents == false:
    CONTINUE NoNativeDispatchPlanHandoff

  IF SUB_AGENT_SESSION_APPROVED != true:
    RUN workflows/shared/inline-fallback-probe.md
    CONTINUE PlanEscalationGate (re-evaluate after resolution)

NOTES:
  ESCALATION_ESTIMATE: estimated line count of the current task, derived from
    target file count x average lines per file x cost-per-line heuristic.
  raw-input-overflow rule defined in the calling workflow's Phase 0 raw-input check
    (generate.md Phase 0).
```

```text
UNIT SubAgentDecompositionBypass

PURPOSE:
  Skip plan escalation when sub-agents are approved; defer decomposition
  to Phase 1.5.

RULES:
  - MUST NOT propose /cf-plan when SUB_AGENT_SESSION_APPROVED == true
    AND INLINE_FALLBACK == false
  - MUST compute and log estimate for telemetry:
    "Plan-escalation: estimate={ESCALATION_ESTIMATE} lines, decomposition deferred to Phase 1.5 (sub-agents approved)"
  - MUST NOT emit any user-facing escalation menu
  - MUST proceed to the next phase

NOTES:
  Decomposition is handled in-workflow by workflows/generate/phase-1.5-author-plan.md,
  which always produces an AUTHOR_EXECUTION_PLAN (parallel sub-agent dispatch in
  Phase 4) regardless of estimated size.
```

```text
UNIT NoNativeDispatchPlanHandoff

PURPOSE:
  Prevent local single-context continuation when native sub-agent dispatch is
  unavailable, unset, or explicitly bypassed; route to plan handoff or stop.

WHEN:
  INLINE_FALLBACK == true
  OR host.supports_native_subagents == false

DO:
  REQUIRE estimate of total context from:
    rules.md
    generation-phase dependencies needed for this run
      (e.g. template.md, example.md, checklist.md only when explicitly required before writing)
    expected output size
    project context
    ~30% reasoning overhead

  EMIT_MENU PlanEscalationMenu
  WAIT user.reply
  STOP_TURN

MENU PlanEscalationMenu:
  TITLE: |
    Native sub-agent dispatch is not active for this generate run.
    Estimated context: ~{ESCALATION_ESTIMATE} lines (`rules.md`, active generation dependencies, output, project ctx).

    Local single-context continuation is not allowed as a default. Use /cf-plan
    to decompose this into focused phases, or stop and rerun with native
    sub-agents enabled.

    Options:
    1. Switch to /cf-plan
    2. Stop

    Suggested: 1 because plan decomposition is the safe fallback when native
    sub-agent dispatch is not active.
    Reply with `1` or `2`.
  OPTIONS:
    1 ->
      EMIT "Run /cf-plan generate {KIND} with the same parameters."
      STOP_TURN
    2 ->
      EMIT "Stopped before local single-context generation."
      STOP_TURN
  INVALID:
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST_NOT continue to the next generate phase from this branch
  - MUST treat an unresolved NativeSubAgentPolicyConflictMenu from
    workflows/shared/inline-fallback-probe.md as higher precedence than this
    menu; do not reinterpret that conflict as permission to hand off to /cf-plan
    or continue locally
  - MUST_NOT offer a "continue here" or local single-context option
  - MUST route to /cf-plan handoff or stop
```
