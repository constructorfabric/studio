# Kit Target Entry

```pdsl
UNIT KitInitAskTarget
PURPOSE: Ask for the target folder when the request did not provide one.
WHEN:
  REQUIRE TARGET_DIR == unset
DO:
  EMIT "To initialize or validate a kit manifest, I need the folder that should become the kit root. If you are in the kit folder now, reply `.` or `path: .`. Otherwise send the relative or absolute path, e.g. `path: ./my-kit`."
  EMIT_MENU KitInitTargetMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer 'use current directory' as the first option in the target-folder ask
  ALWAYS let the user provide the folder path directly in free text
  NEVER continue to preflight while TARGET_DIR is still unset
MENU KitInitTargetMenu
TITLE: Which folder should become or be checked as a kit root? Reply with a number, or send the folder path directly.
OPTIONS:
  1 use current directory — set TARGET_DIR = cwd (suggested for most users) -> SET TARGET_DIR = cwd, SET PLAN_FIRST_CONTINUE = KitInitPreflight, SET CURRENT_WORKFLOW = cf-kit, SET COMPANION_CONTINUE = PlanFirstGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer
  2 path:<folder> | path -> Reply `path: <folder>` or send the folder path alone, then SET TARGET_DIR, SET PLAN_FIRST_CONTINUE = KitInitPreflight, SET CURRENT_WORKFLOW = cf-kit, SET COMPANION_CONTINUE = PlanFirstGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer
  3 cancel -> STOP_TURN
  INVALID -> treat non-empty path-like free text as TARGET_DIR, SET PLAN_FIRST_CONTINUE = KitInitPreflight, SET CURRENT_WORKFLOW = cf-kit, SET COMPANION_CONTINUE = PlanFirstGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer; handle `cancel`, `help`, or non-path text by EMIT "Reply with `path: <folder>`, a path-like folder value, or 3 to cancel." and EMIT_MENU KitInitTargetMenu
```
