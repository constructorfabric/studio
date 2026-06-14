# Plan First Gate

```pdsl
UNIT PlanFirstGate
PURPOSE: Before substantive multi-step work, ask whether to plan first unless a user-approved plan is already active.
WHEN:
  REQUIRE a substantive multi-step task is about to start (validation, review, editing, prompts, skills, code, artifacts, analytical tasks, or other task work) AND no accepted plan is already active
DO:
  EMIT_MENU PlanFirstConfirm
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS ask whether a plan is needed before starting substantive multi-step task work without an accepted plan
  ALWAYS let the user decline and proceed without a plan
  ALWAYS resolve a co-triggering CreativeIntentBrainstormOffer before this gate when both apply to the same request
  NEVER start the substantive operation before this gate resolves
MENU PlanFirstConfirm
TITLE: Plan this work before starting? (recommended for multi-step or sub-agent work)
OPTIONS:
  1 plan -> CONTINUE PlanBuild
  2 no-plan -> proceed without a plan and CONTINUE the requested task
  INVALID -> EMIT_MENU PlanFirstConfirm
```

```pdsl
UNIT PlanBuild
PURPOSE: Build the execution plan, present it for review, and let the user choose where it is kept.
WHEN:
  REQUIRE the user chose to plan in PlanFirstGate
DO:
  RUN draft the plan: define the sub-agent intent for each task, group tasks into parallel, sequential, and inline execution, and order them
  EMIT the drafted plan for user review
  EMIT_MENU PlanStorageChoice
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS define the sub-agent intent for the planned work before execution
  ALWAYS classify each task as a parallel sub-agent, a sequential sub-agent, or an inline task
  ALWAYS present the plan for user review before executing it
  ALWAYS offer to save the plan to disk or keep it in session memory
  NEVER execute the planned work before the user has reviewed the plan and chosen its storage
MENU PlanStorageChoice
TITLE: Plan ready — review it, then choose how to keep it before I start.
OPTIONS:
  1 memory -> keep the plan in session memory and CONTINUE the planned work (suggested for quick iteration)
  2 disk -> WRITE the plan to disk, then CONTINUE the planned work (for persistence)
  3 revise -> revise the plan per user feedback and EMIT_MENU PlanStorageChoice
  4 stop -> STOP_TURN
  INVALID -> EMIT_MENU PlanStorageChoice
```
