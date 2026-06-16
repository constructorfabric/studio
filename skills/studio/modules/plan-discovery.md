# Plan Discovery

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
  LOAD {cf-studio-path}/.core/skills/studio/modules/plan-assess-decompose.md
  RUN ResourceContextMemory
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
