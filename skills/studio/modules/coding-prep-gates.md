# Coding Prep Gates

```pdsl
UNIT CodingExploreGate
PURPOSE: Offer task-relevant context discovery before any code is authored or reviewed, after Bootstrap and before the first edit.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET WORKFLOW_PREP_EXPLORE_MENU = CodingExploreMenu
  SET WORKFLOW_PREP_BRAINSTORM_GATE = CodingBrainstormGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepExploreGate
MENU CodingExploreMenu
TITLE: Before writing or reviewing code, discover task-relevant project context (existing conventions, related modules, call sites) with cf-explore — or skip? Skip is the default when the target and its context are already clear; explore for unfamiliar or cross-cutting code. Reply with a number.
OPTIONS:
  1 explore -> INVOKE skill `cf-explore` with intent=workflow-prep, task=ORIGINAL_INTENT, return_context=true; require it to return resource_context only and not perform review/authoring, SET RESOURCE_CONTEXT = provided, then CONTINUE CodingBrainstormGate
  2 skip -> CONTINUE CodingBrainstormGate
  INVALID -> EMIT_MENU CodingExploreMenu
```

```pdsl
UNIT CodingBrainstormGate
PURPOSE: Offer decision/design exploration via cf-brainstorm as the next step after the explore gate, before any code is authored or reviewed.
DO:
  SET WORKFLOW_PREP_BRAINSTORM_MENU = CodingBrainstormMenu
  SET WORKFLOW_PREP_DISPATCH_UNIT = PlanFirstGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepBrainstormGate
MENU CodingBrainstormMenu
TITLE: Before writing or reviewing code, brainstorm ambiguous decisions or design options with cf-brainstorm — or skip? Skip is the default when the approach is already clear; brainstorm for ambiguous requirements or open design questions. Reply with a number.
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`; require it to return brainstorm_decisions, SET BRAINSTORM_DECISIONS = provided, then SET PLAN_FIRST_CONTINUE = CodingDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  2 skip -> SET PLAN_FIRST_CONTINUE = CodingDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  INVALID -> EMIT_MENU CodingBrainstormMenu
```
