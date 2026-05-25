---
description: "Invoke when Phase 0.7 fires and the brainstorm sub-tree dispatcher must route into offer / panel-selection / round-loop / wrap-handoff sub-files."
name: phase-0.7-brainstorm-index
purpose: Dispatcher for the Phase 0.7 brainstorm sub-tree
loaded_by: workflows/generate.md
version: 1.0
---

# Phase 0.7 — Brainstorm (Dispatcher)

Load each sub-file WHEN its fire condition matches. Sub-files are self-loadable;
they cannot assume sibling sub-files are already in context.

| Sub-file | Load WHEN |
|---|---|
| `offer.md` | Phase 0.7 fires and the orchestrator must offer brainstorm to the user |
| `panel-selection.md` | User accepts brainstorm; session setup begins |
| `state-schema.md` | Before the first round; state object must be initialized |
| `round-loop.md` | Each brainstorm round (dispatch + INLINE_FALLBACK degradation) |
| `wrap-handoff.md` | All rounds complete; consolidate design and hand off to Phase 1 |
| `save-and-rules.md` | `mode=save` requested OR rules-respect / standalone-use check fires |

After `wrap-handoff.md` completes (or after `save-and-rules.md` when that fires last), proceed to `workflows/generate/phase-1-collect.md`.

On `wrap-handoff.md` failure or error return: STOP, surface the error to the user, and do NOT proceed to phase-1-collect.md.
