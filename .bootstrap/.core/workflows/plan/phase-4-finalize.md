---
cf: true
type: workflow-phase
name: plan-phase-4-finalize
description: "Invoke when /cf-plan enters Phase 4 to validate the completed plan, report the result, offer next-steps, and emit the new-chat startup prompt when the user chooses execution handoff."
loaded_by: workflows/plan.md
version: 1.0
---

# Phase 4: Finalize Plan

<!-- toc -->

- [4.1 Validate Plan Before Handoff (MANDATORY)](#41-validate-plan-before-handoff-mandatory)
- [4.2 Report Plan & Offer Next Steps](#42-report-plan--offer-next-steps)
- [New-Chat Startup Prompt](#new-chat-startup-prompt)

<!-- /toc -->

> **Note**: `plan.toml` was already written in Phase 3.1 and briefs were written in Phase 3.2. Enter Phase 4 only if the user selected option `[1]` or `[3]` and all `phase-*` files were produced in Phase 3.3. If the user selected option `[2]` or `[4]`, stop after the brief checkpoint and do not emit `Plan created`.

Status model in `plan.toml`:
- `phases[].status`: `pending`, `in_progress`, `done`, `failed`
- `plan.execution_status`: aggregate phase execution state, independent of lifecycle handling
- `plan.lifecycle_status`: plan-file lifecycle state, independent of whether all phases are already complete

Update rules:
- all phases `pending` → `plan.execution_status = "not_started"`
- user chose option `[4]` at brief checkpoint → `plan.execution_status = "briefs_only"` (valid stop state; resume by presenting `[1]-[4]` menu)
- user chose option `[2]` at brief checkpoint and only downstream compile prompts were emitted → `plan.execution_status = "prompts_emitted"` (valid stop state; phase files do not exist yet)
- any phase `in_progress`, or any mix of `done` and `pending`, → `plan.execution_status = "in_progress"`
- any phase `failed` → `plan.execution_status = "failed"` until explicitly reopened or downgraded
- all phases `done` → `plan.execution_status = "done"`; `plan.lifecycle_status` may still be `ready`, `partial`, `in_progress`, or `manual_action_required`

## 4.1 Validate Plan Before Handoff (MANDATORY)

> **⛔ CRITICAL**: Offer plan validation as the FIRST next step.

Before generating the startup prompt or offering execution handoff:
1. Self-validate against `{cf-studio-path}/.core/requirements/plan-checklist.md`.
2. Report:
```text
═══════════════════════════════════════════════
Plan Self-Validation: {task-slug}
───────────────────────────────────────────────
| Category | Status |
|----------|--------|
| 1. Structural | PASS/FAIL |
| 2. Interactive Questions | PASS/FAIL |
| 3. Rules Coverage | PASS/FAIL |
| 4. Context Completeness | PASS/FAIL |
| 5. Phase Independence | PASS/FAIL |
| 6. Budget Compliance | PASS/FAIL |
| 7. Lifecycle & Handoff | PASS/FAIL |
Overall: PASS/FAIL
═══════════════════════════════════════════════
```
If any category FAILs: list issues and offer to fix them.

## 4.2 Report Plan & Offer Next Steps

If all categories PASS, report:
```text
Plan created: {cf-studio-path}/.plans/{task-slug}/
  Phases: {N}
  Files: {file_count}
  Lifecycle: {lifecycle}
```

You may emit `Plan created` only after Phase 3.4 PASS confirms that `plan.toml`, every `brief-*`, and every compiled `phase-*` file already exist on disk. If the run stopped after brief generation or produced only downstream prompts, omit this section.

Then immediately report the delegation handoff:

```text
Delegation prompt:
  I have a Constructor Studio execution plan ready at:
    {cf-studio-path}/.plans/{task-slug}

  Please delegate this plan to ralphex using Constructor Studio's native delegation flow.
```

Only when `SUB_AGENT_SESSION_APPROVED=true` AND `INLINE_FALLBACK=false`, also
report:

```text
Native execution options available:
  This plan can be delegated to ralphex using Constructor Studio's native delegation feature.
  Command: {cfs_cmd} delegate "{cf-studio-path}/.plans/{task-slug}"

Native phase execution prompt:
  I have a Constructor Studio execution plan ready at:
    {cf-studio-path}/.plans/{task-slug}/plan.toml

  Please execute the next phase using Constructor Studio's native phase runner.
```

When native execution is not currently available (`SUB_AGENT_SESSION_APPROVED`
unset/false, or `INLINE_FALLBACK=true`), do NOT present the native execution
section or a same-chat phase-runner option here. Instead state:

```text
Same-chat native phase execution is not currently available in this run.
If the user later asks to execute a phase in this chat, re-run
`workflows/shared/inline-fallback-probe.md` first. Offer native phase-runner
execution only if that re-probe resolves to `SUB_AGENT_SESSION_APPROVED=true`
and `INLINE_FALLBACK=false`; otherwise keep to validation/review/handoff paths.
```

Then present exactly one of these next-step menus and wait for user choice
before generating any startup prompt:

Native execution available:
```text
What would you like to do next?

The plan passed self-validation. Choose your next action:

  [1] Validate plan thoroughly — run /cf-analyze on the plan
  [2] Execute Phase 1 natively here — dispatch Constructor Studio's dedicated phase-runner subagent in this chat
  [3] Prepare execution handoff — generate the Phase 1 startup prompt for a downstream execution chat
  [4] Review plan files — inspect phase files before execution
  [5] Modify plan — adjust phases, add/remove content
Reply with `1`, `2`, `3`, `4`, or `5`.
[1] Suggested default before execution — verify the plan thoroughly with `/cf-analyze`.
[2] Start executing the first phase now in this chat with the native phase runner.
[3] Generate a handoff prompt for a separate execution chat.
[4] Inspect the plan files manually before deciding what to do next.
[5] Rework the plan structure or contents before execution.
```

Native execution unavailable:
```text
What would you like to do next?

The plan passed self-validation. Choose your next action:

  [1] Validate plan thoroughly — run /cf-analyze on the plan
  [2] Prepare execution handoff — generate the Phase 1 startup prompt for a downstream execution chat
  [3] Review plan files — inspect phase files before execution
  [4] Modify plan — adjust phases, add/remove content
Reply with `1`, `2`, `3`, or `4`.
[1] Suggested default before execution — verify the plan thoroughly with `/cf-analyze`.
[2] Generate a handoff prompt for a separate execution chat.
[3] Inspect the plan files manually before deciding what to do next.
[4] Rework the plan structure or contents before execution.
```

## New-Chat Startup Prompt

When the user chooses option `[2]` from the native-available menu, do **not**
emit a startup prompt. Treat this reply as a fresh native dispatch site:

1. Re-run `workflows/shared/inline-fallback-probe.md` immediately before any
   phase-runner dispatch. Do NOT trust the earlier menu state as sufficient
   proof because `INLINE_FALLBACK` is re-derived per workflow run and may need
   to be re-confirmed after resume/compaction.
2. If that re-probe stops for approval, end the turn there. If it resolves to
   `INLINE_FALLBACK=true`, do NOT dispatch the phase runner; surface that
   same-chat native execution is unavailable for this turn and fall back to the
   non-native Phase 4.2 choices.
3. If the re-probe resolves to `SUB_AGENT_SESSION_APPROVED=true` and
   `INLINE_FALLBACK=false`, set `CF_PHASE_GATE=released_for_dispatch`
   immediately before routing to
   `{cf-studio-path}/.core/skills/studio/agents/cf-phase-runner.md`.
4. The dispatch payload MUST include:
   - `plan_dir = "{cf-studio-path}/.plans/{task-slug}/"`
   - `target_phase = 1`
   - `git_commit_mode = GIT_COMMIT_MODE`
   - `contributing_guide = CONTRIBUTING_GUIDE`
   - `git_constraint` = the mode-matched constraint block from
     `workflows/generate/phase-4-write.md` § Git constraint blocks
5. Reset `CF_PHASE_GATE=armed` immediately after the phase-runner returns —
   success, error, or no-response.
6. Then return only the concise execution summary defined by that agent
   contract.

When the user chooses the handoff option (`[3]` in the native-available menu,
`[2]` in the native-unavailable menu), emit the entire startup prompt inside a
**single fenced code block**:
```text
I have a Constructor Studio execution plan ready at:
  {cf-studio-path}/.plans/{task-slug}/plan.toml

Please read the plan manifest, then execute Phase 1.
The phase file is self-contained — follow its instructions exactly.
After completion, report results and generate the prompt for Phase 2.
```
No explanatory text may be mixed into that code fence.
