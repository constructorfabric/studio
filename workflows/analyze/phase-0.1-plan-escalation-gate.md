---
name: analyze-phase-0.1-plan-escalation-gate
description: "Invoke when running Analyze Phase 0.1 to evaluate the analyze-specific plan escalation gate (thresholds and dispatch route differ from generate)."
purpose: Analyze Phase 0.1 — analyze-specific plan escalation gate (thresholds and dispatch route differ from generate)
loaded_by: workflows/analyze.md
version: 1.0
---

# Analyze Phase 0.1 — Plan Escalation Gate

```text
UNIT AnalyzePlanEscalationGate

PURPOSE:
  Evaluate context size estimate and either bypass escalation (sub-agents
  approved) or offer plan escalation to the user.

STATE:
  PLANNER_ESCALATION_RESULT: unset | bypassed | escalated
    default: unset

WHEN:
  After all Phase 0 dependencies are loaded

DO:
  IF raw-input-overflow.md has already fired for direct input over 500 lines:
    EMIT explicit plan-vs-stop choice from that rule before applying bypass
  IF INLINE_FALLBACK == unset:
    RUN workflows/shared/inline-fallback-probe.md
    CONTINUE AnalyzePlanEscalationGate (re-evaluate after resolution)
  IF SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false:
    EMIT "Plan-escalation: estimate={N} lines, decomposition deferred to Phase 2.5 (sub-agents approved)"
    SET PLANNER_ESCALATION_RESULT = bypassed
    CONTINUE next phase
  IF INLINE_FALLBACK == true OR host.supports_native_subagents == false:
    Estimate total context: rules.md Validation + checklist.md + artifact +
      related cross-refs + expected analysis output + ~30% reasoning overhead
    EMIT_MENU PlanEscalationMenu
    WAIT user.reply
    STOP_TURN

MENU PlanEscalationMenu:
  TITLE: |
    Native sub-agent dispatch is not active for this analyze run.
    Estimated context needed: ~{N} lines:
      - checklist.md:  ~{n} lines
      - rules.md:      ~{n} lines
      - artifact:      ~{n} lines
      - cross-refs:    ~{n} lines
      - output:        ~{n} lines (estimated)

    Local single-context analysis is not allowed as a default.
    The plan workflow can decompose this into focused analysis phases (≤500 lines each)
    that ensure every checklist item is checked and nothing is skipped.

    Suggested: 1 because plan decomposition is the safe fallback when native
    sub-agent dispatch is not active.
  OPTIONS:
    1 -> SET PLANNER_ESCALATION_RESULT = escalated
         EMIT "Switch to Invoke skill `cf-plan` to analyze {KIND} with the same parameters."
         STOP_TURN
    2 -> EMIT "Stopped before local single-context analysis."
         STOP_TURN
  INVALID:
    EMIT "Reply 1 or 2."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST run this gate before any further Phase-0 or Phase-1 work
  - When CHANGE_REVIEW=true and native-sub-agent approval or inline-fallback
    resolution is still missing, this gate MUST stay fail-closed: it MUST_NOT
    run or narrate local git status/diff, cfs validate, local semantic
    review, findings, summaries, remediation menus, plan-escalation bypass
    text, or plan menus; it MAY emit only the missing gate menu or the
    matching `Dispatch blocked: ...` error, then MUST STOP_TURN
  - MUST_NOT propose Invoke skill `cf-plan` when SUB_AGENT_SESSION_APPROVED=true AND INLINE_FALLBACK=false
  - MUST apply raw-input-overflow rule at higher precedence than the bypass
  - MUST treat an unresolved NativeSubAgentPolicyConflictMenu from
    workflows/shared/inline-fallback-probe.md as higher precedence than this
    menu; do not reinterpret that conflict as permission to hand off to Invoke skill `cf-plan`
    or continue locally
  - MUST run plan-handoff/stop fallback only when INLINE_FALLBACK=true OR
    host.supports_native_subagents=false
  - MUST_NOT continue to the next analyze phase from the fallback branch
  - MUST_NOT offer a "continue here" or local single-context option
```
