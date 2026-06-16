# Analyze Routing Menus

```pdsl
UNIT AnalyzeRouteIntentFlow
PURPOSE: Match the analyze intent and route to the correct offer.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN the request spans more than one cf-* domain
  RUN matching of ORIGINAL_INTENT against AVAILABLE_SKILLS by semantic relevance — score each skill's name and description against the intent, keep those clearly on-topic, rank them, synthesize compatible companion groups when the request spans domains, and mark the top-ranked skill or group as suggested
  LOAD {cf-studio-path}/.core/skills/studio/modules/analyze-skill-fallbacks.md WHEN no relevant skill matched
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
  2 other -> LOAD {cf-studio-path}/.core/skills/studio/modules/analyze-skill-fallbacks.md; CONTINUE AnalyzeOtherSkills
  3 none -> STOP_TURN
  INVALID -> EMIT_MENU AnalyzeIntentOffer
MENU AnalyzeLoadOffer
TITLE: No analyze intent given — pick a cf-* skill, or describe intent so I can match the right workflow(s).
OPTIONS:
  1 skill -> INVOKE the user-selected cf-* skill from AVAILABLE_SKILLS with no intent so the skill prompts for its own input; the menu lists each available skill as `<skill-name> — <short description>`
  2 describe-intent | help-me-choose -> LOAD {cf-studio-path}/.core/skills/studio/modules/analyze-intent-capture.md; CONTINUE AnalyzeDescribeIntent
  3 cancel -> STOP_TURN
  INVALID -> EMIT_MENU AnalyzeLoadOffer
```
