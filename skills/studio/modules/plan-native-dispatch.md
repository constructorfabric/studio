# Plan Native Execute

```pdsl
UNIT PlanNativeExecute
PURPOSE: Run native same-chat phase execution via the phase runner when sub-agents are approved.
STATE:
  SET CF_PHASE_GATE: released_for_orchestrator_write | released_for_dispatch | armed | unset (default armed, scope workflow_run)
DO:
  EMIT "This plan has not been approved, so no phase will be dispatched. If its plan.toml carries no approval_status at all, it was written before approvals were recorded — re-run the decomposition gate to approve it; nothing is wrong with the plan. Otherwise approve it at that gate, which re-shows the plan before asking. A plan approved in an earlier session carries plan.approval_status=\"approved\" in its plan.toml; read that file to pick the approval up." and STOP_TURN WHEN plan.approval_status != "approved" in this plan's own plan.toml — the artifact, never the run-scoped flag alone, because `accepted_plan_active` is set by the plan-first gate for a different plan entirely and would authorise these phases without this decomposition ever being approved; say which case it is, since a plan.toml with no approval_status at all was written before approvals were recorded and its owner has already been through a gate they will think they passed
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  RUN GitCommitModeGate before preparing git policy for phase runner dispatch
  RUN SubAgentDispatch to re-probe sub-agent approval + inline-fallback for the selected phase runner dispatch group
  RUN select phase runner isolation policy from plan lifecycle, gitignore state, and whether plan.toml plus declared outputs are worktree-visible
  EMIT "Selected phase runner: {selected_phase_runner}. Rationale: {phase_agent_isolation_rationale}. This determines whether execution writes against main-checkout plan state or an isolated worktree-visible surface."
  SET CF_PHASE_GATE = released_for_dispatch WHEN approved AND not inline-fallback
  DISPATCH the selected phase runner with plan_dir, target_phase=1, git_commit_mode, contributing_guide, and git_constraint WHEN approved AND not inline-fallback
  SET CF_PHASE_GATE = armed WHEN approved AND not inline-fallback
  EMIT "Phase execution dispatched. The phase runner will complete its work and report back. Resume this conversation when Phase 1 is done to continue with Phase 2." WHEN approved AND not inline-fallback
  STOP_TURN WHEN approved AND not inline-fallback
  WHEN not approved OR inline-fallback active:
    EMIT "Native same-chat execution is unavailable (sub-agents not approved or inline fallback active) — use the handoff prompt instead."
    EMIT the new-chat startup prompt in a single fenced code block
    EMIT "Paste this into a new chat to begin execution. Return here after Phase 1 completes to continue with Phase 2."
    EMIT_MENU Phase4NextStepsMenu
    WAIT user.reply
    STOP_TURN
RULES:
  NEVER dispatch a phase whose plan.toml records no approval, nor one this run has revised — stated in this unit's own contract and not only in PlanDispatch's, since a reader of the unit that executes must see what it refuses
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
  NEVER dispatch a phase for a plan the user has not approved; the approval that counts is plan.approval_status in that plan's own plan.toml, since the run-scoped flag is shared with the plan-first gate and says nothing about this decomposition
```
