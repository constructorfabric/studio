---
cf: true
type: workflow
name: cf-map
description: "Invoke when the user asks to build a dependency map, visualize cross-references, scan markdown/code, detect phantom cpts, or render the HTML map viewer."
version: 0.1
purpose: Drive the cfs map CLI to scan markdown and source for dependencies and cpt cross-references, render an interactive HTML map or JSON graph, and detect dangling references, confirming scope before scanning and never writing config without approval.
---

# cf-map

This skill drives the `{cfs_cmd} map` CLI to scan markdown files and source code for dependencies and cpt cross-references, rendering an interactive HTML map or a machine-readable JSON graph. It detects dangling and phantom references that reveal traceability gaps and federation boundaries. It confirms the scan scope and output settings before scanning and never writes a config file without explicit approval.

```pdsl
UNIT MapBootstrap
PURPOSE: Load the runtime rules needed before any map work begins.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapCoreSession
  RUN WorkflowBootstrapCommandTemplateContext
  SET ORIGINAL_INTENT = the user's triggering map request (verbatim or shortest faithful summary)
  SET CURRENT_WORKFLOW = cf-map, SET COMPANION_CONTINUE = MapIntentRouter and LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md and CONTINUE CompanionSkillOffer
RULES:
  ALWAYS run StudioInstructionsMemoryGate before map routing, preflight, scanning, config assist, or handoff
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, writes, git use, or delegation
  ALWAYS load command-resolution before invoking `{cfs_cmd}` map/info commands
  ALWAYS load template-vars before resolving map output paths or unknown template variables
  ALWAYS load context-memory before passing a generated map artifact as resource_context to another workflow
  NEVER require cf or CFS_INIT before map; this workflow owns its prerequisite loads
```

```pdsl
UNIT MapIntentRouter
PURPOSE: Route the map request by user intent.
STATE:
  SET format: html | json (default html, scope workflow_run)
  SET scope: single-repo | with-workspace | markdown-only (default unset, scope workflow_run)
DO:
  EMIT_MENU MapIntentMenu
  WAIT user.reply
  STOP_TURN
MENU MapIntentMenu
TITLE: What would you like to do with the map tool? Generate builds the map; analyze-dangling diagnoses missing refs; export-json produces machine-readable output; config-assist builds md-map.toml category rules. Reply with a number or the option name.
OPTIONS:
  1 generate-map -> CONTINUE MapPreflight
  2 analyze-dangling | analyze -> RUN ResourceContextMemory, ensure a map artifact exists first (CONTINUE MapPreflight to generate one WHEN no ./md-map.json or ./md-map.html[.js] is present), then CONTINUE {cf-studio-path}/.core/workflows/analyze.md passing ORIGINAL_INTENT="analyze the dependency map for dangling and phantom references" and resource_context = the generated map artifact path
  3 export-json | json -> SET format = json, CONTINUE MapPreflight
  4 config-assist | config -> CONTINUE MapConfigAssist
  INVALID -> EMIT_MENU MapIntentMenu
NOTES:
  Option labels of the form `name | alias` accept either word as the reply (e.g. `analyze-dangling` or `analyze`); each is one option, not two.
```

```pdsl
UNIT MapPreflight
PURPOSE: Detect what will be scanned along the federation and source-scanning axes before generating.
DO:
  RUN `{cfs_cmd} --json info`
  CONTINUE MapPreflightInfoFailure WHEN it errors
  SET project_root = the absolute project root path reported by `{cfs_cmd} --json info`
  RUN CHECK for .studio-workspace.toml in the project root (federation axis)
  RUN CHECK for [[systems.codebase]] / [[systems.autodetect.codebase]] entries in {cf-studio-path}/config/artifacts.toml or <project_root>/artifacts.toml (source-scanning axis)
  CONTINUE MapPreflightScopeOffer
```

```pdsl
UNIT MapPreflightInfoFailure
PURPOSE: Stop early when Studio info cannot be read.
DO:
  EMIT "Could not read studio info (`{cfs_cmd} --json info` failed) — ensure Studio is initialized with `cfs init`, then retry."
  STOP_TURN
```

