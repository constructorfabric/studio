# Write Skills Prep Gates

```pdsl
UNIT WriteSkillsExploreGate
PURPOSE: Offer task-relevant context discovery before any skill file is authored or reviewed, after Bootstrap and before the first edit.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET WORKFLOW_PREP_EXPLORE_MENU = WriteSkillsExploreMenu
  SET WORKFLOW_PREP_BRAINSTORM_GATE = WriteSkillsBrainstormGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepExploreGate
MENU WriteSkillsExploreMenu
TITLE: Before writing or reviewing a skill, discover task-relevant project context (sibling skills, workflows, agent contracts, referenced requirements, PDSL conventions) with cf-explore — or skip? Skip is the default when the target and its context are already clear; explore for unfamiliar or cross-cutting prompt work. Reply with a number.
OPTIONS:
  1 explore -> INVOKE skill `cf-explore` with intent=workflow-prep, task=ORIGINAL_INTENT, return_context=true; require it to return resource_context only and not perform review/authoring, SET RESOURCE_CONTEXT = provided, then CONTINUE WriteSkillsBrainstormGate
  2 skip -> CONTINUE WriteSkillsBrainstormGate
  INVALID -> EMIT_MENU WriteSkillsExploreMenu
```

```pdsl
UNIT WriteSkillsBrainstormGate
PURPOSE: Offer decision/design exploration via cf-brainstorm as the next step after the explore gate, before any skill file is authored or reviewed.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET WORKFLOW_PREP_BRAINSTORM_MENU = WriteSkillsBrainstormMenu
  SET WORKFLOW_PREP_DISPATCH_UNIT = PlanFirstGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepBrainstormGate
MENU WriteSkillsBrainstormMenu
TITLE: Before writing or reviewing a skill, brainstorm ambiguous decisions or design options with cf-brainstorm — or skip? Skip is the default when the approach is already clear; brainstorm for ambiguous requirements or open design questions. Reply with a number.
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`; require it to return brainstorm_decisions, then SET BRAINSTORM_DECISIONS = provided, SET PLAN_FIRST_CONTINUE = WriteSkillsAuthorDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  2 skip -> SET PLAN_FIRST_CONTINUE = WriteSkillsAuthorDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  INVALID -> EMIT_MENU WriteSkillsBrainstormMenu
```
