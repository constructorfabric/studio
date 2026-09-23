# Plan Native Execute

```pdsl
UNIT PlanNativeExecute
PURPOSE: Run native same-chat phase execution via the phase runner when sub-agents are approved.
STATE:
  SET CF_PHASE_GATE: released_for_orchestrator_write | released_for_dispatch | armed | unset (default armed, scope workflow_run)
DO:
  EMIT "This plan has not been approved, so no phase will be dispatched. If its plan.toml carries no approval_status at all, it was written before approvals were recorded — re-run the decomposition gate to approve it; nothing is wrong with the plan. Otherwise approve it at that gate, which re-shows the plan before asking. A plan approved in an earlier session carries plan.approval_status=\"approved\" in its plan.toml; read that file to pick the approval up." and STOP_TURN WHEN plan.approval_status != "approved" in this plan's own plan.toml — the artifact, never the run-scoped flag alone, because `accepted_plan_active` is set by the plan-first gate for a different plan entirely and would authorise these phases without this decomposition ever being approved; say which case it is, since a plan.toml with no approval_status at all was written before approvals were recorded and its owner has already been through a gate they will think they passed
  SET runnable_phases = every [[phases]] entry whose status is pending or unset — a phase already done, in_progress or failed is not work this dispatch may start
  SET unknown_status_phases = every [[phases]] entry whose status is none of pending, in_progress, blocked, done or failed — a hand-edited `Block` or `blocking` matches neither the runnable set nor the held one, so it would be silently dropped from both and read as finished work rather than the invalid state it is
  EMIT the phases whose status is not one of the five declared states, naming the status found, and hold them, WHEN unknown_status_phases is not empty — an unreadable state is not evidence that a phase is done
  SET decision_held = every runnable phase whose declared needs still leave a key unresolved against this plan, counting a key the plan answers by rule as resolved when a gate will supply its case — the forecast excludes those and these rules must agree with it
  SET manually_held = every [[phases]] entry carrying status = "blocked", runnable or not: `blocked` is a lifecycle state and deliberately not a runnable one, so scoping this scan to the runnable set excluded the very phases it exists to find and its notice could never fire
  SET held_phases = decision_held together with manually_held and unknown_status_phases
  SET target_phase = the lowest-numbered runnable phase in neither held set
  EMIT every phase in held_phases with the unresolved keys it is waiting on — all of them, and the reason instead when a phase is held by status alone and names no key. Bound and strip every phase label, key and status echoed here: they come from plan.toml, which is author text, and a newline in one forges a line in this notice. WHEN held_phases is not empty. This states the hold; it performs no dispatch. The set it leaves, runnable_phases minus held_phases, is what the RUN steps below dispatch, and nothing here is dispatched before the git-policy gate has run
  EMIT "Every phase in this plan is already done, in_progress or failed, so there was nothing to dispatch." and STOP_TURN WHEN runnable_phases is empty AND manually_held is empty AND unknown_status_phases is empty — an unreadable status is not evidence of finished work, and excluding only the manual holds let an invalid-status plan report itself complete two lines after this unit held it
  EMIT "Some phases carry a status this plan's schema does not define, so no phase was dispatched — an unreadable state is held, never read as finished work. Correct each status named above to one of pending, in_progress, blocked, done or failed and re-run." and STOP_TURN WHEN nothing is left to dispatch AND unknown_status_phases is not empty — first among the hold branches because an invalid status is the one a reader must fix before any other hold can be acted on
  EMIT "Every remaining phase is held — some on an open decision, some by hand with status = \"blocked\" — so no phase was dispatched. Answer the keys listed above and lift the manual holds." and STOP_TURN WHEN nothing is left to dispatch AND unknown_status_phases is empty AND decision_held is not empty AND manually_held is not empty
  EMIT "Every remaining phase is held on an open decision, so no phase was dispatched. Answer the keys listed above and re-run." and STOP_TURN WHEN nothing is left to dispatch AND unknown_status_phases is empty AND decision_held is not empty AND manually_held is empty
  EMIT "Every remaining phase is held by hand with status = \"blocked\", so no phase was dispatched. Lift those holds to continue; there is no decision outstanding." and STOP_TURN WHEN nothing is left to dispatch AND unknown_status_phases is empty AND manually_held is not empty AND decision_held is empty
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  RUN GitCommitModeGate before preparing git policy for phase runner dispatch
  RUN SubAgentDispatch to re-probe sub-agent approval + inline-fallback for the selected phase runner dispatch group
  RUN select phase runner isolation policy from plan lifecycle, gitignore state, and whether plan.toml plus declared outputs are worktree-visible
  EMIT "Selected phase runner: {selected_phase_runner}. Rationale: {phase_agent_isolation_rationale}. This determines whether execution writes against main-checkout plan state or an isolated worktree-visible surface."
  SET CF_PHASE_GATE = released_for_dispatch WHEN approved AND not inline-fallback
  DISPATCH the selected phase runner with plan_dir, target_phase, git_commit_mode, contributing_guide, and git_constraint WHEN approved AND not inline-fallback
  SET CF_PHASE_GATE = armed WHEN approved AND not inline-fallback
  EMIT "Phase execution dispatched. The phase runner will complete its work and report back. Resume this conversation when phase {target_phase} is done to continue with the next one." WHEN approved AND not inline-fallback
  STOP_TURN WHEN approved AND not inline-fallback
  WHEN not approved OR inline-fallback active:
    EMIT "Native same-chat execution is unavailable (sub-agents not approved or inline fallback active) — use the handoff prompt instead."
    EMIT the new-chat startup prompt in a single fenced code block
    EMIT "Paste this into a new chat to begin execution. Return here after phase {target_phase} completes to continue with the next one." — named from target_phase and not written as Phase 1, because this unit now selects the lowest-numbered runnable phase in neither held set, which is phase 1 only until something earlier is done or held
    EMIT_MENU Phase4NextStepsMenu
    WAIT user.reply
    STOP_TURN
RULES:
  NEVER dispatch a phase whose plan.toml records no approval, nor one this run has revised — stated in this unit's own contract and not only in PlanDispatch's, since a reader of the unit that executes must see what it refuses
  NEVER dispatch without a successful sub-agent / inline-fallback re-probe — fall back to the handoff prompt instead
  NEVER dispatch a phase that is not runnable, and never one held by the rule above; hold it, say which keys it waits on — or that it is held by status and names none — and dispatch the rest. a phase is runnable when its status is pending or unset — never done, in_progress or failed — and it is held when re-resolving its declared `needs` against the plan leaves any key unresolved, or when its entry carries status = "blocked"; the stored awaiting_decision is a record of what was outstanding when it was written and is never the authority, so an answer supplied since cannot leave a phase held
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
