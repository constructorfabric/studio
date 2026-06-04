---
name: analyze-phase-0.1-plan-escalation-gate
description: "Invoke when running Analyze Phase 0.1 to evaluate the analyze-specific plan escalation gate (thresholds and dispatch route differ from generate)."
purpose: Analyze Phase 0.1 — analyze-specific plan escalation gate (thresholds and dispatch route differ from generate)
loaded_by: workflows/analyze.md
version: 1.0
---

# Analyze Phase 0.1 — Plan Escalation Gate

```pdsl
UNIT AnalyzePlanEscalationGate

PURPOSE:
  Evaluate context size estimate and either bypass escalation (sub-agents
  approved) or offer plan escalation to the user.

STATE:
  - SET PLANNER_ESCALATION_RESULT: unset | bypassed | escalated
    default: unset

WHEN:
  - REQUIRE After all Phase 0 dependencies are loaded

DO:
  - REQUIRE raw-input-overflow.md has already fired for direct input over 500 lines:
    - EMIT explicit plan-vs-stop choice from that rule before applying bypass
  - REQUIRE INLINE_FALLBACK == unset:
    - RUN workflows/shared/inline-fallback-probe.md
    - CONTINUE AnalyzePlanEscalationGate (re-evaluate after resolution)
  - REQUIRE SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false:
    - EMIT "Plan-escalation bypassed: estimate={N} lines, decomposition deferred to Phase 2.5 because native sub-agents are already approved for this run."
    - SET PLANNER_ESCALATION_RESULT = bypassed
    - CONTINUE next phase
  - REQUIRE host.supports_native_subagents == true AND SUB_AGENT_SESSION_APPROVED != true AND INLINE_FALLBACK != true:
    - EMIT "Native sub-agents are available but not approved for this analyze run."
    - EMIT "Resolve the Session Sub-Agent Approval Gate or choose inline fallback through workflows/shared/inline-fallback-probe.md before plan escalation."
    - STOP_TURN
  - REQUIRE INLINE_FALLBACK == true OR host.supports_native_subagents == false:
    Estimate total context: rules.md Validation + checklist.md + artifact +
      related cross-refs + expected analysis output + ~30% reasoning overhead
    - EMIT_MENU PlanEscalationMenu
    - WAIT user.reply
    - STOP_TURN

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
  - ALWAYS run this gate before any further Phase-0 or Phase-1 work
  - ALWAYS When CHANGE_REVIEW=true and native-sub-agent approval or inline-fallback
    resolution is still missing, this gate ALWAYS stay fail-closed: it NEVER
    run or narrate local git status/diff, cfs validate, local semantic
    review, findings, summaries, remediation menus, plan-escalation bypass
    text, or plan menus; it may emit only the missing gate menu or the
    matching `Dispatch blocked: ...` error, then ALWAYS STOP_TURN
  - NEVER propose Invoke skill `cf-plan` when SUB_AGENT_SESSION_APPROVED=true AND INLINE_FALLBACK=false
  - ALWAYS apply raw-input-overflow rule at higher precedence than the bypass
  - ALWAYS treat an unresolved NativeSubAgentPolicyConflictMenu from
    workflows/shared/inline-fallback-probe.md as higher precedence than this
    menu; do not reinterpret that conflict as permission to hand off to Invoke skill `cf-plan`
    or continue locally
  - ALWAYS run plan-handoff/stop fallback only when INLINE_FALLBACK=true OR
    host.supports_native_subagents=false
  - ALWAYS When SUB_AGENT_SESSION_APPROVED=true AND INLINE_FALLBACK=false, ALWAYS treat
    the bypass as a resolved state: continue directly to the next phase,
    NEVER emit the fallback menu, and NEVER imply that user confirmation
    is still pending for this run
  - NEVER continue to the next analyze phase from the fallback branch
  - NEVER offer a "continue here" or local single-context option
```
