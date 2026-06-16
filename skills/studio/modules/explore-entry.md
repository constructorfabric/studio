# Explore Entry

```pdsl
UNIT ExploreEntry
PURPOSE: Capture the original intent and route to clarify or directly to the explorer.
STATE:
  SET ORIGINAL_INTENT: string (default unset, scope workflow_run)
  SET intent: standalone | brainstorm | generate | analyze | plan | workflow-prep (default standalone, scope workflow_run)
  SET return_context: true | false (default false, scope workflow_run)
DO:
  SET ORIGINAL_INTENT = the user's triggering request (verbatim or shortest faithful summary)
  SET intent = standalone WHEN invoked directly; otherwise the intent supplied by the calling workflow
  SET return_context = true WHEN the caller invoked cf-explore in return-context mode (e.g. cf-brainstorm before round 1); else false
  LOAD {cf-studio-path}/.core/skills/studio/modules/explore-clarify.md WHEN the request is activation-only with no concrete topic, question, path, or decision
  CONTINUE ExploreClarify WHEN the request is activation-only with no concrete topic, question, path, or decision
  LOAD {cf-studio-path}/.core/skills/studio/modules/explore-run.md
  SET PLAN_FIRST_CONTINUE = ExploreRun, SET CURRENT_WORKFLOW = cf-explore, SET COMPANION_CONTINUE = PlanFirstGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer WHEN a concrete topic, path, decision, or workflow purpose is already present AND return_context != true
  CONTINUE ExploreRun WHEN a concrete topic, path, decision, or workflow purpose is already present AND return_context == true
RULES:
  ALWAYS capture ORIGINAL_INTENT before any cf-explorer dispatch
  ALWAYS default intent to standalone and return_context to false when explore is invoked on its own
  ALWAYS set return_context = true only when a calling skill/workflow requested resource_context back
  ALWAYS run PlanFirstGate before standalone concrete exploration when no accepted plan is active; never run it in return-context/helper mode
  ALWAYS when return_context == true or intent == workflow-prep, gather resource_context for the caller only; NEVER execute the caller's authoring, review, validation, planning, or brainstorm task inside explore
  ALWAYS route an activation-only request to ExploreClarify and a concrete request straight to ExploreRun
```
