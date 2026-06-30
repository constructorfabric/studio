# Map Next

```pdsl
UNIT MapNextSteps
PURPOSE: Present post-generation next steps.
DO:
  EMIT_MENU MapNextStepsMenu
  WAIT user.reply
  STOP_TURN
MENU MapNextStepsMenu
TITLE: What would you like to do next? Option 1 is the suggested default. Reply with a number or a short custom instruction.
OPTIONS:
  1 open-viewer | open -> EMIT guidance to open the generated HTML map in a browser, then EMIT_MENU MapNextStepsMenu
  2 export-json | json -> RUN `{cfs_cmd} map --format json --out map.json` (re-runs the map), then EMIT_MENU MapNextStepsMenu
  3 diagnose -> WAIT a cpt-id, RUN `{cfs_cmd} where-used <cpt-id>`, then EMIT_MENU MapNextStepsMenu
  4 config-assist | config -> LOAD {cf-studio-path}/.core/skills/studio/modules/map-config-assist.md; CONTINUE MapConfigAssist
  5 custom -> WAIT the user's next map action, then EMIT_MENU MapNextStepsMenu
  INVALID -> EMIT_MENU MapNextStepsMenu
```
