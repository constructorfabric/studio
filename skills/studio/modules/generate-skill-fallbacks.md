# Generate Skill Fallbacks

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
  3 cancel -> EMIT "Generate routing cancelled. Control is returning to free mode."; STOP_TURN
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
  2 describe-intent | help-me-choose -> LOAD {cf-studio-path}/.core/skills/studio/modules/generate-intent-capture.md; CONTINUE GenerateDescribeIntent
  3 cancel -> EMIT "No generate workflow was launched. Control is returning to free mode."; STOP_TURN
  INVALID -> EMIT_MENU GenerateNoMatchMenu
```
