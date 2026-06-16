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
MENU PlanFirstConfirm
TITLE: Plan this work before starting? (recommended for multi-step or sub-agent work)
OPTIONS:
  1 plan -> CONTINUE PlanBuild
  2 no-plan -> proceed without a plan and CONTINUE PLAN_FIRST_CONTINUE
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
  RUN draft the plan at high granularity: decompose work into concrete actions with owner, input, output, dependency, and verification; group actions into phases when the plan has more than 7 actions or multiple validation checkpoints; define the sub-agent intent for each action; group actions into parallel, sequential, and inline execution; prefer `DISPATCH: <sub-agent-name>` for every task that a capable cf-* sub-agent can perform; reserve `INLINE:` for controller-only gates, simple probes, and operations with no suitable sub-agent; require every inline item to state why it cannot be dispatched; include a git finalization action or phase for any file-writing plan; and end the plan with `CONTINUE workflow protocol: CONTINUE PLAN_FIRST_CONTINUE`
  EMIT the drafted plan for user review
  EMIT_MENU PlanStorageChoice
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS define the sub-agent intent for the planned work before execution
  ALWAYS classify each action as a parallel sub-agent, a sequential sub-agent, or an inline task
  ALWAYS make plans detailed enough that each action is independently executable, reviewable, and has a named verification or validation check
  ALWAYS decompose large plans into named phases when the plan has more than 7 actions, spans multiple files/workflows, or needs more than one validation checkpoint
  ALWAYS make every phase independently verifiable by listing its exit condition and validation command, review, or observable evidence
  ALWAYS require every plan item to include an explicit execution directive; use `DISPATCH: <sub-agent-name>` for delegated sub-agent work and `INLINE:` only for controller-owned gates, simple probes, or tasks with no suitable sub-agent
  ALWAYS choose sub-agent names from the loaded `agents.toml` registry exposed by SubAgentSelectionRegistry; NEVER invent, alias, or infer unregistered sub-agent names
  ALWAYS choose `DISPATCH: <sub-agent-name>` over `INLINE:` when a registered cf-* sub-agent can materially perform the inspect, classify, review, validate, author, fix, plan, explore, or implementation work
  ALWAYS include the selected sub-agent name and whether the delegated task is parallel or sequential in each `DISPATCH:` plan item
  ALWAYS include a short reason in every `INLINE:` plan item explaining why the controller must do it directly
  ALWAYS include a git finalization action for file-writing plans that states whether the workflow should inspect git state only, stage files, or create a commit; any planned staging or commit must explicitly route through GitCommitModeGate before git state changes
  ALWAYS recommend disk storage in the storage prompt when the plan is phase-decomposed, has more than 10 actions, or needs resume-safe execution
  ALWAYS end the reviewed plan with `CONTINUE workflow protocol: CONTINUE PLAN_FIRST_CONTINUE`
  ALWAYS present the plan for user review before executing it
  ALWAYS offer to save the plan to disk or keep it in session memory
  ALWAYS set accepted_plan_active before continuing planned work
  NEVER let an accepted plan silently start task work or bypass the owning workflow protocol; accepted exits must return through `CONTINUE PLAN_FIRST_CONTINUE`
  NEVER execute the planned work before the user has reviewed the plan and chosen its storage
MENU PlanStorageChoice
TITLE: Plan ready — review it, then choose how to keep it before I start. Disk is suggested for large, phased, or resume-sensitive plans; memory is suggested for small plans.
OPTIONS:
  1 memory -> keep the plan in session memory, SET accepted_plan_active = true, and CONTINUE PLAN_FIRST_CONTINUE (suggested for quick iteration)
  2 disk -> WRITE the plan to disk, SET accepted_plan_active = true, and CONTINUE PLAN_FIRST_CONTINUE (for persistence)
  3 revise -> revise the plan per user feedback and EMIT_MENU PlanStorageChoice
  4 stop -> STOP_TURN
  INVALID -> EMIT_MENU PlanStorageChoice
```
