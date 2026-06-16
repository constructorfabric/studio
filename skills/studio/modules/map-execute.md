# Map Configure

```pdsl
UNIT MapConfigure
PURPOSE: Confirm map output settings before scanning.
STATE:
  SET config_exists: true | false (default false, scope workflow_run)
DO:
  EMIT proposed settings — format (html interactive viewer | json machine-readable); out (./md-map.html or ./md-map.json, override with --out PATH); category config (auto-detect or md-map.toml); inline_data (embed JSON into the HTML file vs keep a separate sidecar)
  EMIT_MENU MapConfigMenu
  WAIT user.reply
  STOP_TURN
MENU MapConfigMenu
TITLE: Confirm map output settings. Suggested defaults: HTML to ./md-map.html, auto-detect categories, keep data separate. Reply with a number or list only the fields to change.
OPTIONS:
  1 approve -> RUN `test -f <project_root>/md-map.toml` against the absolute project_root resolved in MapPreflight (never inferred from PWD), SET config_exists = true when the file exists else false, then LOAD {cf-studio-path}/.core/skills/studio/modules/map-config-assist.md WHEN scope != markdown-only AND config_exists == false, EMIT_MENU ConfigAssistOfferMenu WHEN scope != markdown-only AND config_exists == false, else CONTINUE MapGenerate
  2 field-edits | edit -> PARSE named fields (format, out, config, inline_data), reject any unknown field with a one-line hint "Editable fields: format, out, config, inline_data.", re-emit the updated proposal, then EMIT_MENU MapConfigMenu
  INVALID -> EMIT_MENU MapConfigMenu
MENU ConfigAssistOfferMenu
TITLE: No md-map.toml detected at <project_root>. Want help generating one before scanning?
OPTIONS:
  1 yes -> CONTINUE MapConfigAssist
  2 no -> CONTINUE MapGenerate
  INVALID -> EMIT_MENU ConfigAssistOfferMenu
NOTES:
  The config-assist offer is skipped for markdown-only scope because category overrides are only useful when source-code nodes are present.
```
