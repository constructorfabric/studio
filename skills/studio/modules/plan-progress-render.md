# plan-progress-render

This module defines the progress widget that a coding agent emits when executing phases of a saved plan. It covers two responsibilities: reading the plan file and rendering a compact ASCII summary of phase and task completion state, and enforcing the exit contract that every phase must satisfy before returning control to the orchestrator. Together these units ensure the agent always writes its checkbox updates to disk and surfaces a consistent progress view at both the start and end of each phase.

```pdsl
UNIT PlanProgressRender

  PURPOSE: Read plan_file, parse phase/task state, emit ASCII progress widget

  STATE:
    SET PLAN_FILE: string | unset
    SET PLAN_PROGRESS_PHASE: start | end = start

  WHEN:
    REQUIRE PLAN_FILE != unset
    REQUIRE PLAN_SAVE_MODE == save

  DO:
    RUN read PLAN_FILE and parse: for each H2 heading treat it as one phase, count `- [x]` lines within that phase section as done tasks, count `- [ ]` lines as pending tasks, detect `✓ ` prefix on the H2 line as the phase-done marker
    RUN derive summary: compute total_phases as total H2 headings found, done_phases as count of H2 headings carrying the `✓ ` prefix, total_tasks as sum of done and pending tasks across all phases, done_tasks as sum of done tasks across all phases, active_phase as the first phase that has at least one pending task
    EMIT the progress widget using the following format:
      - header line: `Plan progress — {slug}` where slug is derived from PLAN_FILE filename
      - one row per phase: phase number and name, status column (done / active / pending), task count column shown as `(N/M tasks)` only for done and active phases
      - a separator line of em-dashes
      - a totals line: `{done_phases} / {total_phases} phases done  •  {done_tasks} / {total_tasks} tasks done`

  RULES:
    ALWAYS emit at phase start (before phase work begins) and at phase end (after checkboxes are updated)
    ALWAYS derive slug from PLAN_FILE filename by stripping the leading path and stripping any trailing date suffix of the form `-YYYY-MM-DD` before the `.md` extension (e.g. `my-feature` from `my-feature-2026-06-26.md`)
    NEVER emit the widget when PLAN_FILE is unset
    NEVER re-read PLAN_FILE from disk more than once per emit call
```

```pdsl
UNIT PlanPhaseExitContract

  PURPOSE: Define the coding agent's exit contract for a completed phase — update checkboxes then emit widget

  WHEN:
    REQUIRE PLAN_FILE != unset
    REQUIRE PLAN_SAVE_MODE == save

  DO:
    RUN for each completed task in the current phase: replace the corresponding `- [ ]` line with `- [x]` in PLAN_FILE
    RUN when all tasks in the current phase are marked `- [x]`: add `✓ ` prefix to that phase's H2 heading line in PLAN_FILE
    RUN write the updated content back to PLAN_FILE
    RUN PlanProgressRender WITH PLAN_PROGRESS_PHASE = end

  RULES:
    ALWAYS update PLAN_FILE before emitting the widget so the widget reflects the final state
    ALWAYS treat PlanPhaseExitContract as the last action before a phase hands control back to the orchestrator
    NEVER skip the widget emit when PLAN_FILE is set and PLAN_SAVE_MODE == save
    NEVER modify any heading or checkbox outside the current phase's section
```
