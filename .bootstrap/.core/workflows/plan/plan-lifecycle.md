---
cf: true
type: reference
description: "Invoke when Phase 2.1 of /cf-plan requires the user to select a plan lifecycle strategy — presents the lifecycle menu, records the selection, and defines normative handling rules for each strategy."
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

Ask how completed plans should be handled:
```text
Plan files are stored in {cf-studio-path}/.plans/{task-slug}/.
How should completed plans be handled?
  [1] .gitignore — keep plan files in place and ensure .plans/ is gitignored
  [2] Cleanup phase — add a final Cleanup phase that removes compiled plan artifacts after delivery phases pass
  [3] Archive — move the plan directory to {cf-studio-path}/.plans/.archive/
  [4] Manual — stop after execution and ask me what to do with the plan files
Reply with `1`, `2`, `3`, or `4`.
[1] Suggested default for most projects — keep plan files available locally and ensure `.plans/` stays gitignored.
[2] Remove compiled plan artifacts automatically after successful delivery.
[3] Keep the plan, but move it into the archive location after completion.
[4] Ask again at the end instead of choosing a lifecycle strategy now.
```

## Per-Strategy Normative Rules

Record `lifecycle = "gitignore" | "cleanup" | "archive" | "manual"`. Lifecycle handling is deterministic and single-path:
- `gitignore`: planning-time repository hygiene. Ensure `.plans/` is gitignored before or immediately after the first plan file write. The deterministic step is: inspect the active repo ignore targets (`.gitignore` first, then `.git/info/exclude` when project policy prefers local-only ignores), verify whether an existing `.plans/` rule already covers the plan directory, and add the narrowest acceptable ignore rule if not. Set `plan.lifecycle_status = "done"` as soon as the ignore rule exists. No post-completion plan-file lifecycle decision prompt is allowed (this does NOT prohibit pre-execution modification menus like Phase 4.2 [5] Modify plan).
- `cleanup`: reserve a final Cleanup phase now so `total_phases`, dependencies, briefs, and budget estimates are structurally correct before `plan.toml` is written. After all non-lifecycle phases are `done`, set `plan.lifecycle_status = "ready"`, execute the Cleanup phase, then set `plan.lifecycle_status = "done"` only if cleanup succeeds. If cleanup fails (file removal error, permission error, or unexpected state), set `plan.lifecycle_status = "failed"`, report the specific error and affected paths, and offer manual intervention: list the files that could not be removed and ask the user to remove them manually or retry. Partial success (some files removed, others not) sets `plan.lifecycle_status = 'partial'`, lists the files that were removed AND the files that could not be removed, and asks the user to manually remove the residual files or retry. The orchestrator MUST distinguish 'partial' from 'failed' (cleanup never attempted) when reporting status. The Cleanup phase removes `brief-*`, `phase-*`, and `out/`; `plan.toml` remains as the terminal receipt. Those removed plan artifacts are intentional terminal lifecycle cleanup, not delivery regressions: later recovery/audit MUST treat them as exempt when `lifecycle = "cleanup"` and `plan.lifecycle_status = "done"`, and MUST NOT reopen delivery phases or replay Cleanup solely because those files are absent. No post-completion plan-file lifecycle decision prompt is allowed (this does NOT prohibit pre-execution modification menus like Phase 4.2 [5] Modify plan).
- `archive`: after all phases are `done`, set `plan.lifecycle_status = "ready"`, move the plan directory to `{cf-studio-path}/.plans/.archive/{task-slug}/`, then update `plan.active_plan_dir` and set `plan.lifecycle_status = "done"` in the moved manifest. If the archive move target already exists, append a numeric suffix to the archive directory name (`-2`, `-3`, …) mirroring the active-plan collision rule, then complete the move. Set `plan.lifecycle_status = "done"` with the final archive path recorded. Only permission errors and disk errors set `plan.lifecycle_status = "failed"`. If the archive move fails with a permission error or disk error, report the specific error and source path, and offer manual intervention: ask the user to move the directory manually or choose a different lifecycle strategy. No post-completion plan-file lifecycle decision prompt is allowed (this does NOT prohibit pre-execution modification menus like Phase 4.2 [5] Modify plan).
- `manual`: do nothing automatically. After all phases are `done`, set `plan.lifecycle_status = "manual_action_required"` and present exactly one keep/archive/delete choice. This is the only strategy that allows a post-completion plan-file decision prompt.

### Interrupted Lifecycle Recovery

If `plan.lifecycle_status = "in_progress"` is observed on resume (e.g., the agent was interrupted mid-cleanup or mid-archive), do NOT re-run the lifecycle action automatically. Instead, surface the residual state to the user per `workflows/plan/plan-reference.md` § 5.7 Abandoned Plan Recovery, and ask whether to (1) retry the lifecycle action, (2) mark it as `failed` and leave residual artifacts in place, or (3) leave `lifecycle_status` as `in_progress` for later manual handling. Cleanup partial-state: residual deletes are safe to retry; archive partial-state requires inspecting the destination before retry.
