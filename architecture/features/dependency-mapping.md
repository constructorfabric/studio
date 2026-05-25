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
  - [Build cfs Edges](#build-cfs-edges)
  - [Extract File Links](#extract-file-links)
  - [Enrich Edges](#enrich-edges)
  - [Compute Layout](#compute-layout)
  - [Render JSON Output](#render-json-output)
  - [Render HTML Output](#render-html-output)
  - [Define Graph Data Model](#define-graph-data-model)
  - [Walker Algorithm](#walker-algorithm)
  - [Build cfs Edges Algorithm](#build-cfs-edges-algorithm)
  - [Categorize Chain Algorithm](#categorize-chain-algorithm)
  - [Resolve Link Algorithm](#resolve-link-algorithm)
- [4. States (CDSL)](#4-states-cdsl)
  - [Map Generation Lifecycle](#map-generation-lifecycle)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Node and Edge Graph](#node-and-edge-graph)
  - [Phantom Detection](#phantom-detection)
  - [HTML Output](#html-output)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [x] `p1` - **ID**: `cpt-studio-featstatus-dependency-mapping`

## 1. Feature Context

- [x] `p1` - `cpt-studio-feature-dependency-mapping`

### 1. Overview

Produces an interactive graph map of a project's markdown and source files, connected by cpt-identifier edges (`cpt-doc`, `cpt-impl`) and markdown hyperlink edges (`file-link`). Invoked as `cfs map` (or `cfs map`), the command walks the project root, scans every markdown file for cpt-ID definitions and cross-references, scans registered source files for `@cpt-*` scope and block markers, resolves markdown hyperlinks, and emits either a self-contained HTML viewer or a canonical JSON payload. cpt-IDs that are referenced in code but defined nowhere become `phantom-cpt` nodes rendered as warning diamonds, enabling reverse-engineering workflows.

### 2. Purpose

Without a dependency map, navigating large projects requires manual inspection of individual files to understand how specs relate to code. The map command provides an at-a-glance interactive visualization of the entire architecture graph — which markdown specs link to which source files through traceability markers, which source files reference undefined specs (phantoms), and how categories cluster on a rectpack layout. It is the primary audit surface for `cfs validate`-flagged phantom IDs.

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Invokes `cfs map` to generate the project dependency map |
| `cpt-studio-actor-ai-agent` | Uses the JSON output to understand project structure for spec reverse-engineering |
| `cpt-studio-actor-ci-pipeline` | Runs `cfs map --format json` as part of CI artifact generation |

### 4. References

- **PRD**: [PRD.md](../PRD.md) — `cpt-studio-fr-core-dependency-mapping`, `cpt-studio-fr-core-traceability`
- **Design**: [DESIGN.md](../DESIGN.md) — `cpt-studio-component-map-renderer`, `cpt-studio-component-traceability-engine`
- **Dependencies**: `cpt-studio-feature-traceability-validation`, `cpt-studio-feature-workspace`

## 2. Actor Flows (CDSL)

### Run Dependency Map

- [x] `p1` - **ID**: `cpt-studio-flow-map-cli`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs map` → HTML map written to `md-map.html` with all nodes, edges, and layout
- User runs `cfs map --format json --out /tmp/map.json` → canonical JSON written to specified path
- User runs `cfs map --no-source` → markdown-only scan; source nodes and cpt-impl edges omitted
- User runs `cfs map --local-only` → workspace federation skipped; only local source scanned
- User runs `cfs map --inline-data` → HTML produced with data embedded inline (no sidecar `.js` file)

**Error Scenarios**:
- No `artifacts.toml` at project root → stderr warning emitted; source scanning disabled; markdown scan continues
- Invalid `md-map.toml` override config → error printed, exit code 2

**Steps**:
1. [x] - `p1` - User invokes `cfs map [--out PATH] [--format html|json] [--config FILE] [--no-source] [--local-only] [--inline-data] [--verbose]`
2. [x] - `p1` - Discover workspace sources via `find_workspace_config`; include local source always
3. [x] - `p1` - Load optional category override from `md-map.toml` or `--config` path
4. [x] - `p1` - **FOR EACH** reachable source, invoke `scan_repo` using `cpt-studio-algo-map-scan:p1`
5. [x] - `p1` - Categorize all nodes using `cpt-studio-algo-map-categorize:p1`
6. [x] - `p1` - Extract file-link edges using `cpt-studio-algo-map-file-links:p1`
7. [x] - `p1` - Build cfs edges and phantom nodes using `cpt-studio-algo-map-cpt-edges:p1`
8. [x] - `p1` - Enrich edges with definition context using `cpt-studio-algo-map-enrich:p1`
9. [x] - `p1` - Compute layout using `cpt-studio-algo-map-layout:p1`
10. [x] - `p1` - Serialize to JSON using `cpt-studio-algo-map-render-json:p1`
11. [x] - `p1` - **IF** format is html, render HTML using `cpt-studio-algo-map-render-html:p1`; else write JSON directly
12. [x] - `p1` - Print summary: node counts, edge counts, phantom count, output path
## 3. Processes / Business Logic (CDSL)

### Scan Project Files

- [x] `p1` - **ID**: `cpt-studio-algo-map-scan`

**Input**: `ScanOptions(project_root, source_name, no_source, extra_skip_dirs)`

**Output**: `List[Node]` — flat list of markdown and source nodes

**Steps**:
1. [x] - `p1` - Walk all `.md` files under project root (both root-level and recursive) using `cpt-studio-algo-map-scan-walker:p1`
2. [x] - `p1` - **FOR EACH** markdown file, call `scan_cpt_ids` to extract definitions and references; build `CptUse` entries with `marker_kind` ∈ `{md-def, md-ref}`
3. [x] - `p1` - **IF** `no_source` is False, load `artifacts.toml` and enumerate `[[systems.codebase]]` entries using `cpt-studio-algo-map-scan-walker:p1`
4. [x] - `p1` - **FOR EACH** codebase entry, walk source files matching declared extensions; parse each via `CodeFile.from_path`, building `CptUse` entries with `marker_kind` ∈ `{scope, block-begin, block-end}`
5. [x] - `p1` - Skip directories in `DEFAULT_SKIP_DIRS` (.git, node_modules, .venv, __pycache__, .bootstrap, etc.)
6. [x] - `p1` - **RETURN** combined list of markdown and source `Node` objects
### Categorize Nodes

- [x] `p1` - **ID**: `cpt-studio-algo-map-categorize`

**Input**: `List[Node]`, `CategorizeOptions(project_root, override, source_roots)`

**Output**: Nodes mutated in place with `.category` and `.category_origin` filled

**Steps**:
1. [x] - `p1` - Build registry index per source by reading `artifacts.toml` artifact and codebase path prefixes; sort longest-prefix first
2. [x] - `p1` - **FOR EACH** node, apply three-step priority chain using `cpt-studio-algo-map-categorize-chain:p1`
3. [x] - `p1` - Phantom nodes receive `category = "_undefined"` and `category_origin = "phantom"` unconditionally
### Build cfs Edges

- [x] `p1` - **ID**: `cpt-studio-algo-map-cpt-edges`

**Input**: `List[Node]`

**Output**: `(List[Edge], List[Node])` — resolved edges + phantom nodes for undefined cpt-IDs

**Steps**:
1. [x] - `p1` - Build `def_map` (phase-qualified id → markdown node) and `base_def_map` (base id → markdown node) from all markdown `cpt_defs`
2. [x] - `p1` - **FOR EACH** non-phantom node, iterate `cpt_uses` skipping `md-def` entries using `cpt-studio-algo-map-build-cpt-edges:p1`
3. [x] - `p1` - Resolve use → target; if missing create phantom node; emit `cpt-doc` (md→md) or `cpt-impl` (src→md) edge; collapse multiple uses of same id from same source into one edge with multiple `Ref` entries
4. [x] - `p1` - Self-edges (definer uses own id) are dropped
5. [x] - `p1` - **RETURN** `(edges, phantom_node_list)`
### Extract File Links

- [x] `p1` - **ID**: `cpt-studio-algo-map-file-links`

**Input**: `List[Node]`, `project_root`

**Output**: `List[Edge]` — markdown→markdown `file-link` edges

**Steps**:
1. [x] - `p1` - Index all markdown nodes by `rel_path`
2. [x] - `p1` - **FOR EACH** markdown node, load file content from disk; scan for `[label](target)` patterns via regex
3. [x] - `p1` - Resolve each target link using `cpt-studio-algo-map-resolve-link:p1`; skip external URLs, self-links, duplicates
4. [x] - `p1` - Emit `file-link` edge for each resolved target found in the known node index
5. [x] - `p1` - **RETURN** list of file-link edges
### Enrich Edges

- [x] `p1` - **ID**: `cpt-studio-algo-map-enrich`

**Input**: `List[Edge]`, `List[Node]`, `project_root_by_source`

**Output**: Edges mutated in place with `ref.def_line` and `ref.def_snippet` filled

**Steps**:
1. [x] - `p1` - Skip `file-link` edges (no cpt-ID to look up) and dangling edges (phantom targets have no file)
2. [x] - `p1` - For each non-dangling cfs edge, resolve the target markdown file path from its source root
3. [x] - `p1` - Call `get_content_scoped(path, id_value=base_id)` to retrieve the content block for the definition; strip phase suffix before matching
4. [x] - `p1` - Scan for `**ID**: \`{base_id}\`` definition line via `scan_cpt_ids`; use as `def_line`; prepend to content block as `def_snippet`
5. [x] - `p1` - Fallback: if `get_content_scoped` returns None, use 3 lines around the definition line as snippet
6. [x] - `p1` - Replace each edge's `refs` list with enriched `Ref` objects carrying `def_line`/`def_snippet`
### Compute Layout

- [x] `p1` - **ID**: `cpt-studio-algo-map-layout`

**Input**: `List[Node]`, `List[Edge]`, `category_style`, `verbose`

**Output**: `(vis_nodes, bucket_rects, category_bands)` dicts shaped for vis-network

**Steps**:
1. [x] - `p1` - Compute node degree map from edges (used for vis-network `mass` field)
2. [x] - `p1` - Group nodes by `.category`; compute per-category dimensions via `_dims(n, total)` targeting roughly-square grid
3. [x] - `p1` - Generate rectpack layout candidates per category via `rectpack.generate_layout_candidates` trying `MaxRectsBssf`, `MaxRectsBaf`, `MaxRectsBl`, `MaxRectsBlsf`
4. [x] - `p1` - Optimize stacked category arrangement via `rectpack.optimize_stacked_categories`; try rectpack repack and affinity-ordered row-packs; keep arrangement with best score (density + aspect error + affinity)
5. [x] - `p1` - Build vis-network node dicts (`id`, `label`, `x`, `y`, `shape`, `color`, `mass`, `category`, `group`); phantom nodes rendered as red diamonds
6. [x] - `p1` - Build `bucket_rects` (one per category) and `category_bands` (with fill/stroke derived from sha256-hashed hue)
7. [x] - `p1` - **RETURN** `(vis_nodes, bucket_rects, category_bands)`
### Render JSON Output

- [x] `p1` - **ID**: `cpt-studio-algo-map-render-json`

**Input**: `RenderJsonInput(nodes, edges, workspace, scan, vis_nodes, bucket_rects, category_bands)`

**Output**: JSON string

**Steps**:
1. [x] - `p1` - Sort nodes and edges by id for deterministic output
2. [x] - `p1` - Build `dangling_cpt_uses` section: one entry per dangling ref with `{cpt_id, node_id, line, snippet}`
3. [x] - `p1` - Build `categories` section: per-category `{node_count, origin_counts, style}` with deterministic hsl color from sha256
4. [x] - `p1` - Assemble top-level payload: `version`, `generated_at`, `workspace`, `scan`, `nodes`, `edges`, `dangling_cpt_uses`, `categories`, `layout`
5. [x] - `p1` - **RETURN** `json.dumps(payload, indent=2, ensure_ascii=False)`
### Render HTML Output

- [x] `p1` - **ID**: `cpt-studio-algo-map-render-html`

**Input**: `RenderHtmlInput(json_payload, inline_data, sidecar_basename)`

**Output**: `(html_text, sidecar_js_or_None)`

**Steps**:
1. [x] - `p1` - Load `viewer.js` and `viewer.css` from the bundled `assets/` directory
2. [x] - `p1` - **IF** `inline_data`: embed JSON as `window.MAP_DATA = {...}` script tag; sidecar is None
3. [x] - `p1` - **ELSE**: emit `<script src="{sidecar_basename}">` reference; produce sidecar content `window.MAP_DATA = ...`
4. [x] - `p1` - Render HTML template with vis-network CDN script, embedded CSS, data script, and viewer JS
5. [x] - `p1` - **RETURN** `(html, sidecar_js)`
### Define Graph Data Model

- [x] `p1` - **ID**: `cpt-studio-algo-map-data-model`

**Input**: None (module-level definitions)

**Output**: `Node`, `Edge`, `Ref`, `CptUse` dataclasses; `node_id`, `phantom_id` helper functions; type aliases `NodeKind`, `EdgeType`, `CategoryOrigin`, `MarkerKind`

**Entities**:
- `CptUse(cpt_id, line, snippet, marker_kind)` — one use site of a cpt-ID in a file; `marker_kind` ∈ `{scope, block-begin, block-end, md-ref, md-def}`
- `Ref(cpt_id, line, snippet, def_line, def_snippet)` — one cross-reference carried on an edge, enriched with definition location
- `Node(id, rel_path, source, kind, language, category, category_origin, content, loc, cpt_defs, cpt_uses)` — represents a file or a phantom cpt-ID in the graph; `kind` ∈ `{markdown, source, phantom-cpt}`
- `Edge(id, from_id, to_id, type, refs, cross_repo, dangling)` — directed edge; `type` ∈ `{file-link, cpt-doc, cpt-impl}`
- `node_id(source, rel_path) → str` — canonical node id `"<source>:<rel-path>"`
- `phantom_id(cpt_id) → str` — canonical phantom id `"phantom:<cpt_id>"`

### Walker Algorithm

- [x] `p1` - **ID**: `cpt-studio-algo-map-scan-walker`

**Input**: `root: Path`, `source_name: str`, `skip_dirs: Set[str]`, `ext_set: Set[str]`

**Output**: Yields `Node` objects for markdown and source files

**Steps**:
1. [x] - `p1` - For markdown: use `iter_text_files(root, includes=["*.md"])` and `iter_text_files(root, includes=["**/*.md"])`; union results; skip files whose parent directories are in `skip_dirs`
2. [x] - `p1` - For source: use `os.walk(cb_dir)`, pruning `skip_dirs` and hidden directories (`startswith(".")`) from `dirnames` in place
3. [x] - `p1` - Deduplicate source files across codebase entries using a `seen: Set[Path]` set
### Build cfs Edges Algorithm

- [x] `p1` - **ID**: `cpt-studio-algo-map-build-cpt-edges`

**Input**: `nodes: Sequence[Node]`, `def_map: Dict[str, Node]`, `base_def_map: Dict[str, Node]`

**Output**: Populates `edges` list and `phantoms` dict

**Steps**:
1. [x] - `p1` - Lookup order: `def_map[use.cpt_id]` (phase-qualified) → `base_def_map[base_id]` (base id fallback); no BFS traversal needed
2. [x] - `p1` - Collapse: use `(src.id, to_id, use.cpt_id)` as key in `by_key` dict; append `Ref` to existing edge rather than creating new edge
3. [x] - `p1` - Phantom creation: on cache miss, create `Node(kind="phantom-cpt", id=phantom_id(cpt_id))` once per unique cpt-id
### Categorize Chain Algorithm

- [x] `p1` - **ID**: `cpt-studio-algo-map-categorize-chain`

**Input**: `node: Node`, `override: Optional[OverrideConfig]`, `registry_index: List[_RegistryEntry]`

**Output**: `(category: str, origin: CategoryOrigin)`

**Steps**:
1. [x] - `p1` - Step 1 — Override: iterate `override.categories`; match `node.rel_path` against each `pat` in `cat.paths` using gitignore-style glob (supports `**`/`*`/`?`)
2. [x] - `p1` - Step 2 — Registry: iterate `registry_index` longest-prefix-first; match `rel_path == prefix` or `rel_path.startswith(prefix + "/")`
3. [x] - `p1` - Step 3 — Parent dir: use `rel_path.split("/")[-2]`; root-level files get `"_root"`
### Resolve Link Algorithm

- [x] `p1` - **ID**: `cpt-studio-algo-map-resolve-link`

**Input**: `source_rel: str`, `target: str`, `known: Set[str]`

**Output**: `Optional[str]` — resolved `rel_path` or None

**Steps**:
1. [x] - `p1` - Strip fragment (`#...`), query (`?...`); reject empty targets and external URLs (`http://`, `https://`, `mailto:`)
2. [x] - `p1` - **IF** absolute target (starts with `/`): strip leading slash; also try appending `.md` if not already `.md`
3. [x] - `p1` - **ELSE** relative: join `source_dir + "/" + target`; normalize using posix-normpath (handles `..` and `.` segments); also try appending `.md`
4. [x] - `p1` - Return first candidate found in `known`; return None if no candidate matches
## 4. States (CDSL)

### Map Generation Lifecycle

- [x] `p1` - **ID**: `cpt-studio-state-dependency-map`

**States**: NOT_STARTED, SCANNING, CATEGORIZING, RESOLVING, LAYING_OUT, RENDERING, DONE, FAILED

**Transitions**:
1. [x] - `p1` - **FROM** NOT_STARTED **TO** SCANNING **WHEN** CLI invoked with valid arguments
2. [x] - `p1` - **FROM** SCANNING **TO** CATEGORIZING **WHEN** all source nodes collected
3. [x] - `p1` - **FROM** CATEGORIZING **TO** RESOLVING **WHEN** all nodes have category and origin assigned
4. [x] - `p1` - **FROM** RESOLVING **TO** LAYING_OUT **WHEN** all edges built and enriched
5. [x] - `p1` - **FROM** LAYING_OUT **TO** RENDERING **WHEN** vis-nodes and bucket rects computed
6. [x] - `p1` - **FROM** RENDERING **TO** DONE **WHEN** output file(s) written successfully
7. [x] - `p1` - **FROM** any **TO** FAILED **WHEN** unrecoverable error (invalid config, write failure)
## 5. Definitions of Done

### Node and Edge Graph

- [x] `p1` - **ID**: `cpt-studio-dod-dependency-mapping-graph`

The system **MUST** produce a graph where every scanned markdown file becomes a `markdown` node, every registered source file becomes a `source` node, every `@cpt-*` marker in source files produces a `cpt-impl` edge pointing to the defining markdown node, and every markdown cross-reference produces a `cpt-doc` edge. Markdown hyperlinks between markdown files produce `file-link` edges. Each node **MUST** carry `id`, `rel_path`, `source`, `kind`, `category`, `category_origin`, `loc`, `cpt_defs`, `cpt_uses`.

**Implements**:
- `cpt-studio-algo-map-scan:p1`
- `cpt-studio-algo-map-cpt-edges:p1`
- `cpt-studio-algo-map-file-links:p1`

**Covers (PRD)**:
- `cpt-studio-fr-core-dependency-mapping`
- `cpt-studio-fr-core-traceability`

**Covers (DESIGN)**:
- `cpt-studio-component-map-renderer`
- `cpt-studio-component-traceability-engine`

### Phantom Detection

- [x] `p1` - **ID**: `cpt-studio-dod-dependency-mapping-phantoms`

The system **MUST** detect every cpt-ID that is used in a `@cpt-*` source marker or markdown reference but has no matching definition in any scanned markdown file. Each such ID **MUST** produce a `phantom-cpt` node with `id = "phantom:{cpt_id}"` and appear in the `dangling_cpt_uses` section of the JSON output. The `dangling` flag on the edge **MUST** be `true`. Phantom count **MUST** be printed in the CLI summary.

**Implements**:
- `cpt-studio-algo-map-build-cpt-edges:p1`
- `cpt-studio-algo-map-render-json:p1`

**Covers (PRD)**:
- `cpt-studio-fr-core-dependency-mapping`

**Covers (DESIGN)**:
- `cpt-studio-component-map-renderer`

### HTML Output

- [x] `p1` - **ID**: `cpt-studio-dod-dependency-mapping-html`

The system **MUST** produce a self-contained HTML file (or HTML + JS sidecar) that embeds the vis-network library via CDN, the bundled viewer JS and CSS, and the JSON payload (either inline or via sidecar). The viewer **MUST** support node-kind filters, edge-type toggling, and category-band visualization. Output **MUST** be written to `md-map.html` by default (configurable via `--out`).

**Implements**:
- `cpt-studio-algo-map-render-html:p1`
- `cpt-studio-algo-map-layout:p1`

**Covers (PRD)**:
- `cpt-studio-fr-core-dependency-mapping`

**Covers (DESIGN)**:
- `cpt-studio-component-map-renderer`

## 6. Implementation Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| Map CLI | `skills/.../commands/map/cli.py` | Argument parsing, source discovery, orchestration, summary output |
| Data Model | `skills/.../commands/map/model.py` | `Node`, `Edge`, `Ref`, `CptUse` dataclasses; `node_id`, `phantom_id` helpers |
| Scanner | `skills/.../commands/map/scan.py` | Markdown and source file walking; cpt-ID extraction via `scan_cpt_ids` and `CodeFile` |
| Categorizer | `skills/.../commands/map/categorize.py` | Three-step category resolution: override → registry → parent-dir |
| cfs Edge Builder | `skills/.../commands/map/cpt_edges.py` | `cpt-doc`/`cpt-impl` edge construction; phantom node creation |
| File Link Extractor | `skills/.../commands/map/links.py` | Markdown hyperlink scanning; relative-path resolution |
| Edge Enricher | `skills/.../commands/map/enrich.py` | Per-edge content baking via `get_content_scoped` |
| Layout Engine | `skills/.../commands/map/layout.py` | Rectpack-based category layout; vis-network node coordinate assignment |
| JSON Renderer | `skills/.../commands/map/render_json.py` | Canonical JSON serialization with dangling and categories sections |
| HTML Renderer | `skills/.../commands/map/render_html.py` | Self-contained HTML assembly from assets + JSON payload |

## 7. Acceptance Criteria

- [x] `cfs map` produces `md-map.html` containing a vis-network graph of the project
- [x] `cfs map --format json` produces valid JSON with `nodes`, `edges`, `dangling_cpt_uses`, `categories`, `layout` keys
- [x] Every `@cpt-flow` / `@cpt-algo` scope marker in source files produces a `cpt-impl` edge to the defining markdown node
- [x] Every markdown cross-reference to a defined cpt-ID produces a `cpt-doc` edge
- [x] cpt-IDs used in source but undefined in any markdown produce `phantom-cpt` nodes with `dangling=true` edges
- [x] Phantom count is printed in CLI summary as "Phantom IDs: N dangling cfs uses"
- [x] Categories are assigned via override → registry → parent-dir priority chain
- [x] `--no-source` omits source nodes and `cpt-impl` edges
- [x] `--local-only` disables workspace federation; only local source is scanned
- [x] `--inline-data` produces HTML with `window.MAP_DATA` embedded; no sidecar `.js` file
- [x] Layout produces deterministic output for same repo state (sorted by node id)
- [x] Map generation completes in ≤ 30 seconds for typical repositories
- [x] All 14 `cpt-studio-flow-map-*` / `cpt-studio-algo-map-*` IDs resolve to definitions in this file (no phantoms)
