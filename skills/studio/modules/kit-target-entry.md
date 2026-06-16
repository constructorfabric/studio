# Kit Target Entry

```pdsl
UNIT KitInitAskTarget
PURPOSE: Ask for the target folder when the request did not provide one.
WHEN:
  REQUIRE TARGET_DIR == unset
DO:
  EMIT "[Kit Init]: I need the target folder before I can build or validate a kit manifest."
  EMIT_MENU KitInitTargetMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS let the user provide the folder path directly in free text
  NEVER continue to preflight while TARGET_DIR is still unset
MENU KitInitTargetMenu
TITLE: Which folder should become or be checked as a kit root? Reply with a number, or send the folder path directly.
OPTIONS:
  1 path:<folder> | path -> Reply `path: <folder>` or send the folder path alone, then SET TARGET_DIR, SET PLAN_FIRST_CONTINUE = KitInitPreflight, SET CURRENT_WORKFLOW = cf-kit, SET COMPANION_CONTINUE = PlanFirstGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer
  2 cancel -> STOP_TURN
  INVALID -> treat non-empty path-like free text as TARGET_DIR, SET PLAN_FIRST_CONTINUE = KitInitPreflight, SET CURRENT_WORKFLOW = cf-kit, SET COMPANION_CONTINUE = PlanFirstGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer; handle `cancel`, `help`, or non-path text by EMIT "Reply with `path: <folder>`, a path-like folder value, or 2 to cancel." and EMIT_MENU KitInitTargetMenu
```
