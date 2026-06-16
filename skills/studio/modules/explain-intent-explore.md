# Explain Intent Explore

```pdsl
UNIT ExplainIntentCapture
PURPOSE: Capture the explanation target before context discovery or storytelling preflight runs.
STATE:
  SET EXPLAIN_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
DO:
  EMIT "What should I explain? Provide the file, artifact, code area, decision, or topic to walk through."
  SET EXPLAIN_INTENT_CAPTURE_STATE = resume
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS stop the turn after prompting so explain routing resumes in an explicit unit
  NEVER run ExplainE0Preflight while ORIGINAL_INTENT is unset
```

```pdsl
UNIT ExplainIntentCaptureResume
PURPOSE: Route the resumed explanation target into the shared explore gate.
STATE:
  SET EXPLAIN_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE EXPLAIN_INTENT_CAPTURE_STATE == resume
DO:
  SET ORIGINAL_INTENT = user.reply
  SET EXPLAIN_INTENT_CAPTURE_STATE = unset
  CONTINUE ExplainExploreGate
```

```pdsl
UNIT ExplainExploreGate
PURPOSE: Offer task-relevant context discovery before explain preflight, after Bootstrap and before the storytelling target is resolved.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/explain-gates.md
  SET WORKFLOW_PREP_EXPLORE_MENU = ExplainExploreMenu
  SET WORKFLOW_PREP_BRAINSTORM_GATE = ExplainE0Preflight
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepExploreGate
RULES:
  ALWAYS use WorkflowPrepExploreGate for the shared explore prompt mechanics
MENU ExplainExploreMenu
TITLE: Before starting a source-grounded explanation, discover task-relevant context (explicit target, nearby docs/code/artifacts, referenced IDs, and audience-relevant background) with cf-explore — or skip? Explore is suggested when the target is implicit, broad, unfamiliar, or cross-cutting; skip when the target and context are already explicit. Reply with a number.
OPTIONS:
  1 explore -> INVOKE skill `cf-explore` with intent=workflow-prep, task=ORIGINAL_INTENT, return_context=true; require it to return resource_context only and not perform explanation, review, authoring, or validation, SET RESOURCE_CONTEXT = provided, then CONTINUE ExplainE0Preflight
  2 skip -> CONTINUE ExplainE0Preflight
  INVALID -> EMIT_MENU ExplainExploreMenu
```
