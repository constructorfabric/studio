# Plan Compiler Dispatch

```pdsl
UNIT PlanPhaseCompilerDispatch
PURPOSE: Dispatch phase compiler sub-agents through an explicit lifecycle instead of blocking on an async join.
DO:
  EMIT "This plan has not been approved, so no phase will be dispatched. If its plan.toml carries no approval_status at all, it was written before approvals were recorded — re-run the decomposition gate to approve it; nothing is wrong with the plan. Otherwise approve it at that gate, which re-shows the plan before asking. A plan approved in an earlier session carries plan.approval_status=\"approved\" in its plan.toml; read that file to pick the approval up." and STOP_TURN WHEN plan.approval_status != "approved" in this plan's own plan.toml — the artifact, never the run-scoped flag alone, because `accepted_plan_active` is set by the plan-first gate for a different plan entirely and would authorise these phases without this decomposition ever being approved; say which case it is, since a plan.toml with no approval_status at all was written before approvals were recorded and its owner has already been through a gate they will think they passed
  SET runnable_phases = every [[phases]] entry whose status is pending or unset — a phase already done, in_progress or failed is not work this dispatch group may recompile, and its output file already exists
  SET decision_held = every runnable phase whose declared needs still leave a key unresolved against this plan, counting a key the plan answers by rule as resolved when a gate will supply its case — the forecast excludes those and these rules must agree with it
  SET manually_held = every [[phases]] entry carrying status = "blocked", runnable or not: a by-hand hold is not a lifecycle state, so scoping it to the runnable set hid it entirely and its notice could never fire
  SET held_phases = decision_held together with manually_held
  EMIT every phase in held_phases with the unresolved keys it is waiting on — all of them, and the reason instead when a phase is held by status alone and names no key — WHEN held_phases is not empty. This states the hold; it performs no dispatch. The set it leaves, runnable_phases minus held_phases, is what the RUN steps below dispatch, and nothing here is dispatched before the git-policy gate has run
  EMIT "Every phase in this plan is already done, in_progress or failed, so there was nothing to compile." and STOP_TURN WHEN runnable_phases is empty AND manually_held is empty
  EMIT "Every remaining phase is held — some on an open decision, some by hand with status = \"blocked\" — so no compiler was dispatched. Answer the keys listed above and lift the manual holds." and STOP_TURN WHEN nothing is left to dispatch AND decision_held is not empty AND manually_held is not empty
  EMIT "Every remaining phase is held on an open decision, so no compiler was dispatched. Answer the keys listed above and re-run." and STOP_TURN WHEN nothing is left to dispatch AND decision_held is not empty AND manually_held is empty
  EMIT "Every remaining phase is held by hand with status = \"blocked\", so no compiler was dispatched. Lift those holds to continue; there is no decision outstanding." and STOP_TURN WHEN nothing is left to dispatch AND manually_held is not empty AND decision_held is empty
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  RUN GitCommitModeGate before preparing git policy for phase compiler dispatch
  RUN select phase compiler isolation policy from plan lifecycle, gitignore state, and whether plan.toml, briefs, and declared output paths are worktree-visible
  EMIT "Selected phase compiler: {selected_phase_compiler}. Rationale: {phase_agent_isolation_rationale}. This determines whether phase files are written in-place or in a worktree-visible isolated context."
  RUN SubAgentDispatch for the selected phase compiler dispatch group
  RUN PlanPhaseCompilerDispatchRun
  EMIT "Phase compilation dispatched. Resume this conversation after all phase compiler agents signal completion — then continue with PlanPhaseCompilerComplete to validate outputs."
  STOP_TURN
RULES:
  ALWAYS use cf-phase-compiler for gitignored or main-checkout-local plan state, and NEVER include a phase that is not runnable, nor one held by the rule above — hold it, name the keys it waits on or say it is held by status and names none, and dispatch the rest. a phase is runnable when its status is pending or unset — never done, in_progress or failed — and it is held when re-resolving its declared `needs` against the plan leaves any key unresolved, or when its entry carries status = "blocked"; the stored awaiting_decision is a record of what was outstanding when it was written and is never the authority, so an answer supplied since cannot leave a phase held
  ALWAYS use cf-phase-compiler-isolated only when plan.toml, briefs, and declared output paths are tracked or otherwise worktree-visible
  ALWAYS tell the user which compiler variant was selected and why before dispatch, including when sub-agent approval is already saved for the session
  ALWAYS set CF_PHASE_GATE released_for_dispatch before compiler dispatch and armed immediately after
  NEVER use WAIT as an async sub-agent join; resume validation only through PlanPhaseCompilerComplete
```

```pdsl
UNIT PlanPhaseCompilerDispatchRun
PURPOSE: Open the phase gate, dispatch compiler agents, and persist the dispatched state.
STATE:
  SET CF_PHASE_GATE: released_for_orchestrator_write | released_for_dispatch | armed | unset (default armed, scope workflow_run)
DO:
  SET CF_PHASE_GATE = released_for_dispatch
  DISPATCH the selected compiler agent per brief (gated), with dispatch_group_id recorded in plan.toml
  SET CF_PHASE_GATE = armed
  SET plan.execution_status="phase_compilers_dispatched"
```

```pdsl
UNIT PlanPhaseCompilerComplete
PURPOSE: Resume after phase compiler sub-agents complete and prove their outputs exist before validation.
WHEN:
  REQUIRE plan.execution_status == "phase_compilers_dispatched"
DO:
  RUN verify every dispatched compiler signalled completion and every expected phase-NN-*.md output exists on disk, where "expected" is the phases of this dispatch_group_id and never every phase in the plan — a held phase was deliberately not dispatched, so demanding its output would report the hold as a compiler failure and send its author to re-dispatch work that was correctly withheld
  EMIT the phases still held and the keys each waits on, so a plan that compiled everything it dispatched does not read as a plan that compiled everything, WHEN any phase was held back from this dispatch group
  SET plan.execution_status="phase_files_compiled"
  LOAD {cf-studio-path}/.core/skills/studio/modules/plan-validate-finalize.md
  CONTINUE PlanPhase3Validate
ON_ERROR:
  EMIT missing compiler completion or output file evidence
  EMIT_MENU PlanCompilerFailureMenu
  WAIT user.reply
  STOP_TURN
MENU PlanCompilerFailureMenu
TITLE: One or more phase compiler agents did not produce expected output. How would you like to proceed?
OPTIONS:
  1 re-dispatch — re-run failed phase compilers -> CONTINUE PlanPhaseCompilerDispatch
  2 inline — fall back to inline phase compilation for failed phases -> LOAD {cf-studio-path}/.core/skills/studio/modules/plan-validate-finalize.md; CONTINUE PlanPhase3Validate
  3 stop — keep the current outputs and return to free mode -> LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded; RUN NextActionsOffer
  INVALID -> EMIT_MENU PlanCompilerFailureMenu
```
