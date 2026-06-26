# Workflow Prep Gates

```pdsl
UNIT WorkflowPrepExploreGate
PURPOSE: Offer task-relevant context discovery before a workflow's first write or review operation.
STATE:
  SET RESOURCE_CONTEXT: unset | provided (default unset, scope workflow_run)
  SET RESOURCE_CONTEXT_REF: reference | unset (default unset, scope workflow_run)
  SET RESOURCE_CONTEXT_TASK_KEY: string | unset (default unset, scope workflow_run)
  SET RESOURCE_CONTEXT_PROVENANCE: object | unset (default unset, scope workflow_run)
  SET WORKFLOW_PREP_EXPLORE_MENU: menu-name | unset (default unset, scope workflow_run)
  SET WORKFLOW_PREP_BRAINSTORM_GATE: unit-name | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
  REQUIRE WORKFLOW_PREP_EXPLORE_MENU is set
  REQUIRE WORKFLOW_PREP_BRAINSTORM_GATE is set
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md WHEN ResourceContextMemory is not loaded
  RUN ResourceContextMemory
  RUN derive the current normalized workflow-prep task key from ORIGINAL_INTENT, target paths, workflow name, and requested operation
  RUN inspect current workflow state and session resource_context memory for an existing resource_context whose RESOURCE_CONTEXT_TASK_KEY exactly matches the current task key; SET RESOURCE_CONTEXT = provided and retain RESOURCE_CONTEXT_REF and RESOURCE_CONTEXT_PROVENANCE WHEN matching resource_context is already available
  CONTINUE WorkflowPrepExploreRepeatGate WHEN RESOURCE_CONTEXT == provided
  EMIT_MENU WORKFLOW_PREP_EXPLORE_MENU
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer cf-explore context discovery before authoring or reviewing, and ALWAYS let the user skip it
  ALWAYS default to skip when the target and surrounding context are already fully specified
  ALWAYS load context-memory before carrying RESOURCE_CONTEXT into downstream dispatches
  ALWAYS carry RESOURCE_CONTEXT_REF plus RESOURCE_CONTEXT_PROVENANCE into every downstream workflow dispatch payload as read-only context, including author, coder, reviewer, preflight, and storytelling dispatches, NEVER as a gate on a verdict
  NEVER reuse a resource_context unless RESOURCE_CONTEXT_REF is present and RESOURCE_CONTEXT_TASK_KEY exactly matches the current normalized workflow-prep task key
```

```pdsl
UNIT WorkflowPrepExploreRepeatGate
PURPOSE: Confirm whether to reuse existing workflow-prep resource_context or run cf-explore again.
WHEN:
  REQUIRE RESOURCE_CONTEXT == provided
  REQUIRE WORKFLOW_PREP_EXPLORE_MENU is set
  REQUIRE WORKFLOW_PREP_BRAINSTORM_GATE is set
DO:
  EMIT_MENU WorkflowPrepExploreRepeatMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS ask before running cf-explore again when RESOURCE_CONTEXT already exists for the current workflow-prep task
  ALWAYS recommend skipping when existing resource_context still matches ORIGINAL_INTENT and no stale-context evidence is known
  ALWAYS show the stored RESOURCE_CONTEXT_TASK_KEY or concise provenance summary when asking whether to reuse context
  NEVER discard existing RESOURCE_CONTEXT unless the user chooses to run cf-explore again
MENU WorkflowPrepExploreRepeatMenu
TITLE: Existing cf-explore resource_context is already available for this workflow-prep task. Run cf-explore again only if the target changed or the context is stale; skip/reuse is suggested. Reply with a number.
OPTIONS:
  1 skip-reuse -> CONTINUE WORKFLOW_PREP_BRAINSTORM_GATE
  2 explore-again -> SET RESOURCE_CONTEXT = unset; SET RESOURCE_CONTEXT_REF = unset; SET RESOURCE_CONTEXT_TASK_KEY = unset; SET RESOURCE_CONTEXT_PROVENANCE = unset; EMIT_MENU WORKFLOW_PREP_EXPLORE_MENU; WAIT user.reply; STOP_TURN
  INVALID -> EMIT_MENU WorkflowPrepExploreRepeatMenu
```

```pdsl
UNIT WorkflowPrepBrainstormGate
PURPOSE: Offer decision or design exploration after the explore gate and before workflow dispatch.
STATE:
  SET BRAINSTORM_DECISIONS: unset | provided (default unset, scope workflow_run)
  SET WORKFLOW_PREP_BRAINSTORM_MENU: menu-name | unset (default unset, scope workflow_run)
  SET WORKFLOW_PREP_DISPATCH_UNIT: unit-name | unset (default unset, scope workflow_run)
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
