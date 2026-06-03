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

```pdsl
UNIT sources_of_truth
PURPOSE: Define which files and paths contribute nodes to the map.
STATE:
  - SET markdown_sources: every *.md under project root (and reachable sources) minus skip dirs
  - SET code_sources: only [[systems.codebase]] paths from artifacts.toml filtered by extensions
DO:
  - LOAD markdown_sources
  - LOAD code_sources
RULES:
  - NEVER include source nodes from systems where traceability_mode = "DOCS-ONLY"
ON_ERROR:
  artifacts.toml absent -> warn on stderr, use markdown-only mode, exit 0
```

## Output Format: HTML

Self-contained `.html` (plus optional `.js` sidecar) with vis-network viewer.
JSON payload accessible as `window.MAP_DATA` for downstream tooling.

## Output Format: JSON

```pdsl
UNIT json_output
PURPOSE: Emit a validated, stable-ordered JSON map payload.
RULES:
  - ALWAYS validate output against schemas/map.schema.json
  - ALWAYS include top-level keys: version, generated_at, workspace, scan, nodes, edges, dangling_cpt_uses, categories
  - ALWAYS sort nodes and edges by id ascending for stable output ordering
NOTES:
  generated_at reflects actual run time and varies per invocation; "stable" means
  deterministic node/edge ordering, not byte-identical output across runs
```

## Categorization

```pdsl
UNIT categorization
PURPOSE: Assign a category to each node via a first-match priority chain.
DO:
  - SET category: first match of — (1) md-map.toml override, (2) artifacts.toml registry longest path-prefix, (3) parent directory name (_root for repo-root files)
  - SET category_origin: the winning branch name
RULES:
  - ALWAYS record category_origin on every node
```

## Workspace Federation

```pdsl
UNIT workspace_federation
PURPOSE: Scan and link nodes across federated workspace sources.
WHEN:
  - REQUIRE .studio-workspace.toml is present
DO:
  - LOAD sources beyond "local" defined in .studio-workspace.toml
  - SET node_id format: <source>:<rel-path>
  - SET cross_repo: true on edges connecting nodes from different sources
RULES:
  - ALWAYS skip federation when --local-only flag is set
```

## Phantom cpt Nodes

```pdsl
UNIT phantom_cpt_nodes
PURPOSE: Represent cpt-ids that are referenced but never defined in any reachable source.
WHEN:
  - REQUIRE cpt-id appears in markdown or code but is defined nowhere reachable
DO:
  - EMIT node: type phantom-cpt, id phantom:<cpt-id>, red styling
  - SET dangling: true on all incoming edges; style red-dashed
  - EMIT dangling_cpt_uses: mirror phantom info for non-graph consumers
```

## Errors and Exit Codes
| Code | Meaning |
|---|---|
| 0 | Success (warnings allowed) |
| 1 | Internal error |
| 2 | Invalid `md-map.toml` |
