# Feature: Dependency Mapping

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1. Overview](#1-overview)
  - [2. Purpose](#2-purpose)
  - [3. Actors](#3-actors)
  - [4. References](#4-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Run Dependency Map](#run-dependency-map)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Scan Project Files](#scan-project-files)
  - [Categorize Nodes](#categorize-nodes)
  - [Build cpt Edges](#build-cpt-edges)
  - [Extract File Links](#extract-file-links)
  - [Enrich Edges](#enrich-edges)
  - [Compute Layout](#compute-layout)
  - [Render JSON Output](#render-json-output)
  - [Render HTML Output](#render-html-output)
- [4. States (CDSL)](#4-states-cdsl)
  - [Map Generation Lifecycle](#map-generation-lifecycle)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Node and Edge Graph](#node-and-edge-graph)
  - [Phantom Detection](#phantom-detection)
  - [HTML Output](#html-output)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [x] `p1` - **ID**: `cpt-cypilot-featstatus-dependency-mapping`

## 1. Feature Context

- [x] `p1` - `cpt-cypilot-feature-dependency-mapping`

### 1. Overview

Produces an interactive graph map of a project's markdown and source files, connected by cpt-identifier edges (`cpt-doc`, `cpt-impl`) and markdown hyperlink edges (`file-link`). Invoked as `cfc map` (or `cpt map`), the command walks the project root, scans every markdown file for cpt-ID definitions and cross-references, scans registered source files for `@cpt-*` scope and block markers, resolves markdown hyperlinks, and emits either a self-contained HTML viewer or a canonical JSON payload. cpt-IDs that are referenced in code but defined nowhere become `phantom-cpt` nodes rendered as warning diamonds, enabling reverse-engineering workflows.

### 2. Purpose

Without a dependency map, navigating large projects requires manual inspection of individual files to understand how specs relate to code. The map command provides an at-a-glance interactive visualization of the entire architecture graph — which markdown specs link to which source files through traceability markers, which source files reference undefined specs (phantoms), and how categories cluster on a rectpack layout. It is the primary audit surface for `cfc validate`-flagged phantom IDs.

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-cypilot-actor-user` | Invokes `cfc map` to generate the project dependency map |
| `cpt-cypilot-actor-ai-agent` | Uses the JSON output to understand project structure for spec reverse-engineering |
| `cpt-cypilot-actor-ci-pipeline` | Runs `cfc map --format json` as part of CI artifact generation |

### 4. References

- **PRD**: [PRD.md](../PRD.md) — `cpt-cypilot-fr-core-dependency-mapping`, `cpt-cypilot-fr-core-traceability`
- **Design**: [DESIGN.md](../DESIGN.md) — `cpt-cypilot-component-map-renderer`, `cpt-cypilot-component-traceability-engine`
- **Dependencies**: `cpt-cypilot-feature-traceability-validation`, `cpt-cypilot-feature-workspace`

## 2. Actor Flows (CDSL)

### Run Dependency Map

- [x] `p1` - **ID**: `cpt-cypilot-flow-map-cli`

**Actor**: `cpt-cypilot-actor-user`

**Success Scenarios**:
- User runs `cfc map` → HTML map written to `md-map.html` with all nodes, edges, and layout
- User runs `cfc map --format json --out /tmp/map.json` → canonical JSON written to specified path
- User runs `cfc map --no-source` → markdown-only scan; source nodes and cpt-impl edges omitted
- User runs `cfc map --local-only` → workspace federation skipped; only local source scanned
- User runs `cfc map --inline-data` → HTML produced with data embedded inline (no sidecar `.js` file)

**Error Scenarios**:
- No `artifacts.toml` at project root → stderr warning emitted; source scanning disabled; markdown scan continues
- Invalid `md-map.toml` override config → error printed, exit code 2

**Steps**:
1. [x] - `p1` - User invokes `cfc map [--out PATH] [--format html|json] [--config FILE] [--no-source] [--local-only] [--inline-data] [--verbose]` - `inst-map-cli-invoke`
2. [x] - `p1` - Discover workspace sources via `find_workspace_config`; include local source always - `inst-map-discover-sources`
3. [x] - `p1` - Load optional category override from `md-map.toml` or `--config` path - `inst-map-load-override`
4. [x] - `p1` - **FOR EACH** reachable source, invoke `scan_repo` using `cpt-cypilot-flow-map-scan:p1` - `inst-map-scan-sources`
5. [x] - `p1` - Categorize all nodes using `cpt-cypilot-flow-map-categorize:p1` - `inst-map-categorize`
6. [x] - `p1` - Extract file-link edges using `cpt-cypilot-flow-map-file-links:p1` - `inst-map-file-links`
7. [x] - `p1` - Build cpt edges and phantom nodes using `cpt-cypilot-flow-map-cpt-edges:p1` - `inst-map-cpt-edges`
8. [x] - `p1` - Enrich edges with definition context using `cpt-cypilot-flow-map-enrich:p1` - `inst-map-enrich`
9. [x] - `p1` - Compute layout using `cpt-cypilot-flow-map-layout:p1` - `inst-map-layout`
10. [x] - `p1` - Serialize to JSON using `cpt-cypilot-flow-map-render-json:p1` - `inst-map-render-json`
11. [x] - `p1` - **IF** format is html, render HTML using `cpt-cypilot-flow-map-render-html:p1`; else write JSON directly - `inst-map-render-html`
12. [x] - `p1` - Print summary: node counts, edge counts, phantom count, output path - `inst-map-summary`

## 3. Processes / Business Logic (CDSL)

### Scan Project Files

- [x] `p1` - **ID**: `cpt-cypilot-flow-map-scan`

**Input**: `ScanOptions(project_root, source_name, no_source, extra_skip_dirs)`

**Output**: `List[Node]` — flat list of markdown and source nodes

**Steps**:
1. [x] - `p1` - Walk all `.md` files under project root (both root-level and recursive) using `cpt-cypilot-algo-map-scan-walker:p1` - `inst-scan-md-walk`
2. [x] - `p1` - **FOR EACH** markdown file, call `scan_cpt_ids` to extract definitions and references; build `CptUse` entries with `marker_kind` ∈ `{md-def, md-ref}` - `inst-scan-md-cpt`
3. [x] - `p1` - **IF** `no_source` is False, load `artifacts.toml` and enumerate `[[systems.codebase]]` entries using `cpt-cypilot-algo-map-scan-walker:p1` - `inst-scan-source-registry`
4. [x] - `p1` - **FOR EACH** codebase entry, walk source files matching declared extensions; parse each via `CodeFile.from_path`, building `CptUse` entries with `marker_kind` ∈ `{scope, block-begin, block-end}` - `inst-scan-source-parse`
5. [x] - `p1` - Skip directories in `DEFAULT_SKIP_DIRS` (.git, node_modules, .venv, __pycache__, .bootstrap, etc.) - `inst-scan-skip-dirs`
6. [x] - `p1` - **RETURN** combined list of markdown and source `Node` objects - `inst-scan-return`

### Categorize Nodes

- [x] `p1` - **ID**: `cpt-cypilot-flow-map-categorize`

**Input**: `List[Node]`, `CategorizeOptions(project_root, override, source_roots)`

**Output**: Nodes mutated in place with `.category` and `.category_origin` filled

**Steps**:
1. [x] - `p1` - Build registry index per source by reading `artifacts.toml` artifact and codebase path prefixes; sort longest-prefix first - `inst-cat-build-index`
2. [x] - `p1` - **FOR EACH** node, apply three-step priority chain using `cpt-cypilot-algo-map-categorize-chain:p1` - `inst-cat-foreach`
3. [x] - `p1` - Phantom nodes receive `category = "_undefined"` and `category_origin = "phantom"` unconditionally - `inst-cat-phantom`

### Build cpt Edges

- [x] `p1` - **ID**: `cpt-cypilot-flow-map-cpt-edges`

**Input**: `List[Node]`

**Output**: `(List[Edge], List[Node])` — resolved edges + phantom nodes for undefined cpt-IDs

**Steps**:
1. [x] - `p1` - Build `def_map` (phase-qualified id → markdown node) and `base_def_map` (base id → markdown node) from all markdown `cpt_defs` - `inst-cpt-edges-def-map`
2. [x] - `p1` - **FOR EACH** non-phantom node, iterate `cpt_uses` skipping `md-def` entries using `cpt-cypilot-algo-map-build-cpt-edges:p1` - `inst-cpt-edges-iter`
3. [x] - `p1` - Resolve use → target; if missing create phantom node; emit `cpt-doc` (md→md) or `cpt-impl` (src→md) edge; collapse multiple uses of same id from same source into one edge with multiple `Ref` entries - `inst-cpt-edges-resolve`
4. [x] - `p1` - Self-edges (definer uses own id) are dropped - `inst-cpt-edges-no-self`
5. [x] - `p1` - **RETURN** `(edges, phantom_node_list)` - `inst-cpt-edges-return`

### Extract File Links

- [x] `p1` - **ID**: `cpt-cypilot-flow-map-file-links`

**Input**: `List[Node]`, `project_root`

**Output**: `List[Edge]` — markdown→markdown `file-link` edges

**Steps**:
1. [x] - `p1` - Index all markdown nodes by `rel_path` - `inst-fl-index`
2. [x] - `p1` - **FOR EACH** markdown node, load file content from disk; scan for `[label](target)` patterns via regex - `inst-fl-scan-links`
3. [x] - `p1` - Resolve each target link using `cpt-cypilot-algo-map-resolve-link:p1`; skip external URLs, self-links, duplicates - `inst-fl-resolve`
4. [x] - `p1` - Emit `file-link` edge for each resolved target found in the known node index - `inst-fl-emit`
5. [x] - `p1` - **RETURN** list of file-link edges - `inst-fl-return`

### Enrich Edges

- [x] `p1` - **ID**: `cpt-cypilot-flow-map-enrich`

**Input**: `List[Edge]`, `List[Node]`, `project_root_by_source`

**Output**: Edges mutated in place with `ref.def_line` and `ref.def_snippet` filled

**Steps**:
1. [x] - `p1` - Skip `file-link` edges (no cpt-ID to look up) and dangling edges (phantom targets have no file) - `inst-enrich-skip`
2. [x] - `p1` - For each non-dangling cpt edge, resolve the target markdown file path from its source root - `inst-enrich-resolve-path`
3. [x] - `p1` - Call `get_content_scoped(path, id_value=base_id)` to retrieve the content block for the definition; strip phase suffix before matching - `inst-enrich-content-scoped`
4. [x] - `p1` - Scan for `**ID**: \`{base_id}\`` definition line via `scan_cpt_ids`; use as `def_line`; prepend to content block as `def_snippet` - `inst-enrich-def-line`
5. [x] - `p1` - Fallback: if `get_content_scoped` returns None, use 3 lines around the definition line as snippet - `inst-enrich-fallback`
6. [x] - `p1` - Replace each edge's `refs` list with enriched `Ref` objects carrying `def_line`/`def_snippet` - `inst-enrich-mutate`

### Compute Layout

- [x] `p1` - **ID**: `cpt-cypilot-flow-map-layout`

**Input**: `List[Node]`, `List[Edge]`, `category_style`, `verbose`

**Output**: `(vis_nodes, bucket_rects, category_bands)` dicts shaped for vis-network

**Steps**:
1. [x] - `p1` - Compute node degree map from edges (used for vis-network `mass` field) - `inst-layout-degrees`
2. [x] - `p1` - Group nodes by `.category`; compute per-category dimensions via `_dims(n, total)` targeting roughly-square grid - `inst-layout-group`
3. [x] - `p1` - Generate rectpack layout candidates per category via `rectpack.generate_layout_candidates` trying `MaxRectsBssf`, `MaxRectsBaf`, `MaxRectsBl`, `MaxRectsBlsf` - `inst-layout-candidates`
4. [x] - `p1` - Optimize stacked category arrangement via `rectpack.optimize_stacked_categories`; try rectpack repack and affinity-ordered row-packs; keep arrangement with best score (density + aspect error + affinity) - `inst-layout-optimize`
5. [x] - `p1` - Build vis-network node dicts (`id`, `label`, `x`, `y`, `shape`, `color`, `mass`, `category`, `group`); phantom nodes rendered as red diamonds - `inst-layout-vis-nodes`
6. [x] - `p1` - Build `bucket_rects` (one per category) and `category_bands` (with fill/stroke derived from sha256-hashed hue) - `inst-layout-rects`
7. [x] - `p1` - **RETURN** `(vis_nodes, bucket_rects, category_bands)` - `inst-layout-return`

### Render JSON Output

- [x] `p1` - **ID**: `cpt-cypilot-flow-map-render-json`

**Input**: `RenderJsonInput(nodes, edges, workspace, scan, vis_nodes, bucket_rects, category_bands)`

**Output**: JSON string

**Steps**:
1. [x] - `p1` - Sort nodes and edges by id for deterministic output - `inst-rjson-sort`
2. [x] - `p1` - Build `dangling_cpt_uses` section: one entry per dangling ref with `{cpt_id, node_id, line, snippet}` - `inst-rjson-dangling`
3. [x] - `p1` - Build `categories` section: per-category `{node_count, origin_counts, style}` with deterministic hsl color from sha256 - `inst-rjson-categories`
4. [x] - `p1` - Assemble top-level payload: `version`, `generated_at`, `workspace`, `scan`, `nodes`, `edges`, `dangling_cpt_uses`, `categories`, `layout` - `inst-rjson-assemble`
5. [x] - `p1` - **RETURN** `json.dumps(payload, indent=2, ensure_ascii=False)` - `inst-rjson-return`

### Render HTML Output

- [x] `p1` - **ID**: `cpt-cypilot-flow-map-render-html`

**Input**: `RenderHtmlInput(json_payload, inline_data, sidecar_basename)`

**Output**: `(html_text, sidecar_js_or_None)`

**Steps**:
1. [x] - `p1` - Load `viewer.js` and `viewer.css` from the bundled `assets/` directory - `inst-rhtml-load-assets`
2. [x] - `p1` - **IF** `inline_data`: embed JSON as `window.MAP_DATA = {...}` script tag; sidecar is None - `inst-rhtml-inline`
3. [x] - `p1` - **ELSE**: emit `<script src="{sidecar_basename}">` reference; produce sidecar content `window.MAP_DATA = ...` - `inst-rhtml-sidecar`
4. [x] - `p1` - Render HTML template with vis-network CDN script, embedded CSS, data script, and viewer JS - `inst-rhtml-template`
5. [x] - `p1` - **RETURN** `(html, sidecar_js)` - `inst-rhtml-return`

### Define Graph Data Model

- [x] `p1` - **ID**: `cpt-cypilot-flow-map-data-model`

**Input**: None (module-level definitions)

**Output**: `Node`, `Edge`, `Ref`, `CptUse` dataclasses; `node_id`, `phantom_id` helper functions; type aliases `NodeKind`, `EdgeType`, `CategoryOrigin`, `MarkerKind`

**Entities**:
- `CptUse(cpt_id, line, snippet, marker_kind)` — one use site of a cpt-ID in a file; `marker_kind` ∈ `{scope, block-begin, block-end, md-ref, md-def}`
- `Ref(cpt_id, line, snippet, def_line, def_snippet)` — one cross-reference carried on an edge, enriched with definition location
- `Node(id, rel_path, source, kind, language, category, category_origin, content, loc, cpt_defs, cpt_uses)` — represents a file or a phantom cpt-ID in the graph; `kind` ∈ `{markdown, source, phantom-cpt}`
- `Edge(id, from_id, to_id, type, refs, cross_repo, dangling)` — directed edge; `type` ∈ `{file-link, cpt-doc, cpt-impl}`
- `node_id(source, rel_path) → str` — canonical node id `"<source>:<rel-path>"`
- `phantom_id(cpt_id) → str` — canonical phantom id `"phantom:<cpt_id>"`

## 3b. Supporting Algorithms (CDSL)

### Walker Algorithm

- [x] `p1` - **ID**: `cpt-cypilot-algo-map-scan-walker`

**Input**: `root: Path`, `source_name: str`, `skip_dirs: Set[str]`, `ext_set: Set[str]`

**Output**: Yields `Node` objects for markdown and source files

**Steps**:
1. [x] - `p1` - For markdown: use `iter_text_files(root, includes=["*.md"])` and `iter_text_files(root, includes=["**/*.md"])`; union results; skip files whose parent directories are in `skip_dirs` - `inst-walker-md`
2. [x] - `p1` - For source: use `os.walk(cb_dir)`, pruning `skip_dirs` and hidden directories (`startswith(".")`) from `dirnames` in place - `inst-walker-src`
3. [x] - `p1` - Deduplicate source files across codebase entries using a `seen: Set[Path]` set - `inst-walker-dedup`

### Build cpt Edges Algorithm

- [x] `p1` - **ID**: `cpt-cypilot-algo-map-build-cpt-edges`

**Input**: `nodes: Sequence[Node]`, `def_map: Dict[str, Node]`, `base_def_map: Dict[str, Node]`

**Output**: Populates `edges` list and `phantoms` dict

**Steps**:
1. [x] - `p1` - Lookup order: `def_map[use.cpt_id]` (phase-qualified) → `base_def_map[base_id]` (base id fallback); no BFS traversal needed - `inst-build-cpt-lookup`
2. [x] - `p1` - Collapse: use `(src.id, to_id, use.cpt_id)` as key in `by_key` dict; append `Ref` to existing edge rather than creating new edge - `inst-build-cpt-collapse`
3. [x] - `p1` - Phantom creation: on cache miss, create `Node(kind="phantom-cpt", id=phantom_id(cpt_id))` once per unique cpt-id - `inst-build-cpt-phantom`

### Categorize Chain Algorithm

- [x] `p1` - **ID**: `cpt-cypilot-algo-map-categorize-chain`

**Input**: `node: Node`, `override: Optional[OverrideConfig]`, `registry_index: List[_RegistryEntry]`

**Output**: `(category: str, origin: CategoryOrigin)`

**Steps**:
1. [x] - `p1` - Step 1 — Override: iterate `override.categories`; match `node.rel_path` against each `pat` in `cat.paths` using gitignore-style glob (supports `**`/`*`/`?`) - `inst-chain-override`
2. [x] - `p1` - Step 2 — Registry: iterate `registry_index` longest-prefix-first; match `rel_path == prefix` or `rel_path.startswith(prefix + "/")` - `inst-chain-registry`
3. [x] - `p1` - Step 3 — Parent dir: use `rel_path.split("/")[-2]`; root-level files get `"_root"` - `inst-chain-parent-dir`

### Resolve Link Algorithm

- [x] `p1` - **ID**: `cpt-cypilot-algo-map-resolve-link`

**Input**: `source_rel: str`, `target: str`, `known: Set[str]`

**Output**: `Optional[str]` — resolved `rel_path` or None

**Steps**:
1. [x] - `p1` - Strip fragment (`#...`), query (`?...`); reject empty targets and external URLs (`http://`, `https://`, `mailto:`) - `inst-resolve-strip`
2. [x] - `p1` - **IF** absolute target (starts with `/`): strip leading slash; also try appending `.md` if not already `.md` - `inst-resolve-absolute`
3. [x] - `p1` - **ELSE** relative: join `source_dir + "/" + target`; normalize using posix-normpath (handles `..` and `.` segments); also try appending `.md` - `inst-resolve-relative`
4. [x] - `p1` - Return first candidate found in `known`; return None if no candidate matches - `inst-resolve-match`

## 4. States (CDSL)

### Map Generation Lifecycle

- [x] `p1` - **ID**: `cpt-cypilot-state-dependency-map`

**States**: NOT_STARTED, SCANNING, CATEGORIZING, RESOLVING, LAYING_OUT, RENDERING, DONE, FAILED

**Transitions**:
1. [x] - `p1` - **FROM** NOT_STARTED **TO** SCANNING **WHEN** CLI invoked with valid arguments - `inst-state-scan-start`
2. [x] - `p1` - **FROM** SCANNING **TO** CATEGORIZING **WHEN** all source nodes collected - `inst-state-cat-start`
3. [x] - `p1` - **FROM** CATEGORIZING **TO** RESOLVING **WHEN** all nodes have category and origin assigned - `inst-state-resolve-start`
4. [x] - `p1` - **FROM** RESOLVING **TO** LAYING_OUT **WHEN** all edges built and enriched - `inst-state-layout-start`
5. [x] - `p1` - **FROM** LAYING_OUT **TO** RENDERING **WHEN** vis-nodes and bucket rects computed - `inst-state-render-start`
6. [x] - `p1` - **FROM** RENDERING **TO** DONE **WHEN** output file(s) written successfully - `inst-state-done`
7. [x] - `p1` - **FROM** any **TO** FAILED **WHEN** unrecoverable error (invalid config, write failure) - `inst-state-failed`

## 5. Definitions of Done

### Node and Edge Graph

- [x] `p1` - **ID**: `cpt-cypilot-dod-dependency-mapping-graph`

The system **MUST** produce a graph where every scanned markdown file becomes a `markdown` node, every registered source file becomes a `source` node, every `@cpt-*` marker in source files produces a `cpt-impl` edge pointing to the defining markdown node, and every markdown cross-reference produces a `cpt-doc` edge. Markdown hyperlinks between markdown files produce `file-link` edges. Each node **MUST** carry `id`, `rel_path`, `source`, `kind`, `category`, `category_origin`, `loc`, `cpt_defs`, `cpt_uses`.

**Implements**:
- `cpt-cypilot-flow-map-scan:p1`
- `cpt-cypilot-flow-map-cpt-edges:p1`
- `cpt-cypilot-flow-map-file-links:p1`

**Covers (PRD)**:
- `cpt-cypilot-fr-core-dependency-mapping`
- `cpt-cypilot-fr-core-traceability`

**Covers (DESIGN)**:
- `cpt-cypilot-component-map-renderer`
- `cpt-cypilot-component-traceability-engine`

### Phantom Detection

- [x] `p1` - **ID**: `cpt-cypilot-dod-dependency-mapping-phantoms`

The system **MUST** detect every cpt-ID that is used in a `@cpt-*` source marker or markdown reference but has no matching definition in any scanned markdown file. Each such ID **MUST** produce a `phantom-cpt` node with `id = "phantom:{cpt_id}"` and appear in the `dangling_cpt_uses` section of the JSON output. The `dangling` flag on the edge **MUST** be `true`. Phantom count **MUST** be printed in the CLI summary.

**Implements**:
- `cpt-cypilot-algo-map-build-cpt-edges:p1`
- `cpt-cypilot-flow-map-render-json:p1`

**Covers (PRD)**:
- `cpt-cypilot-fr-core-dependency-mapping`

**Covers (DESIGN)**:
- `cpt-cypilot-component-map-renderer`

### HTML Output

- [x] `p1` - **ID**: `cpt-cypilot-dod-dependency-mapping-html`

The system **MUST** produce a self-contained HTML file (or HTML + JS sidecar) that embeds the vis-network library via CDN, the bundled viewer JS and CSS, and the JSON payload (either inline or via sidecar). The viewer **MUST** support node-kind filters, edge-type toggling, and category-band visualization. Output **MUST** be written to `md-map.html` by default (configurable via `--out`).

**Implements**:
- `cpt-cypilot-flow-map-render-html:p1`
- `cpt-cypilot-flow-map-layout:p1`

**Covers (PRD)**:
- `cpt-cypilot-fr-core-dependency-mapping`

**Covers (DESIGN)**:
- `cpt-cypilot-component-map-renderer`

## 6. Implementation Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| Map CLI | `skills/.../commands/map/cli.py` | Argument parsing, source discovery, orchestration, summary output |
| Data Model | `skills/.../commands/map/model.py` | `Node`, `Edge`, `Ref`, `CptUse` dataclasses; `node_id`, `phantom_id` helpers |
| Scanner | `skills/.../commands/map/scan.py` | Markdown and source file walking; cpt-ID extraction via `scan_cpt_ids` and `CodeFile` |
| Categorizer | `skills/.../commands/map/categorize.py` | Three-step category resolution: override → registry → parent-dir |
| cpt Edge Builder | `skills/.../commands/map/cpt_edges.py` | `cpt-doc`/`cpt-impl` edge construction; phantom node creation |
| File Link Extractor | `skills/.../commands/map/links.py` | Markdown hyperlink scanning; relative-path resolution |
| Edge Enricher | `skills/.../commands/map/enrich.py` | Per-edge content baking via `get_content_scoped` |
| Layout Engine | `skills/.../commands/map/layout.py` | Rectpack-based category layout; vis-network node coordinate assignment |
| JSON Renderer | `skills/.../commands/map/render_json.py` | Canonical JSON serialization with dangling and categories sections |
| HTML Renderer | `skills/.../commands/map/render_html.py` | Self-contained HTML assembly from assets + JSON payload |

## 7. Acceptance Criteria

- [x] `cfc map` produces `md-map.html` containing a vis-network graph of the project
- [x] `cfc map --format json` produces valid JSON with `nodes`, `edges`, `dangling_cpt_uses`, `categories`, `layout` keys
- [x] Every `@cpt-flow` / `@cpt-algo` scope marker in source files produces a `cpt-impl` edge to the defining markdown node
- [x] Every markdown cross-reference to a defined cpt-ID produces a `cpt-doc` edge
- [x] cpt-IDs used in source but undefined in any markdown produce `phantom-cpt` nodes with `dangling=true` edges
- [x] Phantom count is printed in CLI summary as "Phantom IDs: N dangling cpt uses"
- [x] Categories are assigned via override → registry → parent-dir priority chain
- [x] `--no-source` omits source nodes and `cpt-impl` edges
- [x] `--local-only` disables workspace federation; only local source is scanned
- [x] `--inline-data` produces HTML with `window.MAP_DATA` embedded; no sidecar `.js` file
- [x] Layout produces deterministic output for same repo state (sorted by node id)
- [x] Map generation completes in ≤ 30 seconds for typical repositories
- [x] All 14 `cpt-cypilot-flow-map-*` / `cpt-cypilot-algo-map-*` IDs resolve to definitions in this file (no phantoms)
