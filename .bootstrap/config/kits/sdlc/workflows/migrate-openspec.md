---
cf-studio: true
type: workflow
name: cf-sdlc-migrate-openspec
description: Invoke when the user asks to migrate or convert OpenSpec artifacts to Constructor Studio SDLC documents — e.g. "migrate openspec", "migrate from openspec", "convert openspec", "openspec to Constructor Studio". Converts OpenSpec proposals/specs/designs/tasks into PRD, DESIGN, ADR, FEATURE, and DECOMPOSITION with code-verified ID traceability.
version: 1.0
purpose: Convert any project's OpenSpec artifacts (proposals, specs, designs, tasks) into Constructor Studio SDLC documents (PRD, DESIGN, ADR, FEATURE, DECOMPOSITION) with full ID-based traceability verified against the actual codebase
---

# Migrate OpenSpec to Constructor Studio SDLC Artifacts

<!-- toc -->

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
  - [Required Variables](#required-variables)
  - [Discovery Protocol](#discovery-protocol)
- [Mapping Model](#mapping-model)
  - [Source → Target Mapping](#source-target-mapping)
  - [Traceability Chain (Post-Migration)](#traceability-chain-post-migration)
- [Context Budget](#context-budget)
- [Review Gates](#review-gates)
- [Code Verification Protocol](#code-verification-protocol)
  - [Verification Method](#verification-method)
  - [Discrepancy Log](#discrepancy-log)
- [Phase 1: Inventory & Analysis](#phase-1-inventory-analysis)
  - [Step 1.1: Catalog Main Specs](#step-11-catalog-main-specs)
  - [Step 1.2: Survey Codebase](#step-12-survey-codebase)
  - [Step 1.3: Catalog Change Artifacts](#step-13-catalog-change-artifacts)
  - [Step 1.4: Define Migration Scope](#step-14-define-migration-scope)
- [Phase 2: Generate PRD](#phase-2-generate-prd)
  - [Dependencies](#dependencies)
  - [Step 2.1: Extract Purpose & Background](#step-21-extract-purpose-background)
  - [Step 2.2: Extract Actors](#step-22-extract-actors)
  - [Step 2.3: Extract Functional Requirements (Code-Verified)](#step-23-extract-functional-requirements-code-verified)
  - [Step 2.4: Extract Non-Functional Requirements (Code-Verified)](#step-24-extract-non-functional-requirements-code-verified)
  - [Step 2.5: Extract Remaining PRD Sections](#step-25-extract-remaining-prd-sections)
  - [Step 2.6: Self-Check (PRD)](#step-26-self-check-prd)
- [Phase 3: Generate DESIGN](#phase-3-generate-design)
  - [Dependencies](#dependencies-1)
  - [Step 3.1: Extract Architecture Vision & Drivers](#step-31-extract-architecture-vision-drivers)
  - [Step 3.2: Extract Principles & Constraints (Code-Verified)](#step-32-extract-principles-constraints-code-verified)
  - [Step 3.3: Extract Component Model (Code-Verified)](#step-33-extract-component-model-code-verified)
  - [Step 3.4: Extract Remaining DESIGN Sections](#step-34-extract-remaining-design-sections)
  - [Step 3.5: Self-Check (DESIGN)](#step-35-self-check-design)
- [Phase 4: Generate ADRs](#phase-4-generate-adrs)
  - [Dependencies](#dependencies-2)
  - [Step 4.1: Extract Decisions](#step-41-extract-decisions)
  - [Step 4.2: Write ADR Documents](#step-42-write-adr-documents)
  - [Step 4.3: Register ADR IDs in DESIGN](#step-43-register-adr-ids-in-design)
  - [Step 4.4: Self-Check (ADRs)](#step-44-self-check-adrs)
- [Phase 5: Generate DECOMPOSITION](#phase-5-generate-decomposition)
  - [Dependencies](#dependencies-3)
  - [Step 5.1: Define Feature Boundaries](#step-51-define-feature-boundaries)
  - [Step 5.2: Write Feature Entries](#step-52-write-feature-entries)
  - [Step 5.3: Add Overall Status](#step-53-add-overall-status)
  - [Step 5.4: Self-Check (DECOMPOSITION)](#step-54-self-check-decomposition)
- [Phase 6: Generate FEATURE Specs](#phase-6-generate-feature-specs)
  - [Dependencies](#dependencies-4)
  - [Step 6.1: Convert Scenarios to CDSL Flows (Code-Verified)](#step-61-convert-scenarios-to-cdsl-flows-code-verified)
  - [Step 6.2: Generate Flow, Algo, State IDs](#step-62-generate-flow-algo-state-ids)
  - [Step 6.3: Write FEATURE Documents](#step-63-write-feature-documents)
  - [Step 6.4: Self-Check (FEATURE)](#step-64-self-check-feature)
- [Phase 7: Place Code Markers](#phase-7-place-code-markers)
  - [Step 7.1: Plan Marker Placement](#step-71-plan-marker-placement)
  - [Step 7.2: Place Markers (Per Feature)](#step-72-place-markers-per-feature)
  - [Step 7.3: Self-Check (Code Markers)](#step-73-self-check-code-markers)
- [Phase 8: Register & Validate](#phase-8-register-validate)
  - [Step 8.1: Update artifacts.toml](#step-81-update-artifactstoml)
  - [Step 8.2: Run Deterministic Validation](#step-82-run-deterministic-validation)
  - [Step 8.3: Run Spec Coverage](#step-83-run-spec-coverage)
  - [Step 8.4: Run TOC Generation](#step-84-run-toc-generation)
  - [Step 8.5: Generate Migration Report](#step-85-generate-migration-report)
- [Phase Execution Order](#phase-execution-order)
- [Error Handling](#error-handling)
  - [Incomplete OpenSpec Source](#incomplete-openspec-source)
  - [Conflicting Information](#conflicting-information)
  - [Missing Design Artifacts](#missing-design-artifacts)
  - [ID Collision](#id-collision)
  - [Code Marker Conflicts](#code-marker-conflicts)
- [Appendix: OpenSpec Format Reference](#appendix-openspec-format-reference)
  - [Directory Structure](#directory-structure)
  - [Main Spec Format](#main-spec-format-specscapabilityspecmd)
  - [Change Artifact Formats](#change-artifact-formats)
  - [Config Format](#config-format-configyaml)
- [Validation Criteria](#validation-criteria)

<!-- /toc -->

## Overview

This workflow converts OpenSpec artifacts (proposals, main specs, designs, tasks, delta specs) into Constructor Studio SDLC standard documents (PRD, DESIGN, ADR, FEATURE, DECOMPOSITION) with full ID-based traceability verified against the actual codebase.

**Input**: OpenSpec artifacts at `{openspec_root}/` (main specs and archived changes) + source code at `{codebase_paths}`
**Output**: Constructor Studio artifacts at `{artifacts_output}/` + `@cpt-*` code markers in source files, registered in `{cf-studio-path}/config/artifacts.toml` with `FULL` traceability

**Why this workflow exists**: OpenSpec uses convention-based traceability with no formal IDs. Its artifacts were never verified against the actual implementation. Constructor Studio uses ID-based traceability (`cpt-{system}-{kind}-{slug}`) with enforced coverage. This workflow bridges the gap by grounding every generated document in what the code actually does — not what the specs claim it does.

**Key principle**: The source code is the ultimate source of truth. When an OpenSpec spec contradicts the code, the Constructor Studio artifact describes the code's actual behavior, and the discrepancy is flagged in the migration report.

---

## Prerequisites

- [ ] Constructor Studio initialized (`{cf-studio-path}/` exists with `config/artifacts.toml`)
- [ ] OpenSpec directory exists at `{openspec_root}/` with main specs and archived changes
- [ ] Source code available at `{codebase_paths}`
- [ ] Agent has read this workflow in full before starting any phase
- [ ] Agent has access to Constructor Studio kit resources (resolved via `cfs resolve-vars`)

---

## Configuration

Before starting migration, resolve these variables:

### Required Variables

| Variable | Source | Description |
|---|---|---|
| `{system}` | `artifacts.toml` → `systems[].slug` | System slug for ID prefixes (`cpt-{system}-*`) |
| `{openspec_root}` | User prompt | Root directory of OpenSpec artifacts |
| `{codebase_paths}` | `artifacts.toml` → `systems[].codebase[].path` | Source code directories to scan |
| `{artifacts_output}` | User prompt or default `architecture/` | Where to write Constructor Studio artifacts |
| `{cf-studio-path}` | Standard Constructor Studio variable | Constructor Studio config directory |
| `{kit_slug}` | `artifacts.toml` → `kits` | Kit providing templates/rules |

### Discovery Protocol

1. Run `cfs info` to get `{cf-studio-path}` and project root
2. Read `{cf-studio-path}/config/artifacts.toml`:
   - Extract `{system}` from first system or ask user if multiple
   - Extract `{codebase_paths}` from system codebase entries
   - Extract `{kit_slug}` from system kit reference
3. Ask user for `{openspec_root}` — the directory containing OpenSpec artifacts
4. Ask user for `{artifacts_output}` or default to `architecture/`
5. Validate that `{openspec_root}` exists and contains expected structure:
   - `{openspec_root}/specs/` — main specification files
   - `{openspec_root}/config.yaml` — project configuration
   - `{openspec_root}/changes/archive/` — archived change artifacts (optional)

---

## Mapping Model

### Source → Target Mapping

| OpenSpec Source | Constructor Studio Target | Relationship |
|---|---|---|
| Main specs (`{openspec_root}/specs/*/spec.md`) | **PRD** § Functional Requirements | Each spec requirement → one `cpt-{system}-fr-*` ID |
| Main specs (non-functional aspects) | **PRD** § Non-Functional Requirements | Performance, reliability, security constraints → `cpt-{system}-nfr-*` IDs |
| Proposal capabilities + spec grouping | **PRD** § Scope, Goals, Actors | Proposal why/what/impact → PRD purpose/background/goals |
| Design decisions (`design.md`) | **ADR** (one per decision) | Each `### Decision N:` → one ADR file `NNNN-{slug}.md` |
| Design architecture (layers, components) | **DESIGN** § Technical Architecture | Component descriptions → `cpt-{system}-component-*` IDs |
| Design principles + constraints | **DESIGN** § Principles & Constraints | Explicit or implicit → `cpt-{system}-principle-*`, `cpt-{system}-constraint-*` IDs |
| Task categories (`tasks.md`) | **DECOMPOSITION** entries | Each `## N. Category` → one feature entry with `cpt-{system}-feature-*` ID |
| Task details + spec scenarios | **FEATURE** specs (per feature) | Given/When/Then scenarios → CDSL flows with `cpt-{system}-flow-*` IDs |

### Traceability Chain (Post-Migration)

```
PRD (fr, nfr, actor, usecase)
  ↓  [coverage required]
DESIGN (component, principle, constraint, seq)
  ↓  [coverage required]
DECOMPOSITION (feature)
  ↓  [coverage required]
FEATURE (flow, algo, state, dod)
  ↓  [to_code markers]
CODE (@cpt-{kind}:{id}:p{N})
```

ADR cross-cuts: each `cpt-{system}-adr-*` referenced in DESIGN § Architecture Drivers.

---

## Context Budget

**Budget**: Load at most 3 OpenSpec source files + 3 code files simultaneously. After extracting content from each batch, summarize and drop raw text before loading the next batch.

**Chunking**: Read OpenSpec main specs in batches of 3 capabilities. For large specs (>500 lines) or large source files, read by section using line ranges.

**Fail-safe**: If context approaches capacity mid-phase, write a checkpoint file at `{artifacts_output}/workflows/.migrate-checkpoint.md` and resume from there.

---

## Review Gates

Every phase ends with a **review gate**. The agent:

1. Writes the artifact file(s) for that phase
2. Presents a summary of what was written and any discrepancies found
3. **STOPS and waits for the user** to review the diff
4. Proceeds to the next phase only after user says to continue

The agent MUST NOT proceed past a review gate without explicit user approval. The agent MUST NOT create commits — the user handles version control.

If the user requests changes after reviewing a phase's output, the agent modifies the artifact and re-presents the summary. This loop continues until the user approves.

---

## Code Verification Protocol

Every generation phase that produces artifact content MUST verify claims against source code. This protocol applies to Phases 2-6.

### Verification Method

For each requirement, component, or flow being documented:

1. **Locate**: Find the source file(s) that implement it (search `{codebase_paths}`)
2. **Confirm**: Read the relevant code and verify the artifact's claim matches actual behavior
3. **Classify** the result:

| Result | Action |
|---|---|
| **VERIFIED** | Spec matches code. Write the requirement as-is. |
| **ADJUSTED** | Spec partially matches code. Write what the code actually does. Log the discrepancy. |
| **NOT_IMPLEMENTED** | Spec describes something the code doesn't do. Mark FR as `[ ]` (unchecked) with note: "Not implemented — OpenSpec spec aspirational". |
| **UNDOCUMENTED** | Code does something no spec describes. Create a new FR/component for it. Log as "Discovered during migration". |

### Discrepancy Log

Maintain a running discrepancy log during migration (chat-only, not a file):

```markdown
| Phase | ID | Type | OpenSpec Says | Code Does | Resolution |
|---|---|---|---|---|---|
| 2 | cpt-{system}-fr-routing-lazy | ADJUSTED | SHALL lazy-load all routes | Only lazy-loads MFE routes | FR updated to match code |
```

Present the accumulated log at each review gate so the user can assess quality.

---

## Phase 1: Inventory & Analysis

**Goal**: Catalog all OpenSpec artifacts, survey the codebase, and plan the migration scope.

### Step 1.1: Catalog Main Specs

Read the `{openspec_root}/specs/` directory. For each capability:

1. Record: capability name, line count, number of requirements, number of scenarios
2. Group capabilities by domain area (SDK core, UI, framework, tooling, etc.)
3. Note any specs with `TBD` purpose sections (incomplete specs)

**Output**: A capability inventory table:

```markdown
| Capability | Domain | Requirements | Scenarios | Lines | Notes |
|---|---|---|---|---|---|
| sdk-core | SDK | 12 | 24 | 450 | Complete |
| routing | Framework | 8 | 16 | 320 | Complete |
```

### Step 1.2: Survey Codebase

Scan `{codebase_paths}` to understand the implementation landscape:

1. List all packages/modules with their entry points and line counts
2. Map packages/modules to OpenSpec capability areas
3. Identify code with no corresponding OpenSpec spec (undocumented code)
4. Identify OpenSpec specs with no corresponding code (unimplemented specs)

**Output**: A codebase-to-spec mapping table:

```markdown
| Package | Entry Point | Lines | OpenSpec Capability | Status |
|---|---|---|---|---|
| {package-a} | {path}/index.ts | 1200 | sdk-core | Covered |
| {package-b} | {path}/index.ts | 800 | sdk-core | Covered |
| {package-c} | {path}/index.ts | 3000 | studio | Partial |
```

### Step 1.3: Catalog Change Artifacts

Scan `{openspec_root}/changes/archive/` for design decisions and task structures:

1. Count changes with `design.md` → these contain ADR-worthy decisions
2. Count unique decisions across all designs (each `### Decision N:` heading)
3. Count task categories across all `tasks.md` → these inform DECOMPOSITION features

**Output**: Change artifact summary with counts.

### Step 1.4: Define Migration Scope

Present the inventory to the user:

```markdown
## Migration Scope

**Main specs**: {N} capabilities across {M} domain areas → PRD functional requirements
**Codebase**: {N} packages, {M} source files
**Spec-Code gaps**: {N} specs without code, {M} code without specs
**Decisions**: {N} architecture decisions across {M} changes → ADR documents
**Components**: {N} logical components identified → DESIGN component model
**Features**: {N} task categories → DECOMPOSITION feature entries

Estimated Constructor Studio artifacts:
- 1 PRD document (~{N} FR IDs, ~{M} NFR IDs)
- 1 DESIGN document (~{N} component IDs, ~{M} principle IDs)
- {N} ADR documents
- 1 DECOMPOSITION document (~{N} feature entries)
- {N} FEATURE documents (one per DECOMPOSITION feature)
- Code markers across ~{N} source files

**Proceed?** [yes/no/modify scope]
```

**MUST**: Get user confirmation before proceeding to Phase 2.

**Review gate**: User reviews scope and approves or adjusts.

---

## Phase 2: Generate PRD

**Goal**: Convert OpenSpec main specs and proposals into a Constructor Studio PRD, verified against the actual codebase.

### Dependencies

ALWAYS load before generating:
- Template: `{prd_template}`
- Rules: `{prd_rules}`
- Checklist: `{prd_checklist}`
- Example: `{prd_example}`

### Step 2.1: Extract Purpose & Background

**Source**: `{openspec_root}/config.yaml` → `context` field + earliest proposals
**Target**: PRD §1 Overview (Purpose, Background, Goals, Glossary)

1. Read `{openspec_root}/config.yaml` `context` field → extract project description
2. Read 3-5 earliest archived proposals → extract founding "Why" sections
3. Synthesize into PRD Overview sections using imperative language

**Transformation rules**:
- `config.yaml` context → PRD §1.1 Purpose (max 2 paragraphs, no implementation details)
- Proposal "Why" sections → PRD §1.2 Background / Problem Statement
- Proposal "What Changes" patterns → PRD §1.3 Goals (make measurable: baseline + target + timeframe)
- Technical terms from specs → PRD §1.4 Glossary (define all domain-specific terms)

### Step 2.2: Extract Actors

**Source**: OpenSpec specs that reference user roles, system actors
**Target**: PRD §2 Actors

1. Scan all main specs for actor references (developer, end-user, build system, runtime, etc.)
2. Create `cpt-{system}-actor-{slug}` ID for each distinct actor
3. Write actor descriptions with responsibilities and interaction patterns

**Transformation rules**:
- Scan specs for actor references and create one `cpt-{system}-actor-{slug}` per distinct actor found
- Each actor gets: Name, Description, Key interactions, Relevant capabilities

### Step 2.3: Extract Functional Requirements (Code-Verified)

**Source**: Each `{openspec_root}/specs/*/spec.md` → `### Requirement:` headings
**Verification**: Actual source code in `{codebase_paths}`
**Target**: PRD §5 Functional Requirements with `cpt-{system}-fr-*` IDs

For each main spec capability:

1. Read the spec file
2. For each `### Requirement:` heading:
   a. Generate ID: `cpt-{system}-fr-{slug}`
   b. **Locate the implementing code** — find the source file(s) in `{codebase_paths}` that implement this requirement
   c. **Verify** — read the code and confirm the requirement matches actual behavior
   d. Apply [Code Verification Protocol](#code-verification-protocol) classification
   e. Convert requirement description to RFC 2119 language (MUST, MUST NOT, MAY)
   f. Reference at least one actor from §2
   g. Add priority (`p1`-`p3`) based on: core functionality = p1, extensions = p2, nice-to-have = p3
   h. Include rationale (from spec context or proposal)
3. Group requirements by domain area (PRD §5.x = one domain area)
4. **Add UNDOCUMENTED requirements** — for code behavior found during verification that no spec describes

**Transformation rules for normative language**:
- OpenSpec `SHALL` → keep as `MUST` (RFC 2119)
- OpenSpec `SHALL NOT` → keep as `MUST NOT`
- OpenSpec `MAY` → keep as `MAY`
- OpenSpec imperative statements without normative keywords → add `MUST` if core, `SHOULD` if recommended

**ID format**: `- [ ] \`p{N}\` - **ID**: \`cpt-{system}-fr-{slug}\``

### Step 2.4: Extract Non-Functional Requirements (Code-Verified)

**Source**: Performance constraints, error handling patterns, security requirements from specs
**Verification**: Actual implementation patterns in source code
**Target**: PRD §6 Non-Functional Requirements with `cpt-{system}-nfr-*` IDs

1. Scan specs for non-functional patterns:
   - Performance: timing constraints, bundle size limits, lazy loading requirements
   - Reliability: error recovery, fallback behavior, graceful degradation
   - Security: isolation, sandboxing, CSP compliance
   - Compatibility: browser support, TypeScript strictness, module formats
2. **Verify each against code** — confirm the constraint is actually enforced in the implementation
3. Generate `cpt-{system}-nfr-{category}-{slug}` IDs
4. Include measurable thresholds with units and conditions

### Step 2.5: Extract Remaining PRD Sections

**Source**: Various OpenSpec artifacts
**Target**: PRD §3 (Operational Concept), §4 (Scope), §7 (Public Interfaces), §8 (Use Cases), §9-12

| PRD Section | Source | Verification |
|---|---|---|
| §3 Operational Concept | `config.yaml` context, design files | Verify against build config, project structure |
| §4.1 In Scope | All spec capabilities | Verify each capability has code |
| §4.2 Out of Scope | Proposal "Non-Goals", design "Out of scope" | Confirm excluded items are actually absent from code |
| §7 Public Interfaces | Specs with API/type exports | **Verify against actual exports** in package entry points |
| §8 Use Cases | Spec scenarios | Cross-check against integration tests if they exist |
| §9 Acceptance Criteria | Spec scenarios with THEN clauses | Aggregate testable outcomes |
| §10 Dependencies | `package.json` or equivalent, design external deps | **Read actual dependency manifests** |
| §11 Assumptions | Design "Context" sections | Extract stated assumptions |
| §12 Risks | Proposal "Risks" sections | Aggregate with mitigation strategies |

### Step 2.6: Self-Check (PRD)

Before presenting to user, verify:

- [ ] All 12 required PRD sections present
- [ ] Every FR has: ID, priority, RFC 2119 language, actor reference, rationale
- [ ] Every FR classified as VERIFIED, ADJUSTED, NOT_IMPLEMENTED, or UNDOCUMENTED
- [ ] Every NFR has: ID, measurable threshold with units
- [ ] No placeholders (TODO, TBD, FIXME, [Description])
- [ ] All IDs follow `cpt-{system}-{kind}-{slug}` format
- [ ] All IDs unique (run `cfs list-ids` after write)
- [ ] Discrepancy log presented for this phase

**Review gate**: Present PRD summary + discrepancy log. Wait for user approval before proceeding.

---

## Phase 3: Generate DESIGN

**Goal**: Convert OpenSpec design artifacts and spec architecture into a Constructor Studio DESIGN document, verified against the actual codebase.

### Dependencies

ALWAYS load before generating:
- Template: `{design_template}`
- Rules: `{design_rules}`
- Checklist: `{design_checklist}`
- Example: `{design_example}`
- PRD (generated in Phase 2) — for cross-references

### Step 3.1: Extract Architecture Vision & Drivers

**Source**: `{openspec_root}/config.yaml` context, design files, PRD from Phase 2
**Target**: DESIGN §1 Architecture Overview

1. Synthesize architectural vision from config context (monorepo, layers, patterns, etc.)
2. Map PRD `fr` and `nfr` IDs → Architecture Drivers (coverage required)
3. Extract architecture layers from project configuration and verify against actual directory/package structure
4. **Verify layers against actual codebase structure** — confirm directories/packages match the described layers

**Transformation rules**:
- Every `cpt-{system}-fr-*` ID from PRD MUST appear in §1.2.a Functional Drivers
- Every `cpt-{system}-nfr-*` ID from PRD MUST appear in §1.2.b NFR Allocation
- Layer descriptions → §1.3 Architecture Layers

### Step 3.2: Extract Principles & Constraints (Code-Verified)

**Source**: Design files (implicit patterns), config context (explicit rules)
**Verification**: Actual code patterns in `{codebase_paths}`
**Target**: DESIGN §2 Principles & Constraints

1. Extract explicit principles from `{openspec_root}/config.yaml` architecture patterns and design files
2. **Verify each principle/constraint against code**:
   - Does the code actually follow the described patterns? Check for corresponding implementations
   - If a principle is violated in code, note the violation and document the actual pattern
3. Extract implicit principles from design decisions across archived changes
4. Each principle: ID, statement, rationale, examples

**ID format**: `cpt-{system}-principle-{slug}` and `cpt-{system}-constraint-{slug}`

### Step 3.3: Extract Component Model (Code-Verified)

**Source**: Main specs (each capability ≈ component), dependency manifests, codebase structure
**Verification**: Actual package/module structure, entry points, exports
**Target**: DESIGN §3.2 Component Model

For each logical component:

1. Generate `cpt-{system}-component-{slug}` ID
2. **Read the actual package/module** — examine its manifest, entry point, key source files
3. Write 4 required subsections based on what the code actually does:
   - **Why this component exists** (from spec Purpose + code analysis)
   - **Responsibility scope** (from actual exports and functionality)
   - **Responsibility boundaries** (what the code does NOT do — check imports to confirm)
   - **Related components** (from actual import graph between packages/modules)

**Mapping heuristic**:
- Each top-level package or module → one component (e.g., `cpt-{system}-component-{package-a}`, `cpt-{system}-component-{package-b}`)
- Cross-cutting capabilities → grouped component where appropriate
- UI capabilities → separate components under UI layer

### Step 3.4: Extract Remaining DESIGN Sections

| DESIGN Section | Source | Verification |
|---|---|---|
| §3.1 Domain Model | Spec TypeScript types, design type references | **Read actual TypeScript types** from source |
| §3.3 API Contracts | Specs with public API surfaces | **Read actual exports** from package entry points |
| §3.4 Internal Dependencies | Package dependency graph | **Read actual dependency manifests** or run dependency analysis |
| §3.5 External Dependencies | Dependency manifests | **Read actual root + package dependency manifests** |
| §3.6 Interactions & Sequences | Spec scenarios with multi-step flows | Verify sequence exists in code (function call chains) |
| §3.7 Database schemas | Scan codebase for database code; if none found, mark N/A with verification note | Confirm by searching for database-related imports and files |

### Step 3.5: Self-Check (DESIGN)

- [ ] All required sections present per template
- [ ] Every PRD `fr` and `nfr` ID referenced in Architecture Drivers (coverage check)
- [ ] Every PRD `interface` and `contract` ID referenced in API Contracts (coverage check)
- [ ] All component IDs have 4 required subsections
- [ ] Component descriptions match actual code behavior
- [ ] No code snippets in DESIGN (MUST NOT HAVE)
- [ ] No placeholders
- [ ] Discrepancy log updated for this phase

**Review gate**: Present DESIGN summary + cumulative discrepancy log. Wait for user approval.

---

## Phase 4: Generate ADRs

**Goal**: Convert OpenSpec design decisions into Constructor Studio ADR documents.

### Dependencies

ALWAYS load before generating:
- Template: `{adr_template}`
- Rules: `{adr_rules}`
- Checklist: `{adr_checklist}`
- Example: `{adr_example}`
- DESIGN (generated in Phase 3) — ADR IDs must appear in DESIGN drivers

### Step 4.1: Extract Decisions

Scan all `{openspec_root}/changes/archive/*/design.md` files for `### Decision` headings:

1. For each decision:
   a. Assess ADR-worthiness: technology choices, architectural patterns, integration approaches = YES; variable naming, file organization = NO
   b. If ADR-worthy, extract: context, choice, rationale, alternatives considered
   c. **Verify the decision is still in effect** — check if the code reflects this decision or if it was later reversed
   d. Generate ID: `cpt-{system}-adr-{slug}`
   e. Assign sequential number: `NNNN-{slug}.md`

### Step 4.2: Write ADR Documents

For each ADR-worthy decision:

1. Create file at `{artifacts_output}/ADR/{NNNN}-{slug}.md`
2. Include required YAML frontmatter:
   ```yaml
   ---
   status: accepted
   date: {original-decision-date-from-change-archive}
   ---
   ```
   If code verification shows the decision was reversed: use `status: deprecated` or `status: superseded`.
3. Fill all required sections:
   - H1: Problem + chosen solution title
   - Context and Problem Statement (from change proposal "Why" + design "Context")
   - Decision Drivers (from rationale)
   - Considered Options (from "Alternatives considered")
   - Decision Outcome (choice + rationale)
   - Consequences (good, bad, neutral)
   - Confirmation (how to verify the decision holds — **include specific code locations**)
   - Pros and Cons of the Options (structured comparison)

**Transformation rules for OpenSpec → ADR**:
- `**Choice:** X` → Decision Outcome: "Chosen option: X"
- `**Rationale:** Y` → fold into Decision Outcome explanation
- `**Alternatives considered:** A, B` → Considered Options list + Pros/Cons section
- If no alternatives documented → note "Alternatives not documented in original design" under More Information

### Step 4.3: Register ADR IDs in DESIGN

After creating ADRs, update DESIGN §1.2 Architecture Drivers to reference all `cpt-{system}-adr-*` IDs.

### Step 4.4: Self-Check (ADRs)

For each ADR:
- [ ] Required frontmatter present (status, date)
- [ ] All required sections present (no numbered headings)
- [ ] ID unique and follows `cpt-{system}-adr-{slug}` format
- [ ] Status reflects reality (accepted if code follows decision, deprecated/superseded if not)
- [ ] Confirmation section includes actual code paths
- [ ] Referenced in DESIGN Architecture Drivers

**Review gate**: Present ADR list with statuses + discrepancy log. Wait for user approval.

---

## Phase 5: Generate DECOMPOSITION

**Goal**: Create the feature manifest bridging DESIGN to implementation.

### Dependencies

ALWAYS load before generating:
- Template: `{decomposition_template}`
- Rules: `{decomposition_rules}`
- Checklist: `{decomposition_checklist}`
- Example: `{decomposition_example}`
- PRD + DESIGN (from Phases 2-3) — for cross-references

### Step 5.1: Define Feature Boundaries

**Source**: OpenSpec task categories, spec capability groupings, DESIGN components
**Verification**: Actual package/module boundaries in code
**Target**: DECOMPOSITION §2 Entries

Feature decomposition strategy:

1. Group by implementation unit (each logical feature = independently implementable)
2. Map OpenSpec task categories (`## N. Category` in `tasks.md`) → feature candidates
3. **Verify feature boundaries align with actual code module boundaries** — a feature should map to a cohesive set of source files
4. Cross-reference with DESIGN components to ensure 100% coverage
5. Assign `cpt-{system}-feature-{slug}` IDs

**Coverage enforcement (CRITICAL)**:
- Every `cpt-{system}-component-*` from DESIGN MUST appear in at least one feature
- Every `cpt-{system}-principle-*` from DESIGN MUST appear in at least one feature
- Every `cpt-{system}-constraint-*` from DESIGN MUST appear in at least one feature

### Step 5.2: Write Feature Entries

For each feature entry (H3 heading):

```markdown
### 2.{N} [{Feature Title}](features/feature-{slug}/) ⏳ {PRIORITY}

- [ ] `p{N}` - **ID**: `cpt-{system}-feature-{slug}`

**Purpose**: {synthesized from spec capabilities + task descriptions}

**Depends On**: {feature IDs or "None"}

**Scope**:
- {in-scope items from related specs}

**Out of scope**:
- {exclusions}

**Requirements Covered**:
- [ ] `cpt-{system}-fr-{...}` — {requirement name}

**Design Principles Covered**:
- [ ] `cpt-{system}-principle-{...}` — {principle name}

**Design Constraints Covered**:
- [ ] `cpt-{system}-constraint-{...}` — {constraint name}

**Domain Model Entities**:
- {entity names from DESIGN domain model}

**Design Components**:
- [ ] `cpt-{system}-component-{...}` — {component name}

**API**:
- {public API endpoints or CLI commands}

**Sequences**:
- [ ] `cpt-{system}-seq-{...}` — {sequence name}

**Data**:
- {summary of data concerns, or "N/A" with verification note if no data layer found in codebase}
```

### Step 5.3: Add Overall Status

```markdown
- [ ] `p1` - **ID**: `cpt-{system}-status-overall`
```

Checkbox cascade: all feature checkboxes checked → overall status checked.

### Step 5.4: Self-Check (DECOMPOSITION)

- [ ] 100% DESIGN element coverage (every component, principle, constraint, seq in at least one feature)
- [ ] No scope overlap between features without explicit justification
- [ ] Each feature has all required fields (Purpose, Depends On, Scope, Out of scope, all reference sections)
- [ ] Feature boundaries align with actual code module boundaries
- [ ] Acyclic dependency graph
- [ ] All checkboxes unchecked (will be checked as code markers are placed in Phase 7)

**Review gate**: Present DECOMPOSITION summary + coverage table. Wait for user approval.

---

## Phase 6: Generate FEATURE Specs

**Goal**: Create detailed CDSL-based feature specifications, verified against actual code behavior.

### Dependencies

ALWAYS load before generating:
- Template: `{feature_template}`
- Rules: `{feature_rules}`
- Checklist: `{feature_checklist}`
- Example: `{feature_example}`
- DECOMPOSITION (from Phase 5) — for feature IDs and scope
- Relevant OpenSpec specs — for Given/When/Then scenarios

### Step 6.1: Convert Scenarios to CDSL Flows (Code-Verified)

For each feature in DECOMPOSITION:

1. Identify relevant OpenSpec specs (from feature's Requirements Covered references)
2. Read spec scenarios (`#### Scenario:` headings with Given/When/Then)
3. **Read the implementing code** for this feature
4. **Verify each scenario step exists in code** — find the actual function/method that performs it
5. Convert to CDSL notation, using the code's actual behavior:

**Transformation rules (Given/When/Then → CDSL)**:

```
OpenSpec:                              Constructor Studio CDSL:
#### Scenario: User Login     →   ### 2.1 User Login Flow
- GIVEN user has credentials  →   1. [ ] - `p1` - Verify credentials exist - `inst-login-verify`
- WHEN user submits form      →   2. [ ] - `p1` - Accept form submission - `inst-login-submit`
- THEN session is created     →   3. [ ] - `p1` - Create user session - `inst-login-session`
- AND token is returned       →   4. [ ] - `p1` - Return auth token - `inst-login-token`
```

**If code behavior differs from spec scenario**: Write the CDSL flow based on what the code does. Log the discrepancy.

**CDSL control flow mapping**:
- OpenSpec conditional scenarios → `**IF** {condition}` with nested steps
- OpenSpec iteration patterns → `**FOR EACH** {item} in {collection}`
- OpenSpec error scenarios → `**TRY**` / `**CATCH** {error}`
- OpenSpec state transitions → `**FROM** {State1} **TO** {State2} **WHEN** {condition}`

### Step 6.2: Generate Flow, Algo, State IDs

For each FEATURE document:

| CDSL Section | ID Kind | Format |
|---|---|---|
| §2 Actor Flows | `flow` | `cpt-{system}-flow-{feature}-{slug}` |
| §3 Processes | `algo` | `cpt-{system}-algo-{feature}-{slug}` |
| §4 States | `state` | `cpt-{system}-state-{feature}-{slug}` |
| §5 DoD entries | `dod` | `cpt-{system}-dod-{feature}-{slug}` |

All `flow`, `algo`, `state`, and `dod` IDs have `to_code = true` — they will require `@cpt-{kind}:{id}:p{N}` markers in Phase 7.

### Step 6.3: Write FEATURE Documents

For each feature, create `{artifacts_output}/features/feature-{slug}/FEATURE.md`:

1. H1: `Feature: {Feature Name}`
2. `featstatus` ID line directly under H1:
   ```
   - [ ] `p1` - **ID**: `cpt-{system}-featstatus-{slug}`
   ```
3. §1 Feature Context: Overview, Purpose (reference PRD fr/nfr IDs), Actors, References
   - FEATURE files are nested two levels deep (`features/feature-{slug}/FEATURE.md`), so relative cross-references must use `../../`:
     - PRD: `../../PRD.md`
     - DESIGN: `../../DESIGN.md`
4. §2 Actor Flows: CDSL flows converted from spec scenarios and verified against code
5. §3 Processes: Business logic algorithms extracted from actual code behavior
6. §4 States: State machines for stateful entities (if applicable, or "No state machines for this feature")
7. §5 Definitions of Done: Each DoD entry references PRD fr/nfr and DESIGN constraints
8. §6 Acceptance Criteria: Testable assertions from spec THEN clauses, verified against code

### Step 6.4: Self-Check (FEATURE)

For each FEATURE:
- [ ] `featstatus` ID present directly under H1
- [ ] All CDSL steps use correct notation: `N. [ ] - \`pN\` - {Description} - \`inst-{step-id}\``
- [ ] All CDSL flows verified against actual code behavior
- [ ] All flow/algo/state IDs unique
- [ ] No system-level type redefinitions (MUST NOT HAVE)
- [ ] No code snippets (MUST NOT HAVE)
- [ ] DoD entries reference PRD and DESIGN IDs
- [ ] FEATURE references match DECOMPOSITION feature ID

**Review gate**: Present each FEATURE summary (or batch if small). Wait for user approval.

---

## Phase 7: Place Code Markers

**Goal**: Add `@cpt-*` traceability markers to source files, linking code to verified FEATURE specs.

### Step 7.1: Plan Marker Placement

For each FEATURE document, identify where markers should go:

1. Read the FEATURE's CDSL flows, algorithms, and states
2. For each `to_code = true` ID (`flow`, `algo`, `state`, `dod`):
   a. Find the source file(s) and function(s) that implement it (already identified during Phase 6 verification)
   b. Plan marker placement: which file, which line, which marker

**Marker format**:
```
@cpt-{kind}:{cpt-id}:p{N}
```

**Placement rules**:
- Place markers as comments near the implementing code (function/method level)
- Use the language's comment syntax: `// @cpt-flow:cpt-{system}-flow-routing-navigate:p1` for TypeScript
- One marker per implementing function/block — do not scatter across lines
- If one function implements multiple steps, use multiple markers on adjacent comment lines

### Step 7.2: Place Markers (Per Feature)

Process one feature at a time. For each feature:

1. Read the FEATURE spec to get all `to_code` IDs
2. For each ID, add the marker comment to the implementing source file
3. After placing all markers for one feature, check the FEATURE's `featstatus` checkbox:
   - If ALL `to_code` IDs for this feature have markers → check `featstatus` as `[x]`
   - Update DECOMPOSITION: check the corresponding feature entry as `[x]`

**MUST NOT**:
- Modify any code logic — only add comment markers
- Place markers on code that doesn't actually implement the requirement
- Guess at marker placement — every marker must be verified against the FEATURE spec

### Step 7.3: Self-Check (Code Markers)

After placing markers for all features:

- [ ] Every `to_code = true` ID from every FEATURE has a corresponding `@cpt-*` marker in source code
- [ ] No orphan markers (markers referencing IDs that don't exist in any FEATURE)
- [ ] No duplicate markers (same marker on multiple unrelated code locations)
- [ ] All `featstatus` checkboxes reflect actual marker coverage
- [ ] DECOMPOSITION `status-overall` reflects actual feature status

**Review gate**: Present a marker placement summary per feature (file paths + marker count). Wait for user approval.

---

## Phase 8: Register & Validate

**Goal**: Register all generated artifacts in Constructor Studio with FULL traceability and run validation.

### Step 8.1: Update artifacts.toml

Update `{cf-studio-path}/config/artifacts.toml` with all artifacts and **FULL traceability**:

```toml
[[systems]]
name = "{system}"
slug = "{system}"
kit = "{kit_slug}"

[[systems.artifacts]]
path = "{artifacts_output}/PRD.md"
kind = "PRD"
traceability = "FULL"

[[systems.artifacts]]
path = "{artifacts_output}/DESIGN.md"
kind = "DESIGN"
traceability = "FULL"

[[systems.artifacts]]
path = "{artifacts_output}/DECOMPOSITION.md"
kind = "DECOMPOSITION"
traceability = "FULL"

# One [[systems.artifacts]] block per ADR file:
[[systems.artifacts]]
path = "{artifacts_output}/ADR/0001-example-decision.md"
kind = "ADR"
traceability = "FULL"

# ... repeat for each ADR generated in Phase 4

# One [[systems.artifacts]] block per FEATURE file:
[[systems.artifacts]]
path = "{artifacts_output}/features/feature-example/FEATURE.md"
kind = "FEATURE"
traceability = "FULL"

# ... repeat for each FEATURE generated in Phase 6
```

**Note**: ADR and FEATURE entries must be enumerated individually — one `[[systems.artifacts]]` block per file. Glob patterns are not valid in `artifacts.toml`.

Add one `[[systems.codebase]]` entry per source directory discovered from `{codebase_paths}`:
```toml
[[systems.codebase]]
path = "packages/"

[[systems.codebase]]
path = "src/"

# ... one entry per path from artifacts.toml systems[].codebase[]
```

### Step 8.2: Run Deterministic Validation

```bash
python3 {cf-studio-path}/.core/skills/cf-studio/scripts/cfs.py validate
```

**MUST**: Fix all validation errors before proceeding. Re-run until `"status": "PASS"`.

Common validation issues during migration:
- Missing cross-references (PRD FR not in DESIGN drivers) → add missing references
- Duplicate IDs → rename with more specific slugs
- Missing required sections → fill from OpenSpec sources or mark N/A with reasoning
- Invalid ID format → fix to `cpt-{system}-{kind}-{slug}`
- Orphan code markers → remove marker or add missing FEATURE ID
- Missing code markers for `to_code` IDs → add markers or mark ID as not-yet-implemented

### Step 8.3: Run Spec Coverage

```bash
python3 {cf-studio-path}/.core/skills/cf-studio/scripts/cfs.py spec-coverage
```

Report coverage percentage. Target: 100% of `to_code` IDs covered.

### Step 8.4: Run TOC Generation

```bash
python3 {cf-studio-path}/.core/skills/cf-studio/scripts/cfs.py toc {artifacts_output}/PRD.md {artifacts_output}/DESIGN.md {artifacts_output}/DECOMPOSITION.md
```

NEVER write TOC manually — always use `cfs toc`.

### Step 8.5: Generate Migration Report

```markdown
## Migration Report

### OpenSpec → Constructor Studio Coverage

| OpenSpec Source | Items | Migrated | Coverage |
|---|---|---|---|
| Main spec requirements | {N} | {M} | {%} |
| Design decisions | {N} | {M} ADRs | {%} |
| Task categories | {N} | {M} features | {%} |
| Spec scenarios | {N} | {M} CDSL flows | {%} |

### Code Verification Results

| Classification | Count | Percentage |
|---|---|---|
| VERIFIED (spec matches code) | {N} | {%} |
| ADJUSTED (spec updated to match code) | {N} | {%} |
| NOT_IMPLEMENTED (spec aspirational) | {N} | {%} |
| UNDOCUMENTED (code without spec) | {N} | {%} |

### Traceability Coverage

| Chain Link | Source IDs | Target References | Coverage |
|---|---|---|---|
| PRD fr → DESIGN drivers | {N} | {M} | {%} |
| PRD nfr → DESIGN drivers | {N} | {M} | {%} |
| DESIGN component → DECOMP | {N} | {M} | {%} |
| DECOMP feature → FEATURE | {N} | {M} | {%} |
| FEATURE → CODE markers | {N} | {M} | {%} |
| ADR → DESIGN drivers | {N} | {M} | {%} |

### Discrepancy Log (Full)

{Complete table of all ADJUSTED, NOT_IMPLEMENTED, and UNDOCUMENTED items from all phases}

### Unmigrated Items

{List any OpenSpec content not captured in Constructor Studio artifacts, with rationale}
```

**Review gate**: Present final migration report. Wait for user approval.

---

## Phase Execution Order

Phases MUST execute in order. Each phase depends on the previous phase's output.

```
Phase 1: Inventory & Analysis     → Scope confirmation
Phase 2: Generate PRD             → PRD.md with code-verified fr/nfr/actor IDs
Phase 3: Generate DESIGN          → DESIGN.md with code-verified components
Phase 4: Generate ADRs            → ADR/*.md with verified decision statuses
Phase 5: Generate DECOMPOSITION   → DECOMPOSITION.md with feature entries
Phase 6: Generate FEATURE specs   → features/*/FEATURE.md with code-verified CDSL
Phase 7: Place Code Markers       → @cpt-* markers in source files
Phase 8: Register & Validate      → artifacts.toml (FULL), validation PASS, migration report
```

**Checkpoint policy**: After each phase, output a brief status to chat. Only write checkpoint files if context capacity is at risk.

**Review gates**: Every phase ends with a review gate. The agent stops and waits for user approval before proceeding. The user reviews the diff independently and tells the agent to continue.

---

## Error Handling

### Incomplete OpenSpec Source

**If an OpenSpec spec has TBD sections**:
- Check if the code implements the capability anyway
- If code exists: write the FR based on code behavior, note "Spec was TBD, FR derived from code"
- If no code: mark as NOT_IMPLEMENTED with note: "Source spec incomplete, no implementation found"
- Do NOT invent requirements — describe what exists or flag for user review

### Conflicting Information

**If proposal and spec contradict**:
- **Code is authoritative** — describe what the code does
- Note the conflict in the discrepancy log
- Ask user to resolve if the conflict affects architecture

### Missing Design Artifacts

**If a capability has no design.md**:
- Extract architecture from the actual code (imports, patterns, module structure)
- Mark DESIGN components with note: "Derived from code analysis — no explicit design artifact"
- Flag for architect review

### ID Collision

**If generated IDs conflict with existing IDs**:
- Run `cfs list-ids` to check uniqueness
- Append disambiguating suffix (e.g., `-v2`, `-alt`)
- Never silently overwrite existing IDs

### Code Marker Conflicts

**If a source file already has comments or markers that would conflict**:
- Place `@cpt-*` markers on separate comment lines (do not merge with existing comments)
- If a function is too small for a separate marker comment, place the marker on the function's JSDoc/docblock

---

## Appendix: OpenSpec Format Reference

This section provides the OpenSpec document format for agents unfamiliar with the source artifacts.

### Directory Structure

```
{openspec_root}/
  config.yaml                              # Project-level config
  specs/                                   # Main specs (living specifications)
    <capability-name>/
      spec.md                              # The canonical spec for this capability
  changes/                                 # Active changes (in progress)
    <change-name>/
      .openspec.yaml                       # Change metadata (newer changes only)
      proposal.md                          # Why + scope
      design.md                            # How (optional)
      tasks.md                             # Implementation checklist
      specs/                               # Delta specs (optional)
        <capability-name>/
          spec.md                          # What changes about this capability
    archive/                               # Completed changes
      YYYY-MM-DD-<change-name>/            # Same structure as active changes
```

### Main Spec Format (`specs/<capability>/spec.md`)

```markdown
# <capability-name> Specification

## Purpose
<1-3 sentence description>

## Requirements

### Requirement: <Requirement Name>
<Description using normative language — SHALL, SHALL NOT, MAY>

#### Scenario: <Scenario Name>
- **GIVEN** <precondition>        (optional)
- **WHEN** <trigger condition>
- **THEN** <expected outcome>
- **AND** <additional outcome>    (zero or more)
```

### Change Artifact Formats

**Proposal (`proposal.md`)**:
- `## Why` — problem/opportunity
- `## What Changes` — bullet points
- `## Capabilities` — new/modified capabilities
- `## Impact` — affected areas
- Optional: `## Future Work`, `## Dependencies`, `## Risks`

**Design (`design.md`)**:
- `## Context` — current state
- `## Decisions` (or `## Architecture Decisions`)
  - `### Decision N: <Title>` with `**Choice:**`, `**Rationale:**`, `**Alternatives considered:**`
- Optional: `## File Map`, `## Risks / Trade-offs`

**Tasks (`tasks.md`)**:
- `## N. <Category>` — grouped by module/concern
- `- [ ]` pending, `- [x]` complete, `- [-]` dropped (with reason)
- Numbered: `<section>.<sequence>` (e.g., 1.1, 1.2)

### Config Format (`config.yaml`)

```yaml
schema: spec-driven
context: |
  <project description injected into AI agent instructions>
rules:
  proposal:
    - <rule for proposals>
  specs:
    - <rule for specs>
  design:
    - <rule for designs>
```

---

## Validation Criteria

- [ ] All 8 phases completed
- [ ] PRD generated with all 12 required sections, code-verified
- [ ] DESIGN generated with all required sections, code-verified, PRD coverage complete
- [ ] ADRs generated for all ADR-worthy decisions with required frontmatter and verified statuses
- [ ] DECOMPOSITION generated with 100% DESIGN element coverage
- [ ] FEATURE specs generated for all DECOMPOSITION features with code-verified CDSL notation
- [ ] `@cpt-*` code markers placed for all `to_code = true` IDs
- [ ] All artifacts registered in `artifacts.toml` with `traceability = "FULL"`
- [ ] `cfs validate` returns PASS
- [ ] `cfs spec-coverage` reports target coverage
- [ ] TOC generated by `cfs toc` (not manual)
- [ ] Migration report produced with discrepancy log
- [ ] No placeholders (TODO, TBD, FIXME) in final artifacts
- [ ] All IDs follow `cpt-{system}-{kind}-{slug}` format
- [ ] Traceability chain complete: PRD → DESIGN → DECOMPOSITION → FEATURE → CODE
