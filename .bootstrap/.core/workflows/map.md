---
cf: true
type: workflow
name: map
description: Build interactive dependency maps — scan markdown, source code, cpt references; detect cross-repo edges and phantom cpts; render HTML viewer or JSON
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
- [Quick Reference](#quick-reference)
- [Next Steps](#next-steps)

<!-- /toc -->

ALWAYS open and follow `{cf-studio-path}/config/AGENTS.md` FIRST.
ALWAYS open and follow `{cf-studio-path}/.gen/AGENTS.md` after config/AGENTS.md.
**Type**: Operation
**Role**: Any
**Output**: Interactive HTML map or JSON graph export

## Overview
Use this workflow to scan markdown files and source code for dependencies, build an interactive map of connections (file links, cpt identifiers, cross-repo references), and detect dangling references. The map reveals architecture, traceability gaps, and federation boundaries.

| User intent | Route |
|---|---|
| Generate map of current project | `generate.md` → `cf-map.md` |
| Analyze map for dangling cpts | `analyze.md` with map target |
| Export map data for tooling | JSON format via `--format json` |

## Phase 1: Pre-flight
**Goal**: detect what will be scanned.

| Step | Action |
|---|---|
| Check artifacts.toml | `python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py --json info` (look for `[[systems.codebase]]` entries) |
| Check workspace config | Look for `.studio-workspace.toml` in project root |
| Report sources | Show "Local markdown only" or list all workspace sources that will be scanned |
| Report systems | List `[[systems.codebase]]` from `artifacts.toml` (or "no artifact registry found") |

**Decision point**: After presenting discovered state, ask:

```text
Why this input is needed: decide whether to scan workspace sources and include source code in the map.
Reply with the scope: local-only, include-workspace, or no-source.
Suggested default: include-workspace if workspace config exists, else local-only.
- `local-only` → scan only this repo's markdown files.
- `include-workspace` → scan workspace sources (requires .studio-workspace.toml).
- `no-source` → skip source code; markdown only.
```

## Phase 2: Configure
**Goal**: confirm map settings.

Present one confirmation prompt covering:
- Output format: `html` (interactive viewer) or `json` (machine-readable)
- Output file: default `./md-map.html` or `./md-map.json` (use `--out PATH` to override)
- Category config: use auto-detect or provide `md-map.toml` for custom categorization
- Inline data: for HTML, embed JSON into the file (no `.js` sidecar) or keep separate

```text
Why this input is needed: confirm map output settings before scanning.
Reply with `approve` to accept defaults, or list only the fields to change.
Suggested defaults: HTML output to ./md-map.html, auto-detect categories, keep data separate.
- `approve` → use proposed settings and continue.
- field edits → update only the named fields, then re-show the proposal.
```

## Phase 3: Generate
**Goal**: invoke `cfs map` and produce output.

| Scope decision | Command |
|---|---|
| Local markdown only | `python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py --json map --no-source [--out PATH] [--format html\|json]` |
| Include workspace sources | `python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py --json map [--out PATH] [--format html\|json]` |
| Local + source code only | `python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py --json map --local-only [--out PATH] [--format html\|json]` |

After generation:
- Confirm output file exists and size is reasonable
- If HTML, display the file path and note that it opens in a browser
- If JSON, note that it can be piped to other tools (e.g., `jq`)

## Phase 4: Validate
**Goal**: inspect the map for completeness and phantom references.

| Check | Action |
|---|---|
| Open HTML map | Open the generated `.html` in a browser; verify vis-network graph renders without errors |
| Count nodes/edges | JSON or browser DevTools → count markdown nodes, source nodes, cross-repo edges |
| Check for dangling cpts | Search JSON for `phantom:<cpt-id>` nodes or `dangling_cpt_uses` array (these are dangling references) |
| Categorization review | Verify nodes are color-coded by category; check if override `md-map.toml` helped or if more rules are needed |
| Route to diagnostics | If dangling cpts found, suggest `cfs where-used <cpt-id>` or `cfs list-ids` for cross-repo IDs |

## Quick Reference

| Intent | Flags |
|---|---|
| Markdown-only quick map | `cfs map --no-source` |
| Single-repo map (skip federation) | `cfs map --local-only` |
| Machine-readable graph | `cfs map --format json --out map.json` |
| Custom categories | `cfs map --config md-map.toml` |
| Self-contained HTML (no sidecar) | `cfs map --inline-data` |
| Debug layout | `cfs map -v` or `cfs map --verbose` |

## Next Steps
**After successful map generation**:
- Use the HTML viewer to explore architecture visually or export images for documentation
- Export JSON and pipe to downstream tools (e.g., GraphQL queries, traceability reports)
- For dangling cpts, use `cfs where-used <cpt-id>` to find missing definitions
- Update `md-map.toml` if categorization needs adjustment
- Share the map with team for architecture review

When presenting next steps to the user, include a suggested default and an explicit reply contract:

```text
What would you like to do next?
Reply with the option number or a short custom instruction.
1. Open the map in a browser — Suggested default; explore the interactive graph.
2. Export JSON and analyze with jq — For programmatic access to nodes/edges.
3. Check for dangling cpts — Run cfs where-used <cpt-id> to diagnose phantom references.
4. Update categorization — Create or refine md-map.toml for better node grouping.
5. Other — describe the next map action you want.
```
