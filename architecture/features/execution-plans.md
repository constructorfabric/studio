# Feature: Execution Plans


<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1.1 Overview](#11-overview)
  - [1.2 Purpose](#12-purpose)
  - [1.3 Actors](#13-actors)
  - [1.4 References](#14-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Generate Execution Plan](#generate-execution-plan)
  - [Chunk Raw Input Package](#chunk-raw-input-package)
  - [Execute Phase](#execute-phase)
  - [Check Plan Status](#check-plan-status)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Decompose Task](#decompose-task)
  - [Compile Phase File](#compile-phase-file)
  - [Enforce Line Budget](#enforce-line-budget)
  - [Normalize Raw Input Sources](#normalize-raw-input-sources)
  - [Compute Raw Input Chunk Ranges](#compute-raw-input-chunk-ranges)
  - [Write Raw Input Package](#write-raw-input-package)
  - [Resolve a Decision From the Plan](#resolve-a-decision-from-the-plan)
  - [Enumerate Deliverable Items From a Plan](#enumerate-deliverable-items-from-a-plan)
  - [Read a Run's Outstanding Open Questions](#read-a-runs-outstanding-open-questions)
  - [Verify a Run Against Its Plan Before Completion](#verify-a-run-against-its-plan-before-completion)
- [4. States (CDSL)](#4-states-cdsl)
  - [Raw Input Package Lifecycle](#raw-input-package-lifecycle)
  - [Plan Lifecycle](#plan-lifecycle)
  - [Phase Lifecycle](#phase-lifecycle)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Raw Input Package](#raw-input-package)
  - [Plan Workflow](#plan-workflow)
  - [Phase File Template](#phase-file-template)
  - [Decomposition Strategies](#decomposition-strategies)
  - [Plan Storage](#plan-storage)
  - [Plan Export Contract](#plan-export-contract)
- [6. Acceptance Criteria](#6-acceptance-criteria)

<!-- /toc -->

- [ ] `p1` - **ID**: `cpt-studio-featstatus-execution-plans`
## 1. Feature Context

- [ ] `p1` - `cpt-studio-feature-execution-plans`

### 1.1 Overview

Execution Plans decompose large agent tasks (artifact generation, validation, code implementation) into self-contained phase files that fit within a single LLM context window. Each phase file is a compiled prompt — all rules, constraints, conventions, and context are pre-resolved and inlined so that any AI agent can execute it without Studio knowledge. Accepted delegated execution extends this model by allowing plan outputs to be exported into executor-specific grammars — beginning with ralphex Markdown plans under `docs/plans/` — while Studio remains authoritative for decomposition, phase compilation, and deterministic validation commands (see `cpt-studio-adr-ralphex-delegation-skill`).

### 1.2 Purpose

Context window overflow is the primary source of non-deterministic results in Studio workflows. A single generate or analyze invocation can load 3000+ lines of instructions (SKILL.md + protocol.md + workflow + rules + template + checklist + example + constraints + project context) before the agent writes any output. This causes:

- **Attention drift**: different parts of instructions "win" attention on each run, producing inconsistent results
- **Partial completion**: agent runs out of context mid-task, requiring manual re-scoping
- **Manual decomposition**: users must figure out how to break tasks into manageable pieces

Execution Plans solve this by moving decomposition from the user to the tool. The plan workflow reads all relevant sources once, decomposes the task into phases, and "compiles" each phase into a focused instruction file (≤500 lines target, ≤1000 max) containing only what's needed for that specific sub-task.

**Requirements**: `cpt-studio-fr-core-workflows`, `cpt-studio-fr-core-execution-plans`

**Principles**: `cpt-studio-principle-determinism-first`, `cpt-studio-principle-occams-razor`

### 1.3 Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Invokes plan workflow, reviews generated phases, triggers phase execution, checks plan progress |
| `cpt-studio-actor-ai-agent` | Generates execution plans, compiles phase files, executes individual phases |

### 1.4 References

- **PRD**: [PRD.md](../PRD.md) — `cpt-studio-fr-core-workflows`, `cpt-studio-fr-core-execution-plans`
- **Design**: [DESIGN.md](../DESIGN.md) — `cpt-studio-component-agent-generator`
- **ADRs**: [ADR-0018](../ADR/0018-cpt-studio-adr-ralphex-delegation-skill-v1.md) — `cpt-studio-adr-ralphex-delegation-skill` (plan export contract)
- **Dependencies**: `cpt-studio-feature-agent-integration` (builds on generate/analyze workflows)

## 2. Actor Flows (CDSL)

### Generate Execution Plan

- [x] `p1` - **ID**: `cpt-studio-flow-execution-plans-generate-plan`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User requests a large task → agent produces a plan manifest + phase files in `.plans/` directory
- User requests plan for specific artifact → agent decomposes by template sections

**Error Scenarios**:
- Task is small enough for single context → agent skips plan, executes directly via generate/analyze
- Kit dependencies missing → agent reports missing deps and stops
- `.plans/` directory cannot be created → agent reports filesystem error

**Steps**:
1. [x] - `p1` - User requests task via plan workflow (e.g., "plan generate PRD", "plan analyze DESIGN") - `inst-user-request`
2. [x] - `p1` - Agent loads task context: identify task type (generate/analyze/implement), target artifact kind, and kit - `inst-load-context`
3. [x] - `p1` - Agent loads all kit dependencies for target kind: template, rules, checklist, example, constraints - `inst-load-deps`
4. [x] - `p1` - Agent runs decomposition algorithm `cpt-studio-algo-execution-plans-decompose` to split task into phases - `inst-decompose`
5. [x] - `p1` - Agent creates `.plans/` directory in `{cf-studio-path}` if not exists - `inst-create-dir`
6. [ ] - `p1` - **IF** `.plans/` not in `.gitignore` → agent adds it - `inst-gitignore`  *(not implemented — only `.archive/` is gitignored)*
7. [x] - `p1` - Agent creates plan directory: `{cf-studio-path}/.plans/{task-slug}/` - `inst-create-plan-dir`
8. [x] - `p1` - **FOR EACH** phase in decomposition result - `inst-loop-phases`
   1. [x] - `p1` - Agent runs compile algorithm `cpt-studio-algo-execution-plans-compile-phase` to produce phase file content - `inst-compile`
   2. [x] - `p1` - Agent runs budget enforcement `cpt-studio-algo-execution-plans-enforce-budget` on compiled content - `inst-budget`
   3. [x] - `p1` - Agent writes phase file: `phase-{NN}-{slug}.md` - `inst-write-phase`
9. [x] - `p1` - Agent writes plan manifest: `plan.toml` with all phase metadata - `inst-write-manifest`
10. [x] - `p1` - Agent reports plan summary: total phases, estimated lines per phase, execution order - `inst-report`

### Chunk Raw Input Package

- [x] `p1` - **ID**: `cpt-studio-flow-execution-plans-chunk-raw-input`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User or planner invokes `cfs chunk-input ... --output-dir ...` → command emits deterministic `input/*.md` chunk files and JSON metadata
- User combines file inputs with direct prompt text via `--include-stdin` → raw prompt is preserved as `direct-prompt.md` and included in chunk metadata
- Planner encounters an existing `input/manifest.json` whose `input_signature` matches the current raw input → package is safely reused without re-chunking

**Error Scenarios**:
- Input file is missing or unreadable → command returns JSON `ERROR`
- `stdin` is required but empty → command returns JSON `ERROR`
- Output directory cannot be written → command returns JSON `ERROR`

**Steps**:
1. [x] - `p1` - User or planner invokes `cfs chunk-input [<path> ...] --output-dir <path> [--include-stdin]` - `inst-user-chunk-input`
2. [x] - `p1` - Command parses arguments and validates required numeric thresholds - `inst-parse-args`
3. [x] - `p1` - Command reads file sources and optional `stdin` according to invocation mode - `inst-read-sources`
4. [x] - `p1` - Command computes total line count, canonical `input_signature`, and whether planning is required - `inst-evaluate-threshold`
5. [x] - `p1` - **IF** `--dry-run` is set → command skips staging, writing, and atomic swap; instead returns the deterministic `input_signature` and a planned manifest (including chunk metadata, source records, and whether `direct-prompt.md` would be preserved) without persisting any files; callers use this for signature-based reuse checks - `inst-dry-run`
6. [x] - `p1` - Command stages a complete replacement package in a temporary sibling directory instead of deleting the active package first - `inst-prepare-output`
7. [x] - `p1` - **IF** `stdin` participated → command preserves raw direct prompt as `direct-prompt.md` inside the staged package - `inst-store-direct-prompt`
8. [x] - `p1` - Command writes deterministic numbered chunk files bounded by `max_lines` and `manifest.json` carrying `input_signature` and chunk metadata - `inst-write-chunks`
9. [x] - `p1` - Command atomically swaps the staged package into place; on write failure, the previously active package remains intact - `inst-return-result`

### Execute Phase

- [x] `p1` - **ID**: `cpt-studio-flow-execution-plans-execute-phase`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User asks to execute next phase → agent reads phase file, follows instructions, produces output
- All acceptance criteria pass → phase marked done in manifest
- Gitignored plan state under `{cf-studio-path}/.plans/` is executed with the
  non-isolated phase runner so status updates and outputs land in the
  authoritative main checkout
- Tracked or worktree-visible plan state may use the isolated phase runner
  variant when the plan manifest and declared outputs are present inside the
  worktree

**Error Scenarios**:
- Phase depends on incomplete phase → agent reports dependency and stops
- Acceptance criteria fail → phase marked failed, agent reports specifics
- Phase file missing or corrupted → agent reports error

**Steps**:
1. [x] - `p1` - User requests phase execution (next phase or specific phase number) - `inst-user-exec`
2. [x] - `p1` - Agent reads `plan.toml` manifest to determine target phase - `inst-read-manifest`
3. [x] - `p1` - **IF** target phase has unmet dependencies → **RETURN** error with dependency list - `inst-check-deps`
4. [x] - `p1` - Agent updates phase status to `in_progress` in manifest - `inst-update-status-start`
5. [x] - `p1` - Agent reads phase file content (self-contained instructions) - `inst-read-phase`
6. [ ] - `p1` - Agent selects phase execution isolation policy: use
   `cf-phase-runner` when plan state or declared outputs are gitignored or
   main-checkout-local; use `cf-phase-runner-isolated` only when the plan
   manifest and outputs are tracked or otherwise worktree-visible -
   `inst-select-phase-runner-isolation`
7. [x] - `p1` - Agent follows phase instructions exactly (the phase file contains ALL needed context) - `inst-execute`
8. [x] - `p1` - Agent self-checks against acceptance criteria in phase file - `inst-self-check`
9. [x] - `p1` - **IF** all acceptance criteria pass - `inst-check-pass`
   1. [x] - `p1` - Agent updates phase status to `done` in manifest - `inst-mark-done`
   2. [x] - `p1` - Agent reports phase completion and next phase - `inst-report-done`
10. [x] - `p1` - **ELSE** - `inst-check-fail`
   1. [x] - `p1` - Agent updates phase status to `failed` in manifest with details - `inst-mark-failed`
   2. [x] - `p1` - Agent reports failed criteria - `inst-report-failed`

### Check Plan Status

- [x] `p2` - **ID**: `cpt-studio-flow-execution-plans-check-status`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User asks for plan status → agent reads manifest and reports phase progress

**Error Scenarios**:
- No active plan found → agent reports no plan

**Steps**:
1. [x] - `p2` - User requests plan status - `inst-user-status`
2. [x] - `p2` - Agent reads `plan.toml` manifest - `inst-read-manifest-status`
3. [x] - `p2` - Agent reports: plan name, total phases, completed/pending/failed counts, next actionable phase - `inst-report-status`

## 3. Processes / Business Logic (CDSL)

### Decompose Task

- [x] `p1` - **ID**: `cpt-studio-algo-execution-plans-decompose`

**Input**: Task type (generate/analyze/implement), target artifact kind, kit dependencies (template, checklist, rules)

**Output**: Ordered list of phases, each with: title, scope description, relevant template sections, relevant checklist items, relevant rules subset, dependency list

**Steps**:
1. [x] - `p1` - Determine decomposition strategy based on task type - `inst-determine-strategy`
2. [x] - `p1` - **IF** task type is `generate` (artifact creation) - `inst-strategy-generate`
   1. [x] - `p1` - Parse template into logical section groups (2-4 sections per phase) - `inst-parse-template`
   2. [x] - `p1` - Assign each section group to a phase in template order - `inst-assign-sections`
   3. [x] - `p1` - For each phase, extract only the rules applicable to its sections - `inst-extract-rules`
   4. [x] - `p1` - For each phase, extract only the checklist items applicable to its sections - `inst-extract-checklist`
3. [x] - `p1` - **IF** task type is `analyze` (validation/review) - `inst-strategy-analyze`
   1. [x] - `p1` - Parse checklist into category groups (structural, semantic, cross-reference, traceability) - `inst-parse-checklist`
   2. [x] - `p1` - Assign each category group to a phase - `inst-assign-categories`
   3. [x] - `p1` - Add synthesis phase at end (aggregate results, final verdict) - `inst-add-synthesis`
4. [x] - `p1` - **IF** task type is `implement` (code from FEATURE) - `inst-strategy-implement`
   1. [x] - `p1` - Parse FEATURE CDSL blocks (flows, algorithms, states) - `inst-parse-cdsl`
   2. [x] - `p1` - Assign each CDSL block + its tests to a phase - `inst-assign-cdsl`
   3. [x] - `p1` - Order phases by CDSL dependency graph - `inst-order-by-deps`
5. [x] - `p1` - Set phase dependencies: each phase depends on all prior phases that produce content it references - `inst-set-deps`
6. [x] - `p1` - **RETURN** ordered phase list with metadata - `inst-return-phases`

### Compile Phase File

- [x] `p1` - **ID**: `cpt-studio-algo-execution-plans-compile-phase`

**Input**: Phase metadata (from decompose), full kit dependencies, project context

**Output**: Self-contained phase file content (markdown) following `plan-template.md` structure

**Steps**:
1. [x] - `p1` - Generate TOML frontmatter: plan ID, phase number, total, type, status, dependencies, input/output paths - `inst-gen-frontmatter`
2. [x] - `p1` - Write "What" section: 2-3 sentences describing this phase's scope and its place in the plan - `inst-write-what`
3. [x] - `p1` - Write "Prior Context" section: summary of what previous phases produced (or "First phase" if phase 1) - `inst-write-prior`
4. [x] - `p1` - Write "Rules" section: inline ONLY rules applicable to THIS phase's scope - `inst-write-rules`
   1. [x] - `p1` - Extract structural rules relevant to phase's template sections - `inst-extract-structural`
   2. [x] - `p1` - Extract content rules relevant to phase's scope - `inst-extract-content`
   3. [x] - `p1` - Extract quality rules (always included, condensed) - `inst-extract-quality`
5. [x] - `p1` - Write "Input" section: pre-resolve all file paths, inline project context needed for this phase - `inst-write-input`
6. [x] - `p1` - Write "Task" section: numbered step-by-step instructions specific to this phase - `inst-write-task`
7. [x] - `p1` - Write "Acceptance Criteria" section: binary pass/fail checklist for this phase - `inst-write-criteria`
8. [x] - `p1` - Write "Output Format" section: exact expected output format and completion report template - `inst-write-output`
9. [x] - `p1` - Resolve ALL template variables (`{variable}` → absolute paths) in the compiled content - `inst-resolve-vars`
10. [ ] - `p1` - Select phase compilation isolation policy: use
    `cf-phase-compiler` when `.plans` is gitignored or main-checkout-local; use
    `cf-phase-compiler-isolated` only when the brief, output path, and plan
    manifest are worktree-visible - `inst-select-phase-compiler-isolation`
11. [x] - `p1` - **RETURN** compiled phase file content - `inst-return-compiled`

### Enforce Line Budget

- [x] `p1` - **ID**: `cpt-studio-algo-execution-plans-enforce-budget`

**Input**: Compiled phase file content, target budget (500 lines), maximum budget (1000 lines)

**Output**: Budget-compliant phase file content, or split recommendation

**Steps**:
1. [x] - `p1` - Count lines in compiled content - `inst-count-lines`
2. [x] - `p1` - **IF** lines ≤ target budget (500) → **RETURN** content as-is - `inst-under-target`
3. [x] - `p1` - **IF** lines > target but ≤ maximum (1000) - `inst-over-target`
   1. [x] - `p1` - ~~Trim rules section: remove rules not directly applicable to phase scope~~ — **SUPERSEDED** by "Kit Rules Are Law" constraint: rules are NEVER trimmed, phases are split instead - `inst-trim-rules`
   2. [x] - `p1` - ~~Condense quality rules to bullet points~~ — **SUPERSEDED** by "Kit Rules Are Law" constraint - `inst-condense-quality`
   3. [x] - `p1` - **IF** still > target → accept (within maximum budget) - `inst-accept-over`
4. [x] - `p1` - **IF** lines > maximum (1000) - `inst-over-max`
   1. [x] - `p1` - **RETURN** split recommendation: suggest splitting this phase into N sub-phases with proposed scope boundaries - `inst-recommend-split`

### Normalize Raw Input Sources

- [x] `p1` - **ID**: `cpt-studio-algo-execution-plans-chunk-normalize-input`

**Input**: CLI paths, `stdin`, `stdin_label`

**Output**: Ordered normalized raw-input sources with labels, display names, paths, text, and line counts

**Steps**:
1. [x] - `p1` - Normalize newline style for every input source before counting or chunking - `inst-normalize-newlines`
2. [x] - `p1` - Derive stable source labels from file stems or the supplied `stdin` label - `inst-slugify-source`
3. [x] - `p1` - Resolve file paths, read file contents as UTF-8, and reject missing inputs - `inst-read-file-source`
4. [x] - `p1` - Read `stdin` only when no file paths were provided or when `--include-stdin` explicitly requests mixed input - `inst-read-stdin-source`
5. [x] - `p1` - **RETURN** normalized sources in deterministic order with `kind`, `display_name`, `path`, `text`, and `line_count` - `inst-return-sources`

### Compute Raw Input Chunk Ranges

- [x] `p1` - **ID**: `cpt-studio-algo-execution-plans-chunk-ranges`

**Input**: `total_lines`, `max_lines`

**Output**: Ordered inclusive `(start_line, end_line)` ranges for one source

**Steps**:
1. [x] - `p1` - **IF** the source has zero effective lines → return a single empty range `(1, 0)` - `inst-empty-range`
2. [x] - `p1` - Iterate from line 1 in windows of size `max_lines` - `inst-range-loop`
3. [x] - `p1` - Cap each chunk end line at `total_lines` - `inst-range-cap`
4. [x] - `p1` - **RETURN** ordered inclusive chunk ranges - `inst-return-ranges`

### Write Raw Input Package

- [x] `p1` - **ID**: `cpt-studio-algo-execution-plans-chunk-write`

**Input**: Normalized sources, output directory, `max_lines`

**Output**: Written raw-input package files plus ordered chunk metadata

**Steps**:
1. [x] - `p1` - Create the parent directory if it does not already exist and allocate a temporary staging directory beside the target package - `inst-create-output-dir`
2. [x] - `p1` - **IF** a `stdin` source exists → write `direct-prompt.md` into the staged package and record its stored file - `inst-write-direct-prompt`
3. [x] - `p1` - Compute chunk ranges per source and render chunk text with normalized trailing newline handling - `inst-build-chunk-text`
4. [x] - `p1` - Write deterministic filenames `NNN-SS-label-part-PP.md` and collect per-chunk metadata - `inst-write-chunk-file`
5. [x] - `p1` - Write `manifest.json` with `input_signature`, source metadata, and chunk metadata for authoritative package reuse checks - `inst-write-package-manifest`
6. [x] - `p1` - Replace the live package only after the staged package is fully written; restore the previous package on `OSError` - `inst-return-chunks`

### Resolve a Decision From the Plan

- [x] `p1` - **ID**: `cpt-studio-algo-execution-plans-decision-lookup`

**Input**: A decision key, the task's plan directory, and optionally the value the caller holds for a declared dimension

**Output**: One outcome in the frozen resolution contract's own field names — `decision_key` → `value` → `provenance` → `status` — plus the evidence the outcome rests on

**Steps**:
1. [x] - `p1` - Name the plan's vocabulary in one place: the file read, the `[[gate_decisions]]` array — **not** `decisions`, which this same file already carries as a table that `ralphex_export` reaches into with `.get()`, so an array there would raise inside a shipped export command — and the two keys a policy declaration carries — the dimension it is keyed on and the table of rows — so a schema change is one edit rather than a search - `inst-plan-vocab`
2. [x] - `p1` - Return the outcome in the ledger's own four field names rather than a parallel shape, since the contract requires the ledger to share the plan's shape distinguished by provenance, and a renamed field would make a reader map between two vocabularies to answer one question. Mark, beside those four, an outcome that is undecided only because the lookup carried no value for a dimension the plan declared a rule over — the plan is whole and the asker has not said which case it holds — leaving the four contract fields untouched, since a gate that asked that way really did fail to resolve - `inst-plan-outcome`
3. [x] - `p1` - Obtain a descriptor on the plan without ever waiting for one, and judge what is behind it on that descriptor rather than on a prior look at the path. A FIFO named `plan.toml` reports a size of zero, so it passes any size guard, and opening it blocking waits for a writer that never arrives — no exception, no timeout, the gate simply never returns. Refuse anything that is not a regular file, tell a dangling symlink from nothing at all since something is sitting at that path either way, and describe a failed open by its errno and the system's own text, which is what an operator diagnoses from - `inst-plan-open`
4. [x] - `p1` - Read and parse the plan on **every** call, never caching: a cached `resolved` is a stale authority, so a plan edited mid-run takes effect on the next lookup. Bound the read by size, since a file in the task directory that is not a plan would otherwise stall every gate that consults it, and return the reason a read failed rather than swallowing it — "no such plan" and "this plan will not parse" both stop the gate and only one is a defect - `inst-plan-read`
5. [x] - `p1` - Select declarations by **exact** string equality on the key and nothing else — no casefold, no strip, no separator folding, each of which is a similarity match wearing a smaller name — and skip a malformed member rather than raising, counting it so a declaration lost to a typo is visible rather than merely missing - `inst-plan-entries`
6. [x] - `p1` - Resolve a policy declaration through the enum dimension **the plan names**, never one inferred from the shape of the table: a guessed dimension is the same inference this refuses everywhere else, and it loses the distinction between a policy that misses this case and one that was never about this dimension. Every way a policy fails to determine a value is `ambiguous` - `inst-plan-policy`
7. [x] - `p1` - Keep `absent` and `ambiguous` apart though both ask: `absent` is the plan being silent, `ambiguous` is the plan having spoken without deciding, and collapsing them files a gap in the plan under the same heading as a question the plan never undertook to answer. An unresolved lookup carries the literal `unspecified` as its value, matching the ledger's own default, so it reads as visibly unanswered rather than as an empty field - `inst-plan-verdicts`
8. [x] - `p1` - Decide the outcome: no declaration is `absent`; more than one for a key is `ambiguous`; a declaration carrying both a direct value and a policy is `ambiguous`, since which answer is meant cannot be known; an unreadable plan is `ambiguous` and warned about rather than `absent`, because `absent` asserts something about the plan's contents that an unparseable file cannot support - `inst-plan-resolve`
9. [x] - `p1` - Report, before any phase runs, which phases will stop and on which decisions — comparing each phase's declared `needs` against what the plan answers. Without it a plan missing one answer stops at the first phase that needs it, the author supplies it, and the next phase stops on the same key: one interruption served once per phase instead of the whole blast radius stated once. A phase declaring nothing is reported as running, which is what makes the declaration safe to adopt gradually — an undeclared phase behaves exactly as it would without this, stopping when it reaches the question rather than before. The declaration buys **warning, never enforcement**: nothing here decides whether a phase may run, only what it will find when it tries. A key the plan answers by rule is not forecast as blocking: this runs before any gate, so it holds no value for the dimension that rule is keyed on, and a gate will supply one — reporting it would send an author to answer a key their plan already answers, in the one field whose whole job is to be believed. Tell that apart by a field on the outcome rather than by the sentence attached to it, which is the defect already corrected once here when silence was recognised by its description. **This report has no caller in code yet**: the dispatch units re-resolve a phase's declared decisions themselves at dispatch time, and the consumer that will read this whole-plan forecast is a later increment — the capability is built and reachable, not yet wired, and saying so here keeps the step from reading as a description of what runs today - `inst-plan-preflight`

### Enumerate Deliverable Items From a Plan

- [x] `p1` - **ID**: `cpt-studio-algo-execution-plans-deliverable-items`

**Input**: The task's plan directory

**Output**: The deliverable items the plan declares, in phase then authoring order, each carrying the author's done-claim, a verification kind, and the open question it waits on (if any); plus the phases that declared no criteria and the phases whose files could not be fully read

**Steps**:
1. [x] - `p1` - Read the plan's phases on **every** call, never caching, for the same reason the decision lookup re-reads — a plan edited mid-run has to take effect on the next read. A manifest that will not load returns the reason it failed and no items, rather than a silent empty list. A `phases` that is declared but is not an array is the author's defect and is reported as such, kept distinct from a plan that declares no phases at all, which is simply nothing to read - `inst-items-read`
2. [x] - `p1` - Let each phase contribute to exactly the lists it has something to say for: its items when it has acceptance criteria, its number to the without-criteria list when it has none, and a read-problem note when its file could not be fully read — a truncated phase yields both items and a note. One unreadable phase file is a reported gap about that phase, never a crash that hides the items of the others - `inst-items-phase`
3. [x] - `p1` - Treat the phase file name as author-controlled: require the resolved path to stay inside the plan directory, so a name escaping it is refused rather than read, and read the file bounded and **strictly** as UTF-8 — a criterion decoded with replacement silently changes what the run is checked against. A phase whose declared number will not parse falls back to its position rather than raising, since a mis-numbering is the structural validator's finding, not a reason to read no items - `inst-items-file`
4. [x] - `p1` - Collect the task-list checkboxes under the `## Acceptance Criteria` heading **only** — the section opens on that heading and closes on the next — in authoring order, bounding both the per-phase count and each criterion's text through the same transform the ledger uses. The `[x]` box is the author's **claim** and never a verdict; whether the item is satisfied is verification's job, not the box's. Every item is `explicit` until the plan declares how it is checked — the conservative direction, so an unspecified check becomes a statement to make at completion, not a guess. A phase may raise several read problems, not one, so its problems are collected as a list — a truncation note and a malformed-marker note can both arise in the same phase - `inst-items-criteria`
5. [x] - `p1` - Read an optional trailing `(needs: key)` marker as the open question a criterion waits on, by that question's decision key, reusing the existing `needs` vocabulary and the shared decision-key grammar — only the inline placement is new. **The marker is not stripped from the criterion text:** two criteria with identical wording but different dependency keys are different deliverables, and stripping would collapse them to one `(phase, text)` verdict identity — keeping the marker in the text keeps them distinct and lets an author give each its own verdict. Leave the dependency unset and **report** it — fail-loud, never a silent partial application — when the key is not a valid decision key, is the reserved sentinel the log uses for "no key" (so it could never block), or when a second earlier marker is present (only the trailing one is read) - `inst-items-needs`
6. [x] - `p1` - Model a deliverable item and the reader's result as frozen records, one shape for every outcome: an item carries its phase, its authoring order, its bounded text, the author's done-claim, its verification kind, and the open-question key it waits on (or none); the result carries the items, the reason a manifest would not load, the phases that declared no criteria, and the per-phase read problems — so a caller reads one list for the items and one field for a load failure, never a second shape per outcome. Fix the acceptance heading, the checkbox, heading and `(needs: …)` grammar, the per-phase item cap, and the default verification kind as named constants beside that model, since a grammar or a bound stated twice drifts and only one copy gets the next fix - `inst-items-model`

### Read a Run's Outstanding Open Questions

- [x] `p1` - **ID**: `cpt-studio-algo-execution-plans-open-questions`

**Input**: The decision log path (the default log when none is given) and the run id to scope to (the current run when none is given)

**Output**: The keyed open questions still outstanding **for that one run** — each with the gate it was raised on and the reason it could not be ruled — projected from the log, answered questions dropped

**Steps**:
1. [x] - `p1` - Fix the gate-event kind a parked question is recorded under, and the kinds that **answer** one, as named constants. A question is closed by a later `plan-resolved` or `blocking-confirmed` for the same key; `auto-proceeded` is deliberately **not** an answer — proceeding on a default does not resolve the question that was raised, so leaving it open is the fail-safe direction, toward holding the dependent item and never toward a silent pass - `inst-oq-kinds`
2. [x] - `p1` - Model one open question and the register as frozen records: a question carries the key it is addressable by, the gate it was raised on, and the reason it could not be resolved; the register maps each still-open key to its question **and holds the set of keys that were answered**. The one thing a completion check asks is whether a named key was **answered** — a key still outstanding **or one never raised** is not answered, so a dependency on it blocks. That makes an absent or unreadable log fail safe: no key reads as answered, so every declared dependency holds rather than silently passing - `inst-oq-model`
3. [x] - `p1` - Read the `gate` events oldest-first through the log's own reader — never a second copy of the parsing rules — **scoped to a single run** (the given run id, or the current run), and replay them: an `open-question` event opens its key, a later answering event for the same key closes it **and records the key as answered**, and a re-deferral opens it again **and un-records it as answered**, so the final state holds both what is open now and which keys were settled. The scope is the correctness crux: the log is shared across runs, so an unscoped read would let one run's answer clear a *different* run's blocker, completing that run's unfinished item. Re-read on every call, never caching, for the same reason the plan readers re-read. A deferral that recorded no `decision_key` is skipped — not addressable by an item, so not a blocker — never treated as an error. **Known limitation:** the register is re-derived from the log, which the reader serves from the live plus one rotated segment, so a question whose opening and answer both survive two rotations can age out of both segments and no longer be replayed; because the check asks whether a key was **answered**, a key the replay no longer reports reads as not answered, so its item is **held, not completed** (the fail-safe direction, never a silent pass) — a durable store is the tracked follow-up, not built here - `inst-oq-read`

### Verify a Run Against Its Plan Before Completion

- [x] `p1` - **ID**: `cpt-studio-algo-execution-plans-verify-completion`

**Input**: The task's plan directory and the verdicts file the run recorded

**Output**: A completion outcome — complete, incomplete, or a fault — and the contract exit code it maps to, with the items that block completion named

**Steps**:
1. [x] - `p1` - Model the verdicts a run recorded and the completion outcome as frozen records: a verdict carries its token and its evidence; the outcome carries the status, the contract exit code, and the items that block completion — split by cause into unsatisfied, unstated, and **waiting on an open question** — one shape for every outcome, so a caller reads one list per blocking cause and one field for a fault. Track an item a verdicts file answered more than once as untrustworthy rather than resolving it to its last answer - `inst-verify-model`
2. [x] - `p1` - Read the verdicts file through the plan loader's fail-loud TOML read, not a second one. Key each verdict by `(phase, bounded-text)` — a verdict entry may name an optional `phase`, which is what lets the **same criterion in two phases** receive two separate answers; an entry with no phase keys under phase `None`. A file that declares no verdicts array means the run stated nothing — every item reads as unstated — not an error; a verdicts key present but not an array is the author's defect and is reported - `inst-verify-read-verdicts`
3. [x] - `p1` - Decide one item's verdict fail-safe toward not-satisfied, and return an explicit **reason** so the caller classifies on it and never on the evidence text: look the answer up by `(phase, text)` first, falling back to a phase-less entry **only when that text is unique across the plan** (a phase-less answer to a text in several phases is `ambiguous`). An item with no usable verdict (`missing`), with conflicting verdicts for its key (`conflict`), or with a verdict outside the enumerated set (`unrecognised`) is `not-satisfied`, never assumed done — accepting an invented verdict such as `done`, or letting one phase-less answer silently pass every phase, would slip an unchecked item through - `inst-verify-item`
4. [x] - `p1` - Reconcile the plan's declared items against the run's recorded verdicts, recording one verification event per item — **with its phase** — so the close is auditable and two phases that declare the same criterion stay distinguishable in the log, and a later summary can be projected from the ledger. An item whose `(needs: key)` key was **not answered** in the register (read from the same log **scoped to the run being verified**) is checked **first** and **overrides its verdict** — recorded not-satisfied, reason blocked-on-question — since an item cannot be shown done while a declared dependency is unaddressed. A key is unanswered when it is still outstanding **or was never raised**: a never-raised dependency is not assumed irrelevant, it blocks, the fail-safe direction. Read the register only when some item declares a dependency, so a plan using no marker pays no log read and behaves exactly as before. Report **incomplete** if any item is unsatisfied, unstated, blocked on a question, or if any phase's criteria could not be read — a criterion that could not be read means an item may be missing entirely, so the run cannot be shown complete, the fail-safe direction being more friction and never a pass. A plan that declares no items is a vacuous pass, stated as not-applicable rather than hidden; a verdict for an item the plan does not declare is reported, not counted against completion - `inst-verify-assess`
5. [x] - `p1` - Render one result shape for every outcome: a human headline that names the first blocking cause, each blocking item listed under it — grouped by cause, including those waiting on an open question — and a structured payload a JSON caller reads - `inst-verify-report`
6. [x] - `p1` - Expose the check as a command whose arguments are the plan directory, an optional verdicts path, and an optional run id scoping the open-question check (defaulting to the current run) — so run stand-alone with no run id this command's own run has answered nothing, so **every** `(needs: …)` item blocks and the run reports incomplete, the fail-safe direction; meaningful enforcement needs the close to run in the executing run or that run's id passed, a limitation the command states plainly — returning the contract exit codes — **0** when the run is complete, **2** when a check failed (an item unsatisfied, unstated, blocked on an open question, or its criteria unreadable), **1** when a fault stopped the check (the plan or the verdicts file could not be read). A fault is kept apart from a failed check so CI keying on **2** for an incomplete run is not confused by a close that could not run - `inst-verify-cli`

## 4. States (CDSL)

### Raw Input Package Lifecycle

- [x] `p1` - **ID**: `cpt-studio-state-execution-plans-raw-input-package`

**States**: absent, materialized, reused, failed

**Initial State**: absent

**Transitions**:
1. [x] - `p1` - **FROM** absent **TO** materialized **WHEN** `chunk-input` writes a new raw-input package successfully - `inst-package-materialized`
2. [x] - `p1` - **FROM** materialized **TO** materialized **WHEN** `chunk-input` re-runs in place after cleaning stale generated outputs - `inst-package-rewritten`
3. [x] - `p1` - **FROM** materialized **TO** reused **WHEN** the planner detects and reuses an existing authoritative raw-input package - `inst-package-reused`
4. [x] - `p1` - **FROM** absent **TO** failed **WHEN** source loading or package writing fails - `inst-package-failed`

### Plan Lifecycle

- [x] `p1` - **ID**: `cpt-studio-state-execution-plans-plan-lifecycle`

**States**: pending, in_progress, done, failed

**Initial State**: pending

**Transitions**:
1. [x] - `p1` - **FROM** pending **TO** in_progress **WHEN** first phase execution starts - `inst-plan-start`
2. [x] - `p1` - **FROM** in_progress **TO** done **WHEN** all phases are done - `inst-plan-done`
3. [x] - `p1` - **FROM** in_progress **TO** failed **WHEN** any phase fails and user does not retry - `inst-plan-failed`

### Phase Lifecycle

- [x] `p1` - **ID**: `cpt-studio-state-execution-plans-phase-lifecycle`

**States**: pending, in_progress, blocked, done, failed

**Initial State**: pending

**Transitions**:
1. [x] - `p1` - **FROM** pending **TO** in_progress **WHEN** agent begins executing phase - `inst-phase-start`
2. [x] - `p1` - **FROM** in_progress **TO** done **WHEN** all acceptance criteria pass - `inst-phase-done`
3. [x] - `p1` - **FROM** in_progress **TO** failed **WHEN** acceptance criteria fail - `inst-phase-failed`
4. [x] - `p1` - **FROM** pending **TO** blocked **WHEN** a person or an external tool holds the phase by hand - `inst-phase-blocked`
5. [x] - `p1` - **FROM** blocked **TO** pending **WHEN** that hold is lifted by hand - `inst-phase-unblocked`
4. [x] - `p1` - **FROM** failed **TO** in_progress **WHEN** user retries phase - `inst-phase-retry`

## 5. Definitions of Done

### Raw Input Package

- [x] `p1` - **ID**: `cpt-studio-dod-execution-plans-raw-input`

The system MUST provide a `chunk-input` command that takes file paths and/or `stdin` input and emits a deterministic raw-input package in the output directory. The package MUST contain:
- `manifest.json` with `input_signature`, source metadata, and ordered chunk metadata
- `direct-prompt.md` (if `stdin` was used)
- `NNN-SS-label-part-PP.md` chunk files (where `NNN` is the chunk number, `SS` is the source sequence number (zero-padded index), `label` is the slugified source label (lowercase, ASCII-safe, spaces and special characters replaced with hyphens or underscores to ensure deterministic, filesystem-safe filenames), and `PP` is the part number)

Package reuse MUST depend on an exact `input_signature` match, not only on plan target identity or directory existence. Re-running the command with changed raw input MUST preserve the previous live package unless the replacement package is fully written and successfully swapped into place.

**Implements**:
- `cpt-studio-flow-execution-plans-chunk-raw-input`
- `cpt-studio-algo-execution-plans-chunk-normalize-input`
- `cpt-studio-algo-execution-plans-chunk-ranges`
- `cpt-studio-algo-execution-plans-chunk-write`

**Constraints**: `cpt-studio-constraint-markdown-contract`

**Touches**:
- Directory: `{cf-studio-path}/.plans/{task-slug}/input/` (new, contains raw-input package)

### Plan Workflow

- [x] `p1` - **ID**: `cpt-studio-dod-execution-plans-workflow`

The system MUST provide a `plan.md` workflow file that instructs AI agents how to decompose tasks into phases and generate self-contained phase files. The workflow MUST follow the same structure as existing `generate.md` and `analyze.md` workflows.

**Implements**:
- `cpt-studio-flow-execution-plans-generate-plan`
- `cpt-studio-flow-execution-plans-execute-phase`
- `cpt-studio-flow-execution-plans-check-status`

**Constraints**: `cpt-studio-constraint-markdown-contract`

**Touches**:
- File: `workflows/plan.md` (new)
- File: `{cf-studio-path}/.core/workflows/plan.md` (synced copy)

### Phase File Template

- [x] `p1` - **ID**: `cpt-studio-dod-execution-plans-template`

The system MUST provide a `plan-template.md` requirement file that defines the strict structure for generated phase files. The template MUST enforce:
- TOML frontmatter with plan/phase metadata
- Self-contained preamble ("Any AI agent can execute this file")
- Sections: What, Prior Context, Rules (inlined), Input (pre-resolved), Task (step-by-step), Acceptance Criteria (binary), Output Format
- No unresolved template variables
- No external file references that require Studio knowledge

**Implements**:
- `cpt-studio-algo-execution-plans-compile-phase`

**Constraints**: `cpt-studio-constraint-markdown-contract`

**Touches**:
- File: `requirements/plan-template.md` (new)
- File: `{cf-studio-path}/.core/requirements/plan-template.md` (synced copy)

### Decomposition Strategies

- [x] `p1` - **ID**: `cpt-studio-dod-execution-plans-decomposition`

The system MUST provide a `plan-decomposition.md` requirement file that defines decomposition strategies for each task type:
- **Generate**: split by template section groups (2-4 sections per phase)
- **Analyze**: split by checklist category groups (structural → semantic → cross-ref → traceability → synthesis)
- **Implement**: split by CDSL blocks (each flow/algorithm/state + its tests = 1 phase)

The file MUST include budget enforcement rules (500-line target, 1000-line max) and phase dependency resolution.

**Implements**:
- `cpt-studio-algo-execution-plans-decompose`
- `cpt-studio-algo-execution-plans-enforce-budget`

**Constraints**: `cpt-studio-constraint-markdown-contract`

**Touches**:
- File: `requirements/plan-decomposition.md` (new)
- File: `{cf-studio-path}/.core/requirements/plan-decomposition.md` (synced copy)

### Plan Storage

- [x] `p1` - **ID**: `cpt-studio-dod-execution-plans-storage`

The system MUST store execution plans in `{cf-studio-path}/.plans/{task-slug}/` directory. The directory MUST be added to `.gitignore` automatically on first use. Each plan directory contains:
- `plan.toml` — manifest with phase metadata and status tracking
- `input/` — authoritative raw-input package when oversized workflow input was materialized (`manifest.json`, optional `direct-prompt.md`, plus numbered chunk files)
- `phase-{NN}-{slug}.md` — self-contained phase files

The manifest MAY also carry a `[[gate_decisions]]` array — the author-facing counterpart of a
menu's declared `KEY:`. Each entry's `key` is selected by exact string equality (see *Resolve a
Decision From the Plan*), so it uses the same snake_case shape a `KEY:` declaration does — never a
dotted or hyphenated form, which no `KEY:` can name and so nothing would ever match. A decision
pre-resolved for a human in a phase file's *Already Decided* list is made resolvable from the plan
by a matching entry here, so a gate that declares that key can resolve against the plan instead of
re-asking:

```toml
[[gate_decisions]]
key = "runtime_base_image"
value = "ubuntu-24.04"
cost_if_wrong = "a rebuild on the wrong base; minutes, reversible"
why = "the task targets the current LTS"
```

An entry MAY carry two optional fields beside `key`/`value`: `cost_if_wrong` (what it costs if this
pre-decision is wrong, one line) and `why` (a one-line rationale). When `cost_if_wrong` is present,
the autonomous default records the resolution to the decision log (`cfs gate-log --kind
plan-resolved …`), so an autonomous ruling is auditable — it states what it answered and what being
wrong costs. An entry that omits `cost_if_wrong` resolves the gate identically; the audit record is
simply not written (best-effort). The deterministic Python write path is a later increment.

A policy entry names the enum dimension the plan resolves it through and the row table, rather than
a single `value`:

```toml
[[gate_decisions]]
key = "review_follow_up_depth"
dimension = "register.classification"
[gate_decisions.policy]
serious = "full-review"
normal = "spot-check"
```

**Implements**:
- `cpt-studio-flow-execution-plans-chunk-raw-input`
- `cpt-studio-flow-execution-plans-generate-plan`
- `cpt-studio-state-execution-plans-raw-input-package`
- `cpt-studio-state-execution-plans-plan-lifecycle`
- `cpt-studio-state-execution-plans-phase-lifecycle`

**Touches**:
- Directory: `{cf-studio-path}/.plans/` (new, git-ignored)

### Plan Export Contract

- [ ] `p1` - **ID**: `cpt-studio-dod-execution-plans-export`

The system MUST support exporting Studio plan outputs into executor-specific grammars for delegated execution. The initial target grammar is ralphex Markdown plans.

**Export rules**:
- One Studio execution plan exports to one ralphex plan file under the ralphex-resolved `plans_dir` (default `docs/plans/`; resolved from ralphex config precedence, not Studio-owned)
- One Studio phase maps to one `### Task N:` block or a small contiguous task group inside the exported plan
- Studio phase instructions, task steps, and acceptance criteria are flattened into ralphex-compatible checkboxes and validation commands
- Exported plans MUST contain a `## Validation Commands` section derived from Studio's deterministic validation contract
- `{cf-studio-path}/.plans/{task}/out/` remains the stable interchange point for intermediate outputs consumed by later export passes
- Exported plans are derived artifacts compiled from canonical Studio sources — they are not a second SDLC source of truth
- Export MUST NOT copy the entire SDLC kit into the executor plan; only the bounded slices needed for the delegated task are included

This feature owns the canonical plan structure and export contract definition. Concrete delegated export (compilation into ralphex grammar, `.ralphex/` overrides, CLI invocation) is implemented by `cpt-studio-feature-ralphex-delegation` — specifically `cpt-studio-algo-ralphex-delegation-compile-plan` and `cpt-studio-algo-ralphex-delegation-map-phase`.

**Constraints**: `cpt-studio-constraint-markdown-contract`

**Touches**:
- Directory: `{plans_dir}/` (exported ralphex-compatible plans, written by ralphex-delegation feature; path resolved from ralphex config, default `docs/plans/`)
- Directory: `{cf-studio-path}/.plans/{task}/out/` (intermediate interchange outputs)

## 6. Acceptance Criteria

- [x] Plan workflow file (`workflows/plan.md`) exists and follows workflow structure conventions
- [x] Phase template file (`requirements/plan-template.md`) exists with all required sections
- [x] Decomposition strategies file (`requirements/plan-decomposition.md`) exists with strategies for generate/analyze/implement
- [x] Generated phase files are self-contained: zero unresolved `{variable}` references, zero "open file X" instructions
- [x] Generated phase files respect line budget: ≤500 lines target, ≤1000 lines maximum
- [x] Phase files can be executed by any AI agent without Studio context or tools
- [x] Plan manifest (`plan.toml`) correctly tracks phase status across executions
- [x] Oversized workflow input can be materialized into deterministic `input/*.md` chunk files with `direct-prompt.md` preservation and stale-output cleanup
- [ ] `.plans/` directory is automatically git-ignored *(only `.archive/` is currently gitignored)*
- [ ] Studio plan outputs can be exported into ralphex-compatible Markdown plan files under the ralphex-resolved `plans_dir`
- [ ] Exported plans contain `## Validation Commands` and `### Task N:` sections matching ralphex grammar
- [ ] Phase-to-task mapping flattens Studio acceptance criteria into ralphex checkboxes
