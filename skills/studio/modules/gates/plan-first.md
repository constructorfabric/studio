# Plan First Gate

```pdsl
UNIT PlanFirstGate
PURPOSE: Before substantive multi-step work, ask whether to plan first unless a user-approved plan is already active.
STATE:
  SET PLAN_FIRST_CONTINUE: unit-name (default unset, scope workflow_run)
WHEN:
  REQUIRE a substantive multi-step task is about to start (validation, review, editing, prompts, skills, code, artifacts, analytical tasks, or other task work) AND no accepted plan is already active
DO:
  EMIT_MENU PlanFirstConfirm
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS ask whether a plan is needed before starting substantive multi-step task work without an accepted plan
  ALWAYS let the user decline and proceed without a plan
  ALWAYS run this gate only after companion selection has resolved for the current workflow, so planning covers the selected workflow path
  NEVER start the substantive operation before this gate resolves
  NEVER run without PLAN_FIRST_CONTINUE set by the caller
RULES:
  ALWAYS mark option 1 (plan) as (suggested) when the task has more than 5 steps or involves sub-agent dispatch; ALWAYS mark option 2 (no-plan) as (suggested) for single-file or single-step tasks
MENU PlanFirstConfirm
TITLE: Plan this work before starting? (recommended for multi-step or sub-agent work) Choosing no-plan will start the task immediately.
OPTIONS:
  1 plan -> CONTINUE PlanBuild
  2 no-plan -> proceed without a plan and CONTINUE PLAN_FIRST_CONTINUE
  3 stop — cancel and return without starting -> STOP_TURN
  INVALID -> EMIT_MENU PlanFirstConfirm
```

```pdsl
UNIT PlanBuild
PURPOSE: Build the execution plan, present it for review, and let the user choose where it is kept.
WHEN:
  REQUIRE the user chose to plan in PlanFirstGate
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN SubAgentSelectionRegistry
  RUN draft the plan at high granularity, following the PlanShapeContract, PlanExecutionDirectives, PlanGitFinalizationContract, PlanAcceptedExecutionContract, and PlanDeviationContract
  RUN validate that every `DISPATCH:` directive in the drafted plan names a sub-agent present in the loaded SubAgentSelectionRegistry; fail fast with a clear error when any name is unregistered
  EMIT the drafted plan for user review
  EMIT_MENU PlanStorageChoice
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS recommend disk storage in the storage prompt when the plan is phase-decomposed, has more than 10 actions, or needs resume-safe execution
  ALWAYS end the reviewed plan with `CONTINUE workflow protocol: CONTINUE PLAN_FIRST_CONTINUE`
  ALWAYS present the plan for user review before executing it
  ALWAYS offer to save the plan to disk or keep it in session memory
  ALWAYS set accepted_plan_active before continuing planned work
RULES:
  ALWAYS mark option 2 disk as (suggested) when the plan is phase-decomposed, has more than 10 actions, or needs resume-safe execution; ALWAYS mark option 1 memory as (suggested) for small, single-step plans
MENU PlanStorageChoice
TITLE: Plan ready — review it, then choose how to keep it before I start. Disk is suggested for large, phased, or resume-sensitive plans; memory is suggested for small plans.
OPTIONS:
  1 memory -> keep the plan in session memory, SET accepted_plan_active = true, and CONTINUE PLAN_FIRST_CONTINUE (suggested for quick iteration)
  2 disk -> WRITE the plan to disk, SET accepted_plan_active = true, and CONTINUE PLAN_FIRST_CONTINUE (for persistence)
  3 revise -> revise the plan per user feedback and EMIT_MENU PlanStorageChoice
  4 stop -> STOP_TURN
  INVALID -> EMIT_MENU PlanStorageChoice
```

