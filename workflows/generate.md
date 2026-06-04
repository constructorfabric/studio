---
cf: true
type: workflow
name: cf-generate
description: Invoke when the user asks to create, update, edit, fix, implement, refactor, add, set up, configure, or build any artifact or code.
version: 2.0
purpose: Backwards-compatible entry point that routes a generate intent to the most relevant cf-* skill available in the session, or loads a chosen one when no intent is given.
---

# cf-generate

This workflow is kept as a stable, backwards-compatible entry point for the
`generate` verb. It performs no create-or-modify work itself. Instead it
discovers the cf-* skills available to the current session (via the shared
WorkflowResolution rule), matches the user's generate intent against them, and offers the
most relevant skill for invocation — passing the user's intent into it. When no
intent is present it lists the available cf-* skills and loads the one the user
picks. The legacy multi-phase generate workflow has been retired; routing is the only behavior here.

```pdsl
UNIT GenerateBootstrap
PURPOSE: Ensure the cf skill is loaded before any routing work.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
DO:
  EMIT_MENU LoadCfSkillConfirm WHEN CFS_INIT != true
  CONTINUE GenerateRoute WHEN CFS_INIT == true
RULES:
  ALWAYS verify the cf skill is loaded, CFS_INIT == true, before any routing work
MENU LoadCfSkillConfirm
TITLE: The cf skill is not loaded. It is the Constructor Studio core that loads the shared rules and routes to cf-* skills, so this generate entry point cannot run without it. Load it now to continue?
OPTIONS:
  1 load -> INVOKE skill `cf` and CONTINUE GenerateBootstrap
  2 stop -> STOP_TURN
  INVALID -> EMIT_MENU LoadCfSkillConfirm
```

```pdsl
UNIT GenerateRoute
PURPOSE: Capture the generate intent, resolve cf-* skills via WorkflowResolution, and route to the chosen skill.
STATE:
  SET ORIGINAL_INTENT: string (default unset, scope workflow_run)
  SET AVAILABLE_SKILLS: list (default unset, scope workflow_run)
WHEN:
  REQUIRE CFS_INIT == true
DO:
  SET ORIGINAL_INTENT = the user's triggering generate request (verbatim or shortest faithful summary), or unset when activation-only
  RUN WorkflowResolution to resolve the available cf-* skills
  SET AVAILABLE_SKILLS = the resolved cf-* skills (name + its workflow description), excluding this router (cf-generate)
  CONTINUE GenerateNoMatch WHEN AVAILABLE_SKILLS is empty
  RUN matching of ORIGINAL_INTENT against AVAILABLE_SKILLS by semantic relevance — score each skill's name and description against the intent, keep those clearly on-topic, rank them, and mark the top-ranked as suggested — WHEN ORIGINAL_INTENT != unset
  EMIT_MENU GenerateIntentOffer WHEN ORIGINAL_INTENT != unset AND at least one relevant skill matched
  CONTINUE GenerateNoMatch WHEN ORIGINAL_INTENT != unset AND no relevant skill matched
  EMIT_MENU GenerateLoadOffer WHEN ORIGINAL_INTENT == unset
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS resolve cf-* skills via WorkflowResolution, never by guessing and never via a CLI skills-list command
  ALWAYS exclude the skill whose name equals this router (cf-generate) from AVAILABLE_SKILLS to prevent self-routing recursion
  ALWAYS pass ORIGINAL_INTENT into the invoked skill when an intent is present
  ALWAYS render each offered skill as `<skill-name> — <short description>` from AVAILABLE_SKILLS
  NEVER load or run any legacy generate phase logic; routing is the only behavior
NOTES:
  Empty-state ownership: WorkflowResolution STOP_TURNs when zero cf-* skills are discovered (a broken install), so that case never reaches this router; the CONTINUE GenerateNoMatch WHEN AVAILABLE_SKILLS is empty branch handles the distinct case where resolution succeeds but excluding this router (cf-generate) leaves no other skill.
MENU GenerateIntentOffer
TITLE: Generate intent matched these cf-* skills — pick one to run with your request.
OPTIONS:
  1 most-relevant (suggested) -> INVOKE the top-ranked matched cf-* skill (the one whose description best fits your intent), passing ORIGINAL_INTENT as its input
  2 other -> EMIT_MENU listing every AVAILABLE_SKILLS entry as a numbered option (use this when the suggested match is not the one you want), then INVOKE the user-selected skill, passing ORIGINAL_INTENT
  3 none -> STOP_TURN
  INVALID -> EMIT_MENU GenerateIntentOffer
MENU GenerateLoadOffer
TITLE: No generate intent given — pick a cf-* skill to load.
OPTIONS:
  1 skill -> INVOKE the user-selected cf-* skill from AVAILABLE_SKILLS with no intent so the skill prompts for its own input; the menu lists each available skill as `<skill-name> — <short description>`
  2 cancel -> STOP_TURN
  INVALID -> EMIT_MENU GenerateLoadOffer
```

```pdsl
UNIT GenerateNoMatch
PURPOSE: Handle the case where no cf-* skill matches the intent (or none are available).
DO:
  EMIT a one-line note that no cf-* skill matched the generate intent
  EMIT the full AVAILABLE_SKILLS list as `<skill-name> — <short description>`, or a one-line note that no cf-* skills are available and the user can install one or refine the intent
  EMIT_MENU GenerateNoMatchMenu
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER fall back to legacy generate phases when nothing matches
  ALWAYS let the user pick a listed skill or cancel
MENU GenerateNoMatchMenu
TITLE: No match — load a listed cf-* skill, or cancel.
OPTIONS:
  1 skill -> INVOKE the user-selected cf-* skill, passing ORIGINAL_INTENT when present else load only
  2 cancel -> STOP_TURN
  INVALID -> EMIT_MENU GenerateNoMatchMenu
```
