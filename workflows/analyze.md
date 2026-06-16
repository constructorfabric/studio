---
cf: true
type: workflow
name: cf-analyze
description: Invoke when the user asks to analyze, validate, review, inspect, audit, check, or compare any artifact, code, or instruction document.
version: 2.0
purpose: Backwards-compatible entry point that routes an analyze intent to the most relevant cf-* skill or companion skill group available in the session, or helps the user describe intent when none is given.
---

# cf-analyze

This workflow is kept as a stable, backwards-compatible entry point for the
`analyze` verb. It performs no analysis itself. Instead it discovers the cf-*
skills available to the current session (via the shared WorkflowResolution
rule), matches the user's analyze intent against them, and offers the most
relevant skill or companion skill group for invocation — passing the user's
intent into it. When no intent is present it lists the available cf-* skills
plus a `describe intent / help me choose` option. The legacy
multi-phase analyze workflow has been retired; routing is the only behavior here.

```pdsl
UNIT AnalyzeBootstrap
PURPOSE: Load the runtime routing rules needed before any analyze routing work.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapCommandWorkflowResolution
  CONTINUE AnalyzeRoute
RULES:
  ALWAYS load command-resolution and workflow-resolution before AnalyzeRoute
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing or delegation
  NEVER require cf or CFS_INIT before routing; this workflow owns its prerequisite loads
```

```pdsl
UNIT AnalyzeRoute
PURPOSE: Capture the analyze intent, resolve cf-* skills via WorkflowResolution, and route to the chosen skill.
STATE:
  SET ORIGINAL_INTENT: string (default unset, scope workflow_run)
  SET AVAILABLE_SKILLS: list (default unset, scope workflow_run)
WHEN:
  REQUIRE WorkflowResolution is loaded
DO:
  SET ORIGINAL_INTENT = the user's triggering analyze request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN WorkflowResolution to resolve the available cf-* skills
  SET AVAILABLE_SKILLS = the resolved cf-* skills (name + its workflow description), excluding `cf`, `cf-analyze`, and `cf-generate`
  CONTINUE AnalyzeNoMatch WHEN AVAILABLE_SKILLS is empty
  CONTINUE AnalyzeRouteIntentFlow WHEN ORIGINAL_INTENT != unset
  CONTINUE AnalyzeRouteLoadFlow WHEN ORIGINAL_INTENT == unset
RULES:
  ALWAYS preserve ORIGINAL_INTENT when it was already set by AnalyzeDescribeIntent
  ALWAYS resolve cf-* skills via WorkflowResolution, never by guessing and never via a CLI skills-list command
  ALWAYS exclude `cf`, `cf-analyze`, and `cf-generate` from AVAILABLE_SKILLS and companion groups; these are routers/entrypoints and must never be offered as companions
  ALWAYS pass ORIGINAL_INTENT into every invoked skill when an intent is present
  ALWAYS render each offered skill as `<skill-name> — <short description>` from AVAILABLE_SKILLS
  ALWAYS support compatible companion multi-select, invoking selected skills sequentially so each skill's prerequisites and gates run in order
  NEVER let a companion or multi-select route bypass any selected skill's WAIT, STOP_TURN, approval, brainstorm, plan, validation, or sub-agent gate
  NEVER load or run any legacy analyze phase logic; routing is the only behavior
NOTES:
  Empty-state ownership: WorkflowResolution STOP_TURNs when zero cf-* skills are discovered (a broken install), so that case never reaches this router; the CONTINUE AnalyzeNoMatch WHEN AVAILABLE_SKILLS is empty branch handles the distinct case where resolution succeeds but excluding this router (cf-analyze) leaves no other skill.
```

```pdsl
UNIT AnalyzeRouteIntentFlow
PURPOSE: Load companion-skill context when needed, match the analyze intent, and route to the correct offer.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN the request spans more than one cf-* domain
  RUN matching of ORIGINAL_INTENT against AVAILABLE_SKILLS by semantic relevance — score each skill's name and description against the intent, keep those clearly on-topic, rank them, synthesize compatible companion groups when the request spans domains, and mark the top-ranked skill or group as suggested
  CONTINUE AnalyzeRouteIntentMenu WHEN at least one relevant skill matched
  CONTINUE AnalyzeNoMatch WHEN no relevant skill matched
RULES:
  ALWAYS load companion-skills before synthesizing companion groups
```

