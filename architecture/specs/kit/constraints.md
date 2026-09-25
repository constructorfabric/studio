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
  - [Artifact Kind Keys](#artifact-kind-keys)
  - [Heading Constraints](#heading-constraints)
  - [ID Constraints](#id-constraints)
  - [Reference Rules](#reference-rules)
- [Validation Semantics](#validation-semantics)
  - [Severity](#severity)
  - [TOC Options](#toc-options)
  - [Heading Validation](#heading-validation)
  - [Section Order](#section-order)
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

**Not in scope: formatting.** These constraints govern *structure* — which sections
exist, at which level, in which order, and which identifiers live under them. They say
nothing about table alignment, bullet markers, heading capitalisation, line length or
any other formatting convention, and no `[validation]` key turns such a check on. Use
`markdownlint` or a formatter for those; they are not Studio gates. The boundary was
implicit until teams discovered it by finding that a formatting problem passed
validation, so it is written here and in the configuration guide's
"What `cfs validate` does not check".

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

### Artifact Kind Keys

Each `[artifacts.<KIND>]` table carries the kind's own keys alongside its
`headings` and `identifiers` blocks.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | — | Human-readable name for the artifact kind |
| `description` | string | — | Description of the artifact kind |
| `toc` | boolean | `true` | Whether the TOC phase runs for this kind |
| `order` | array of strings or `"declared"` | omit | Which declared sections must appear in declaration order — see [Section Order](#section-order). Omitted means no order is enforced |
| `validation` | table | — | Severity and TOC options scoped to this kind |

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

**Ordering rules**: see [Section Order](#section-order) below. Order is opt-in: a kind
that declares no `order` accepts its constrained sections in any sequence.

**Presence and repetition**:
- `required = true` (default): heading must exist
- `multiple = false`: at most one match allowed
- `multiple = true`: at least two matches required. Reported as
  `heading-requires-multiple`, whose default severity is `off` — "at least two"
  is true of a kit's repeated-block sections and false of every document with a
  single flow, state or definition of done, so a kind that means it raises the
  rule in its own `[artifacts.<KIND>.validation.severity]` table. The count is
  taken over the whole parent section, not the run of consecutive matches
  `multiple = false` looks at: a section that genuinely repeats carries its own
  subsections between the copies
- `multiple` omitted: any number allowed

**Numbering**:
- `numbered = true`: each matching heading MUST have a numbering prefix
- `numbered = false`: MUST NOT have a numbering prefix
- "Each matching heading" means every copy in the parent section, not only the
  first consecutive run. The run is what `multiple = false` asks about; whether
  a section is numbered is a property of the section, so a second copy with
  subsections between it and the first is checked like any other
- Numbering progression: consecutive numbered headings at the same level must increment by 1; nested numbering must be consistent with parent prefix. Reported as `heading-number-not-consecutive`, an ordinary rule code: a kind that numbers its sections by hand lowers or disables it in its own `[artifacts.<KIND>.validation.severity]` table

### Section Order

A kind says which of its sections must appear in the sequence the kit declares
them:

```toml
[artifacts.PRD]
order = ["prd-context", "prd-requirements", "prd-acceptance"]  # only these three
# order = "declared"                                           # every declared heading
```

**Omitted means no order.** A kind that does not declare `order` accepts its
constrained sections in any sequence. This is the default because a rule a kit
cannot state is a rule a kit cannot relax either: before this key existed the
order was enforced as a side effect of how the matcher walked the document, and
a kit that genuinely wanted context before requirements had no way to say so —
or to say that it did not care.

**A list is partial.** Only the ids named are constrained, and only relative to
each other. Every other section, constrained or not, may appear anywhere.

**`order` chooses what is enforced; it does not re-sequence the declarations.**
The entries must follow the sequence of the `[[headings]]` list, and an order
that runs against it fails the load. The required sequence is therefore
readable in one place — the headings list — and `order` says which parts of it
are checked. A kit that wants a different sequence reorders its headings.

**`"declared"` is every heading, in declaration order** — the strictness the
matcher used to impose on every kit, now a one-line opt-in.

**Merging.** When two kits bind the same artifact kind, their orders add up as
the union of what each kit stated, closed under transitivity: one kit's "a
before c" and another's "c before b" together mean a before b. What the merge
must not do is splice the two lists into one sequence — `["a", "c"]` spliced
onto `["b", "c"]` gives `["a", "c", "b"]`, which states c before b, the reverse
of what the second kit wrote, and a before b, which neither kit wrote. Two kits
that sequence one pair in opposite directions fail the load naming the pair,
because keeping either kit's word would enforce an order the other kit's author
would read as already satisfied. A cycle that only closes across three kits is
one such pair once the relations are closed, so it fails the same way.

**How a violation is found and reported.** The matcher walks the document
forward. Where a constraint finds no match ahead of the cursor, a *rescue pass*
re-searches that constraint's parent range from the start for an unclaimed
heading that matches. A section found there exists — so it is no longer
reported as `heading-missing`, and it is measured by its own `multiple` and
`numbered` rules like any other match. Whether anything is *said* about where
it sits depends on `order`:

- No `order`: silence. The kit never said where the section goes.
- `order` relates it to an already-matched section it now precedes: one
  `heading-order-violation`, carrying `heading_id`, `heading_line` and
  `expected_after` (the nearest section it must clear, with that section's own
  line). The message names both sections and both lines.

Only the "after" direction exists. Constraints are walked in declaration order
and an `order` follows the declarations, so every related section already
matched is one this section is supposed to follow; there is no already-matched
section it was supposed to precede.

A displaced section carries its subsections with it, so the descendants of a
reported section are not reported again — one move, one finding. A subsection
that did *not* travel with its parent is a different matter: it is looked for
inside the parent it is declared under, where it is not, and is reported as
`heading-missing`. That is the section that really is out of place. Before the
rescue pass the same document reported the *parent* missing, which was false —
the parent was present, just early.

**One behaviour change to be aware of.** A section written out of declaration
order used to be reported as absent, and nothing else about it was ever looked
at. Finding it means checking it: an *optional* out-of-order section that also
breaks its own `numbered` or `multiple` rule was silently unvalidated before and
now produces those findings. `prev` and `next` are unaffected — they remain
auto-linked from declaration order and used only to phrase the
`heading-missing` message.

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

A definition is written **bare**. The same line written as a markdown link
(``**ID**: [`cpt-my-system-fr-login`](spec.md)``) defines nothing: the scanner emits
`type: definition-link-form` for it, which is neither a definition nor a reference,
and the validator reports `def-link-form-not-allowed`. Before that code existed such
a line was filed as a reference to the very ID it meant to declare. With the ID's
system registered, that self-reference raised `ref-no-definition` on the definition
line itself — an error that misnamed the problem; with it unregistered, the reference
was skipped as external and nothing was reported at all.

**ID references** — recognized in three ways:
- Standalone backticked IDs on list lines: `` - `cpt-my-system-fr-login` ``
- Standalone link-form IDs: ``[`cpt-my-system-fr-login`](../prd/PRD.md#login)`` — same
  line grammar as the bare form, so the task marker and priority are read the same way
- Any inline backticked occurrence: `` ...`cpt-my-system-fr-login`... ``

Both spellings resolve to one node, because the node is the ID string; the link only
tells a reader where to go next. The accepted link form is narrow on purpose — the ID
must be marked up as an ID. A link whose *target* merely contains an ID
(`[the login flow](spec.md#cpt-my-system-fr-login)`) stays prose.

Scanner emits: `type: reference`, `id`, `line`

**CDSL instructions** — lines matching CDSL step format (see CDSL spec)

Scanner emits: `type: cdsl_instruction`, `phase`, `inst`, `line`, `parent_id` (nearest preceding ID definition)

**Code fence exclusion**: all scanning MUST ignore content inside fenced code blocks.

---

## Full Example

See [examples/constraints-prd.toml](examples/constraints-prd.toml) — full `constraints.toml` for an SDLC kit showing PRD heading outline and ID kind constraints with cross-artifact reference rules.

---

## Error Handling

These are the rule codes the validator emits, as they appear in each finding's
`code` field and in a `[validation.severity]` table. Every one of them is
configurable per kind and per entry; the severity column is the built-in
default.

| Code | Default | Cause | Resolution |
|------|---------|-------|------------|
| `heading-missing` | error | `required = true` but no matching heading anywhere in the constraint's range | Add the required section |
| `heading-order-violation` | error | The kind declares an `order` and this section precedes one it must follow | Move the section after the one named in `expected_after` |
| `heading-prohibits-multiple` | error | `multiple = false` but the heading matched more than once | Remove the duplicate sections |
| `heading-requires-multiple` | off | `multiple = true` but the heading matched exactly once | Add a second occurrence, or leave the rule off |
| `heading-numbering-mismatch` | error | `numbered` is `true` and the prefix is absent, or `false` and it is present | Add or remove the numbering prefix |
| `heading-number-not-consecutive` | error | Sibling numbered headings do not increment by 1 | Renumber the siblings, or lower the rule for this kind |
| `toc-heading-depth-jump` | warning | A heading skips a level below its parent | Add the intermediate level, or lower the rule for this kind |
| `required-id-kind-missing` | error | `required = true` but no ID of this kind is defined | Add at least one ID definition |
| `def-missing-task` / `def-prohibited-task` | error | `task` is `true` and the definition has no checkbox, or `false` and it has one | Add or remove the `[ ]` / `[x]` checkbox |
| `def-missing-priority` / `def-prohibited-priority` | error | `priority` is `true` and the definition has no priority token, or `false` and it has one | Add or remove the priority marker (e.g. `` `p1` ``) |
| `def-wrong-headings` | error | An ID is defined outside the sections its `headings` list allows | Move the definition under an allowed heading |
| `def-link-form-not-allowed` | error | An `**ID**:` line wraps the ID in a markdown link (``**ID**: [`cpt-x`](target)``), which defines nothing | To define the ID here, write it bare. If it is defined elsewhere and the line points there, delete `**ID**:` and keep the link — the line becomes a reference |
| `ref-missing-from-kind` | error | `coverage = true` but the target artifact kind references the ID nowhere | Add the reference in the target artifact |
| `ref-from-prohibited-kind` | error | `coverage = false` but the target artifact kind references the ID | Remove the reference |
| `ref-done-def-not-done` / `def-done-ref-not-done` | error | A reference and its definition disagree about being done | Mark the definition done, or unmark the reference |
| `constraints-invalid` | error | `constraints.toml` could not be loaded | Fix the error the message names; the whole file is refused |
| `constraints-unknown-key` | warning | A key under a `[validation]` table this engine does not read | Check the spelling, or ignore it if the kit targets a newer engine |
