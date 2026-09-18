---
studio: true
type: spec
name: Constraints Specification
version: 1.0
purpose: Define the format, structure, validation semantics, and usage of constraints.toml kit files
drivers:
  - cpt-studio-fr-core-kits
  - cpt-studio-fr-sdlc-validation
  - cpt-studio-component-validator
---

# Constraints Specification (constraints.toml)


<!-- toc -->

- [Overview](#overview)
- [Location](#location)
- [Constraint Structure](#constraint-structure)
- [File Format](#file-format)
  - [Root Structure](#root-structure)
  - [Heading Constraints](#heading-constraints)
  - [ID Constraints](#id-constraints)
  - [Reference Rules](#reference-rules)
- [Validation Semantics](#validation-semantics)
  - [Severity](#severity)
  - [TOC Options](#toc-options)
  - [Heading Validation](#heading-validation)
  - [ID Validation](#id-validation)
  - [Cross-Artifact Validation](#cross-artifact-validation)
- [Artifact Scanning](#artifact-scanning)
- [Full Example](#full-example)
- [Error Handling](#error-handling)

<!-- /toc -->

---
---

## Overview

`constraints.toml` is a kit-wide file that defines structural validation rules. It is authored by kit authors and user-editable after installation.

- Document outline constraints (heading patterns, levels, ordering)
- ID definition and reference validation rules
- Cross-artifact reference coverage rules

**Key properties**:
- Kit file — user-editable, preserved across kit updates via file-level diff
- Kit-wide: one file per kit, with per-artifact constraints grouped under `[artifacts.<KIND>]`
- Used by the Validator for deterministic structural checks

---

## Location

**Kit-wide**: `{cf-studio-path}/config/kits/<slug>/constraints.toml`

---

## Constraint Structure

> **Legacy note**: In the previous blueprint-based model, `constraints.toml` was generated from `@cpt:heading` and `@cpt:id` markers across all artifact blueprints. In the current model, `constraints.toml` is authored directly by kit authors. See [blueprint.md](blueprint.md) (DEPRECATED) for legacy marker reference.

`constraints.toml` defines per-artifact heading and ID constraints. Kit authors maintain this file directly.

---

## File Format

### Root Structure

```toml
# Kit-wide structural constraints
kit = "sdlc"

# Per-artifact constraints are grouped under [artifacts.<KIND>]

# Heading constraints (from @cpt:heading markers)
[[artifacts.PRD.headings]]
id = "prd-h1-title"
level = 1
required = true
pattern = "PRD\\s*[—–-]\\s*.+"

[[artifacts.PRD.headings]]
id = "prd-overview"
level = 2
required = true
numbered = true
pattern = "Overview"

# ID kind constraints (from @cpt:id markers)
[artifacts.PRD.identifiers.fr]
name = "Functional Requirement"
required = true
task = true
priority = true
to_code = true

[artifacts.PRD.identifiers.fr.ref.DESIGN]
coverage = true

[artifacts.PRD.identifiers.fr.ref.DECOMPOSITION]
# coverage omitted = optional

# Another artifact kind in the same file
[[artifacts.DESIGN.headings]]
id = "design-h1-title"
level = 1
required = true
pattern = "DESIGN\\s*[—–-]\\s*.+"
```

### Heading Constraints

Each `[[artifacts.<KIND>.headings]]` entry defines a constraint for one heading position in the artifact outline.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `id` | string | — | Stable identifier (from `@cpt:heading.id`) |
| `level` | integer 1–6 | — | Required heading level |
| `required` | boolean | `true` | Whether this heading must be present |
| `multiple` | boolean or omit | omit | `true` = required multiple, `false` = prohibited, omit = allowed |
| `numbered` | boolean or omit | omit | `true` = required, `false` = prohibited, omit = allowed |
| `pattern` | string (regex) | — | Applied to heading title text (excluding `#` markers and numbering prefix) |
| `description` | string | — | Human-readable description of section intent |
| `severity` | `error` / `warning` / `off` | code default | Severity for the rules this entry owns |
| `locked` | boolean | `false` | When true, a project may raise this entry's rules but not lower them |
| `prev` / `next` | string | auto | Neighbouring heading constraint ids. Auto-linked from declaration order; used in message text only — ordering is not enforced from them |

**Boolean convention**: `true` = required, `false` = prohibited, omit = optional/allowed.

### ID Constraints

Each `[artifacts.<KIND>.identifiers.<kind>]` table defines validation rules for one ID kind.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | — | Human-readable name |
| `description` | string | — | Description of the ID kind |
| `required` | boolean | `true` | Whether at least one ID of this kind must be defined |
| `task` | boolean or omit | omit | `true` = task checkbox required, `false` = prohibited, omit = allowed |
| `priority` | boolean or omit | omit | `true` = priority marker required, `false` = prohibited, omit = allowed |
| `to_code` | boolean | `false` | Whether this ID kind must be traceable to code |
| `headings` | array of strings | — | Heading constraint IDs where this ID kind must be defined |
| `severity` | `error` / `warning` / `off` | code default | Severity for the rules this ID-kind entry owns |
| `locked` | boolean | `false` | When true, a project may raise this entry's rules but not lower them |

### Reference Rules

Each `[artifacts.<KIND>.identifiers.<kind>.ref.<TARGET>]` sub-table defines cross-artifact reference rules.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `coverage` | boolean or omit | omit | `true` = required, `false` = prohibited, omit = optional |
| `task` | boolean or omit | omit | `true` = task on reference required, `false` = prohibited, omit = allowed |
| `priority` | boolean or omit | omit | `true` = priority on reference required, `false` = prohibited, omit = allowed |
| `headings` | array of strings | — | Heading constraint IDs where references must appear in the target artifact |

**Boolean convention**: same as everywhere — `true` = required, `false` = prohibited, omit = optional/allowed.

---

## Validation Semantics

### Severity

Every finding carries a `severity` of `error`, `warning` or `off`. `error` gates the run, `warning` is reported without gating, and `off` suppresses the finding — counted in the report's `suppressed_count`, never simply dropped.

A kit declares severity in three places, most specific first:

```toml
[validation.severity]                      # whole kit, per rule code
"toc-missing" = "warning"

[artifacts.PRD.validation.severity]        # one artifact kind, per rule code
"heading-number-not-consecutive" = "off"

[[artifacts.PRD.headings]]                 # one constraint entry
id = "prd-metrics"
severity = "warning"
locked = true
```

The root `[validation]` table is lifted out before the `artifacts` unwrap. In the legacy unwrapped layout the artifact kinds are root keys, so a `[validation]` table left in place would be read as an artifact kind named `VALIDATION` and fail the file to load.

**Resolution is two layers, not six.** The kit's own opinion settles first by specificity — constraint entry, then per-kind table, then whole-kit table, then the built-in default for the code. The project's `core.toml` `[validation]` table is then admitted against that value: a stricter project value always wins; a weaker one wins only if the governing entry is not `locked`, and is reported under `severity_overrides`; a weaker value against a `locked` entry is refused and the refusal is reported.

Reading it as six layers of plain specificity cannot be right: the constraint entry is the most specific declaration of all, so a project could never override one and `locked` would have nothing to mean.

**Unknown values and unknown keys differ.** A `severity` value outside the vocabulary fails the load — it would otherwise disable a check while the run still reported success. An unknown *key* under a `[validation]` table is reported by `validate-kits` as a `constraints-unknown-key` warning and the rest of the file loads, so a kit written for a newer engine remains installable on an older one.

**Merging** answers two different questions, and they do not have the same answer.

*Within one kit*, specificity decides: a kit that declares `"toc-missing" = "warning"` under `[validation.severity]` and `"toc-missing" = "off"` under `[artifacts.PRD.validation.severity]` means `off` for PRD. That is what a per-kind table is for, and it matches the resolution order above.

*Between kits* bound into one project, strictness decides — including across the whole-kit/per-kind boundary. One kit's whole-kit `error` is not relaxed by another kit's PRD-scoped `off`, because neither kit has agreed to be overruled by the other. Each kit contributes its own effective value for the kind (its kind-scoped entry if it has one, else its whole-kit entry), and the strictest of those wins. `locked` merges as a plain OR, for the same reason.

See `cpt-studio-adr-validation-severity-policy` for the decision record.

### TOC Options

`toc = false` on an artifact kind switches the TOC phase off. A kind that keeps it on can also say how deep and how large that check looks:

```toml
[artifacts.PRD.validation.toc]
max_level = 2            # deepest heading level the TOC must cover (default 3)
max_section_lines = 150  # warn above this section length (default 300)
```

Both options are optional, and both apply wherever TOC checking runs — the TOC phase inside `cfs validate`, which enforced a fixed depth of 3 for every kind before, and `cfs validate-toc`, which now maps each registered file to its kind and reads that kind's options.

An option left out means the kind has no opinion, not that it asked for the default. That is the distinction `cfs validate-toc` needs: an explicit `--max-level` on the command line wins over a configured value, a configured value wins over the engine default, and none of the three can be told apart if "unset" and "3" are stored the same way.

There is no kit-wide `[validation.toc]`. How deep a document's outline goes is a property of the artifact kind, the same way the `toc` switch it configures is, and a whole-kit default would be a second answer to that question with no rule for which one wins. A `[validation.toc]` written at the root is reported as a `constraints-unknown-key` warning like any other key this engine does not read there.

**Merging** applies when one kit binds more than one constraints file and both configure the same kind. It follows the same strictest-wins rule severity does, read through what each option does: the deeper `max_level` wins, because it puts more headings under the completeness check, and the smaller `max_section_lines` wins, because it flags more sections. A file with no opinion never loosens one that has an opinion.

Note the scope. These options are *structural* constraints, so — like `headings`, `identifiers` and the `toc` switch itself — they come from the kit that owns the artifact's system, and a second kit bound to the same project does not reach them. Severity is different, and merges across every loaded kit, because it is a project-wide policy question rather than a contract about one kind's shape.

An unreadable value — a `max_level` outside 1–6, a non-positive `max_section_lines`, a boolean where an integer belongs — fails the load, for the same reason an unreadable severity does: it leaves a check running to a depth nobody can predict. A misspelled option name is a `constraints-unknown-key` warning, not a silent no-op.

### Heading Validation

The validator walks the artifact's Markdown headings and checks against `[[artifacts.<KIND>.headings]]` entries in `constraints.toml`:

**Matching rules**:
- Heading `level` is derived from leading `#` count
- Heading `raw title` is the text after `# ` prefix
- If numbered, the prefix is parsed as `^<num>(\.<num>)*\s+` and stripped before pattern matching
- A constraint matches when `level` matches AND `pattern` matches the stripped title text

**Ordering rules**:
- Constrained headings MUST appear in the order declared in `[[headings]]`
- Between two constrained headings `H_i` and `H_{i+1}`: deeper-level headings are allowed freely unless they are constrained elsewhere
- Same-or-higher-level headings that don't match `H_{i+1}` are a mixing error

**Presence and repetition**:
- `required = true` (default): heading must exist
- `multiple = false`: at most one match allowed
- `multiple = true`: at least two matches required
- `multiple` omitted: any number allowed

**Numbering**:
- `numbered = true`: each matching heading MUST have a numbering prefix
- `numbered = false`: MUST NOT have a numbering prefix
- Numbering progression: consecutive numbered headings at the same level must increment by 1; nested numbering must be consistent with parent prefix

### ID Validation

For each `[artifacts.<KIND>.identifiers.<kind>]` in `constraints.toml`:

- **`required = true`**: at least one ID definition of this kind must exist; validation FAILS if none found
- **`task = true`**: definition line MUST have a checkbox (`[ ]` / `[x]`); `task = false`: MUST NOT
- **`priority = true`**: definition line MUST have a priority token (`` `p1` ``); `priority = false`: MUST NOT
- **`to_code = true`**: ID must be traceable to code (see traceability spec)
  - If definition has a checked checkbox (`[x]`): code marker required
  - If definition has an unchecked checkbox (`[ ]`): code marker prohibited
  - If no checkbox: code marker required
- **`headings`**: ID definitions MUST appear within a section whose active heading constraint ID is in the list

### Cross-Artifact Validation

Cross-artifact validation builds an index of all ID definitions and references across registered artifacts, then enforces `[identifiers.<kind>.ref.<TARGET>]` rules:

**Coverage rules** (per ID definition `d` of kind `K` in artifact kind `A`, for each `ref.T` rule):

| `coverage` | Behavior |
|------------|----------|
| `true` (required) | At least one reference to `d` must exist in an artifact of kind `T`. If no `T` artifacts exist for the system → warning. |
| `false` (prohibited) | No references to `d` may exist in artifacts of kind `T`. |
| omitted (optional) | No requirement. |

**Reference task/priority rules**: when a reference exists, its line is checked for task/priority markers per the `ref.T.task` and `ref.T.priority` settings.

**Checkbox synchronization**: if a reference is marked done (`[x]`) and both the reference and definition track task status, the definition MUST also be marked done.

**System scoping**: IDs are scoped to systems. System prefixes are derived from the system tree in `artifacts.toml` using slug hierarchy. Matching is longest-prefix-wins.

---

## Artifact Scanning

Studio extracts IDs, references, and CDSL instructions from artifacts using best-effort scanning.

**ID definitions** — recognized via human-facing formats:
```markdown
- [ ] **ID**: `cpt-my-system-fr-login`
- [x] `p1` - **ID**: `cpt-my-system-flow-login`
```

Scanner emits: `type: definition`, `id`, `line`, `checked: true|false`, `priority: pN`

**ID references** — recognized in two ways:
- Standalone backticked IDs on list lines: `` - `cpt-my-system-fr-login` ``
- Any inline backticked occurrence: `` ...`cpt-my-system-fr-login`... ``

Scanner emits: `type: reference`, `id`, `line`

**CDSL instructions** — lines matching CDSL step format (see CDSL spec)

Scanner emits: `type: cdsl_instruction`, `phase`, `inst`, `line`, `parent_id` (nearest preceding ID definition)

**Code fence exclusion**: all scanning MUST ignore content inside fenced code blocks.

---

## Full Example

See [examples/constraints-prd.toml](examples/constraints-prd.toml) — full `constraints.toml` for an SDLC kit showing PRD heading outline and ID kind constraints with cross-artifact reference rules.

---

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `CONSTRAINTS_HEADING_ORDER` | Constrained headings appear out of order in artifact | Reorder sections to match constraint order |
| `CONSTRAINTS_HEADING_MISSING` | Required heading not found in artifact | Add the required section |
| `CONSTRAINTS_HEADING_DUPLICATE` | `multiple = false` but heading matched more than once | Remove duplicate sections |
| `CONSTRAINTS_HEADING_NOT_NUMBERED` | `numbered = true` but heading lacks numbering prefix | Add numbering prefix |
| `CONSTRAINTS_ID_MISSING` | `required = true` but no IDs of this kind found | Add at least one ID definition |
| `CONSTRAINTS_ID_NO_TASK` | `task = true` but ID definition has no checkbox | Add checkbox `[ ]` or `[x]` to definition |
| `CONSTRAINTS_ID_NO_PRIORITY` | `priority = true` but ID definition has no priority token | Add priority marker (e.g., `` `p1` ``) |
| `CONSTRAINTS_ID_WRONG_HEADING` | ID defined outside allowed heading sections | Move ID to a section under an allowed heading |
| `CONSTRAINTS_COVERAGE_MISSING` | `coverage = true` but no reference found in target artifact kind | Add reference in target artifact |
| `CONSTRAINTS_COVERAGE_PROHIBITED` | `coverage = false` but references found in target artifact kind | Remove references from target artifact |
| `CONSTRAINTS_CHECKBOX_SYNC` | Reference marked done but definition not marked done | Mark definition as done or unmark reference |
