---
name: generate-phase-3-summary
description: "Invoke when the generate workflow reaches Phase 3 to emit the Summary block, run the STRICT self-check, and await the yes/no/modify confirmation gate before writing files."
purpose: Generate Phase 3 — Summary block + STRICT self-check + yes/no/modify gate
loaded_by: workflows/generate.md
version: 1.0
---

<!-- toc -->

- [Phase 3: Summary](#phase-3-summary)

<!-- /toc -->

## Phase 3: Summary

```text
UNIT Phase3Summary

PURPOSE:
  Emit Summary block with STRICT self-check and await yes/no/modify gate
  before any file writes.

DO:
  REQUIRE AUTHOR_PLAN_OFFER_RESOLVED is set by
    workflows/generate/phase-1.5-author-plan.md
  IF AUTHOR_PLAN_OFFER_RESOLVED is unset:
    FAIL-STOP
    ROUTE back to workflows/generate/phase-1.5-author-plan.md

  IF AUTHOR_PLAN_OFFER_RESOLVED is a terminal cancellation state
    (cancelled_by_stop_token | cancelled_planner_failure | cancelled_partial_write):
    STOP current generate sub-flow
    LEAVE target files untouched
    RETURN

  EMIT exactly:
---
## Summary
**Target**: {TARGET_TYPE}
**Kind**: {KIND}
**Name**: {name}
**Path**: {path}
**Mode**: {MODE}
**Content preview**: {brief overview of what will be created/changed}
**Author plan**: {memory/disk/auto-skipped/cancelled}; {task count + parallel group summary OR "single author flow"}
**Files to write**: `{path}`: {description}; {additional files if any}
**Artifacts registry**: `{cf-studio-path}/config/artifacts.toml`: {entry additions/updates, if any}
**STRICT self-check**: template loaded = {yes/no}; example referenced = {yes/no}; checklist status = {required-and-complete/deferred-to-phase-5}; placeholders absent = {yes/no}; explicit `yes` received = {yes/no}
**Proceed?** [yes/no/modify]
Reply with `yes`, `no`, or `modify`.
`yes` → Suggested when the summary is accurate; write files and continue to validation.
`no` → Cancel without writing files.
`modify` → Revisit the inputs or proposal before any files are written.
---
  WAIT user.reply
  STOP_TURN

MENU Phase3ConfirmationMenu:
  TITLE: Phase 3 confirmation
  OPTIONS:
    yes ->
      CONTINUE workflows/generate/phase-4-write.md
    no ->
      CANCEL without writing files
    modify ->
      EMIT "What would you like to change?"
      WAIT user.reply
      STOP_TURN
      REVISIT inputs or proposal
      ITERATE (max 3 iterations)
      IF iterations exhausted:
        REQUIRE explicit "continue iterating" or stop token
        IF stop token:
          LOAD {cf-studio-path}/.core/workflows/shared/stop-token-policy.md
          STOP generate workflow
  INVALID:
    EMIT "Reply with yes, no, or modify."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST NOT emit Summary block when AUTHOR_PLAN_OFFER_RESOLVED is a
    terminal cancellation state
  - MUST NOT write files before receiving yes
  - Max 3 modify iterations; after that require explicit "continue iterating"
    or stop the generate workflow
```
