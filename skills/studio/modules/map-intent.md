# Map Intent

```pdsl
UNIT MapIntentRouter
PURPOSE: Route the map request by user intent.
STATE:
  SET format: html | json (default html, scope workflow_run)
  SET scope: single-repo | with-workspace | markdown-only (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/map-preflight.md
  SET COMPANION_CONTINUE = MapIntentMenu
  RUN CompanionSkillOffer
  EMIT_MENU MapIntentMenu
  WAIT user.reply
  STOP_TURN
MENU MapIntentMenu
TITLE: What would you like to do with the map tool? Generate builds the map; analyze-dangling diagnoses missing refs; export-json produces machine-readable output; config-assist builds md-map.toml category rules. Reply with a number or the option name.
OPTIONS:
  1 generate-map -> CONTINUE MapPreflight
  2 analyze-dangling | analyze -> RUN ResourceContextMemory, ensure a map artifact exists first (CONTINUE MapPreflight to generate one WHEN no ./md-map.json or ./md-map.html[.js] is present), then CONTINUE {cf-studio-path}/.core/workflows/analyze.md passing ORIGINAL_INTENT="analyze the dependency map for dangling and phantom references" and resource_context = the generated map artifact path
  3 export-json | json -> SET format = json, CONTINUE MapPreflight
  4 config-assist | config -> LOAD {cf-studio-path}/.core/skills/studio/modules/map-config-assist.md; CONTINUE MapConfigAssist
  INVALID -> EMIT_MENU MapIntentMenu
NOTES:
  Option labels of the form `name | alias` accept either word as the reply (e.g. `analyze-dangling` or `analyze`); each is one option, not two.
```
