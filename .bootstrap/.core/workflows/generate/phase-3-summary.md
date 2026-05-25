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

Prerequisite: `AUTHOR_PLAN_OFFER_RESOLVED` MUST be set by
`workflows/generate/phase-1.5-author-plan.md`. If unset, fail-stop and route
back to `workflows/generate/phase-1.5-author-plan.md` so its state contract and
offer/dispatch modules can re-run.

If `AUTHOR_PLAN_OFFER_RESOLVED` is a terminal cancellation state
(`cancelled_by_stop_token`, `cancelled_planner_failure`,
`cancelled_partial_write`), do NOT emit the Summary block. Stop the current
generate sub-flow and leave target files untouched.

```markdown
## Summary
**Target**: {TARGET_TYPE}
**Kind**: {KIND}
**Name**: {name}
**Path**: {path}
**Mode**: {MODE}
**Content preview**: {brief overview of what will be created/changed}
**Author plan**: {memory/disk/declined/auto-skipped}; {task count + parallel group summary OR "single author flow"}
**Files to write**: `{path}`: {description}; {additional files if any}
**Artifacts registry**: `{cf-studio-path}/config/artifacts.toml`: {entry additions/updates, if any}
**STRICT self-check**: template loaded = {yes/no}; example referenced = {yes/no}; checklist status = {required-and-complete/deferred-to-phase-5}; placeholders absent = {yes/no}; explicit `yes` received = {yes/no}
**Proceed?** [yes/no/modify]
Reply with `yes`, `no`, or `modify`.
`yes` → Suggested when the summary is accurate; write files and continue to validation.
`no` → Cancel without writing files.
`modify` → Revisit the inputs or proposal before any files are written.
```

Responses: `yes` = create files and validate; `no` = cancel; `modify` = revisit a question and iterate (max 3 iterations, then require explicit `continue iterating` or stop the generate workflow (reply with a stop token — open and follow {cf-studio-path}/.core/workflows/shared/stop-token-policy.md)).
