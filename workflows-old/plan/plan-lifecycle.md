---
cf: true
type: reference
description: "Invoke when Phase 2.1 of cf-plan requires the user to select a plan lifecycle strategy — presents the lifecycle menu, records the selection, and defines normative handling rules for each strategy."
loaded_by: workflows/plan.md
version: 1.0
---

# Plan Lifecycle Selection

<!-- toc -->

- [Lifecycle Menu](#lifecycle-menu)
- [Per-Strategy Normative Rules](#per-strategy-normative-rules)
  - [Interrupted Lifecycle Recovery](#interrupted-lifecycle-recovery)

<!-- /toc -->

## Lifecycle Menu

```pdsl
UNIT PlanLifecycleMenu

PURPOSE:
  Obtain the user's lifecycle strategy choice before phase boundaries are finalized.

DO:
  - EMIT_MENU LifecycleChoiceMenu
  - WAIT user.reply
  - STOP_TURN

MENU LifecycleChoiceMenu:
  TITLE: How should completed plans be handled?
  PREAMBLE:
    Plan files are stored in {cf-studio-path}/.plans/{task-slug}/.
  OPTIONS:
    1 -> SET lifecycle = "gitignore"
         CONTINUE PlanLifecycleGitignore
         ([1] Suggested default for most projects — keep plan files available locally
          and ensure .plans/ stays gitignored.)
    2 -> SET lifecycle = "cleanup"
         CONTINUE PlanLifecycleCleanup
         ([2] Remove compiled plan artifacts automatically after successful delivery.)
    3 -> SET lifecycle = "archive"
         CONTINUE PlanLifecycleArchive
         ([3] Keep the plan, but move it into the archive location after completion.)
    4 -> SET lifecycle = "manual"
         CONTINUE PlanLifecycleManual
         ([4] Ask again at the end instead of choosing a lifecycle strategy now.)
  PREAMBLE_REPLY: Reply with `1`, `2`, `3`, or `4`.
  INVALID:
    EMIT "Reply with 1, 2, 3, or 4."
    WAIT user.reply
    STOP_TURN
```

## Per-Strategy Normative Rules

```pdsl
UNIT PlanLifecycleGitignore

PURPOSE:
  Repository-hygiene lifecycle: ensure .plans/ is gitignored.

DO:
  - RUN INSPECT active repo ignore targets (.gitignore first, then .git/info/exclude)
  - RUN VERIFY whether an existing .plans/ rule already covers the plan directory
  - REQUIRE no rule exists:
    - SET CF_PHASE_GATE = released_for_orchestrator_write
      scope = {project_root}/.gitignore
    ADD narrowest acceptable ignore rule
    - SET CF_PHASE_GATE = armed
  - SET plan.lifecycle_status = "done"

RULES:
  - ALWAYS perform gitignore step before or immediately after the first plan file write
  - NEVER present a post-completion plan-file lifecycle decision prompt
    (does NOT prohibit pre-execution modification menus like Phase 4.2 [5] Modify plan)
```

```pdsl
UNIT PlanLifecycleCleanup

PURPOSE:
  Reserve a Cleanup phase and execute it after all delivery phases complete.

DO:
  - RUN RESERVE a final Cleanup phase now so total_phases, dependencies, briefs, and
  - RUN budget estimates are structurally correct before plan.toml is written

  - RUN AFTER all non-lifecycle phases are done:
    - SET plan.lifecycle_status = "ready"
    EXECUTE Cleanup phase (removes brief-*, phase-*, out/; plan.toml remains as terminal receipt)

    IF cleanup succeeds:
      - SET plan.lifecycle_status = "done"

    IF cleanup fails (file removal error, permission error, unexpected state):
      - SET plan.lifecycle_status = "failed"
      - EMIT specific error and affected paths
      OFFER manual intervention: list files that could not be removed and ask user to remove manually or retry

    IF partial success (some files removed, others not):
      - SET plan.lifecycle_status = "partial"
      - EMIT list of files removed AND list of files that could not be removed
      ASK user to manually remove residual files or retry

RULES:
  - ALWAYS distinguish "partial" from "failed" (failed = cleanup never attempted)
  - NEVER present a post-completion plan-file lifecycle decision prompt
    (does NOT prohibit pre-execution modification menus like Phase 4.2 [5] Modify plan)
  - ALWAYS Cleanup removals of brief-*, phase-*, and out/ are intentional terminal lifecycle cleanup —
    recovery/audit ALWAYS treat them as exempt when lifecycle = "cleanup" AND plan.lifecycle_status = "done"
  - NEVER reopen delivery phases or replay Cleanup solely because those files are absent
```

```pdsl
UNIT PlanLifecycleArchive

PURPOSE:
  Move the completed plan directory to the archive location.

DO:
  - RUN AFTER all phases are done:
    - SET plan.lifecycle_status = "ready"
    MOVE plan directory to {cf-studio-path}/.plans/.archive/{task-slug}/

    IF archive move target already exists:
      APPEND numeric suffix to archive directory name (-2, -3, ...) mirroring active-plan collision rule
      COMPLETE the move

    - SET plan.active_plan_dir = {final archive path}
    - SET plan.lifecycle_status = "done"  (with final archive path recorded in moved manifest)

    IF archive move fails with permission error or disk error:
      - SET plan.lifecycle_status = "failed"
      - EMIT specific error and source path
      OFFER manual intervention: ask user to move directory manually or choose a different lifecycle strategy

RULES:
  - ALWAYS Only permission errors and disk errors set plan.lifecycle_status = "failed"
  - NEVER present a post-completion plan-file lifecycle decision prompt
    (does NOT prohibit pre-execution modification menus like Phase 4.2 [5] Modify plan)
```

```pdsl
UNIT PlanLifecycleManual

PURPOSE:
  Defer lifecycle decision until after all phases complete.

DO:
  - RUN AFTER all phases are done:
    - SET plan.lifecycle_status = "manual_action_required"
    PRESENT exactly one keep/archive/delete choice

RULES:
  - ALWAYS This is the ONLY strategy that allows a post-completion plan-file decision prompt
```

### Interrupted Lifecycle Recovery

```pdsl
UNIT PlanLifecycleInterruptedRecovery

PURPOSE:
  Handle lifecycle_status = "in_progress" observed on resume without re-running
  the lifecycle action automatically.

WHEN:
  - REQUIRE plan.lifecycle_status == "in_progress" on resume

DO:
  - RUN SURFACE residual state to user per {cf-studio-path}/.core/workflows/plan/plan-reference.md § 5.7 Abandoned Plan Recovery
  - EMIT_MENU InterruptedLifecycleMenu
  - WAIT user.reply
  - STOP_TURN

MENU InterruptedLifecycleMenu:
  TITLE: Interrupted lifecycle detected — how to proceed?
  OPTIONS:
    1 -> RETRY the lifecycle action
    2 -> SET plan.lifecycle_status = "failed"
         LEAVE residual artifacts in place
    3 -> LEAVE plan.lifecycle_status = "in_progress" for later manual handling
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN

NOTES:
  Cleanup partial-state: residual deletes are safe to retry.
  Archive partial-state: inspect the destination before retry.
```
