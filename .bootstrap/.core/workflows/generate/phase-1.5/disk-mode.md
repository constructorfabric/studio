---
cf: true
type: workflow-fragment
parent: workflows/generate/phase-1.5-author-plan.md
description: "Invoke when AUTHOR_PLAN_OFFER_RESOLVED=disk to render the author-plan cache files and handle partial-write recovery for Generate Phase 1.5."
---

<!-- toc -->

- [Disk Mode Rendering](#disk-mode-rendering)

<!-- /toc -->

## Disk Mode Rendering

When `AUTHOR_PLAN_OFFER_RESOLVED=disk`, render the validated
`AUTHOR_EXECUTION_PLAN` to:

Set `CF_PHASE_GATE=released_for_orchestrator_write` with scope =
`{cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/` immediately before
writing these cache files:

```text
{cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/index.md
{cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/plan.json
{cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/agents/{author_agent}.md
{cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/tasks/{task_id}.md
```

`index.md` contains the summary, risk flags, ordered parallel groups, and a
task table. `plan.json` is the exact parsed `AUTHOR_EXECUTION_PLAN`. Each
`agents/{author_agent}.md` file contains the subset of tasks assigned to that
author, grouped by parallel group and dependency order. Each task file contains
task title, intent, target paths, recommended author, dependencies, parallel
group, rationale, input keys, and acceptance criteria.

After writing cache files, set `AUTHOR_PLAN_CACHE_DIR` to the directory path
and emit:

```text
Author plan saved: {AUTHOR_PLAN_CACHE_DIR}
```

Reset `CF_PHASE_GATE=armed` immediately after the named writes complete or
fail.

If any cache file write fails: emit a structured error block listing files that
were written and files that failed. Do not silently proceed with a partial
cache. Offer:

```text
Partial cache write failure. Some plan cache files could not be written.

Written: {list of successfully written files, one per line, or "none"}
Failed:  {list of files that failed with error reason, one per line}

How do you want to proceed?

| Option | Action |
|---|---|
| 1 | Retry disk mode — re-attempt the failed writes |
| 2 | Continue in memory mode — discard the partial cache files and proceed with `AUTHOR_EXECUTION_PLAN` in-context |
| 3 | Cancel the author plan (`AUTHOR_PLAN_OFFER_RESOLVED=cancelled_partial_write`) |

Suggested: 1 because retrying only the failed files avoids discarding already-successful writes and preserves disk plan mode.

Reply `1`, `2`, or `3`.
```

On `1`: re-attempt only the failed writes; do not re-write already successful
files. If the retry still fails, re-emit the menu.

On `2`: set `AUTHOR_PLAN_OFFER_RESOLVED=memory`, discard any partially written
cache files, clear `AUTHOR_PLAN_CACHE_DIR`, and proceed to Phase 3 with
`AUTHOR_EXECUTION_PLAN` in-context.

On `3`: set `AUTHOR_PLAN_OFFER_RESOLVED=cancelled_partial_write`, set
`AUTHOR_EXECUTION_PLAN=null`, reset `CF_PHASE_GATE=armed`, and stop the current
generate sub-flow without entering Phase 3 or Phase 4.

A stop token at this partial-cache recovery prompt is equivalent to option `3`.

Disk-mode cache files are pre-Phase-4 writes. They are not target-artifact
writes, but they must be disclosed on failure/abandonment and either resumed
from or cleaned up explicitly; open and follow `workflows/generate/error-handling.md`.
