---
cf: true
type: workflow-fragment
parent: workflows/generate/phase-1.5-author-plan.md
description: Canonical state contract for Generate Phase 1.5 author-plan offer resolution, continuation states, and terminal cancellation states.
---

<!-- toc -->

- [State Contract](#state-contract)
  - [Mandatory-Decompose Branch](#mandatory-decompose-branch)
  - [Downstream Requirements](#downstream-requirements)

<!-- /toc -->

## State Contract

Set `AUTHOR_PLAN_OFFER_RESOLVED` to exactly one of:

- `memory`
- `disk`
- `declined`
- `auto_skipped_no_author_plan_flag`
- `auto_skipped_rules_disabled`
- `cancelled_by_stop_token`
- `cancelled_planner_failure`
- `cancelled_partial_write`

Derived state families:

- **Continuation states**: `memory`, `disk`, `declined`,
  `auto_skipped_no_author_plan_flag`, `auto_skipped_rules_disabled`
- **Terminal cancellation states**: `cancelled_by_stop_token`,
  `cancelled_planner_failure`, `cancelled_partial_write`

Set `AUTHOR_EXECUTION_PLAN` to the parsed `author_plan` JSON only when
`AUTHOR_PLAN_OFFER_RESOLVED` is `memory` or `disk`; otherwise set it to `null`.

Set `AUTHOR_PLAN_CACHE_DIR` only when `AUTHOR_PLAN_OFFER_RESOLVED=disk` and the
cache render completed successfully. If disk-mode cache writes fail, do not
claim a cache directory unless the successfully written subset is explicitly
reported to the user.

Auto-skip the offer only when one of these conditions applies:

- the user passed `--no-author-plan` in the invocation
- the KIND's `rules.md` explicitly sets `author_plan = "disabled"`

### Mandatory-Decompose Branch

When `SUB_AGENT_SESSION_APPROVED=true` AND `INLINE_FALLBACK=false` AND no
auto-skip condition applies, the author plan is mandatory.

In that branch:

- the initial user choice is only plan storage (`memory` vs `disk`)
- direct user-decline from the offer itself is unreachable
- `auto_skipped_*` states are unreachable
- planner dispatch is unconditional
- `AUTHOR_EXECUTION_PLAN` is expected to be non-null on successful planner exit

However, `declined` remains reachable in this branch through **planner-failure
recovery** when planner validation fails and the user explicitly chooses the
"Skip author plan" recovery option. That recovery path is valid and proceeds to
Phase 3 as a continuation state.

### Downstream Requirements

Phase 3 and Phase 4 may run only when `AUTHOR_PLAN_OFFER_RESOLVED` is a
continuation state.

If a later phase observes a terminal cancellation state, it MUST fail-stop
without dispatching a write-capable author and must leave any target files
untouched. Plan-cache files written under disk mode are not target-file writes;
their cleanup/resume handling is defined by
`workflows/generate/phase-1.5/disk-mode.md` and
`workflows/generate/error-handling.md`.
