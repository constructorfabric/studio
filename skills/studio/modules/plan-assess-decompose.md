# Plan Assess

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
  LOAD {cf-studio-path}/.core/requirements/plan-decomposition.md
  RUN follow the plan-decomposition.md methodology rules
  LOAD {cf-studio-path}/.core/skills/studio/modules/planning-runtime.md
  RUN PlanningPhaseContract
  RUN PlanningChecklistContract
  RUN select a lifecycle from the STATE lifecycle options (gitignore | cleanup | archive | manual)
  RUN decompose by task-type strategy into phases (sections/categories/CDSL blocks), map intermediate results to out/ artifacts, insert review gates where the target workflow requires approval, and predict per-phase context budget — split any phase over 2000 lines
  LOAD {cf-studio-path}/.core/skills/studio/modules/plan-compile.md
  EMIT the decomposition summary — phases, est. lines, budget
  EMIT_MENU DecompositionConfirmMenu
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER write any file before this confirmation, and NEVER hide raw-input chunk estimates in vague totals
  ALWAYS normalize decomposed phases against the shared PlanningPhaseContract and PlanningChecklistContract before standalone packaging begins
MENU DecompositionConfirmMenu
TITLE: Explicit confirmation required before writing plan.toml + briefs. This writes plan.toml + N brief files under .plans/{task-slug}/; after confirming you choose how to produce phase files. Proceed with this decomposition?
OPTIONS:
  1 y | yes -> CONTINUE PlanPhase3Compile
  2 n | no -> EMIT "Decomposition declined — rework boundaries and re-run cf-plan when ready." and STOP_TURN
  3 revise — describe what to change about this decomposition -> EMIT "Describe what to change (e.g. split phase 2, merge phases 3 and 4, adjust scope). I will rework and re-show."; WAIT user.reply; STOP_TURN; CONTINUE PlanPhase2Decompose
  INVALID -> EMIT_MENU DecompositionConfirmMenu
```
