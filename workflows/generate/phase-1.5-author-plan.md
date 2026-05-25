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

This phase is a mandatory offer gate after Phase 1 inputs are approved and
before Phase 3 summary. The author plan itself is optional in the legacy branch
but the offer is not optional unless an explicit auto-skip condition applies.

Open, load, and follow
`workflows/generate/phase-1.5/state-contract.md` first. That file is the
canonical contract for:

- allowed `AUTHOR_PLAN_OFFER_RESOLVED` values
- which states continue to Phase 3 / Phase 4
- which states are terminal cancellations
- when `AUTHOR_EXECUTION_PLAN` and `AUTHOR_PLAN_CACHE_DIR` may be non-null
- mandatory-vs-optional offer semantics under sub-agent approval

## Load Order

After the state contract is loaded:

1. Open, load, and follow
   `workflows/generate/phase-1.5/offer-dispatch.md`.
2. Open, load, and follow
   `workflows/generate/phase-1.5/disk-mode.md` only when
   `AUTHOR_PLAN_OFFER_RESOLVED=disk`.

The offer/dispatch module owns:

- mandatory storage-choice prompting when
  `SUB_AGENT_SESSION_APPROVED=true` AND `INLINE_FALLBACK=false`
- the legacy optional offer when that branch is not active
- planner dispatch and validation
- planner-failure recovery, including the only path in the mandatory branch
  that may still resolve `AUTHOR_PLAN_OFFER_RESOLVED=declined`

The disk-mode module owns:

- cache-file rendering under
  `{cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/`
- cache-write retry / memory fallback / cancellation handling
- cleanup expectations for partially written plan-cache files

## Handoff

Continue to `workflows/generate/phase-3-summary.md` only when
`AUTHOR_PLAN_OFFER_RESOLVED` is one of the continuation states defined in
`workflows/generate/phase-1.5/state-contract.md`.

Do NOT enter Phase 3 or Phase 4 when `AUTHOR_PLAN_OFFER_RESOLVED` is one of the
terminal cancellation states. In those states, the current generate sub-flow
ends without any Phase 4 author dispatch.
