# Map Palette

```pdsl
UNIT MapConfigAssistPaletteOffer
PURPOSE: Present the derived category palette choices and wait for the user's selection.
DO:
  EMIT_MENU PaletteMenu
  WAIT user.reply
  STOP_TURN
MENU PaletteMenu
TITLE: Pick a color palette for the proposed categories — this affects visual distinction and accessibility in the rendered map.
OPTIONS:
  1 fixed -> Tailwind-500, high contrast on light+dark; SET palette = fixed-tailwind-500 and EMIT_MENU UncategorizedMenu
  2 light -> Tailwind-300, muted light-theme; SET palette = theme-light and EMIT_MENU UncategorizedMenu
  3 dark -> Tailwind-700, deep dark-theme; SET palette = theme-dark and EMIT_MENU UncategorizedMenu
  4 pastel -> Tailwind-100, very soft; SET palette = theme-pastel and EMIT_MENU UncategorizedMenu
  5 neon -> fluorescent on near-black; SET palette = theme-neon and EMIT_MENU UncategorizedMenu
  INVALID -> EMIT_MENU PaletteMenu
MENU UncategorizedMenu
TITLE: Should nodes matching no [[categories]] path be hidden, or shown as a single "_uncategorized" bucket?
OPTIONS:
  1 hide -> SET show_uncategorized = false, EMIT the proposed TOML, then EMIT_MENU ConfigAssistActionMenu
  2 bucket -> SET show_uncategorized = true, EMIT the proposed TOML, then EMIT_MENU ConfigAssistActionMenu
  INVALID -> EMIT_MENU UncategorizedMenu
MENU ConfigAssistActionMenu
TITLE: Review the proposed TOML above. What would you like to do?
OPTIONS:
  1 approve -> EMIT "About to write <project_root>/md-map.toml — reply yes to confirm", WAIT user.reply, WRITE <project_root>/md-map.toml only on yes (orchestrator write), then CONTINUE MapGenerate with `--config <project_root>/md-map.toml`
  2 edit-names | edit -> WAIT renames as `old-name: new-name`, re-emit the TOML, then EMIT_MENU ConfigAssistActionMenu
  3 add-manual | add -> WAIT entries as `{name, paths:[...], style?}`, append them, re-emit the TOML, then EMIT_MENU ConfigAssistActionMenu
  4 skip -> LOAD {cf-studio-path}/.core/skills/studio/modules/map-next.md; CONTINUE MapNextSteps
  INVALID -> EMIT_MENU ConfigAssistActionMenu
NOTES:
  Quick reference — markdown-only: `cfs map --no-source`; single-repo: `cfs map --local-only`; json: `cfs map --format json --out map.json`; custom categories: `cfs map --config md-map.toml`; self-contained html: `cfs map --inline-data`; debug: `cfs map -v`.
```
