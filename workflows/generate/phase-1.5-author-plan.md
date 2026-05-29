---
description: "Invoke when Phase 1 inputs are approved and the author-plan offer gate must run (mandatory when sub-agents approved; offered otherwise) before Phase 3 summary."
name: generate-phase-1.5-author-plan
purpose: Generate Phase 1.5 — author-plan offer routing, state contract, and handoff into planner/disk-mode submodules
loaded_by: workflows/generate.md
version: 1.0
---

# Phase 1.5: Author Plan

<!-- toc -->

- [Phase Contract](#phase-contract)
- [Load Order](#load-order)
- [Handoff](#handoff)

<!-- /toc -->

## Phase Contract

```text
UNIT Phase15AuthorPlanContract

PURPOSE:
  Mandatory offer gate after Phase 1 inputs approved; before Phase 3 summary.
  The author plan itself is optional in the legacy branch but the offer is not
  optional unless an explicit auto-skip condition applies.

DO:
  LOAD {cf-studio-path}/.core/workflows/generate/phase-1.5/state-contract.md FIRST
    (canonical contract for AUTHOR_PLAN_OFFER_RESOLVED values, continuation
     states, terminal cancellation states, when AUTHOR_EXECUTION_PLAN and
     AUTHOR_PLAN_CACHE_DIR may be non-null, and mandatory-vs-optional offer
     semantics under sub-agent approval)
```

## Load Order

```text
UNIT Phase15LoadOrder

PURPOSE:
  Define load order for Phase 1.5 sub-modules.

DO:
  1. LOAD {cf-studio-path}/.core/workflows/generate/phase-1.5/offer-dispatch.md
  2. LOAD {cf-studio-path}/.core/workflows/generate/phase-1.5/disk-mode.md
       ONLY when AUTHOR_PLAN_OFFER_RESOLVED == disk

NOTES:
  offer-dispatch.md owns:
    - mandatory storage-choice prompting when SUB_AGENT_SESSION_APPROVED=true
      AND INLINE_FALLBACK=false
    - the legacy optional offer when that branch is not active
    - planner dispatch and validation
    - planner-failure recovery, including the only path in the mandatory branch
      that may still resolve AUTHOR_PLAN_OFFER_RESOLVED=declined

  disk-mode.md owns:
    - cache-file rendering under
      {cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/
    - cache-write retry / memory fallback / cancellation handling
    - cleanup expectations for partially written plan-cache files
```

## Handoff

```text
UNIT Phase15Handoff

PURPOSE:
  Route to Phase 3 on continuation states; stop on terminal cancellation states.

DO:
  IF AUTHOR_PLAN_OFFER_RESOLVED is a continuation state
    (see {cf-studio-path}/.core/workflows/generate/phase-1.5/state-contract.md):
    CONTINUE workflows/generate/phase-3-summary.md

  IF AUTHOR_PLAN_OFFER_RESOLVED is a terminal cancellation state:
    STOP current generate sub-flow
    FORBID entering Phase 3 or Phase 4
    LEAVE target files untouched

RULES:
  - MUST NOT enter Phase 3 or Phase 4 when AUTHOR_PLAN_OFFER_RESOLVED
    is a terminal cancellation state
```
