---
description: "Invoke when Phase 0.7 fires and the brainstorm sub-tree dispatcher must route into offer / panel-selection / round-loop / wrap-handoff sub-files."
name: phase-0.7-brainstorm-index
purpose: Dispatcher for the Phase 0.7 brainstorm sub-tree
loaded_by: workflows/generate.md
version: 1.0
---

# Phase 0.7 — Brainstorm (Dispatcher)

```text
UNIT Phase07BrainstormDispatcher

PURPOSE:
  Load each sub-file when its fire condition matches.
  Sub-files are self-loadable; they cannot assume sibling sub-files are in context.

DO:
  LOAD offer.md
    WHEN Phase 0.7 fires and orchestrator must offer brainstorm to user
  LOAD panel-selection.md
    WHEN user accepts brainstorm; session setup begins
  LOAD state-schema.md
    WHEN before the first round; state object must be initialized
  LOAD round-loop.md
    WHEN each brainstorm round (dispatch + INLINE_FALLBACK degradation)
  LOAD wrap-handoff.md
    WHEN all rounds complete; consolidate design and route to the user's chosen next step
  LOAD save-and-rules.md
    WHEN mode=save requested OR rules-respect / standalone-use check fires

  AFTER wrap-handoff.md completes:
    DO NOT auto-continue to phase-1-collect.md
    wrap-handoff.md owns the next-step route selection

  AFTER save-and-rules.md when that fires last:
    DO NOT auto-continue to phase-1-collect.md unless wrap-handoff.md selected
    the generate route explicitly

ON_ERROR:
  wrap_handoff_failure ->
    STOP
    EMIT error to user
    FORBID proceeding to phase-1-collect.md or analyze.md
```
