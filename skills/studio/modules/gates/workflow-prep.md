# Workflow Prep Gates

```pdsl
UNIT WorkflowPrepExploreGate
PURPOSE: Offer task-relevant context discovery before a workflow's first write or review operation.
STATE:
  SET RESOURCE_CONTEXT: unset | provided (default unset, scope workflow_run)
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
  REQUIRE WORKFLOW_PREP_EXPLORE_MENU is set
  REQUIRE WORKFLOW_PREP_BRAINSTORM_GATE is set
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md WHEN ResourceContextMemory is not loaded
  RUN ResourceContextMemory
  EMIT_MENU WORKFLOW_PREP_EXPLORE_MENU
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer cf-explore context discovery before authoring or reviewing, and ALWAYS let the user skip it
  ALWAYS default to skip when the target and surrounding context are already fully specified
  ALWAYS load context-memory before carrying RESOURCE_CONTEXT into downstream dispatches
  ALWAYS carry any returned RESOURCE_CONTEXT into every downstream workflow dispatch payload as read-only context, including author, coder, reviewer, preflight, and storytelling dispatches, NEVER as a gate on a verdict
```

```pdsl
UNIT WorkflowPrepBrainstormGate
PURPOSE: Offer decision or design exploration after the explore gate and before workflow dispatch.
STATE:
  SET BRAINSTORM_DECISIONS: unset | provided (default unset, scope workflow_run)
WHEN:
  REQUIRE WORKFLOW_PREP_BRAINSTORM_MENU is set
  REQUIRE WORKFLOW_PREP_DISPATCH_UNIT is set
DO:
  EMIT_MENU WORKFLOW_PREP_BRAINSTORM_MENU
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer cf-brainstorm decision exploration after the explore gate and before authoring or reviewing, and ALWAYS let the user skip it
  ALWAYS default to skip when the approach and its decisions are already clear and unambiguous
  ALWAYS require caller brainstorm menu options that invoke cf-brainstorm to capture a returned brainstorm_decisions object into BRAINSTORM_DECISIONS before continuing
  ALWAYS carry BRAINSTORM_DECISIONS into every downstream workflow dispatch payload as read-only context, including author, coder, reviewer, preflight, and storytelling dispatches, NEVER as a gate on a verdict
```
