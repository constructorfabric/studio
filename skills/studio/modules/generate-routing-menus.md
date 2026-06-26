# Generate Routing Menus

```pdsl
UNIT GenerateRouteIntentFlow
PURPOSE: Match the generate intent and route to the correct offer.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN the request spans more than one cf-* domain
  RUN CompanionSkillResolutionSetup WHEN the request spans more than one cf-* domain
  RUN matching of ORIGINAL_INTENT against AVAILABLE_SKILLS by semantic relevance — score each skill's name and description against the intent, keep those clearly on-topic, rank them, synthesize compatible companion groups when the request spans domains, and mark the top-ranked skill or group as suggested
  LOAD {cf-studio-path}/.core/skills/studio/modules/generate-skill-fallbacks.md WHEN no relevant skill matched
  CONTINUE GenerateRouteIntentMenu WHEN at least one relevant skill matched
  CONTINUE GenerateNoMatch WHEN no relevant skill matched
RULES:
  ALWAYS load companion-skills before synthesizing companion groups
NOTES:
  This module owns the conditional LOAD of companion-skills.md for the generate routing domain. The caller (generate.md) does not pre-load it; this is the canonical load site for companion-skill routing in this domain.
```

```pdsl
UNIT GenerateRouteIntentMenu
PURPOSE: Present the matched generate routes and wait for the user's selection.
DO:
  EMIT_MENU GenerateIntentOffer
  WAIT user.reply
  STOP_TURN
MENU GenerateIntentOffer
TITLE: Generate intent matched these cf-* workflow(s) — pick one, or pick a companion group / comma-separated compatible skills.
OPTIONS:
  1 most-relevant (suggested) -> INVOKE the top-ranked matched cf-* skill or companion group, passing ORIGINAL_INTENT as its input to every invoked skill
  2 other -> LOAD {cf-studio-path}/.core/skills/studio/modules/generate-skill-fallbacks.md; CONTINUE GenerateOtherSkills
  3 none -> EMIT "No generate workflow was launched. Control is returning to free mode."; STOP_TURN
  INVALID -> EMIT_MENU GenerateIntentOffer
```

```pdsl
UNIT GenerateRouteLoadFlow
PURPOSE: Present the generate load menu when no intent was provided.
DO:
  EMIT_MENU GenerateLoadOffer
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER silently skip describe-intent routing when the intent-capture module fails to load; EMIT an error and re-show the menu WHEN the LOAD of generate-intent-capture.md fails
NOTES:
  The inline LOAD of generate-intent-capture.md in GenerateLoadOffer option 2 is the canonical load site for GenerateDescribeIntent routing from the load-offer path. The fallback module (generate-skill-fallbacks.md) independently loads it for the no-match path. Both load sites are intentional and own distinct routing paths.
MENU GenerateLoadOffer
TITLE: No generate intent given — pick a cf-* skill, or describe intent so I can match the right workflow(s).
OPTIONS:
  1 skill -> INVOKE the user-selected cf-* skill from AVAILABLE_SKILLS with no intent so the skill prompts for its own input; the menu lists each available skill as `<skill-name> — <short description>`
  2 describe-intent | help-me-choose -> LOAD {cf-studio-path}/.core/skills/studio/modules/generate-intent-capture.md; CONTINUE GenerateDescribeIntent
  3 cancel -> EMIT "Generate routing cancelled. Control is returning to free mode."; STOP_TURN
  INVALID -> EMIT_MENU GenerateLoadOffer
```
