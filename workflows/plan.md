---
cf: true
type: workflow
name: cf-plan
description: "Invoke when the user asks to plan, create a plan, decompose, break down, or organize a large or multi-step task into phases — produces self-contained phase files with brief + compiled forms."
version: 0.1
purpose: Drive a phased planning workflow that assesses scope, decomposes a large task into self-contained phase files, and hands off to execution — only planning, never implementing, and confirming before every write.
---

# cf-plan

This skill drives a phased planning workflow that assesses scope, decomposes a large or multi-step task into self-contained phase files (plan.toml + briefs + phase files under {cf-studio-path}/.plans/{task-slug}/), and hands off to execution. It only PLANS (never implements), confirms before writing anything, and compiles one phase at a time to stay within context budget.

```pdsl
UNIT PlanBootstrap
PURPOSE: Ensure the cf skill is loaded before any plan work begins.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
DO:
  EMIT_MENU LoadCfSkillConfirm WHEN CFS_INIT != true
  STOP_TURN WHEN CFS_INIT != true
  CONTINUE PlanPhase0Discover WHEN CFS_INIT == true
RULES:
  ALWAYS verify the cf skill is loaded, CFS_INIT == true, before any plan work
  ALWAYS treat CFS_INIT as false when its value is unknown, ambiguous, or unset
  NEVER proceed past PlanBootstrap unless CFS_INIT == true is positively confirmed
  ALWAYS only generate execution plans here, never implement, and ALWAYS LOAD the relevant requirement doc per phase rather than all docs upfront
  NEVER hold all phase files in context at once — compile one at a time
  ALWAYS write plan.toml before compiling phase files
MENU LoadCfSkillConfirm
TITLE: The cf skill is not loaded. Load it now to continue?
OPTIONS:
  1 load -> INVOKE skill `cf` and CONTINUE PlanBootstrap
  2 stop -> STOP_TURN
  INVALID -> EMIT_MENU LoadCfSkillConfirm
```
```pdsl
UNIT PlanPhase0Discover
PURPOSE: Resolve runtime variables and build a dynamic tool map before any path-dependent step (Phase 0).
DO:
  RUN `{cfs_cmd} --json info`
  SET {cf-studio-path}, {project_root}, and the variables dict from the result
  RUN build a tool map from {cf-studio-path}/.core/skills/studio/studio.clispec (one entry per command) plus any kit scripts
  CONTINUE PlanExploreBrainstormGate
ON_ERROR:
  `{cfs_cmd} --json info` failure -> EMIT "Could not read studio info (`{cfs_cmd} --json info` failed) — ensure Studio is initialized with `cfs init`, then retry." and STOP_TURN
RULES:
  ALWAYS carry {cfs_cmd}, {cf-studio-path}, and {project_root} into the plan.toml [meta] table at Phase 3
  ALWAYS re-run `{cfs_cmd} --json info` on resume or context loss before any path-dependent step
```
```pdsl
UNIT PlanExploreBrainstormGate
PURPOSE: Offer resource discovery or decision exploration before scope assessment (Phase 0.a).
DO:
  EMIT_MENU PlanGateMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS carry any resource_context / brainstorm decisions into Phase 1 assessment, and ALWAYS let the user skip the gate
MENU PlanGateMenu
TITLE: Before assessing scope, explore project resources or brainstorm decisions — or skip straight to assessment? Skip is the default when the task is already well-defined; explore for unfamiliar projects, brainstorm for ambiguous requirements. Reply with a number.
OPTIONS:
  1 explore -> INVOKE skill `cf-explore` with intent=plan and return_context=true, then CONTINUE PlanPhase1Assess
  2 brainstorm -> INVOKE skill `cf-brainstorm`, then CONTINUE PlanPhase1Assess
  3 skip -> CONTINUE PlanPhase1Assess
  INVALID -> EMIT_MENU PlanGateMenu
```
```pdsl
UNIT PlanPhase1Assess
PURPOSE: Identify task type, extract target-workflow rules, estimate size, and scan every interaction point (Phase 1).
STATE:
  SET task_type: generate | analyze | implement (default unset, scope workflow_run)
DO:
  RUN map the request to a task_type and its target workflow (generate -> generate.md, analyze -> analyze.md, implement -> generate.md code mode)
  RUN extract the target workflow's navigation rules, estimate compiled size, and scan for every user interaction point (questions, confirmations, decisions, reviews, required inputs) so phases assign them
  RUN resolve the target artifact, {task-slug}, target_key, and input_signature; SET plan_dir = {cf-studio-path}/.plans/{task-slug}/
  LOAD {cf-studio-path}/.core/requirements/raw-input-overflow.md and chunk raw input under {cf-studio-path}/.plans/{task-slug}/input/ WHEN the raw task input exceeds 500 lines
  CONTINUE PlanPhase2Decompose
RULES:
  ALWAYS treat kit rules as law, and ALWAYS capture every interaction point so phases assign them
```
```pdsl
UNIT PlanPhase2Decompose
PURPOSE: Choose a lifecycle, decompose into phases, predict per-phase budget, and confirm before any write (Phase 2).
STATE:
  SET lifecycle: gitignore | cleanup | archive | manual (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/requirements/plan-decomposition.md and follow it
  RUN select a lifecycle from the STATE lifecycle options (gitignore | cleanup | archive | manual)
  RUN decompose by task-type strategy into phases (sections/categories/CDSL blocks), map intermediate results to out/ artifacts, insert review gates where the target workflow requires approval, and predict per-phase context budget — split any phase over 2000 lines
  EMIT the decomposition summary — phases, est. lines, budget
  EMIT_MENU DecompositionConfirmMenu
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER write any file before this confirmation, and NEVER hide raw-input chunk estimates in vague totals
MENU DecompositionConfirmMenu
TITLE: Explicit confirmation required before writing plan.toml + briefs. This writes plan.toml + N brief files under .plans/{task-slug}/; after confirming you choose how to produce phase files. Proceed with this decomposition?
OPTIONS:
  1 y | yes -> CONTINUE PlanPhase3Compile
  2 n | no -> EMIT "Decomposition declined — rework boundaries and re-run cf-plan when ready." and STOP_TURN
  INVALID -> EMIT_MENU DecompositionConfirmMenu
```
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
  1 inline -> compile each phase file inline from its on-disk brief (apply a context boundary, read brief from disk, WRITE phase-NN-*.md with CF_PHASE_GATE released/armed), then CONTINUE PlanPhase3Validate
  2 prompts -> emit one self-contained downstream compilation prompt per brief (no phase files written), SET plan.execution_status="prompts_emitted", and STOP_TURN (Phase 3.4 validation skipped in this mode)
  3 subagents -> CONTINUE PlanPhaseCompilerDispatch
  4 stop -> SET plan.execution_status="briefs_only" and STOP_TURN
  INVALID -> EMIT_MENU BriefCheckpointMenu
