---
name: inline-fallback-probe
description: "Invoke when any workflow is about to dispatch a cf-* sub-agent to apply the canonical sub-agent approval gate and INLINE_FALLBACK probe rule."
purpose: Canonical sub-agent approval + INLINE_FALLBACK probe rule (citation to SKILL.md)
loaded_by: "workflows/generate.md, workflows/analyze.md, workflows/plan.md, workflows/analyze/phase-0-dependencies.md, workflows/analyze/phase-0-change-review-scope.md, workflows/analyze/phase-2.5-reviewer-plan.md, workflows/generate/phase-0-dependencies.md, workflows/generate/phase-4-write.md, workflows/generate/phase-5/phase-5.2-semantic.md, workflows/generate/phase-5/phase-5.3-findings.md, plus any individual phase file that requires inline-fallback resolution before a sub-agent dispatch"
version: 1.0
---

# Inline Fallback Probe

```pdsl
UNIT InlineFallbackProbe

PURPOSE: Apply the canonical sub-agent approval gate and resolve INLINE_FALLBACK
  before any cf-* sub-agent dispatch; native dispatch is the default when supported.

STATE:
  SUB_AGENT_SESSION_APPROVED: unset | true  default: unset  scope: session
    reset: external-entry handoff re-probes
  INLINE_FALLBACK: unset | true | false     default: unset  scope: workflow_run
  INLINE_FALLBACK_PROBED: false | true      default: false  scope: workflow_run
  NATIVE_SUBAGENT_POLICY_CONFLICT: false | true  default: false  scope: workflow_run

WHEN: any workflow is about to dispatch a cf-* sub-agent

DO:
  REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md § "Session Sub-Agent Approval Gate" is loaded
  REQUIRE {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md is loaded
  IF NATIVE_SUBAGENT_POLICY_CONFLICT == false
     AND native cf-* sub-agents are discoverable or already selected for this workflow
     AND host/tool policy requires explicit delegation before sub-agent tool use
     AND SUB_AGENT_SESSION_APPROVED == unset
     AND INLINE_FALLBACK == unset:
    SET NATIVE_SUBAGENT_POLICY_CONFLICT = true
    EMIT_MENU NativeSubAgentPolicyConflictMenu
    WAIT user.reply
    STOP_TURN
  IF host.supports_native_subagents == true AND SUB_AGENT_SESSION_APPROVED == true:
    SET INLINE_FALLBACK = false
    SET INLINE_FALLBACK_PROBED = true
    RETURN { state: resolved, sub_agent_session_approved: true, inline_fallback: false, resolved_by: "inline-fallback-probe" }
  IF INLINE_FALLBACK == true:
    SET INLINE_FALLBACK_PROBED = true
    RETURN { state: resolved, sub_agent_session_approved: SUB_AGENT_SESSION_APPROVED, inline_fallback: true, resolved_by: "inline-fallback-probe" }
  IF host.supports_native_subagents == true AND SUB_AGENT_SESSION_APPROVED == unset:
    EMIT_MENU SubAgentApprovalMenu
    WAIT user.reply
    STOP_TURN
  IF host.supports_native_subagents == false:
    EMIT_MENU HostNoNativeSubAgentMenu
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST apply SKILL.md § "Session Sub-Agent Approval Gate" then sub-agent-dispatch.md, in that order
  - MUST treat native sub-agent dispatch as the default when the host supports it
  - MUST treat explicit-delegation host-policy conflict as a distinct approval boundary
  - MUST_NOT fall through to HostNoNativeSubAgentMenu when native cf-* agents are discoverable but only policy-blocked pending explicit delegation
  - MUST_NOT let the orchestrator decide to run locally instead of dispatching cf-* sub-agents when native sub-agents are available
  - MUST set INLINE_FALLBACK = false only after SUB_AGENT_SESSION_APPROVED = true is confirmed; no other path may set INLINE_FALLBACK = false
  - MUST set INLINE_FALLBACK = true only when user explicitly selected option 2 in SubAgentApprovalMenu or NativeSubAgentPolicyConflictMenu, or option 1 in HostNoNativeSubAgentMenu
  - MUST_NOT set INLINE_FALLBACK = true from ambiguity, timeout, host UI behavior, or mere absence of reply
  - MUST NOT treat absence of user reply as option 2
  - MUST_NOT default INLINE_FALLBACK = true from missing approval
  - MUST_NOT default INLINE_FALLBACK = false
  - MUST_NOT set INLINE_FALLBACK = false from host capability, ambiguity, or convenience
  - MUST set INLINE_FALLBACK_PROBED = true immediately before every RETURN from this unit
  - MUST_NOT allow any caller to read INLINE_FALLBACK unless this unit returned
    `state: resolved` for the active workflow run
  - MUST treat unresolved native dispatch state as fail-closed and observable:
    emit the active approval menu or matching `Dispatch blocked: ...` error,
    preserve the dispatch manifest/checkpoint fingerprint when one exists,
    then STOP_TURN
  - MUST_NOT allow any INLINE_FALLBACK-gated block or SubAgentDecompositionBypass logic to execute unless INLINE_FALLBACK_PROBED == true
  - MUST emit SubAgentApprovalMenu, NativeSubAgentPolicyConflictMenu, and HostNoNativeSubAgentMenu verbatim as defined in SKILL.md § "Session Sub-Agent Approval Gate"
  - SubAgentApprovalMenu title begins: "Approve sub-agent use for this session"
  - SubAgentApprovalMenu keeps Suggested: 1 as the native-dispatch recommendation
  - MUST_NOT redefine approval-menu title text, options, suggested choices, or option semantics locally
  - MUST treat the approval menu as a hard interaction boundary: STOP_TURN immediately after emitting — do NOT load agent contracts, inspect diffs, dispatch agents, run inline fallback, or emit a [sub-agent-approval] status line in the same response
  - MUST_NOT re-emit NativeSubAgentPolicyConflictMenu after option 2 has
    resolved INLINE_FALLBACK for the active workflow run
  - MUST trim reply and accept the active menu's option numbers when embedded in longer phrases (e.g. "option 1 please")
  - MUST re-probe on external entry from analyze.md into a generate.md phase; SUB_AGENT_SESSION_APPROVED carries across the handoff, INLINE_FALLBACK and INLINE_FALLBACK_PROBED do not
  - MUST_NOT bypass this probe with local host-capability inference
  - MUST_NOT prescribe caller-specific continuation, phase routing, or
    manual-patch handling after resolution; callers own their post-probe flow

ON_ERROR:
  INLINE_FALLBACK == unset at dispatch site ->
    STOP dispatch
    RUN InlineFallbackProbe
    REQUIRE returned.state == resolved
    CONTINUE dispatch site after resolution
  INLINE_FALLBACK_PROBED == false at dispatch site ->
    STOP dispatch
    RUN InlineFallbackProbe
    REQUIRE returned.state == resolved
    CONTINUE dispatch site after resolution
  returned.state != resolved ->
    EMIT "Dispatch blocked: inline fallback probe did not resolve fallback state for this workflow run."
    STOP_TURN

INVARIANTS:
  - MUST NOT execute any INLINE_FALLBACK-gated logic unless INLINE_FALLBACK_PROBED == true
  - MUST NOT set INLINE_FALLBACK = false unless SUB_AGENT_SESSION_APPROVED == true

NOTES:
  Approval menus are defined canonically in skills/studio/SKILL.md — reference
  them there and do not redefine them locally.

  INLINE_FALLBACK_PROBED guards against race conditions: bypass logic MUST check this flag
  before acting on INLINE_FALLBACK value.

  INLINE_FALLBACK-gated dispatch sites:
    workflows/generate/phase-0.7/offer.md
    workflows/generate/phase-0.7/round-loop.md
    workflows/generate/phase-1.5-author-plan.md
    workflows/generate/phase-4-write.md
    workflows/generate/phase-5/phase-5.2-semantic.md
    workflows/generate/phase-5/phase-5.3-findings.md
    workflows/analyze/phase-2-det-gate.md
    workflows/analyze/phase-2.5-reviewer-plan.md

  Single-agent panel mode (rounds[].panel_mode="single-agent") is inherently
  sequential; INLINE_FALLBACK degradation is a no-op for it.

  Canon: {cf-studio-path}/.core/skills/studio/SKILL.md § "Session Sub-Agent
  Approval Gate" and {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md.

  "Native cf-* sub-agents are discoverable or desired for this workflow" means
  the current workflow/phase references a cf-* dispatch path or selected
  planner/author/reviewer contract and the controller can name the relevant
  native agent(s) from the registered native sub-agent set or loaded contract
  inventory.

  This probe resolves state through the canonical approval menus and, on the
  non-menu fast path, RETURNs a resolution struct. The caller owns continuation
  to its own dispatch site, including any later manual-patch routing. Do not
  embed caller-specific routing in this shared unit.
```
