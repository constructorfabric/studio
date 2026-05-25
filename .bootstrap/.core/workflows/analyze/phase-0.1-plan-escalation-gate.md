---
name: analyze-phase-0.1-plan-escalation-gate
description: "Invoke when running Analyze Phase 0.1 to evaluate the analyze-specific plan escalation gate (thresholds and dispatch route differ from generate)."
purpose: Analyze Phase 0.1 — analyze-specific plan escalation gate (thresholds and dispatch route differ from generate)
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->

- [Phase 0.1: Plan Escalation Gate](#phase-01-plan-escalation-gate)
  - [Sub-Agent Decomposition Bypass](#sub-agent-decomposition-bypass)
  - [Legacy Size-Based Escalation (inline-fallback path)](#legacy-size-based-escalation-inline-fallback-path)

<!-- /toc -->




## Phase 0.1: Plan Escalation Gate

### Sub-Agent Decomposition Bypass

When `SUB_AGENT_SESSION_APPROVED=true` AND `INLINE_FALLBACK=false`, this gate **MUST NOT** propose `/cf-plan`. Decomposition is handled in-workflow by `workflows/analyze/phase-2.5-reviewer-plan.md`, which builds a `REVIEWER_EXECUTION_PLAN` that partitions the analysis across reviewer sub-agents (methodology × path-partition) for parallel dispatch in Phase 3.

Raw-input overflow remains higher precedence: if `{cf-studio-path}/.core/requirements/raw-input-overflow.md` has already fired for direct prompt/provided-file input over `500` lines, emit that rule's explicit plan-vs-continue choice before applying this sub-agent decomposition bypass.

In that mode: compute and log the estimate for telemetry — `"Plan-escalation: estimate={N} lines, decomposition deferred to Phase 2.5 (sub-agents approved)"` — then skip the rest of this file and proceed. Do not emit any user-facing escalation menu.

Run the legacy size-based escalation below only when `SUB_AGENT_SESSION_APPROVED` is unset/false OR `INLINE_FALLBACK=true`.

### Legacy Size-Based Escalation (inline-fallback path)

**MUST** estimate total context: target `rules.md` Validation, target `checklist.md`, artifact content, related cross-reference artifacts, expected analysis output, and ~30% reasoning overhead.

| Estimated total | Action |
|----------------|--------|
| `≤ 1200` lines | Proceed normally — optimal zone, >95% checklist coverage. |
| `1201-2000` lines | Proceed with warning + aggressive summarize-and-drop: _"This is a medium-sized analysis. Activating chunked loading — will output PARTIAL if context runs low."_ |
| `> 2000` lines | **MUST** offer plan escalation before proceeding. |

Offer when `> 2000` lines:
```
⚠️ This analysis is large — estimated ~{N} lines of context needed:
  - checklist.md:  ~{n} lines
  - rules.md:      ~{n} lines
  - artifact:      ~{n} lines
  - cross-refs:    ~{n} lines
  - output:        ~{n} lines (estimated)

This exceeds the safe single-context budget (~2000 lines).
The plan workflow can decompose this into focused analysis phases (≤500 lines each)
that ensure every checklist item is checked and nothing is skipped.

Options:
1. Switch to /cf-plan (recommended for thorough analysis)
2. Continue here (risk: context overflow, checks may be partially applied)

Suggested: 1 because plan decomposition is the safer default for >2000-line budgets.
Reply 1 or 2.
```
If user chooses plan: stop and tell them to run `/cf-plan analyze {KIND}` with the same parameters. If user chooses continue: proceed with aggressive chunking and log _"Proceeding in single-context mode — some checks may be missed for large artifacts."_
