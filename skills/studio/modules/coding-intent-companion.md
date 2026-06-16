# Coding Intent Companion
```pdsl
UNIT CodingIntentCapture
PURPOSE: Capture the coding target before any context discovery or design gate runs.
DO:
  EMIT "Describe the code work you want done: the behavior, bug, refactor, review target, or files if known. I need that target before cf-explore or brainstorm can search usefully."
  CONTINUE CodingIntentResume after user.reply
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER offer cf-explore, cf-brainstorm, or dispatch coder/reviewer agents while ORIGINAL_INTENT == unset
```
```pdsl
UNIT CodingIntentResume
PURPOSE: Resume the workflow after the user provides the coding target.
WHEN:
  REQUIRE user.reply exists
DO:
  SET ORIGINAL_INTENT = user.reply
  CONTINUE CodingIntentClassify
```
```pdsl
UNIT CodingIntentClassify
PURPOSE: Classify ORIGINAL_INTENT to set review-first routing, then hand off to companion skill offer.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  RUN classify ORIGINAL_INTENT by requested operation plus whether it evaluates existing code; SET REVIEW_LOOP_REQUESTED = true WHEN ORIGINAL_INTENT asks to review, audit, critique, inspect, check, validate, verify, analyze, compare behavior, or find issues/findings, bugs, risks, failures, regressions, bypasses, defects, root causes, routing problems, or behavioral-analysis concerns in existing code, including review-and-fix wording
  RUN default REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset AND ORIGINAL_INTENT primarily evaluates existing code rather than creating or changing it
  RUN classify ORIGINAL_INTENT; SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  RUN CodingCompanionSetup
RULES:
  ALWAYS route review/audit/critique/inspect/check/validate/verify/analyze/behavior-comparison/find-issues/bug-risk-failure-regression-bypass-defect-root-cause-routing-analysis intents through CodingReviewLoop first; any fixes must be gated by ReviewFindingsReportBrowser and ReviewFixApprovalGate, not by direct coder dispatch
  NEVER run when ORIGINAL_INTENT == unset
```
```pdsl
UNIT CodingCompanionSetup
PURPOSE: Prepare the companion-skill and plan-first routing handoff for cf-coding.
DO:
  SET PLAN_FIRST_CONTINUE = CodingDispatch
  SET CURRENT_WORKFLOW = cf-coding
  SET COMPANION_CONTINUE = CodingExploreGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-prep-gates.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md
  CONTINUE CompanionSkillOffer
```