```
```pdsl
UNIT PlanPhaseCompilerDispatch
PURPOSE: Dispatch phase compiler sub-agents through an explicit lifecycle instead of blocking on an async join.
DO:
  RUN select phase compiler isolation policy from plan lifecycle, gitignore state, and whether plan.toml, briefs, and declared output paths are worktree-visible
  EMIT "Selected phase compiler: {selected_phase_compiler}. Rationale: {phase_agent_isolation_rationale}. This determines whether phase files are written in-place or in a worktree-visible isolated context."
  SET CF_PHASE_GATE = released_for_dispatch, DISPATCH the selected compiler agent per brief (gated), with dispatch_group_id recorded in plan.toml, SET CF_PHASE_GATE = armed
  SET plan.execution_status="phase_compilers_dispatched"
  STOP_TURN
RULES:
  ALWAYS use cf-phase-compiler for gitignored or main-checkout-local plan state
  ALWAYS use cf-phase-compiler-isolated only when plan.toml, briefs, and declared output paths are tracked or otherwise worktree-visible
  ALWAYS tell the user which compiler variant was selected and why before dispatch, including when sub-agent approval is already saved for the session
  ALWAYS set CF_PHASE_GATE released_for_dispatch before compiler dispatch and armed immediately after
  NEVER use WAIT as an async sub-agent join; resume validation only through PlanPhaseCompilerComplete
```
```pdsl
UNIT PlanPhaseCompilerComplete
PURPOSE: Resume after phase compiler sub-agents complete and prove their outputs exist before validation.
WHEN:
  REQUIRE plan.execution_status == "phase_compilers_dispatched"
DO:
  RUN verify every dispatched compiler signalled completion and every expected phase-NN-*.md output exists on disk
  SET plan.execution_status="phase_files_compiled"
  CONTINUE PlanPhase3Validate
ON_ERROR:
  EMIT missing compiler completion or output file evidence and STOP_TURN
```
```pdsl
UNIT PlanPhase3Validate
PURPOSE: Verify produced phase files match their briefs and cover all rules (Phase 3.4).
WHEN:
  REQUIRE phase files were produced this run (option 1 or 3)