```pdsl
UNIT AnalyzeRouteIntentMenu
PURPOSE: Present the matched analyze routes and wait for the user's selection.
DO:
  EMIT_MENU AnalyzeIntentOffer
  WAIT user.reply
  STOP_TURN
```

```pdsl
UNIT AnalyzeRouteLoadFlow
PURPOSE: Present the analyze load menu when no intent was provided.
DO:
  EMIT_MENU AnalyzeLoadOffer
  WAIT user.reply
  STOP_TURN
MENU AnalyzeIntentOffer
TITLE: Analyze intent matched these cf-* workflow(s) — pick one, or pick a companion group / comma-separated compatible skills.
OPTIONS:
  1 most-relevant (suggested) -> INVOKE the top-ranked matched cf-* skill or companion group, passing ORIGINAL_INTENT as its input to every invoked skill
  2 other -> CONTINUE AnalyzeOtherSkills
  3 none -> STOP_TURN
  INVALID -> EMIT_MENU AnalyzeIntentOffer
MENU AnalyzeLoadOffer
TITLE: No analyze intent given — pick a cf-* skill, or describe intent so I can match the right workflow(s).
OPTIONS:
  1 skill -> INVOKE the user-selected cf-* skill from AVAILABLE_SKILLS with no intent so the skill prompts for its own input; the menu lists each available skill as `<skill-name> — <short description>`
  2 describe-intent | help-me-choose -> CONTINUE AnalyzeDescribeIntent
  3 cancel -> STOP_TURN
  INVALID -> EMIT_MENU AnalyzeLoadOffer
```

```pdsl
UNIT AnalyzeDescribeIntent
PURPOSE: Capture an analyze intent as a separate turn before routing.
STATE:
  SET ANALYZE_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
DO:
  EMIT "Describe what you want to analyze, review, validate, or compare. I will match the relevant cf-* workflow(s), including companions when needed."
  SET ANALYZE_INTENT_CAPTURE_STATE = resume
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS stop the turn after prompting so analyze intent routing resumes in an explicit unit
```

```pdsl
UNIT AnalyzeDescribeIntentResume
PURPOSE: Route the resumed analyze intent after the prompt turn completes.
STATE:
  SET ANALYZE_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE ANALYZE_INTENT_CAPTURE_STATE == resume
DO:
  SET ORIGINAL_INTENT = user.reply
  SET ANALYZE_INTENT_CAPTURE_STATE = unset
  CONTINUE AnalyzeRoute
```

```pdsl
UNIT AnalyzeOtherSkills
PURPOSE: Offer every available cf-* skill after the suggested analyze match is not desired.
DO:
  EMIT_MENU AnalyzeOtherSkillsMenu
  WAIT user.reply
  STOP_TURN
MENU AnalyzeOtherSkillsMenu
TITLE: All available cf-* workflow(s) for analyze — pick one, or enter comma-separated compatible skills.
OPTIONS:
  1 skill -> INVOKE the user-selected cf-* skill, passing ORIGINAL_INTENT
  2 companion-selection -> INVOKE each selected compatible cf-* skill sequentially, passing ORIGINAL_INTENT
  3 cancel -> STOP_TURN
  INVALID -> EMIT_MENU AnalyzeOtherSkillsMenu
```

```pdsl
UNIT AnalyzeNoMatch
PURPOSE: Handle the case where no cf-* skill matches the intent (or none are available).
DO:
  EMIT a one-line note that no cf-* skill matched the analyze intent
  EMIT the full AVAILABLE_SKILLS list as `<skill-name> — <short description>`, or a one-line note that no cf-* skills are available and the user can install one or refine the intent
  EMIT_MENU AnalyzeNoMatchMenu
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER fall back to legacy analyze phases when nothing matches
  ALWAYS let the user pick one or more compatible listed skills, describe clearer intent, or cancel
MENU AnalyzeNoMatchMenu
TITLE: No match — load listed cf-* skill(s), describe intent again, or cancel.
OPTIONS:
  1 skill -> INVOKE the user-selected cf-* skill(s), passing ORIGINAL_INTENT when present else load only
  2 describe-intent | help-me-choose -> CONTINUE AnalyzeDescribeIntent
  3 cancel -> STOP_TURN
  INVALID -> EMIT_MENU AnalyzeNoMatchMenu
```
