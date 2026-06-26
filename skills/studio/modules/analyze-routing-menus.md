# Analyze Routing Menus

```pdsl
UNIT AnalyzeRouteIntentFlow
PURPOSE: Match the analyze intent and route to the correct offer.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN the request spans more than one cf-* domain
  RUN CompanionSkillResolutionSetup WHEN the request spans more than one cf-* domain
  RUN matching of ORIGINAL_INTENT against AVAILABLE_SKILLS by semantic relevance — score each skill's name and description against the intent, keep those clearly on-topic, rank them, synthesize compatible companion groups when the request spans domains, and mark the top-ranked skill or group as suggested
  LOAD {cf-studio-path}/.core/skills/studio/modules/analyze-skill-fallbacks.md WHEN no relevant skill matched
  CONTINUE AnalyzeRouteIntentMenu WHEN at least one relevant skill matched
  CONTINUE AnalyzeNoMatch WHEN no relevant skill matched
RULES:
  ALWAYS load companion-skills before synthesizing companion groups
NOTES:
  This module owns the conditional LOAD of companion-skills.md for the analyze routing domain. The caller (analyze.md) does not pre-load it; this is the canonical load site for companion-skill routing in this domain.
```

```pdsl
UNIT AnalyzeRouteIntentMenu
PURPOSE: Present the matched analyze routes and wait for the user's selection.
DO:
  EMIT_MENU AnalyzeIntentOffer
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS expand option 1 with the actual resolved skill name and description before emitting the menu; never emit the token 'most-relevant' as a visible label
MENU AnalyzeIntentOffer
TITLE: Analyze intent matched these cf-* workflow(s) — pick one, or pick a companion group / comma-separated compatible skills.
OPTIONS:
  1 [resolved skill name] — [skill description] (suggested) -> INVOKE this skill with ORIGINAL_INTENT; STOP_TURN when the skill owns the next turn
  2 browse all analyze workflows -> LOAD {cf-studio-path}/.core/skills/studio/modules/analyze-skill-fallbacks.md; CONTINUE AnalyzeOtherSkills
  3 none -> EMIT "No analyze workflow was launched. Control is returning to free mode."; STOP_TURN
  INVALID -> EMIT_MENU AnalyzeIntentOffer
```

```pdsl
UNIT AnalyzeRouteLoadFlow
PURPOSE: Present the analyze load menu when no intent was provided.
DO:
  EMIT_MENU AnalyzeLoadOffer
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER silently skip describe-intent routing when the intent-capture module fails to load; EMIT an error and re-show the menu WHEN the LOAD of analyze-intent-capture.md fails
  ALWAYS mark the describe-intent option as (suggested) when ORIGINAL_INTENT == unset
NOTES:
  The inline LOAD of analyze-intent-capture.md in AnalyzeLoadOffer option 2 is the canonical load site for AnalyzeDescribeIntent routing from the load-offer path. The fallback module (analyze-skill-fallbacks.md) independently loads it for the no-match path. Both load sites are intentional and own distinct routing paths.
MENU AnalyzeLoadOffer
TITLE: No analyze intent given — pick a cf-* skill, or describe intent so I can match the right workflow(s).
OPTIONS:
  1 skill -> INVOKE the user-selected cf-* skill from AVAILABLE_SKILLS with no intent so the skill prompts for its own input; the menu lists each available skill as `<skill-name> — <short description>`
  2 describe-intent | help-me-choose (suggested) -> LOAD {cf-studio-path}/.core/skills/studio/modules/analyze-intent-capture.md; CONTINUE AnalyzeDescribeIntent
  3 cancel -> EMIT "Analyze routing cancelled. Control is returning to free mode."; STOP_TURN
  INVALID -> EMIT_MENU AnalyzeLoadOffer
```
