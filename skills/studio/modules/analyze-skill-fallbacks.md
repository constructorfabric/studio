# Analyze Skill Fallbacks

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
  3 cancel -> EMIT "Analyze routing cancelled. Control is returning to free mode."; STOP_TURN
  INVALID -> EMIT_MENU AnalyzeOtherSkillsMenu
```

```pdsl
UNIT AnalyzeNoMatch
PURPOSE: Handle the case where no cf-* skill matches the intent (or none are available).
NOTES:
  The inline LOAD of analyze-intent-capture.md in AnalyzeNoMatchMenu option 2 covers the no-match fallback path. The load-offer path in analyze-routing-menus.md covers the direct describe-intent selection. Both are intentional and own distinct routing paths.
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
  2 describe-intent | help-me-choose -> LOAD {cf-studio-path}/.core/skills/studio/modules/analyze-intent-capture.md; CONTINUE AnalyzeDescribeIntent
  3 cancel -> EMIT "No analyze workflow was launched. Control is returning to free mode."; STOP_TURN
  INVALID -> EMIT_MENU AnalyzeNoMatchMenu
```
