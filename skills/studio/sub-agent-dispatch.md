---
description: "Invoke when about to dispatch a cf-* sub-agent — applies dispatch protocol and selects Mode A (native) or Mode B (inline)."
---

# Sub-Agent Dispatch

Workflows reference named `cf-*` sub-agents. Each agent prompt source lives in
`{cf-studio-path}/.core/skills/studio/agents/<name>.md` and is read by the
controller as orchestration-time guidance for generating the final dispatch
prompt.

Mode A: when native dispatch is approved for this session, the controller loads
the agent prompt source, synthesizes a final task-specific dispatch prompt from
that source plus `SHARED_CONTEXT_PACK`, then dispatches the named agent and
consumes its declared output.

Mode B: when the user explicitly declined native dispatch for this session or
the host has no native sub-agent support, inline the named agent prompt source:
open and follow the agent file, use it as orchestration guidance to synthesize
the final task-specific prompt, satisfy its Response Completion Gate, and
return the declared output shape. If the named agent file has no explicit
Response Completion Gate section, apply the default completion criterion:
return the full declared output shape with no required field empty or null.

Synthesis invariants:
- Final dispatch prompt synthesis MUST be lossless with respect to required semantics in the source prompt.
- The controller MUST carry forward all mandatory input fields, output fields, invariants, enums, row schemas, completion gates, and invalid-output conditions from the source prompt.
- The controller MUST_NOT replace a normative schema or invariant block with a loose prose summary when doing so could omit required fields or behavioral constraints.
- If a source prompt defines required per-row or per-item fields, the final dispatch prompt MUST restate those requirements explicitly.
- If the controller cannot preserve the required semantics without ambiguity, it MUST include the stricter source-side rules verbatim or near-verbatim rather than compressing further.

Pre-dispatch discipline:
- First apply the Session Sub-Agent Approval Gate in `{cf-studio-path}/.core/skills/studio/SKILL.md`.
- Probe once per workflow run for INLINE_FALLBACK; SUB_AGENT_SESSION_APPROVED carries across runs in the same chat session (see `{cf-studio-path}/.core/skills/studio/SKILL.md` § Session Sub-Agent Approval Gate for the canonical probe semantics). INLINE_FALLBACK does NOT carry across workflow runs — it is re-derived from SUB_AGENT_SESSION_APPROVED at the start of each workflow run and MUST NOT be inherited from a prior run's resolved value.
- Never switch modes silently mid-workflow. If a mid-workflow re-probe (triggered by an external-entry handoff or unset INLINE_FALLBACK at a dispatch site) yields a different result from the prior probe (Mode A → Mode B or vice versa), the orchestrator MUST surface the change to the user before continuing.
- If a dispatch site finds `INLINE_FALLBACK` unset, stop and run
  `workflows/shared/inline-fallback-probe.md`.

When `INLINE_FALLBACK=true`, the orchestrator MUST warn the user before entering
any of these high-risk dispatch contexts (brainstorm fan-out, long review loops,
generate-author writes, deterministic-validator subprocess context). The warning
MUST state which guarantees are reduced: parallelism, context isolation,
subprocess separation. Workflows specify the exact warning text inline at the
dispatch site; if no inline text is provided, use this canonical wording:
"Inline-fallback mode active — isolation, parallelism, and subprocess separation
guarantees are reduced for this dispatch. Continue? [y/n]" Affirmative replies (matched case-insensitively after whitespace trim): "y" or "yes". Any other reply is non-affirmative.

If the user replies "n" (or any non-affirmative), abort the dispatch and offer the user the choice of (a) retry with inline-fallback acknowledged, (b) switch back to the parent workflow's plan-escalation menu, or (c) stop. Do not silently continue.

## Registered native sub-agent set & INLINE_FALLBACK_THIS_ROUND

The **registered native sub-agent set** is the set of `cf-*` sub-agents the host has loaded into its dispatch tool list for the current chat session. The orchestrator determines membership by:

1. **Announced-list method (preferred):** when the host announces its tool list at session start (Claude Code's tool registry, OpenAI Assistant tools field, etc.), the orchestrator inspects that list and treats any `cf-*` name present in it as registered.
2. **Probe-by-tool-presence method (fallback):** when no announced list is available, the orchestrator treats any agent referenced by name in a `Skill` / `Agent`-style tool definition surfaced to it as registered, and all others as unregistered.

When neither method can resolve membership, the orchestrator MUST default to treating the agent as **unregistered**, surface the availability menu, and rely on the user's selection (inline / mode-switch / abort) rather than attempting a probe dispatch that would consume `SUB_AGENT_SESSION_APPROVED` capacity without authorization.

**`INLINE_FALLBACK_THIS_ROUND`** is an iteration-scoped flag, distinct from the session-level `INLINE_FALLBACK` defined above. Lifecycle:

- **Scope:** one round of the brainstorm loop (or any caller-defined unit of work that documents the same scope).
- **Default:** `false` at the start of every round.
- **Set:** only by the calling workflow's availability-check recovery menu when the user selects the "inline this round" option.
- **Cleared:** automatically by the calling workflow at the start of the next iteration; the orchestrator MUST NOT carry the flag across iterations.
- **Precedence:** when `INLINE_FALLBACK_THIS_ROUND=true`, the round uses Mode B (inlined contract) regardless of the session-level `INLINE_FALLBACK` value. When `INLINE_FALLBACK_THIS_ROUND=false`, the session-level `INLINE_FALLBACK` governs the round.

Calling workflows are responsible for clearing the flag between iterations; this file documents only the semantics.
