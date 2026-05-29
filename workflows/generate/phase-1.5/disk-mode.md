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

```text
UNIT Phase15DiskModeRendering

PURPOSE:
  Render validated AUTHOR_EXECUTION_PLAN to cache files and handle
  partial-write recovery.

WHEN:
  AUTHOR_PLAN_OFFER_RESOLVED == disk

DO:
  SET CF_PHASE_GATE = released_for_orchestrator_write
    WITH scope = {cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/

  WRITE these cache files:
    {cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/index.md
      (work_request, summary, risk flags, ordered parallel groups, task table)
    {cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/plan.json
      (exact parsed AUTHOR_EXECUTION_PLAN including work_request)
    {cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/agents/{author_agent}.md
      per involved author (subset of tasks for that author, grouped by parallel
      group and dependency order)
    {cf-studio-path}/.cache/generate-plans/{slug}-{ISO}/tasks/{task_id}.md
      per planned task (task title, work_request, intent, target paths, recommended author,
      dependencies, parallel group, rationale, input keys, acceptance criteria)

  IF all writes succeed:
    SET AUTHOR_PLAN_CACHE_DIR = directory path
    EMIT "Author plan saved: {AUTHOR_PLAN_CACHE_DIR}"
  SET CF_PHASE_GATE = armed  # immediately after named writes complete or fail

  IF any cache file write fails:
    EMIT structured error block listing written files and failed files
    EMIT_MENU PartialCacheFailureMenu
    WAIT user.reply
    STOP_TURN

MENU PartialCacheFailureMenu:
  TITLE: Partial cache write failure. Some plan cache files could not be written.
    Written: {list or "none"}
    Failed: {list with error reason}
    How do you want to proceed?
  OPTIONS:
    1 ->
      NOTE: Suggested — retrying only failed files avoids discarding
            already-successful writes and preserves disk plan mode.
      RE-ATTEMPT only failed writes; MUST NOT re-write already successful files
      IF retry fails: RE-EMIT this menu
    2 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = memory
      DISCARD partial cache files
      CLEAR AUTHOR_PLAN_CACHE_DIR
      CONTINUE Phase3 WITH AUTHOR_EXECUTION_PLAN in-context
    3 ->
      SET AUTHOR_PLAN_OFFER_RESOLVED = cancelled_partial_write
      SET AUTHOR_EXECUTION_PLAN = null
      SET CF_PHASE_GATE = armed
      STOP current generate sub-flow
      FORBID entering Phase 3 or Phase 4
  stop_token ->
    TREAT as option 3
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST set CF_PHASE_GATE = released_for_orchestrator_write IMMEDIATELY before writing
  - MUST reset CF_PHASE_GATE = armed IMMEDIATELY after named writes complete or fail
  - MUST NOT silently proceed with partial cache
  - MUST emit structured error block listing written and failed files on any failure
  - MUST NOT re-write already successful files on retry (option 1)
  - Disk-mode cache files are pre-Phase-4 writes (not target-artifact writes);
    MUST disclose on failure/abandonment; open and follow {cf-studio-path}/.core/workflows/generate/error-handling.md
```
