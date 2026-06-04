---
name: plan-escalation-gate
description: "Invoke when running the generate Phase 0.1 plan-escalation gate (generate.md only; analyze.md uses its own gate with different thresholds/route)."
purpose: Canonical Phase 0.1 plan-escalation gate for generate.md only; analyze.md uses workflows/analyze/phase-0.1-plan-escalation-gate.md (different thresholds/route).
loaded_by: workflows/generate.md
version: 1.0
---

# Phase 0.1: Plan Escalation Gate

```pdsl
UNIT PlanEscalationGate

PURPOSE:
  Decide whether to hand off to Invoke skill `cf-plan` or proceed with native in-workflow
  decomposition based on resolved sub-agent dispatch mode. The estimate is
  informational for this gate.

STATE:
  - SET SUB_AGENT_SESSION_APPROVED: unset | true
    scope: session
  - SET INLINE_FALLBACK: unset | true | false
    scope: workflow_run
  - SET INLINE_FALLBACK_PROBED: false | true
    default: false
    scope: workflow_run
  - SET ESCALATION_ESTIMATE: integer (lines)
    scope: workflow_run

WHEN:
  - REQUIRE entering Phase 0.1 of generate workflow

DO:
  - SET ESCALATION_ESTIMATE = computed line count

  - REQUIRE raw-input-overflow rule has already fired for direct prompt/provided-file
  - RUN input over 500 lines:
    - EMIT raw-input-overflow plan-vs-stop choice (higher precedence — resolve first)
    - STOP_TURN

  - REQUIRE INLINE_FALLBACK_PROBED != true:
    - RUN workflows/shared/inline-fallback-probe.md
    - CONTINUE PlanEscalationGate (re-evaluate after resolution)

  - REQUIRE INLINE_FALLBACK_PROBED == true
     AND INLINE_FALLBACK == false
     AND SUB_AGENT_SESSION_APPROVED != true:
    FAIL_FAST invariant violation:
      INLINE_FALLBACK=false is allowed only when INLINE_FALLBACK_PROBED=true
      and SUB_AGENT_SESSION_APPROVED=true; the inline-fallback probe NEVER
      leave or flip to SUB_AGENT_SESSION_APPROVED!=true with INLINE_FALLBACK=false.
    SURFACE invalid state and STOP before retrying plan escalation.

  - REQUIRE SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false:
    - CONTINUE SubAgentDecompositionBypass

  - REQUIRE INLINE_FALLBACK == unset:
    STOP and surface unresolved INLINE_FALLBACK after inline-fallback-probe.md;
    do not enter NoNativeDispatchPlanHandoff or SubAgentDecompositionBypass.

  - REQUIRE INLINE_FALLBACK == true OR host.supports_native_subagents == false:
    - CONTINUE NoNativeDispatchPlanHandoff

NOTES:
  ESCALATION_ESTIMATE: estimated line count of the current task, derived from
    target file count x average lines per file x cost-per-line heuristic.
  raw-input-overflow rule defined in the calling workflow's Phase 0 raw-input check
    (generate.md Phase 0).
```

```pdsl
UNIT SubAgentDecompositionBypass

PURPOSE:
  Skip plan escalation when sub-agents are approved; defer decomposition
  to Phase 1.5.

RULES:
  - NEVER propose Invoke skill `cf-plan` when SUB_AGENT_SESSION_APPROVED == true
    AND INLINE_FALLBACK == false
  - ALWAYS compute and log estimate for telemetry:
    "Plan-escalation: estimate={ESCALATION_ESTIMATE} lines, decomposition deferred to Phase 1.5 (sub-agents approved)"
  - NEVER emit any user-facing escalation menu
  - ALWAYS proceed to the next phase

NOTES:
  Decomposition is handled in-workflow by workflows/generate/phase-1.5-author-plan.md,
  which always produces an AUTHOR_EXECUTION_PLAN (parallel sub-agent dispatch in
  Phase 4) regardless of estimated size.
```

```pdsl
UNIT NoNativeDispatchPlanHandoff

PURPOSE:
  Prevent local single-context continuation when native sub-agent dispatch is
  unavailable, unset, or explicitly bypassed; route to plan handoff, stop, or
  an inline continuation when the user explicitly chooses it.

WHEN:
  - REQUIRE INLINE_FALLBACK == true
  - OR host.supports_native_subagents == false

DO:
  - REQUIRE estimate of total context from:
    rules.md
    generation-phase dependencies needed for this run
      (e.g. template.md, example.md, checklist.md only when explicitly required before writing)
    expected output size
    project context
    ~30% reasoning overhead

  - EMIT_MENU PlanEscalationMenu
  - WAIT user.reply
  - STOP_TURN

MENU PlanEscalationMenu:
  TITLE: |
    Native sub-agent dispatch is not active for this generate run.
    Estimated context: ~{ESCALATION_ESTIMATE} lines (`rules.md`, active generation dependencies, output, project ctx).

    Local single-context continuation is not allowed as a default. Use Invoke skill `cf-plan`
    to decompose this into focused phases, or stop and rerun with native
    sub-agents enabled. You may also choose to continue inline — that is your
    explicit decision, not a default.

    Options:
    1. Switch to Invoke skill `cf-plan`
    2. Stop
    3. Continue inline

    Suggested: 1 because plan decomposition is the safe fallback when native
    sub-agent dispatch is not active.
    Reply with `1`, `2`, or `3`.
  OPTIONS:
    1 ->
      EMIT "Invoke skill `cf-plan` to generate {KIND} with the same parameters."
      STOP_TURN
    2 ->
      EMIT "Stopped before local single-context generation."
      STOP_TURN
    3 ->
      EMIT "Proceeding inline at your request."
      CONTINUE next generate phase
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN

RULES:
  - NEVER continue to the next generate phase from this branch automatically or
    by default; continue inline ONLY when the user explicitly selects option 3
  - ALWAYS treat an unresolved NativeSubAgentPolicyConflictMenu from
    workflows/shared/inline-fallback-probe.md as higher precedence than this
    menu; do not reinterpret that conflict as permission to hand off to Invoke skill `cf-plan`
    or continue locally
  - NEVER offer an automatic or default "continue here" / local single-context option
  - ALWAYS route to one of three options: Invoke skill `cf-plan` handoff, stop,
    or user-confirmed inline continuation (option 3)
```
