# Plan Compile

```pdsl
UNIT PlanPhase3Compile
PURPOSE: Write plan.toml and one brief per phase, then choose how to produce phase files (Phase 3).
DO:
  LOAD {cf-studio-path}/.core/requirements/plan-template.md and {cf-studio-path}/.core/requirements/brief-template.md and follow them
  SET CF_PHASE_GATE = released_for_orchestrator_write (scope plan.toml), WRITE {cf-studio-path}/.plans/{task-slug}/plan.toml ([meta] + [plan] + [[phases]] per the template), SET CF_PHASE_GATE = armed
  SET CF_PHASE_GATE = released_for_orchestrator_write (scope brief-*.md), WRITE one brief-{NN}-{slug}.md per phase (~50-80 lines; context boundary, metadata, load instructions, budget; never copy kit content), SET CF_PHASE_GATE = armed
  EMIT_MENU BriefCheckpointMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS write plan.toml before any brief or phase file
  ALWAYS reopen CF_PHASE_GATE released_for_orchestrator_write (scoped) before each write and reset to armed immediately after
  ALWAYS read each brief FROM DISK before compiling
  NEVER emit "Plan created" at this checkpoint
MENU BriefCheckpointMenu
TITLE: Brief package prepared (plan.toml + N briefs, 0/N phase files) — choose how to produce phase files: 1 inline (uses this chat's budget); 2 prompts (skips validation); 3 subagents (needs sub-agent approval); 4 stop (keep briefs). Reply with a number.
OPTIONS:
  1 inline -> LOAD {cf-studio-path}/.core/skills/studio/modules/plan-validate-finalize.md; compile each phase file inline from its on-disk brief (apply a context boundary, read brief from disk, WRITE phase-NN-*.md with CF_PHASE_GATE released/armed), then CONTINUE PlanPhase3Validate
  2 prompts -> emit one self-contained downstream compilation prompt per brief (no phase files written), SET plan.execution_status="prompts_emitted", and STOP_TURN (Phase 3.4 validation skipped in this mode)
  3 subagents -> LOAD {cf-studio-path}/.core/skills/studio/modules/plan-compiler-dispatch.md; CONTINUE PlanPhaseCompilerDispatch
  4 stop -> SET plan.execution_status="briefs_only" and STOP_TURN
  INVALID -> EMIT_MENU BriefCheckpointMenu
```