```pdsl
UNIT PlanShapeContract
PURPOSE: Define required structure for drafted execution plans.
RULES:
  ALWAYS define the sub-agent intent for each planned action before execution
  ALWAYS classify each action as a parallel sub-agent, a sequential sub-agent, or an inline task
  ALWAYS make every action list owner, input, output, dependency, and verification
  ALWAYS ensure declared dependencies form a directed acyclic graph with no circular references between planned actions
  ALWAYS ensure each action's declared inputs are satisfied by the outputs of its declared dependencies or by explicit workflow/bootstrap context already in scope
  ALWAYS make plans detailed enough that each action is independently executable, reviewable, and has a named verification or validation check
  ALWAYS decompose large plans into named phases when the plan has more than 7 actions, spans multiple files/workflows, or needs more than one validation checkpoint; every phase lists its exit condition and validation command, review, or observable evidence
  ALWAYS make every phase independently verifiable with an exit condition and validation command, review, or observable evidence
```

```pdsl
UNIT PlanExecutionDirectives
PURPOSE: Define the accepted execution-directive syntax for plan items.
RULES:
  ALWAYS require every plan item to include exactly one execution directive: `DISPATCH:`, `INLINE:`, or `GIT_FINALIZATION:`
  ALWAYS use `DISPATCH: <sub-agent-name>` for delegated sub-agent work, prefer it over `INLINE:` when a registered cf-* sub-agent can materially perform the work, and include whether the dispatch is parallel or sequential in the plan item body
  ALWAYS prefer `DISPATCH: <sub-agent-name>` over inline steps when a registered cf-* sub-agent can materially perform the planned action
  ALWAYS choose `DISPATCH: <sub-agent-name>` over `INLINE:` for capable registered cf-* sub-agents
  ALWAYS use `INLINE: <controller reason>` only for controller-owned gates, simple probes, or tasks with no suitable registered sub-agent
  ALWAYS state why it cannot be dispatched when a planned action uses `INLINE:` instead of a capable registered cf-* sub-agent
  ALWAYS use `GIT_FINALIZATION: inspect-only | stage | create-commit` as the only git-handling execution directive for accepted plans
  ALWAYS choose sub-agent names from the loaded `agents.toml` registry exposed by SubAgentSelectionRegistry; NEVER invent, alias, or infer unregistered sub-agent names
```

```pdsl
UNIT PlanGitFinalizationContract
PURPOSE: Define git-finalization placement and gate requirements for file-writing plans.
RULES:
  ALWAYS include at least one `GIT_FINALIZATION:` plan item or phase in every file-writing plan
  ALWAYS include a git finalization action in every file-writing plan
  ALWAYS require any `GIT_FINALIZATION: stage` or `GIT_FINALIZATION: create-commit` action to run GitCommitModeGate before any git state change
  ALWAYS route through GitCommitModeGate before git state changes in any `GIT_FINALIZATION: stage` or `GIT_FINALIZATION: create-commit` action
  ALWAYS place any `GIT_FINALIZATION: create-commit` action after file edits and required validation/review gates unless the owning workflow defines a stricter commit point
```

```pdsl
UNIT PlanAcceptedExecutionContract
PURPOSE: Define how accepted plans execute after storage selection.
RULES:
  ALWAYS after accepted_plan_active is set, treat the accepted plan as the controlling execution contract until it completes, is revised, or is explicitly cancelled
  ALWAYS before executing each planned action, read and follow its execution directive: `DISPATCH:`, `INLINE:`, or `GIT_FINALIZATION:`
  ALWAYS execute `DISPATCH: <sub-agent-name>` actions through SubAgentDispatch for the named sub-agent; NEVER perform a DISPATCH action inline merely because it appears small, local, faster, or easier
  ALWAYS execute `INLINE:` actions directly only when the accepted plan labels that action INLINE
  ALWAYS execute `GIT_FINALIZATION:` actions exactly as labeled; `inspect-only` permits read-only git inspection, `stage` must run GitCommitModeGate before any git state change, and `create-commit` must run GitCommitModeGate before any git state change or commit preparation
```

```pdsl
UNIT PlanDeviationContract
PURPOSE: Fail closed when accepted plan execution cannot follow the reviewed plan.
RULES:
  ALWAYS STOP_TURN and report a plan-deviation error when the next planned action cannot be executed as written
  NEVER let an accepted plan silently start task work or bypass the owning workflow protocol; accepted exits must return through `CONTINUE PLAN_FIRST_CONTINUE`
  NEVER execute the planned work before the user has reviewed the plan and chosen its storage
```
