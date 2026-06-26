# Write Docs Prep Gates

```pdsl
UNIT WriteDocsExploreGate
PURPOSE: Offer task-relevant context discovery before any document is authored or reviewed, after Bootstrap and before the first edit.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET WORKFLOW_PREP_EXPLORE_MENU = WriteDocsExploreMenu
  SET WORKFLOW_PREP_BRAINSTORM_GATE = WriteDocsBrainstormGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepExploreGate
RULES:
  ALWAYS use WorkflowPrepExploreGate for the shared explore prompt mechanics
  ALWAYS auto-skip and CONTINUE the next unit when ORIGINAL_INTENT resolves to a single known file with no cross-cutting references; emit a single-line note "Skipping context discovery — target is clear." when auto-skipping
MENU WriteDocsExploreMenu
TITLE: Before writing or reviewing docs, discover task-relevant project context (existing docs, related guides, source material, conventions) with cf-explore — or skip? Skip is the default when the target and its context are already clear; explore for unfamiliar or cross-cutting documentation. cf-explore scans the project and returns a summary of relevant files and context. Reply with a number.
OPTIONS:
  1 explore -> INVOKE skill `cf-explore` with intent=workflow-prep, task=ORIGINAL_INTENT, return_context=true; require it to return resource_context only and not perform review/authoring, SET RESOURCE_CONTEXT = provided, then CONTINUE WriteDocsBrainstormGate
  2 skip (suggested when task is not clearly cross-cutting) -> CONTINUE WriteDocsBrainstormGate
  INVALID -> EMIT_MENU WriteDocsExploreMenu
```

```pdsl
UNIT WriteDocsBrainstormGate
PURPOSE: Offer decision/design exploration via cf-brainstorm as the next step after the explore gate, before any document is authored or reviewed.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET WORKFLOW_PREP_BRAINSTORM_MENU = WriteDocsBrainstormMenu
  SET WORKFLOW_PREP_DISPATCH_UNIT = PlanFirstGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepBrainstormGate
RULES:
  ALWAYS use WorkflowPrepBrainstormGate for the shared brainstorm prompt mechanics
  ALWAYS auto-skip and CONTINUE the next unit when ORIGINAL_INTENT resolves to a single known file with no cross-cutting references; emit a single-line note "Skipping context discovery — target is clear." when auto-skipping
NOTES: To reduce turn count, callers may collapse this gate and WriteDocsExploreGate into a single preparation menu offering explore, brainstorm, both, or skip.
MENU WriteDocsBrainstormMenu
TITLE: Before writing or reviewing docs, brainstorm ambiguous decisions or framing options with cf-brainstorm — or skip? Skip is the default when the approach is already clear; brainstorm for ambiguous requirements or open framing questions. Reply with a number.
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`; require it to return brainstorm_decisions, SET BRAINSTORM_DECISIONS = provided, then SET PLAN_FIRST_CONTINUE = WriteDocsAuthorDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  2 skip (suggested when approach is clear) -> SET PLAN_FIRST_CONTINUE = WriteDocsAuthorDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  INVALID -> EMIT_MENU WriteDocsBrainstormMenu
```
