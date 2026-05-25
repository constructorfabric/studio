---
name: analyze-context-budget
description: "Invoke when loading analyze workflow context-budget rules for sizing, chunked loading, fail-safe behavior, and the Phase 0.1 plan-escalation pointer."
purpose: Analyze workflow context-budget rules — sizing, chunked loading, fail-safe, and Phase 0.1 plan-escalation pointer
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->

- [Context Budget & Overflow Prevention (CRITICAL)](#context-budget--overflow-prevention-critical)

<!-- /toc -->

## Context Budget & Overflow Prevention (CRITICAL)
- Budget first: estimate size before loading large docs (for example with `wc -l`) and state the budget for this turn.
- Load only what you use: prefer rules.md Validation and only needed checklist categories; avoid large registries/specs unless required.
- Chunk reads and summarize-and-drop: use `read_file` ranges, summarize each chunk, and keep only extracted criteria.
- Fail-safe: if checks cannot be completed within context, output `PARTIAL` with checkpoint status and resume guidance; do not claim overall PASS.
- Plan escalation: [Phase 0.1](phase-0.1-plan-escalation-gate.md) is mandatory after dependencies load. When `SUB_AGENT_SESSION_APPROVED=true` AND `INLINE_FALLBACK=false`, the gate logs the estimate and proceeds without proposing `/cf-plan`; decomposition is handled in-workflow by Phase 2.5 (reviewer plan). Otherwise the legacy size-based escalation menu fires when budget is exceeded.

Next: `workflows/analyze/phase-0-dependencies.md` for Phase 0 dependency resolution.
