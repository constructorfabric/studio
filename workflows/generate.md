---
cf: true
type: workflow
name: cf-generate
description: Invoke when the user asks to create, update, edit, fix, implement, refactor, add, set up, configure, or build any artifact or code.
version: 2.0
purpose: Backwards-compatible entry point that routes a generate intent to the most relevant cf-* skill or companion skill group available in the session, or helps the user describe intent when none is given.
---

# cf-generate

This workflow is kept as a stable, backwards-compatible entry point for the
`generate` verb. It performs no create-or-modify work itself. Instead it
discovers the `cf-*` skills available to the current session (via the shared
WorkflowResolution rule), matches the user's generate intent against them, and
offers the most relevant skill or companion skill group for invocation —
passing the user's intent into it. When no intent is present it lists the
available `cf-*` skills plus a `describe intent / help me choose` option. The
legacy multi-phase generate workflow has been retired; routing is the only behavior here.

```pdsl
UNIT GenerateBootstrap
PURPOSE: Load the runtime routing rules needed before any generate routing work.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/skill-invocation-art.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  RUN SkillInvocationArt
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  RUN CommandResolution to resolve {cfs_cmd}
  CONTINUE GenerateRoute
RULES:
  ALWAYS load command-resolution and workflow-resolution before GenerateRoute
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing or delegation
  NEVER require cf or CFS_INIT before routing; this workflow owns its prerequisite loads
```

```pdsl
UNIT GenerateRoute
PURPOSE: Capture the generate intent, resolve cf-* skills via WorkflowResolution, and route to the chosen skill.
STATE:
  SET ORIGINAL_INTENT: string (default unset, scope workflow_run)
  SET AVAILABLE_SKILLS: list (default unset, scope workflow_run)
WHEN:
  REQUIRE WorkflowResolution is loaded
DO:
  SET ORIGINAL_INTENT = the user's triggering generate request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN WorkflowResolution to resolve the available cf-* skills
  SET AVAILABLE_SKILLS = the resolved cf-* skills (name + its workflow description), excluding `cf`, `cf-analyze`, and `cf-generate`
  CONTINUE GenerateNoMatch WHEN AVAILABLE_SKILLS is empty
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN the request spans more than one cf-* domain
  RUN matching of ORIGINAL_INTENT against AVAILABLE_SKILLS by semantic relevance — score each skill's name and description against the intent, keep those clearly on-topic, rank them, synthesize compatible companion groups when the request spans domains, and mark the top-ranked skill or group as suggested — WHEN ORIGINAL_INTENT != unset
  EMIT_MENU GenerateIntentOffer WHEN ORIGINAL_INTENT != unset AND at least one relevant skill matched
  CONTINUE GenerateNoMatch WHEN ORIGINAL_INTENT != unset AND no relevant skill matched
  EMIT_MENU GenerateLoadOffer WHEN ORIGINAL_INTENT == unset
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS preserve ORIGINAL_INTENT when it was already set by GenerateDescribeIntent
  ALWAYS resolve cf-* skills via WorkflowResolution, never by guessing and never via a CLI skills-list command
  ALWAYS exclude `cf`, `cf-analyze`, and `cf-generate` from AVAILABLE_SKILLS and companion groups; these are routers/entrypoints and must never be offered as companions
  ALWAYS pass ORIGINAL_INTENT into every invoked skill when an intent is present
  ALWAYS render each offered skill as `<skill-name> — <short description>` from AVAILABLE_SKILLS
  ALWAYS load companion-skills before synthesizing companion groups
  ALWAYS support compatible companion multi-select, invoking selected skills sequentially so each skill's prerequisites and gates run in order
  NEVER let a companion or multi-select route bypass any selected skill's WAIT, STOP_TURN, approval, brainstorm, plan, validation, or sub-agent gate
  NEVER load or run any legacy generate phase logic; routing is the only behavior
NOTES:
  Empty-state ownership: WorkflowResolution STOP_TURNs when zero cf-* skills are discovered (a broken install), so that case never reaches this router; the CONTINUE GenerateNoMatch WHEN AVAILABLE_SKILLS is empty branch handles the distinct case where resolution succeeds but excluding this router (cf-generate) leaves no other skill.
MENU GenerateIntentOffer
TITLE: Generate intent matched these cf-* workflow(s) — pick one, or pick a companion group / comma-separated compatible skills.
OPTIONS:
  1 most-relevant (suggested) -> INVOKE the top-ranked matched cf-* skill or companion group, passing ORIGINAL_INTENT as its input to every invoked skill
  2 other -> CONTINUE GenerateOtherSkills
  3 none -> STOP_TURN
  INVALID -> EMIT_MENU GenerateIntentOffer
MENU GenerateLoadOffer
TITLE: No generate intent given — pick a cf-* skill, or describe intent so I can match the right workflow(s).
OPTIONS:
  1 skill -> INVOKE the user-selected cf-* skill from AVAILABLE_SKILLS with no intent so the skill prompts for its own input; the menu lists each available skill as `<skill-name> — <short description>`
  2 describe-intent | help-me-choose -> CONTINUE GenerateDescribeIntent
  3 cancel -> STOP_TURN
  INVALID -> EMIT_MENU GenerateLoadOffer
```

```pdsl
UNIT GenerateDescribeIntent
PURPOSE: Capture a generate intent as a separate turn before routing.
DO:
  EMIT "Describe what you want to generate, change, or fix. I will match the relevant cf-* workflow(s), including companions when needed."
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS on the resumed reply set ORIGINAL_INTENT = user.reply and CONTINUE GenerateRoute
```

```pdsl
UNIT GenerateOtherSkills
PURPOSE: Offer every available cf-* skill after the suggested generate match is not desired.
DO:
  EMIT_MENU GenerateOtherSkillsMenu
  WAIT user.reply
  STOP_TURN
MENU GenerateOtherSkillsMenu
TITLE: All available cf-* workflow(s) for generate — pick one, or enter comma-separated compatible skills.
OPTIONS:
  1 skill -> INVOKE the user-selected cf-* skill, passing ORIGINAL_INTENT
  2 companion-selection -> INVOKE each selected compatible cf-* skill sequentially, passing ORIGINAL_INTENT
  3 cancel -> STOP_TURN
  INVALID -> EMIT_MENU GenerateOtherSkillsMenu
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
  ALWAYS let the user pick one or more compatible listed skills, describe clearer intent, or cancel
MENU GenerateNoMatchMenu
TITLE: No match — load listed cf-* skill(s), describe intent again, or cancel.
OPTIONS:
  1 skill -> INVOKE the user-selected cf-* skill(s), passing ORIGINAL_INTENT when present else load only
  2 describe-intent | help-me-choose -> CONTINUE GenerateDescribeIntent
  3 cancel -> STOP_TURN
  INVALID -> EMIT_MENU GenerateNoMatchMenu
```
