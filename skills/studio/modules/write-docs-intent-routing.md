# Write Docs Intent Routing
```pdsl
UNIT WriteDocsIntentCapture
PURPOSE: Capture the documentation target before any context discovery or framing gate runs.
DO:
  EMIT "Describe the documentation work you want done: the document, audience, goal, and any source material you already know. I need that target before cf-explore or brainstorm can search usefully."
  RUN register WriteDocsIntentResume as the resume continuation for the next user.reply
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER offer cf-explore, cf-brainstorm, or dispatch author/reviewer agents while ORIGINAL_INTENT == unset
```
```pdsl
UNIT WriteDocsIntentResume
PURPOSE: Resume the workflow after the user provides the documentation target.
WHEN:
  REQUIRE user.reply exists
DO:
  SET ORIGINAL_INTENT = user.reply
  CONTINUE WriteDocsIntentClassify
```
```pdsl
UNIT WriteDocsIntentClassify
PURPOSE: Classify ORIGINAL_INTENT to set review-first routing, then hand off to companion routing.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  RUN classify ORIGINAL_INTENT by requested operation plus whether it evaluates an existing document, guide, report, README, or documentation artifact; SET REVIEW_LOOP_REQUESTED = true WHEN ORIGINAL_INTENT asks to review, audit, critique, inspect, check, validate, verify, analyze, compare behavior, or find issues/findings, bugs, risks, failures, regressions, bypasses, defects, root causes, routing problems, or behavioral-analysis concerns in an existing target, including review-and-fix wording
  RUN default REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset AND ORIGINAL_INTENT primarily evaluates an existing document, guide, report, README, or documentation artifact rather than creating one
  RUN classify ORIGINAL_INTENT; SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  CONTINUE WriteDocsCompanionRouting
RULES:
  ALWAYS route review/audit/critique/inspect/check/validate/verify/analyze/behavior-comparison/find-issues/bug-risk-failure-regression-bypass-defect-root-cause-routing-analysis intents through WriteDocsReviewLoop first; any fixes must be gated by ReviewFindingsReportBrowser and ReviewFixApprovalGate, not by direct author dispatch
  NEVER run when ORIGINAL_INTENT == unset
```
```pdsl
UNIT WriteDocsCompanionRouting
PURPOSE: Centralize companion-skill and plan-first routing after intent classification.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET PLAN_FIRST_CONTINUE = WriteDocsDispatch
  SET CURRENT_WORKFLOW = cf-write-docs
  SET COMPANION_CONTINUE = WriteDocsExploreGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-prep-gates.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md
  CONTINUE CompanionSkillOffer
```
