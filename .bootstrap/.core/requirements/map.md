---
cf: true
type: requirement
name: cfs map
version: 1.0
purpose: Specify cfs map CLI, output formats, and behavior
---
# cfs map Specification

<!-- toc -->

- [Overview](#overview)
- [CLI](#cli)
- [Sources of Truth](#sources-of-truth)
- [Output Format: HTML](#output-format-html)
- [Output Format: JSON](#output-format-json)
- [Categorization](#categorization)
- [Workspace Federation](#workspace-federation)
- [Phantom cpt Nodes](#phantom-cpt-nodes)
- [Errors and Exit Codes](#errors-and-exit-codes)

<!-- /toc -->

## Overview
`cfs map` builds an interactive dependency map of all markdown files plus
source files registered in `artifacts.toml`, connected by file links and cpt
identifiers.

## CLI
| Flag | Default | Effect |
|---|---|---|
| `--out PATH` | `./md-map.html` (or `.json`) | Output file path. |
| `--format html\|json` | `html` | Output format. |
| `--config PATH` | autodetect `md-map.toml` | Category override config. |
| `--no-source` | false | Skip `[[systems.codebase]]` scanning. |
| `--local-only` | false | Disable workspace federation. |
| `--inline-data` | false | Embed JSON into HTML; no .js sidecar. |
| `-v / --verbose` | false | Layout/scan debug output. |

## Sources of Truth
- Markdown: every `*.md` under project root (and reachable sources) minus skip dirs.
- Source code: only `[[systems.codebase]]` paths from `artifacts.toml`, filtered by `extensions`.
- `traceability_mode = "DOCS-ONLY"` systems contribute no source nodes.
- No `artifacts.toml` → markdown-only mode + stderr warning, exit 0.

## Output Format: HTML
Self-contained `.html` (plus optional `.js` sidecar) with vis-network viewer.
JSON payload accessible as `window.MAP_DATA` for downstream tooling.

## Output Format: JSON
Validated against `schemas/map.schema.json`. Top-level keys: `version`,
`generated_at`, `workspace`, `scan`, `nodes`, `edges`, `dangling_cpt_uses`,
`categories`. Nodes and edges sorted by `id` ascending for byte-stable output.

## Categorization
Priority chain (first match wins): (1) override config `md-map.toml`,
(2) `artifacts.toml` registry (longest path-prefix), (3) parent directory name
(`_root` for files at repo root). `category_origin` field on each node records
the winning branch.

## Workspace Federation
When `.studio-workspace.toml` or `.studio-workspace.toml` is present,
sources beyond "local" are scanned. Node IDs use the form `<source>:<rel-path>`.
Edges between source A and source B are marked `cross_repo = true`.
`--local-only` skips federation entirely.

## Phantom cpt Nodes
A cpt-id used (in markdown or code) but defined nowhere reachable produces a
`phantom-cpt` node with id `phantom:<cpt-id>` and red styling. Incoming edges
are styled `dangling = true` and red-dashed. The same information is mirrored
in `dangling_cpt_uses` for non-graph consumers.

## Errors and Exit Codes
| Code | Meaning |
|---|---|
| 0 | Success (warnings allowed) |
| 1 | Internal error |
| 2 | Invalid `md-map.toml` |
