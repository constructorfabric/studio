# Plan Compile

```pdsl
UNIT PlanPhase3Compile
PURPOSE: Choose how to produce phase files, which is also the authorisation to write plan.toml and the briefs (Phase 3).
STATE:
  SET CF_PHASE_GATE: released_for_orchestrator_write | released_for_dispatch | armed | unset (default armed, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/requirements/plan-template.md and {cf-studio-path}/.core/requirements/brief-template.md and follow them
  EMIT_MENU PlanProduceChoice
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER write any file before PlanProduceChoice resolves — every option that writes calls PlanWriteBriefPackage, so the authorisation and the write are the same decision
  ALWAYS read each brief FROM DISK before compiling
  ALWAYS reopen CF_PHASE_GATE released_for_orchestrator_write (scoped) before the phase-file write in option 1 and reset to armed immediately after
MENU PlanProduceChoice
TITLE: Decomposition ready. Choose how to produce phase files — options 1-4 also authorise writing plan.toml + N brief files under .plans/{task-slug}/, and options 5-6 write nothing: 1 inline (uses this chat's budget); 2 prompts (skips validation); 3 subagents (needs sub-agent approval); 4 briefs-only (write the package and stop); 5 revise the decomposition; 6 no (write nothing). Reply with a number.
TYPE: decision
OPTIONS:
  1 inline -> RUN PlanWriteBriefPackage; SET plan.approval_status="approved"; LOAD {cf-studio-path}/.core/skills/studio/modules/plan-validate-finalize.md; compile each phase file inline from its on-disk brief (apply a context boundary, read brief from disk, WRITE phase-NN-*.md with CF_PHASE_GATE released/armed), then CONTINUE PlanPhase3Validate
  2 prompts -> RUN PlanWriteBriefPackage; SET plan.approval_status="approved"; emit one self-contained downstream compilation prompt per brief (no phase files written), SET plan.execution_status="prompts_emitted", EMIT "Start a new chat and paste Phase 1's prompt to begin compilation. Each prompt is self-contained and independent.", then LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded; RUN NextActionsOffer (Phase 3.4 validation skipped in this mode)
  3 subagents -> RUN PlanWriteBriefPackage; SET plan.approval_status="approved"; LOAD {cf-studio-path}/.core/skills/studio/modules/plan-compiler-dispatch.md; CONTINUE PlanPhaseCompilerDispatch
  4 briefs-only — write plan.toml + briefs and stop there -> RUN PlanWriteBriefPackage; SET plan.approval_status="approved"; SET plan.execution_status="briefs_only"; LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded; RUN NextActionsOffer
  5 revise — describe what to change about this decomposition -> SET plan.approval_status="revised" WHEN plan.toml already exists; EMIT "Describe what to change (e.g. split phase 2, merge phases 3 and 4, adjust scope). I will rework and re-show."; CONTINUE PlanPhase2Decompose after user.reply; WAIT user.reply; STOP_TURN
  6 n | no -> EMIT "Decomposition declined — nothing written. Rework boundaries and re-run cf-plan when ready." and STOP_TURN
  INVALID -> EMIT_MENU PlanProduceChoice
```

```pdsl
UNIT PlanWriteBriefPackage
PURPOSE: Write plan.toml and one brief per phase once PlanProduceChoice has authorised it (Phase 3.2).
STATE:
  SET CF_PHASE_GATE: released_for_orchestrator_write | released_for_dispatch | armed | unset (default armed, scope workflow_run)
WHEN:
  REQUIRE the user chose a production mode at PlanProduceChoice
DO:
  SET CF_PHASE_GATE = released_for_orchestrator_write (scope plan.toml), WRITE {cf-studio-path}/.plans/{task-slug}/plan.toml ([meta] + [plan] + [[phases]] per the template), SET CF_PHASE_GATE = armed
  SET CF_PHASE_GATE = released_for_orchestrator_write (scope brief-*.md), WRITE one brief-{NN}-{slug}.md per phase (~50-80 lines; context boundary, metadata, load instructions, budget; never copy kit content), SET CF_PHASE_GATE = armed
  EMIT the brief package summary — plan.toml + N briefs, 0/N phase files
RULES:
  ALWAYS write plan.toml before any brief or phase file, and write plan.approval_status="approved" only once that write has succeeded — an approval whose artifact never reached disk claims something no later session can read
  ALWAYS reopen CF_PHASE_GATE released_for_orchestrator_write (scoped) before each write and reset to armed immediately after
  ALWAYS emit the brief package summary only after a complete write — it reports a package the mode was chosen before, and it is the only completeness signal a downstream consumer has, so a failed or interrupted write emits none and recovery is a fresh PlanProduceChoice choice that rewrites plan.toml before any brief
  NEVER emit "Plan created" in this summary — no phase file exists yet
  NEVER run without a production mode chosen at PlanProduceChoice
ON_ERROR:
  write_failed -> EMIT "The brief package is incomplete — plan.toml or a brief file failed to write, so nothing will run against it."; EMIT "ERROR: <the raw error from the failed write>"; SET CF_PHASE_GATE = armed; STOP_TURN
```
