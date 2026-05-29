---
name: inline-fallback-probe
description: "Invoke when any workflow is about to dispatch a cf-* sub-agent to apply the canonical sub-agent approval gate and INLINE_FALLBACK probe rule."
purpose: Canonical sub-agent approval + INLINE_FALLBACK probe rule (citation to SKILL.md)
loaded_by: "workflows/generate.md, workflows/analyze.md, workflows/plan.md, workflows/analyze/phase-0-dependencies.md, workflows/analyze/phase-0-change-review-scope.md, workflows/analyze/phase-2.5-reviewer-plan.md, workflows/generate/phase-0-dependencies.md, workflows/generate/phase-4-write.md, workflows/generate/phase-5/phase-5.2-semantic.md, workflows/generate/phase-5/phase-5.3-findings.md, plus any individual phase file that requires inline-fallback resolution before a sub-agent dispatch"
version: 1.0
---

```text
UNIT InlineFallbackProbe

PURPOSE:
  Apply the canonical sub-agent approval gate and resolve INLINE_FALLBACK
  before any cf-* sub-agent dispatch.

STATE:
  SUB_AGENT_SESSION_APPROVED: unset | true
    default: unset
    scope: session
    reset: external-entry handoff re-probes

  INLINE_FALLBACK: unset | true | false
    default: unset
    scope: workflow_run (NOT carried across workflow runs)

WHEN:
  any workflow is about to dispatch a cf-* sub-agent

DO:
  REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md § "Session Sub-Agent Approval Gate" is loaded
  REQUIRE `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md` is loaded
  IF host.supports_native_subagents == true AND SUB_AGENT_SESSION_APPROVED == unset:
    EMIT_MENU SubAgentApprovalMenu
    WAIT user.reply
    STOP_TURN

MENU SubAgentApprovalMenu:
  TITLE: Approve sub-agent use for this session (reply 1 or 2)
  OPTIONS:
    1 ->
      SET SUB_AGENT_SESSION_APPROVED = true
      SET INLINE_FALLBACK = false
      RETURN { sub_agent_session_approved: true, inline_fallback: false }
    2 ->
      SET INLINE_FALLBACK = true
      RETURN { sub_agent_session_approved: false, inline_fallback: true }
  INVALID:
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST apply SKILL.md § "Session Sub-Agent Approval Gate" then `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`, in that order
  - MUST emit SubAgentApprovalMenu verbatim as defined in SKILL.md § "Session Sub-Agent Approval Gate"
    (option 1 = native sub-agents + remember for session, Suggested: 1;
     option 2 = inline fallback for this workflow)
  - MUST treat the approval menu as a hard interaction boundary:
    STOP_TURN immediately after emitting — do NOT load agent contracts,
    inspect diffs, dispatch agents, run inline fallback, or emit
    a [sub-agent-approval] status line in the same response
  - MUST NOT treat absence of user reply as option 2
  - MUST NOT set INLINE_FALLBACK = true from ambiguity, timeout, host UI
    behavior, or the mere fact the prompt was printed
  - MUST re-prompt and remain blocked when user reply is not exactly 1 or 2
    (after trimming)
  - MUST set INLINE_FALLBACK before any dispatch site or any
    INLINE_FALLBACK-gated block fires
  - MUST_NOT default INLINE_FALLBACK = false from host capability, ambiguity,
    or convenience
  - MUST_NOT default INLINE_FALLBACK = true from missing approval when host
    can ask
  - MUST set INLINE_FALLBACK = false only after SUB_AGENT_SESSION_APPROVED = true
  - MUST set INLINE_FALLBACK = true only when user explicitly replied 2
    OR host has no native sub-agent support
  - MUST re-probe on external entry from analyze.md into a generate.md phase;
    SUB_AGENT_SESSION_APPROVED carries across the handoff, INLINE_FALLBACK does not
  - MUST_NOT bypass this probe with local host-capability inference.

ON_ERROR:
  INLINE_FALLBACK == unset at dispatch site ->
    STOP dispatch
    RUN InlineFallbackProbe
    RETURN { state: resolved }
    CONTINUE dispatch site after resolution

NOTES:
  INLINE_FALLBACK-gated dispatch sites:
    workflows/generate/phase-0.7/offer.md (brainstorm offer)
    workflows/generate/phase-0.7/round-loop.md (sequential degradation)
    workflows/generate/phase-1.5-author-plan.md (planner dispatch / planned parallelism)
    workflows/generate/phase-4-write.md (Phase 4 author dispatch)
    workflows/generate/phase-5/phase-5.2-semantic.md (long-loop warning)
    workflows/generate/phase-5/phase-5.3-findings.md (Phase 5.3 inline write)
    workflows/analyze/phase-2-det-gate.md (deterministic validator dispatch)
    workflows/analyze/phase-2.5-reviewer-plan.md (reviewer plan sub-agent dispatch)

  Single-agent panel mode (rounds[].panel_mode="single-agent") is inherently
  sequential; INLINE_FALLBACK degradation is a no-op for it.

  Canon: {cf-studio-path}/.core/skills/studio/SKILL.md § "Session Sub-Agent
  Approval Gate" and {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md.

  This probe RETURNs a resolution struct; the caller owns continuation to its
  own dispatch site. Do not embed caller-specific routing in this shared unit.
```
