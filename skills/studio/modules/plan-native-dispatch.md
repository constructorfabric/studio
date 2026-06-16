# Plan Native Execute

```pdsl
UNIT PlanNativeExecute
PURPOSE: Run native same-chat phase execution via the phase runner when sub-agents are approved.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  RUN GitCommitModeGate before preparing git policy for phase runner dispatch
  RUN SubAgentDispatch to re-probe sub-agent approval + inline-fallback for the selected phase runner dispatch group
  RUN select phase runner isolation policy from plan lifecycle, gitignore state, and whether plan.toml plus declared outputs are worktree-visible
  EMIT "Selected phase runner: {selected_phase_runner}. Rationale: {phase_agent_isolation_rationale}. This determines whether execution writes against main-checkout plan state or an isolated worktree-visible surface."
  SET CF_PHASE_GATE = released_for_dispatch, DISPATCH the selected phase runner with plan_dir, target_phase=1, git_commit_mode, contributing_guide, and git_constraint, SET CF_PHASE_GATE = armed, then STOP_TURN WHEN approved AND not inline-fallback
  EMIT "Native same-chat execution is unavailable (sub-agents not approved or inline fallback active) — use the handoff prompt instead." then EMIT the new-chat startup prompt in a single fenced code block and STOP_TURN WHEN not approved OR inline-fallback active
RULES:
  NEVER dispatch without a successful sub-agent / inline-fallback re-probe — fall back to the handoff prompt instead
  ALWAYS set CF_PHASE_GATE released_for_dispatch before dispatch and armed immediately after, and ALWAYS include plan_dir, target_phase, git_commit_mode, contributing_guide, and git_constraint
```

```pdsl
UNIT PlanReference
PURPOSE: Load execution, status, storage-format, or execution-log reference on demand (post-creation).
WHEN:
  REQUIRE ORIGINAL_INTENT != unset AND ORIGINAL_INTENT matches plan execution | plan status | plan.toml | storage format | execution log
DO:
  LOAD {cf-studio-path}/.core/requirements/plan-checklist.md and follow it for the plan.toml manifest contract, status fields, lifecycle, and handoff validation rules
  LOAD {cf-studio-path}/.core/requirements/plan-template.md and follow it for the next-phase execution prompt and final handoff output shape
```

```pdsl
UNIT PlanDispatch
PURPOSE: Name the sub-agents used and guard the plan safety rails.
RULES:
  ALWAYS use cf-phase-compiler and cf-phase-runner as the default non-isolated phase agents when the plan lifecycle is gitignore, plan state is gitignored, or declared outputs are main-checkout-local
  ALWAYS use cf-phase-compiler-isolated only when plan.toml, briefs, and declared output paths are tracked or otherwise worktree-visible; use cf-phase-runner-isolated only when plan.toml, briefs, phase outputs, and declared target outputs are tracked or otherwise worktree-visible
  ALWAYS tell the user which phase agent variant was selected and why before dispatch
  ALWAYS run GitCommitModeGate before preparing git policy for native phase compiler or phase runner dispatch
  ALWAYS run SubAgentDispatch before native phase compiler or phase runner dispatch
  NEVER dispatch either without the sub-agent approval + inline-fallback re-probe resolving to approved-and-not-fallback
  ALWAYS synthesize each dispatch from the agent contract plus the needed slices and ALWAYS include git_commit_mode, contributing_guide, git_constraint, and (for the compiler) the {cf-studio-path}/.core/requirements/prompt-engineering.md slice
  NEVER let a sub-agent reopen prompt or instruction files from disk
  ALWAYS offer cf-explore / cf-brainstorm via PlanExploreBrainstormGate before assessment
```
