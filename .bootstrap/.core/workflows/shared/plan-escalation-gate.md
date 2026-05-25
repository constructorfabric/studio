---
name: plan-escalation-gate
description: "Invoke when running the generate Phase 0.1 plan-escalation gate (generate.md only; analyze.md uses its own gate with different thresholds/route)."
purpose: Canonical Phase 0.1 plan-escalation gate for generate.md only; analyze.md uses workflows/analyze/phase-0.1-plan-escalation-gate.md (different thresholds/route).
loaded_by: workflows/generate.md
version: 1.0
---

## Phase 0.1: Plan Escalation Gate

### Sub-Agent Decomposition Bypass

When `SUB_AGENT_SESSION_APPROVED=true` AND `INLINE_FALLBACK=false`, this gate **MUST NOT** propose `/cf-plan`. Decomposition is handled in-workflow by `workflows/generate/phase-1.5-author-plan.md`, which always produces an `AUTHOR_EXECUTION_PLAN` (parallel sub-agent dispatch in Phase 4) regardless of estimated size. If `SUB_AGENT_SESSION_APPROVED=true` AND `INLINE_FALLBACK` is unset (a new workflow run after the probe-once-per-run reset), run `workflows/shared/inline-fallback-probe.md` first to resolve `INLINE_FALLBACK`; then re-evaluate this bypass condition.

Raw-input overflow remains higher precedence: if `{cf-studio-path}/.core/requirements/raw-input-overflow.md` has already fired for direct prompt/provided-file input over `500` lines, emit that rule's explicit plan-vs-continue choice before applying this sub-agent decomposition bypass.

In that mode: still compute and log the estimate for telemetry — `"Plan-escalation: estimate={N} lines, decomposition deferred to Phase 1.5 (sub-agents approved)"` — then skip the rest of this file and proceed to the next phase. Do not emit any user-facing escalation menu.

Run the legacy size-based escalation below only when `SUB_AGENT_SESSION_APPROVED` is unset/false OR `INLINE_FALLBACK=true`.

### Legacy Size-Based Escalation (inline-fallback path)

**MUST** estimate total context from `rules.md`, the generation-phase dependencies actually needed for this run (for example `template.md` and `example.md`, plus `checklist.md` only when explicitly required before writing), expected output size, project context, and ~30% reasoning overhead.

| Estimated total | Action |
|----------------|--------|
| `≤ 1500` lines | Proceed normally — optimal zone, >95% rule adherence. |
| `1501-2500` lines | Proceed with warning + aggressive summarize-and-drop: _"This is a medium-sized task. Activating chunked loading — will checkpoint if context runs low."_ |
| `> 2500` lines | **MUST** offer plan escalation before proceeding. |

> **Why these thresholds**: rule-following quality drops above ~2000 lines of active constraints; SDLC kit files plus output and reasoning can easily exceed 2500.

When `> 2500` lines, offer:

```text
⚠️ This task is large — estimated ~{N} lines of context needed (`rules.md`, active generation dependencies, output, project ctx).
This exceeds the safe single-context budget (~2500 lines). The plan workflow can decompose this into focused phases (≤500 lines each) that ensure every kit rule is followed and nothing is skipped.

Options:
1. Switch to /cf-plan (recommended for full quality)
2. Continue here (risk: context overflow, rules may be partially applied)

Suggested: 1 because plan decomposition is the safer default for large tasks.
Reply with `1` or `2`.
```

Per-option rationale (for reference only — not part of the user-facing prompt):
- Option 1 (Switch to /cf-plan) → decomposes the task into focused phases and reduces context-overflow risk.
- Option 2 (Continue here) → faster, but context overflow may reduce rule coverage.

If user chooses plan: stop and tell them to run `/cf-plan generate {KIND}` with the same parameters. If user chooses continue: proceed with aggressive chunking and log _"Proceeding in single-context mode — quality may be reduced for large artifacts."_
