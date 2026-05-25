---
studio: true
type: spec
name: Rules Specification
version: 2.0
purpose: Define the format, structure, and usage of rules.md kit files
drivers:
  - cpt-studio-fr-core-kits
  - cpt-studio-fr-core-workflows
---

# Rules Specification (rules.md)


<!-- toc -->

- [Overview](#overview)
- [File Location and Discovery](#file-location-and-discovery)
  - [Kit Resolution](#kit-resolution)
  - [Kit Directory Context](#kit-directory-context)
  - [Artifact Type Detection](#artifact-type-detection)
- [File Structure](#file-structure)
- [Rules.md Format](#rulesmd-format)
  - [Strict Section Order](#strict-section-order)
- [Section Reference](#section-reference)
  - [Section Kinds](#section-kinds)
  - [Sub-Sections](#sub-sections)
  - [Content Format](#content-format)
  - [Dependencies Header](#dependencies-header)
- [Workflow Interaction Protocol](#workflow-interaction-protocol)
  - [Generate Workflow](#generate-workflow)
  - [Analyze (Validate) Workflow](#analyze-validate-workflow)
- [Parsing Rules.md](#parsing-rulesmd)
  - [Dependencies Extraction](#dependencies-extraction)
  - [Section Extraction](#section-extraction)
  - [Task Item Extraction](#task-item-extraction)
- [Example: Generated rules.md](#example-generated-rulesmd)
- [Error Handling](#error-handling)
  - [Rules.md Not Found](#rulesmd-not-found)
  - [Rules.md Parse Error](#rulesmd-parse-error)
  - [Missing Dependency File](#missing-dependency-file)
  - [Unknown Artifact Type](#unknown-artifact-type)
- [Validation Checklist](#validation-checklist)
  - [Structure (S)](#structure-s)
  - [Content (C)](#content-c)
  - [Consistency (X)](#consistency-x)
- [References](#references)

<!-- /toc -->

---
---

## Overview

`rules.md` is the **single entry point** for generate and analyze workflows. It is a kit file authored by kit authors and user-editable after installation.

**Key properties**:
- Kit file — user-editable, preserved across kit updates via file-level diff
- Strictly structured: six section kinds in fixed order
- All content is task-list format (`- [ ] ...`)
- Entry point for both `generate` and `analyze` (validate) workflows

**Location**: `{cf-studio-path}/config/kits/<slug>/artifacts/<KIND>/rules.md`

---

## File Location and Discovery

### Kit Resolution

1. Find system for target artifact in `{cf-studio-path}/config/artifacts.toml`
2. Get `kit` ID from system (e.g., `"studio-sdlc"`)
3. Resolve kit slug from `{cf-studio-path}/config/core.toml` (e.g., `"sdlc"`)
4. Build full path: `{cf-studio-path}/config/kits/{slug}/artifacts/{KIND}/rules.md`

### Kit Directory Context

```
config/kits/<slug>/
├── conf.toml                 # Kit version metadata
├── constraints.toml          # Kit-wide structural constraints
├── SKILL.md                  # Per-kit skill instructions
├── artifacts/<KIND>/
│   ├── rules.md              # Workflow entry point (this file)
│   ├── template.md           # Heading structure
│   ├── checklist.md          # Quality checklist
│   └── examples/example.md   # Concrete example
├── codebase/
│   ├── rules.md              # Codebase agent rules
│   └── checklist.md          # Codebase quality checklist
└── workflows/                # Workflow definitions
```

### Artifact Type Detection

Workflows determine artifact type from:

1. **Explicit parameter**: `cfs generate PRD`
2. **From artifacts.toml**: lookup artifact by path → get `kind`
3. **Codebase**: if path matches `codebase[].path` → CODE

---

## File Structure

> **Legacy note**: In the previous blueprint-based model, `rules.md` was generated from `@cpt:rules` and `@cpt:rule` markers. In the current model, `rules.md` is authored directly by kit authors. See [blueprint.md](blueprint.md) (DEPRECATED) for legacy marker reference.

`rules.md` follows the strict six-section structure defined below. Kit authors maintain this file directly.

---

## Rules.md Format

### Strict Section Order

Every `rules.md` follows this exact structure:

```markdown
# {KIND} Rules

**Artifact**: {KIND}
**Kit**: {kit-slug}

**Dependencies**:
- `template.md` — structural reference
- `checklist.md` — semantic quality criteria
- `examples/example.md` — reference implementation

---

## Prerequisites

### Load Dependencies
- [ ] Load `template.md` for structure
- [ ] Load `checklist.md` for semantic guidance
- [ ] Load `examples/example.md` for reference style

---

## Requirements

### Structural
- [ ] requirement 1
- [ ] requirement 2

### Semantic
- [ ] semantic requirement 1
  - VALID: "good example"
  - INVALID: "bad example"

---

## Tasks

### Content Creation
- [ ] task 1
- [ ] task 2

### IDs and Structure
- [ ] Generate IDs following `cpt-{system}-{kind}-{slug}` convention
- [ ] Verify ID uniqueness

---

## Validation

### Structural
- [ ] validation check 1

### Semantic
- [ ] validation check 2

---

## Error Handling

### Recovery Options
- [ ] If structural validation fails → fix heading structure first
- [ ] If ID validation fails → check ID format and uniqueness

---

## Next Steps

### Options
- [ ] Run `cfs validate` to verify artifact
- [ ] Proceed to next artifact in pipeline
```

---

## Section Reference

### Section Kinds

The six section kinds always appear in this fixed order:

| # | Kind | H2 Heading | Purpose |
|---|------|-----------|---------|
| 1 | `prerequisites` | `## Prerequisites` | Files to load before starting |
| 2 | `requirements` | `## Requirements` | Rules the artifact MUST satisfy |
| 3 | `tasks` | `## Tasks` | Steps to execute during generation |
| 4 | `validation` | `## Validation` | Checks to run after generation |
| 5 | `error_handling` | `## Error Handling` | Recovery procedures for failures |
| 6 | `next_steps` | `## Next Steps` | Available actions after completion |

### Sub-Sections

Each kind contains one or more sub-sections (H3 headings):

```toml
[prerequisites]
sections = ["load_dependencies"]

[requirements]
sections = ["structural", "semantic"]

[tasks]
sections = ["content_creation", "ids_and_structure"]

[validation]
sections = ["structural", "semantic"]

[error_handling]
sections = ["recovery_options"]

[next_steps]
sections = ["options"]
```

Sub-section names are converted to title-case H3 headings: `load_dependencies` → `### Load Dependencies`.

### Content Format

All content within sub-sections is **strictly task lists**:

```markdown
- [ ] Rule or task text
```

Rules may include `VALID`/`INVALID` example sub-items for semantic rules:

```markdown
- [ ] Purpose MUST explain WHY the product exists
  - VALID: "Enables developers to validate artifacts" (explains purpose)
  - INVALID: "A tool for Studio" (doesn't explain why it matters)
```

### Dependencies Header

Every `rules.md` starts with a **Dependencies** block (before the first `---`). This declares sibling files that workflows must load:

```markdown
**Dependencies**:
- `template.md` — structural reference
- `checklist.md` — semantic quality criteria
- `examples/example.md` — reference implementation
- `taxonomy.md` — kit taxonomy (optional, sibling to artifacts/)
```

Format: `` `path` — description ``. All paths are relative to the same kit config directory (`{cf-studio-path}/config/kits/{slug}/`).

**taxonomy.md** is an optional dependency — generated by `cfs generate-resources` at `{cf-studio-path}/config/kits/{slug}/taxonomy.md`. It provides artifact kind definitions, ID type descriptions, and cross-artifact traceability context. Workflows MAY use it to understand the kit's naming conventions and artifact relationships.

---

## Workflow Interaction Protocol

### Generate Workflow

```
1. DETECT artifact type (explicit parameter or from artifacts.toml)
   ↓
2. RESOLVE kit:
   - Find system in {cf-studio-path}/config/artifacts.toml
   - Get kit ID → resolve path from config/core.toml
   ↓
3. LOAD rules.md from .gen/kits/{slug}/artifacts/{KIND}/rules.md
   ↓
4. PARSE Dependencies → LOAD sibling files:
   - template.md → structural reference
   - checklist.md → semantic guidance
   - example.md → style reference
   ↓
5. CONFIRM Prerequisites:
   - Agent loads all dependency files
   ↓
6. READ Requirements:
   - Agent reads and confirms understanding of all rules
   ↓
7. EXECUTE Tasks:
   - Execute each task item in order
   - Use loaded dependencies as context
   ↓
8. OUTPUT artifact
   ↓
9. SELF-VALIDATE using Validation section
   ↓
10. CHECK Error Handling if issues found
   ↓
11. PRESENT Next Steps
```

### Analyze (Validate) Workflow

```
1. DETECT artifact type from target file
   ↓
2. RESOLVE kit (same as generate)
   ↓
3. LOAD rules.md + dependencies
   ↓
4. EXECUTE Validation section:
   - Structural checks (deterministic, from constraints.toml)
   - Semantic checks (checklist-based, agent-driven)
   ↓
5. APPLY Requirements as validation criteria
   ↓
6. OUTPUT Validation Report
   ↓
7. PRESENT Error Handling + Next Steps if issues found
```

---

## Parsing Rules.md

### Dependencies Extraction

```regex
^\*\*Dependencies\*\*:\s*$
```

Following lines until `---`:
```regex
^-\s+`([^`]+)`\s+—\s+(.+)$
```
- Group 1: relative path to sibling file
- Group 2: description of the dependency's role

### Section Extraction

Each section starts with an H2 heading matching one of the six section kinds:

```regex
^## (Prerequisites|Requirements|Tasks|Validation|Error Handling|Next Steps)\s*$
```

Sub-sections start with H3 headings:
```regex
^### (.+)\s*$
```

### Task Item Extraction

Within each sub-section, collect task items:
```regex
^- \[ \] (.+)$
```

Optional VALID/INVALID sub-items:
```regex
^\s+- (VALID|INVALID): (.+)$
```

---

## Example: Generated rules.md

For a PRD artifact, `{cf-studio-path}/config/kits/sdlc/artifacts/PRD/rules.md`:

```markdown
# PRD Rules

**Artifact**: PRD
**Kit**: sdlc

**Dependencies**:
- `template.md` — structural reference
- `checklist.md` — semantic quality criteria
- `examples/example.md` — reference implementation

---

## Prerequisites

### Load Dependencies
- [ ] Load `template.md` for structure
- [ ] Load `checklist.md` for semantic guidance
- [ ] Load `examples/example.md` for reference style

---

## Requirements

### Structural
- [ ] Document MUST follow template.md heading structure
- [ ] All headings MUST match constraints.toml patterns
- [ ] All IDs MUST follow `cpt-{system}-{kind}-{slug}` convention

### Semantic
- [ ] Purpose MUST explain WHY the product exists
  - VALID: "Enables developers to validate artifacts" (explains purpose)
  - INVALID: "A tool for Studio" (doesn't explain why it matters)
- [ ] Vision MUST explain the target end-state
- [ ] Each functional requirement MUST be independently testable

---

## Tasks

### Content Creation
- [ ] Write Purpose and Vision sections
- [ ] Define actors and use cases
- [ ] Write functional requirements with IDs
- [ ] Write non-functional requirements with IDs

### IDs and Structure
- [ ] Generate IDs: `cpt-{system}-fr-{slug}`, `cpt-{system}-nfr-{slug}`, `cpt-{system}-actor-{slug}`
- [ ] Add priority markers to all requirements
- [ ] Add task checkboxes to all requirements
- [ ] Verify ID uniqueness

---

## Validation

### Structural
- [ ] All required headings present per template.md
- [ ] Heading numbering is sequential
- [ ] All IDs match `cpt-{system}-{kind}-{slug}` pattern

### Semantic
- [ ] Purpose section explains product value
- [ ] Each FR is independently testable
- [ ] No placeholder content (TODO, TBD, FIXME)

---

## Error Handling

### Recovery Options
- [ ] If structural validation fails → compare against template.md
- [ ] If ID format fails → check identifiers spec
- [ ] If semantic validation fails → review against checklist.md

---

## Next Steps

### Options
- [ ] Run `cfs validate` to verify the artifact
- [ ] Proceed to DESIGN artifact
```

---

## Error Handling

### Rules.md Not Found

```
⚠️ Rules not found: config/kits/{slug}/artifacts/{KIND}/rules.md
→ Fix: Run `cfs kit install` to install the kit, or verify kit installation
```
**Action**: STOP — cannot execute workflow without rules.

### Rules.md Parse Error

```
⚠️ Cannot parse rules.md: {path}
→ Error: {parse error}
→ Expected sections: Prerequisites, Requirements, Tasks, Validation, Error Handling, Next Steps
→ Fix: Restore from kit source with `cfs kit update --force`
```
**Action**: STOP — rules.md may have been manually modified.

### Missing Dependency File

```
⚠️ Dependency not found: {path}
→ Referenced in: rules.md Dependencies section
→ Fix: Run `cfs kit update --force` to restore kit files from source
```
**Action**: STOP — cannot proceed without required dependencies.

### Unknown Artifact Type

```
⚠️ No rules found for artifact type: {KIND}
→ Searched: config/kits/{slug}/artifacts/{KIND}/rules.md
→ Fix: Check that the kit supports this artifact kind
```
**Action**: STOP — cannot generate/validate without rules.

---

## Validation Checklist

**Use this checklist to validate a generated rules.md file.**

### Structure (S)

| # | Check | Required | How to Verify |
|---|-------|----------|---------------|
| S.1 | rules.md exists at correct path | YES | File at `{cf-studio-path}/config/kits/<slug>/artifacts/<KIND>/rules.md` |
| S.2 | Has Artifact and Kit header fields | YES | `**Artifact**:` and `**Kit**:` present |
| S.3 | Dependencies block present | YES | `**Dependencies**:` before first `---` |
| S.4 | All six section kinds present | YES | H2 headings: Prerequisites, Requirements, Tasks, Validation, Error Handling, Next Steps |
| S.5 | Section order is correct | YES | Kinds appear in fixed order (1→6) |
| S.6 | Each section has ≥1 sub-section | YES | At least one H3 heading per H2 |

### Content (C)

| # | Check | Required | How to Verify |
|---|-------|----------|---------------|
| C.1 | All content is task-list format | YES | Only `- [ ] ...` items (plus VALID/INVALID sub-items) |
| C.2 | Dependencies reference sibling files | YES | `template.md`, `checklist.md`, `examples/example.md` listed |
| C.3 | All referenced files exist | YES | Each path resolves to existing file |
| C.4 | Prerequisites loads all dependencies | YES | Load tasks for each dependency file |
| C.5 | Sub-sections follow standard structure | YES | All declared sections present |

### Consistency (X)

| # | Check | Required | How to Verify |
|---|-------|----------|---------------|
| X.1 | rules.md follows standard six-section structure | YES | Section kinds and sub-sections align |
| X.2 | All rules are complete and actionable | YES | Every rule has clear task-list items |

---

## References

- **Kit specification**: `{cf-studio-path}/.core/architecture/specs/kit/kit.md` — kit structure, installation, update model
- **Execution protocol**: `{cf-studio-path}/.core/requirements/execution-protocol.md` — workflow execution rules
- **Identifiers & Traceability**: `{cf-studio-path}/.core/architecture/specs/traceability.md` — ID formats, naming, code traceability
- **CLI**: `{cf-studio-path}/.core/architecture/specs/cli.md` — `generate`, `validate` commands
