# Map Config Assist

```pdsl
UNIT MapConfigAssist
PURPOSE: Generate or refine ./md-map.toml from an existing map run.
STATE:
  SET palette: fixed-tailwind-500 | theme-light | theme-dark | theme-pastel | theme-neon (default unset, scope workflow_run)
  SET show_uncategorized: true | false (default false, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/requirements/map-config-assist.md for palettes, name normalization, and candidate thresholds
  LOAD {cf-studio-path}/.core/skills/studio/modules/map-generate-validate.md
  SET scope = single-repo WHEN scope is unset (config-assist default scan scope; the user can re-scope via generate-map)
  RUN locate the JSON payload — prefer ./md-map.json, else ./md-map.html.js with the leading `window.MAP_DATA = ` and trailing `;` stripped, else generate ./md-map.json for the chosen scope via `{cfs_cmd} --json map`
  RUN read the located JSON payload
  RUN derive category candidates and names per the loaded reference
  LOAD {cf-studio-path}/.core/skills/studio/modules/map-config-palette.md
  CONTINUE MapConfigAssistPaletteOffer
RULES:
  NEVER write ./md-map.toml without an explicit yes
  ALWAYS derive category names and pick palette colors per the loaded reference
```