```pdsl
UNIT MapPreflightScopeOffer
PURPOSE: Present the discovered map-scope capabilities and wait for scope selection.
DO:
  EMIT the discovered state — Federation: ".studio-workspace.toml present" OR "no workspace config — federation unavailable"; Source scanning: codebase entries found OR "no codebase entries found — source scanning unavailable"
  EMIT_MENU MapScopeMenu
  WAIT user.reply
  STOP_TURN
MENU MapScopeMenu
TITLE: Choose the scan scope across two axes — federation (this repo only vs. include workspace sources) and source scanning (scan code vs. markdown only). Suggested: with-workspace if a workspace + codebase exist; else single-repo if codebase exists; else markdown-only.
OPTIONS:
  1 single-repo -> SET scope = single-repo and CONTINUE MapConfigure
  2 with-workspace | workspace -> REQUIRE .studio-workspace.toml exists, SET scope = with-workspace and CONTINUE MapConfigure
  3 markdown-only | markdown -> SET scope = markdown-only and CONTINUE MapConfigure
  INVALID -> EMIT_MENU MapScopeMenu
```

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
  1 approve -> RUN `test -f <project_root>/md-map.toml` against the absolute project_root resolved in MapPreflight (never inferred from PWD), SET config_exists = true when the file exists else false, then EMIT_MENU ConfigAssistOfferMenu WHEN scope != markdown-only AND config_exists == false, else CONTINUE MapGenerate
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

```pdsl
UNIT MapGenerate
PURPOSE: Invoke cfs map for the chosen scope and produce the output artifact.
DO:
  RUN `{cfs_cmd} --json map --local-only [--out PATH] [--format html|json] [--config PATH] [--inline-data]` WHEN scope == single-repo
  RUN `{cfs_cmd} --json map [--out PATH] [--format html|json] [--config PATH] [--inline-data]` WHEN scope == with-workspace
  RUN `{cfs_cmd} --json map --no-source [--out PATH] [--format html|json] [--config PATH] [--inline-data]` WHEN scope == markdown-only
  RUN verify the output file exists and its size is reasonable
  EMIT the output path — html opens in a browser; json can be piped to tools like jq
  CONTINUE MapValidate
RULES:
  ALWAYS pass --inline-data only when format == html AND inline_data == true
```

```pdsl
UNIT MapValidate
PURPOSE: Inspect the map for completeness and phantom references.
DO:
  RUN parse the output — html: verify the vis-network graph renders and count nodes/edges via the embedded JSON or the .html.js sidecar; json: verify top-level nodes/edges arrays exist and count them directly
  RUN search for phantom:<cpt-id> nodes or a dangling_cpt_uses array
  RUN verify nodes are color-coded by category
  EMIT a suggestion to run `{cfs_cmd} where-used <cpt-id>` (shows where a cpt is used) or `{cfs_cmd} list-ids` (lists known cpts) WHEN dangling cpts are found
  CONTINUE MapNextSteps
```

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
  1 open-viewer | open -> EMIT guidance to open the generated HTML map in a browser, then STOP_TURN
  2 export-json | json -> RUN `{cfs_cmd} map --format json --out map.json` (re-runs the map), then STOP_TURN
  3 diagnose -> WAIT a cpt-id, RUN `{cfs_cmd} where-used <cpt-id>`, then STOP_TURN
  4 config-assist | config -> CONTINUE MapConfigAssist
  5 custom -> WAIT the user's next map action, then STOP_TURN
  INVALID -> EMIT_MENU MapNextStepsMenu
```

```pdsl
UNIT MapConfigAssist
PURPOSE: Generate or refine ./md-map.toml from an existing map run.
STATE:
  SET palette: fixed-tailwind-500 | theme-light | theme-dark | theme-pastel | theme-neon (default unset, scope workflow_run)
  SET show_uncategorized: true | false (default false, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/requirements/map-config-assist.md for palettes, name normalization, and candidate thresholds
  SET scope = single-repo WHEN scope is unset (config-assist default scan scope; the user can re-scope via generate-map)
  RUN locate the JSON payload — prefer ./md-map.json, else ./md-map.html.js with the leading `window.MAP_DATA = ` and trailing `;` stripped, else generate ./md-map.json for the chosen scope via `{cfs_cmd} --json map`
  RUN read the located JSON payload
  RUN derive category candidates and names per the loaded reference
  CONTINUE MapConfigAssistPaletteOffer
RULES:
  NEVER write ./md-map.toml without an explicit yes
  ALWAYS derive category names and pick palette colors per the loaded reference
```

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
  4 skip -> CONTINUE MapNextSteps
  INVALID -> EMIT_MENU ConfigAssistActionMenu
NOTES:
  Quick reference — markdown-only: `cfs map --no-source`; single-repo: `cfs map --local-only`; json: `cfs map --format json --out map.json`; custom categories: `cfs map --config md-map.toml`; self-contained html: `cfs map --inline-data`; debug: `cfs map -v`.
```
