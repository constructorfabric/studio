# Write Skills Intent Routing

```pdsl
UNIT WriteSkillsIntentCapture
PURPOSE: Capture the skill-writing target before any context discovery or design gate runs.
STATE:
  SET WRITE_SKILLS_INTENT_CAPTURE_STATE: resume | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE ORIGINAL_INTENT == unset
DO:
  EMIT "Describe the skill, prompt, workflow, agent instruction, or system prompt work you want done. I need the target and goal before cf-explore or brainstorm can search usefully."
  SET WRITE_SKILLS_INTENT_CAPTURE_STATE = resume
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER offer cf-explore, cf-brainstorm, or dispatch author/reviewer agents while ORIGINAL_INTENT == unset
  ALWAYS capture ORIGINAL_INTENT before offering cf-explore, cf-brainstorm, plan-first, validation, authoring, review, or dispatch work
```

```pdsl
UNIT WriteSkillsIntentResume
PURPOSE: Resume the workflow after the user provides the skill-writing target.
STATE:
  SET WRITE_SKILLS_INTENT_CAPTURE_STATE: resume | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE user.reply exists
  REQUIRE WRITE_SKILLS_INTENT_CAPTURE_STATE == resume
DO:
  SET ORIGINAL_INTENT = user.reply
  SET WRITE_SKILLS_INTENT_CAPTURE_STATE = unset
  CONTINUE WriteSkillsIntentClassify
```

```pdsl
UNIT WriteSkillsIntentClassify
PURPOSE: Classify ORIGINAL_INTENT to set REVIEW_LOOP_REQUESTED, then set up routing vars and hand off to companion skill offer.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  RUN classify ORIGINAL_INTENT; SET REVIEW_LOOP_REQUESTED = true WHEN ORIGINAL_INTENT asks to review, audit, critique, inspect, check, validate, verify, analyze, compare behavior, or find issues/findings, bugs, risks, failures, regressions, bypasses, defects, root causes, routing problems, or behavioral-analysis concerns in an existing target (including review-and-fix wording), OR WHEN ORIGINAL_INTENT primarily evaluates an existing skill, prompt, workflow, agent instruction, or system prompt rather than creating one; SET REVIEW_LOOP_REQUESTED = false otherwise
  RUN WriteSkillsCompanionSetup
RULES:
  ALWAYS run after ORIGINAL_INTENT is set and before companion routing
  NEVER run when ORIGINAL_INTENT == unset
```

```pdsl
UNIT WriteSkillsCompanionSetup
PURPOSE: Prepare the companion-skill and plan-first routing handoff for cf-write-skills.
DO:
  SET PLAN_FIRST_CONTINUE = WriteSkillsAuthorDispatch
  SET CURRENT_WORKFLOW = cf-write-skills
  SET COMPANION_CONTINUE = WriteSkillsExploreGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-prep-gates.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md
  CONTINUE CompanionSkillOffer
```
