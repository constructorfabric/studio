# Plan Compiler Dispatch

```pdsl
UNIT PlanPhaseCompilerDispatch
PURPOSE: Dispatch phase compiler sub-agents through an explicit lifecycle instead of blocking on an async join.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  RUN GitCommitModeGate before preparing git policy for phase compiler dispatch
  RUN select phase compiler isolation policy from plan lifecycle, gitignore state, and whether plan.toml, briefs, and declared output paths are worktree-visible
  EMIT "Selected phase compiler: {selected_phase_compiler}. Rationale: {phase_agent_isolation_rationale}. This determines whether phase files are written in-place or in a worktree-visible isolated context."
  RUN SubAgentDispatch for the selected phase compiler dispatch group
  RUN PlanPhaseCompilerDispatchRun
  STOP_TURN
RULES:
  ALWAYS use cf-phase-compiler for gitignored or main-checkout-local plan state
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
  RUN verify every dispatched compiler signalled completion and every expected phase-NN-*.md output exists on disk
  SET plan.execution_status="phase_files_compiled"
  LOAD {cf-studio-path}/.core/skills/studio/modules/plan-validate-finalize.md
  CONTINUE PlanPhase3Validate
ON_ERROR:
  EMIT missing compiler completion or output file evidence and STOP_TURN
```