DO:
  RUN verify every brief exists, each phase file matches its brief's load instructions, no unresolved {...} vars outside code fences, each phase file <= 1000 lines (split if oversized), and the union of all phase Rules sections covers 100% of applicable rules (re-split rather than drop rules)
  CONTINUE PlanPhase4Finalize
ON_ERROR:
  each phase file <= 1000 lines (split if oversized) check fails -> RUN auto-split the oversized phase file into ordered phase-NN-*.md parts (re-split rather than drop rules), update plan.toml [[phases]], then re-run the verify step; EMIT the oversized file path with explicit split instructions and STOP_TURN WHEN it still exceeds 1000 lines after the auto-split
RULES:
  NEVER drop rules to meet budget
```
```pdsl
UNIT PlanPhase4Finalize
PURPOSE: Self-validate the plan against the checklist and offer next steps (Phase 4).
WHEN:
  REQUIRE phase files were produced this run (brief-checkpoint option 1 or 3)
DO:
  LOAD {cf-studio-path}/.core/requirements/plan-checklist.md
  RUN self-validate against the 7 checklist categories (structural, interactive questions, rules coverage, context completeness, phase independence, budget, lifecycle & handoff) and update plan.toml status fields
  EMIT the self-validation table and offer to fix any FAIL
  EMIT "Plan created: {cf-studio-path}/.plans/{task-slug}/ (phases, files, lifecycle)" WHEN all categories PASS
  EMIT_MENU Phase4NextStepsMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS run self-validation before any handoff or startup prompt
  ALWAYS emit "Plan created" only after validation PASS confirms plan.toml + every brief + every phase file exist on disk
  ALWAYS wrap the startup prompt in a single fenced code block with no other text
  ALWAYS keep option 2 execute safe — when sub-agents are unavailable it falls back to the handoff prompt rather than failing
MENU Phase4NextStepsMenu
TITLE: Plan passed self-validation — what next? Option 1 (analyze) is the suggested default before execution. Reply with a number.
OPTIONS:
  1 analyze -> CONTINUE {cf-studio-path}/.core/workflows/analyze.md with target_paths=[plan.toml], cross_refs=[phase-*.md] to validate the plan
  2 execute -> CONTINUE PlanNativeExecute (native same-chat execution; if sub-agents are unavailable it falls back to the handoff prompt)
  3 handoff -> EMIT the new-chat startup prompt in a single fenced code block (read plan.toml, execute Phase 1, then report and prompt for Phase 2), then STOP_TURN
  4 review -> EMIT the plan file paths to inspect, then STOP_TURN
  5 modify -> WAIT the user's plan changes (add/remove phases, adjust scope, update files), then STOP_TURN
  INVALID -> EMIT_MENU Phase4NextStepsMenu
```
```pdsl
UNIT PlanNativeExecute
PURPOSE: Run native same-chat phase execution via the phase runner when sub-agents are approved.
DO:
  RUN re-probe sub-agent approval + inline-fallback
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
  REQUIRE the user asks about plan execution, status, storage format, or the execution log
DO:
  LOAD {cf-studio-path}/.core/requirements/plan-template.md and follow it for plan.toml storage format, status fields, and the execution/handoff prompt
```
```pdsl
UNIT PlanDispatch
PURPOSE: Name the sub-agents used and guard the plan safety rails.
RULES:
  ALWAYS use cf-phase-compiler and cf-phase-runner as the default non-isolated phase agents when the plan lifecycle is gitignore, plan state is gitignored, or declared outputs are main-checkout-local
  ALWAYS use cf-phase-compiler-isolated only when plan.toml, briefs, and declared output paths are tracked or otherwise worktree-visible; use cf-phase-runner-isolated only when plan.toml, briefs, phase outputs, and declared target outputs are tracked or otherwise worktree-visible
  ALWAYS tell the user which phase agent variant was selected and why before dispatch
  NEVER dispatch either without the sub-agent approval + inline-fallback re-probe resolving to approved-and-not-fallback
  ALWAYS synthesize each dispatch from the agent contract plus the needed slices and ALWAYS include git_commit_mode, contributing_guide, git_constraint, and (for the compiler) the {cf-studio-path}/.core/requirements/prompt-engineering.md slice
  NEVER let a sub-agent reopen prompt or instruction files from disk
  ALWAYS offer cf-explore / cf-brainstorm via PlanExploreBrainstormGate before assessment
```
