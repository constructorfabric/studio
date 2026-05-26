---
cf: true
type: workflow
name: cf-map
description: Invoke when the user asks to build a dependency map, visualize cross-references, scan markdown/code, detect phantom cpts, or render the HTML map viewer.
version: 1.0
purpose: Guide cfs map workflow from pre-flight through validation
---

# Constructor Studio Map Workflow

<!-- toc -->

- [Overview](#overview)
- [Phase 1: Pre-flight](#phase-1-pre-flight)
- [Phase 2: Configure](#phase-2-configure)
- [Phase 3: Generate](#phase-3-generate)
- [Phase 4: Validate](#phase-4-validate)
- [Phase Config-Assist](#phase-config-assist)
- [Quick Reference](#quick-reference)
- [Next Steps](#next-steps)

<!-- /toc -->

```text
UNIT MapBootstrap

PURPOSE:
  Load required agent context before any map phase work begins.

DO:
  REQUIRE {cf-studio-path}/config/AGENTS.md is loaded and followed FIRST
  REQUIRE {cf-studio-path}/.gen/AGENTS.md is loaded and followed after config/AGENTS.md
  EMIT_MENU MapIntentRouter
  WAIT user.reply
  STOP_TURN

NOTES:
  Type: Operation. Role: Any. Output: Interactive HTML map or JSON graph export.
```

## Overview

```text
UNIT MapOverview

PURPOSE:
  Define map workflow routing by user intent.

MENU MapIntentRouter:
  TITLE: >
    What would you like to do with the map tool?
    Reply with a number or the option name.
  OPTIONS:
    1 generate-map ->
      CONTINUE MapPhase1
    2 analyze-dangling ->
      LOAD analyze.md with map target
    3 export-json ->
      SET map.format = json
      CONTINUE MapPhase1
    4 config-assist ->
      CONTINUE MapPhaseConfigAssist
  INVALID:
    EMIT "Reply with 1 generate-map, 2 analyze-dangling, 3 export-json, or 4 config-assist."
    WAIT user.reply
    STOP_TURN

NOTES:
  Scans markdown files and source code for dependencies; builds interactive map
  of connections (file links, cpt identifiers, cross-repo references); detects
  dangling references. Reveals architecture, traceability gaps, federation boundaries.
```

## Phase 1: Pre-flight

```text
UNIT MapPhase1

PURPOSE:
  Detect what will be scanned before generating the map.

DO:
  RUN python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py --json info
    (look for [[systems.codebase]] or [[systems.autodetect.codebase]] entries in artifacts.toml)
  CHECK for .studio-workspace.toml in project root (federation axis)
  CHECK for [[systems.codebase]] or [[systems.autodetect.codebase]] entries in
    <adapter_dir>/config/artifacts.toml or <project_root>/artifacts.toml (source-scanning axis)
  EMIT discovered state:
    Federation: ".studio-workspace.toml present" OR "no workspace config — federation unavailable"
    Source scanning: list [[systems.codebase]] / [[systems.autodetect.codebase]] entries found,
      OR "no codebase entries found — source scanning unavailable"
  EMIT_MENU MapScopeMenu
  WAIT user.reply
  STOP_TURN

MENU MapScopeMenu:
  TITLE: >
    Why this input is needed: decide the scan scope along two independent axes —
    federation (this repo only vs. include workspace sources) and source scanning
    (scan source code vs. markdown only).
    Reply with a number (1, 2, or 3) or the option name.
    Suggested default:
      2 with-workspace  when .studio-workspace.toml exists AND codebase entries exist
      1 single-repo     when no .studio-workspace.toml but codebase entries exist
      3 markdown-only   when no codebase entries exist
  OPTIONS:
    1 single-repo ->
      SET map.scope = single-repo
      CONTINUE MapPhase2
    2 with-workspace ->
      REQUIRE .studio-workspace.toml exists
      SET map.scope = with-workspace
      CONTINUE MapPhase2
    3 markdown-only ->
      SET map.scope = markdown-only
      CONTINUE MapPhase2
  INVALID:
    EMIT "Reply with 1 single-repo, 2 with-workspace, or 3 markdown-only."
    WAIT user.reply
    STOP_TURN
```

## Phase 2: Configure

```text
UNIT MapPhase2

PURPOSE:
  Confirm map settings before scanning.

DO:
  EMIT proposed settings:
    Output format: html (interactive viewer) or json (machine-readable)
    Output file: ./md-map.html or ./md-map.json (use --out PATH to override)
    Category config: auto-detect or provide md-map.toml for custom categorization
    Inline data: for HTML, embed JSON into file (no .js sidecar) or keep separate
  EMIT_MENU MapConfigMenu
  WAIT user.reply
  STOP_TURN

MENU MapConfigMenu:
  TITLE: >
    Why this input is needed: confirm map output settings before scanning.
    Reply with a number (1 or 2) or the option name to accept defaults or list only the fields to change.
    Suggested defaults: HTML output to ./md-map.html, auto-detect categories, keep data separate.
  OPTIONS:
    1 approve ->
      RUN test -f <project_root>/md-map.toml  (deterministic existence check; use absolute path)
        # MUST execute this shell check before deciding — do NOT infer from PWD or assume
      SET map.config_exists = (exit_code == 0)
      WHEN map.scope != markdown-only AND map.config_exists == false:
        EMIT "No md-map.toml detected at <project_root>. Want help generating one before scanning?"
        EMIT_MENU ConfigAssistOfferMenu
        WAIT user.reply
        STOP_TURN
      OTHERWISE:
        CONTINUE MapPhase3
    2 field-edits ->
      SET map.config_pending_edits = user.named_fields
      RE-EMIT updated proposal with map.config_pending_edits applied
      WAIT user.reply
      STOP_TURN
  INVALID:
    EMIT "Reply with 1 approve or 2 field-edits."
    WAIT user.reply
    STOP_TURN

MENU ConfigAssistOfferMenu:
  TITLE: >
    Would you like to generate an md-map.toml config before scanning?
    A prior map run with JSON output is needed; if none exists, one will be run first.
    Reply with a number (1 or 2) or the option name.
  OPTIONS:
    1 yes ->
      CONTINUE MapPhaseConfigAssist
    2 no ->
      CONTINUE MapPhase3
  INVALID:
    EMIT "Reply with 1 yes or 2 no."
    WAIT user.reply
    STOP_TURN

NOTES:
  The config-assist offer is skipped for markdown-only scope because category
  overrides are typically only useful when source-code nodes are present.
  When the user picks "yes", MapPhaseConfigAssist will run MapPhase3 internally
  (if a JSON artifact is missing) and then return control to MapPhase3 after
  writing the config.
```

## Phase 3: Generate

```text
UNIT MapPhase3

PURPOSE:
  Invoke cfs map and produce output.

DO:
  WHEN map.scope == single-repo:
    RUN python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py --json map --local-only [--out PATH] [--format html|json] [--config PATH]
  WHEN map.scope == with-workspace:
    RUN python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py --json map [--out PATH] [--format html|json] [--config PATH]
  WHEN map.scope == markdown-only:
    RUN python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py --json map --no-source [--out PATH] [--format html|json] [--config PATH]
  VERIFY output file exists and size is reasonable
  IF format == html:
    EMIT file path; note that it opens in a browser
  IF format == json:
    EMIT note that it can be piped to other tools (e.g., jq)
  CONTINUE MapPhase4
```

## Phase 4: Validate

```text
UNIT MapPhase4

PURPOSE:
  Inspect the map for completeness and phantom references.

DO:
  CHECK: Open generated .html in a browser; verify vis-network graph renders without errors
  COUNT: nodes/edges via JSON or browser DevTools (markdown nodes, source nodes, cross-repo edges)
  CHECK: Search JSON for phantom:<cpt-id> nodes or dangling_cpt_uses array (dangling references)
  VERIFY: nodes are color-coded by category; check if md-map.toml override helped
  IF dangling cpts found:
    SUGGEST `cfs where-used <cpt-id>` or `cfs list-ids` for cross-repo IDs
  CONTINUE MapNextSteps
```

## Phase Config-Assist

```text
UNIT MapPhaseConfigAssist

PURPOSE:
  Help the user generate or refine ./md-map.toml from an existing map run.

PREREQUISITES:
  A JSON map artifact must exist for this project. If not, run MapPhase3 first
  with --format json (or both html+json side-by-side) to produce ./md-map.json
  (or read the existing ./md-map.html.js sidecar — same JSON shape).

DO:
  1. LOCATE the JSON payload:
       - prefer ./md-map.json if it exists,
       - else ./md-map.html.js (strip the leading `window.MAP_DATA = ` if present
         and trailing `;`).
       - If neither exists:
           EMIT "No JSON map artifact found. Running MapPhase3 with --format json first."
           CONTINUE MapPhase3 with --format json
           (after MapPhase3 completes, resume from step 2 here)
  2. PARSE nodes; collect candidates: nodes where category_origin == "parent-dir".
  3. GROUP candidates by top-2 path segments (e.g. `src/studio`, `docs/architecture`).
     For each group capture: prefix, node_count, sample 3 rel_paths.
  4. FILTER groups: keep only those with node_count >= 5.
  5. SORT by node_count descending; take top 10.
  6. DERIVE category names deterministically from the group's path prefix using:
       - Lowercase the entire prefix
       - Replace `/`, `.`, and `_` with `-`
       - Strip leading `-` characters
       - Collapse consecutive `-` into a single `-`
       - Strip trailing `-`
     On collision (two prefixes normalize to the same name), suffix duplicates with `-2`, `-3`, ...
     in order of appearance.
     Then PROPOSE one [[categories]] entry per group with:
       - name = "<derived-name>" (derived from path prefix per rule above)
       - paths = [<group_prefix> + "/**"]
       - style.color / style.background = picked from palette (see step 7).
     
     Normalization examples:
     | Prefix | → | Derived Name |
     |---|---|---|
     | `skills/studio` | → | `skills-studio` |
     | `.bootstrap/config` | → | `bootstrap-config` |
     | `.claude/agents` | → | `claude-agents` |
     | `architecture/ADR` | → | `architecture-adr` |
     | `examples/overwork_alert` | → | `examples-overwork-alert` |
  7. EMIT_MENU PaletteMenu
     WAIT user.reply
     STOP_TURN
  8. After palette chosen, EMIT_MENU UncategorizedBucketMenu
     WAIT user.reply
     STOP_TURN
  9. After uncategorized bucket choice, emit the full proposed TOML block in chat with:
     - Top-level field: show_uncategorized = {true|false} (based on step 8 choice)
     - Derived category names populated in the `name = "..."` field for each category
     Include a note: "Names are derived from path prefixes. Use 2 edit-names if you want to
     refine them, or 1 approve to accept. Toggle `show_uncategorized` directly in the TOML
     if you change your mind before approve."
  10. EMIT_MENU ConfigAssistActionMenu
      WAIT user.reply
      STOP_TURN
  11. On 1 approve:
        a. EMIT "About to write ./md-map.toml ({N} categories). Reply `yes` to confirm."
        b. WAIT user.reply
           STOP_TURN
        c. If reply == "yes":
             write ./md-map.toml (orchestrator-write, gate released_for_orchestrator_write)
        d. After write:
             EMIT "Re-running map with new config..."
             CONTINUE MapPhase3 with `--config ./md-map.toml` appended to the RUN line
  12. On 2 edit-names:
        WAIT user.reply with renames
        STOP_TURN
        RE-EMIT updated TOML; loop back to step 10
  13. On 3 add-manual:
        WAIT user.reply for one or more manual {name, paths, style?} entries
        STOP_TURN
        APPEND to proposed config; loop back to step 10
  14. On 4 skip:
        CONTINUE MapNextSteps

MENU PaletteMenu:
  TITLE: >
    Pick a color palette for the proposed categories. Reply with 1 or 2.
  OPTIONS:
    1 fixed ->
      SET palette = fixed-tailwind-500
      (10 colors, Tailwind-500 series, contrast-safe on light AND dark backgrounds)
      Colors in order:
        #ef4444 / #fee2e2   (red-500    / red-50)
        #f97316 / #ffedd5   (orange-500 / orange-50)
        #f59e0b / #fffbeb   (amber-500  / amber-50)
        #eab308 / #fefce8   (yellow-500 / yellow-50)
        #84cc16 / #f7fee7   (lime-500   / lime-50)
        #22c55e / #f0fdf4   (green-500  / green-50)
        #14b8a6 / #f0fdfa   (teal-500   / teal-50)
        #06b6d4 / #ecfeff   (cyan-500   / cyan-50)
        #3b82f6 / #eff6ff   (blue-500   / blue-50)
        #6366f1 / #eef2ff   (indigo-500 / indigo-50)
    2 theme ->
      EMIT_MENU ThemePickerMenu
      WAIT user.reply
      STOP_TURN
  INVALID:
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN

MENU ThemePickerMenu:
  TITLE: >
    Pick a theme. Reply with a number (1-4) or the option name.
  OPTIONS:
    1 light ->
      SET palette = theme-light
      (Tailwind-200 series — muted mid-tone fills, paired with -50 backgrounds)
      Colors in order:
        #fca5a5 / #fee2e2   (red-300    / red-50    — lighter for light themes)
        #fdba74 / #ffedd5   (orange-300 / orange-50)
        #fcd34d / #fffbeb   (amber-300  / amber-50)
        #fde047 / #fefce8   (yellow-300 / yellow-50)
        #bef264 / #f7fee7   (lime-300   / lime-50)
        #86efac / #f0fdf4   (green-300  / green-50)
        #5eead4 / #f0fdfa   (teal-300   / teal-50)
        #67e8f9 / #ecfeff   (cyan-300   / cyan-50)
        #93c5fd / #eff6ff   (blue-300   / blue-50)
        #a5b4fc / #eef2ff   (indigo-300 / indigo-50)
    2 dark ->
      SET palette = theme-dark
      (Tailwind-700 series — deep fills, paired with -900 backgrounds)
      Colors in order:
        #b91c1c / #450a0a   (red-700    / red-950)
        #c2410c / #431407   (orange-700 / orange-950)
        #b45309 / #451a03   (amber-700  / amber-950)
        #a16207 / #422006   (yellow-700 / yellow-950)
        #4d7c0f / #1a2e05   (lime-700   / lime-950)
        #15803d / #052e16   (green-700  / green-950)
        #0f766e / #042f2e   (teal-700   / teal-950)
        #0e7490 / #083344   (cyan-700   / cyan-950)
        #1d4ed8 / #172554   (blue-700   / blue-950)
        #4338ca / #1e1b4b   (indigo-700 / indigo-950)
    3 pastel ->
      SET palette = theme-pastel
      (Tailwind-100 series — very soft fills, paired with white-equivalent backgrounds)
      Colors in order:
        #fee2e2 / #fff5f5   (red-100    / red-50  near-white)
        #ffedd5 / #fff8f0   (orange-100 / orange-50 near-white)
        #fef3c7 / #fffdf0   (amber-100  / amber-50 near-white)
        #fef9c3 / #fffeeb   (yellow-100 / yellow-50 near-white)
        #ecfccb / #f9ffe8   (lime-100   / lime-50  near-white)
        #dcfce7 / #f0fdf4   (green-100  / green-50)
        #ccfbf1 / #f0fdfa   (teal-100   / teal-50)
        #cffafe / #ecfeff   (cyan-100   / cyan-50)
        #dbeafe / #eff6ff   (blue-100   / blue-50)
        #e0e7ff / #eef2ff   (indigo-100 / indigo-50)
    4 neon ->
      SET palette = theme-neon
      (fluorescent / saturated set — bright fills on near-black backgrounds)
      Colors in order:
        #ff073a / #1a0005   (neon red    / near-black)
        #ff6d00 / #1a0d00   (neon orange / near-black)
        #ffe600 / #1a1800   (neon yellow / near-black)
        #39ff14 / #021a00   (neon green  / near-black)
        #00ffcc / #001a16   (neon teal   / near-black)
        #00e5ff / #001a1f   (neon cyan   / near-black)
        #1b9aff / #00101a   (neon blue   / near-black)
        #b400ff / #0d001a   (neon purple / near-black)
        #ff00c8 / #1a0016   (neon pink   / near-black)
        #ffffff / #0d0d0d   (white       / near-black — neutral contrast anchor)
  INVALID:
    EMIT "Reply with 1 light, 2 dark, 3 pastel, or 4 neon."
    WAIT user.reply
    STOP_TURN

MENU UncategorizedBucketMenu:
  TITLE: >
    Should nodes NOT matching any [[categories]] path be hidden, or shown as a single "_uncategorized" bucket?
    Reply 1 (hide) or 2 (show as bucket).
  OPTIONS:
    1 hide ->
      SET config.show_uncategorized = false
      CONTINUE next step (render TOML)
    2 bucket ->
      SET config.show_uncategorized = true
      CONTINUE next step (render TOML)
  INVALID:
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN

MENU ConfigAssistActionMenu:
  TITLE: >
    Review the proposed TOML above. What would you like to do?
    Reply with a number (1-4) or the option name.
  OPTIONS:
    1 approve ->
      (proceed to step 11 — write confirmation)
    2 edit-names ->
      (proceed to step 12 — rename loop)
    3 add-manual ->
      (proceed to step 13 — append manual entries)
    4 skip ->
      CONTINUE MapNextSteps
  INVALID:
    EMIT "Reply with 1 approve, 2 edit-names, 3 add-manual, or 4 skip."
    WAIT user.reply
    STOP_TURN
```

## Quick Reference

| Intent | Flags |
|---|---|
| Markdown-only quick map | `cfs map --no-source` |
| Single-repo map (skip federation) | `cfs map --local-only` |
| Machine-readable graph | `cfs map --format json --out map.json` |
| Custom categories | `cfs map --config md-map.toml` (use `/cf-map` → option 4 "Generate or refine md-map.toml config" to scaffold) |
| Self-contained HTML (no sidecar) | `cfs map --inline-data` |
| Debug layout | `cfs map -v` or `cfs map --verbose` |

## Next Steps

```text
UNIT MapNextSteps

PURPOSE:
  Present post-generation next steps with a suggested default and explicit reply contract.

DO:
  EMIT_MENU MapNextStepsMenu
  WAIT user.reply
  STOP_TURN

MENU MapNextStepsMenu:
  TITLE: >
    What would you like to do next?
    Reply with the option number or a short custom instruction.
  OPTIONS:
    1 ->
      EMIT "Opening the map in a browser — explore the interactive graph."
      (Suggested default)
    2 ->
      EMIT "Export JSON and analyze with jq — for programmatic access to nodes/edges."
    3 ->
      EMIT "Check for dangling cpts — run cfs where-used <cpt-id> to diagnose phantom references."
    4 ->
      CONTINUE MapPhaseConfigAssist
    5 ->
      WAIT user description of next map action
  INVALID:
    EMIT "Reply with 1, 2, 3, 4, or 5."
    WAIT user.reply
    STOP_TURN

NOTES:
  After successful map generation:
  - Use HTML viewer to explore architecture visually or export images for documentation
  - Export JSON and pipe to downstream tools (e.g., GraphQL queries, traceability reports)
  - For dangling cpts, use `cfs where-used <cpt-id>` to find missing definitions
  - Update md-map.toml if categorization needs adjustment (option 4 scaffolds the file)
  - Share the map with team for architecture review
```
