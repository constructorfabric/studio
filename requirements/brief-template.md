---
cf: true
type: requirement
name: Compilation Brief Template
version: 2.0
purpose: Template for per-phase compilation briefs — filled by LLM during plan Phase 3.2
---

# Compilation Brief Template


<!-- toc -->

- [Overview](#overview)
- [Template](#template)
- [Load Instructions: How to Fill](#load-instructions-how-to-fill)
- [Example](#example)
- [Fill Rules](#fill-rules)

<!-- /toc -->

## Overview

A compilation brief tells the executing agent what to read, how to use it, and how to compile one phase file. This template is task-agnostic.

## Template

~~~markdown
# Compilation Brief: Phase {number}/{total} — {title}

--- CONTEXT BOUNDARY ---
Disregard all previous context. This brief is self-contained.
Read ONLY the files listed below. Follow the instructions exactly.
---

## Phase Metadata
```toml
[phase]
number = {number}
total = {total}
type = "{type}"
title = "{title}"
depends_on = {depends_on}
input_manifest = "{input_manifest}"
input_signature = "{input_signature}"
input_files = {input_files}
output_files = {output_files}
outputs = {outputs}
inputs = {inputs}
```
When the plan contains raw-input chunk files under `input/`, list the assigned chunk paths in `input_files` here exactly as they will be read at runtime. Use them only from the authoritative package referenced by `input_manifest`, and only when its `input_signature` matches the current plan input.
Files listed under `inputs` are execution-time dependencies for the phase. If an `inputs` entry points into `out/`, treat it as a runtime artifact produced by an earlier phase, not as a compile-time prerequisite for brief or phase-file generation.

## Compilation Clarification

- `input_files` and `inputs` describe phase execution dependencies, not mandatory compile-time reads.
- During brief generation and phase compilation, `out/*` entries under `inputs` MUST be preserved as future runtime reads in the compiled phase's frontmatter, `Input`, and `Task` sections.
- If a referenced `out/*` file already exists, it MAY be read for grounding.
- If a referenced `out/*` file does not yet exist, the compiler MUST NOT fail solely because it is absent; its absence becomes relevant only when the compiled phase is later executed.

## Load Instructions
{numbered list of load items}

**Do NOT load**: {irrelevant files}

## Compile Phase File
Write to: `{plan_dir}/{phase_file}`

Required sections:
1. TOML frontmatter
2. Preamble — use the verbatim preamble from `plan-template.md`
3. What
4. Prior Context
5. User Decisions
6. Rules
7. Input
8. Task — add `Read <file>` steps for runtime-read items, including every assigned `input/*.md` chunk
9. Acceptance Criteria
10. Output Format — use the required completion report + next-phase prompt from `plan-template.md`

If `input_manifest` is non-empty, the Load Instructions MUST also identify `input/manifest.json` as the authoritative description of the raw-input package and keep the assigned chunk list consistent with that manifest.

## Context Budget
- Phase file target: ≤ 600 lines
- Inlined content estimate: ~{N} lines
- Total execution context: ≤ 2000 lines
- If Rules exceeds 300 lines, narrow scope — NEVER drop rules

## After Compilation
Report: "Phase {number} compiled → {phase_file} (N lines)"
Then apply context boundary and proceed to the next brief.
~~~

## Load Instructions: How to Fill

Use this item format:

```text
N. **Label**: Read `{path}` (lines {from}-{to}, ~{N} lines)
   - Action: inline or runtime read
   - Scope: what to keep/skip
```

Range rules: use `lines {from}-{to}` for partial reads, omit ranges for whole-file reads, and use `~` when exact ranges are unknown.

| Action | Meaning | Goes into |
|--------|---------|-----------|
| Inline | Copy content into the compiled phase file | Rules, Input, or both |
| Runtime read | Read during phase execution only | Task |

Inline stable structural content such as rules, templates, checklists, examples, and standards.

Runtime-read dynamic or large content such as project files, source code, prior outputs, config, and external docs.
When a prior output under `out/` is not yet present, describe it as a runtime dependency instead of a required compile-time read.

## Example

```text
1. **Rules**: Read `{kit}/artifacts/ADR/rules.md` (lines 30-450, ~420 lines)
   - Inline → Rules section
   - Keep MUST/MUST NOT requirements; skip Prerequisites, Load Dependencies, Tasks, Next Steps
2. **Template**: Read `{kit}/artifacts/ADR/template.md` (lines 10-48, ~38 lines)
   - Inline → Input section
3. **Project context**: Read `{cf-studio-path}/.core/workflows/plan.md` (lines 1-80, ~80 lines)
   - Runtime read → add `Read {cf-studio-path}/.core/workflows/plan.md` to Task
```

## Fill Rules

```pdsl
UNIT BriefFillRules

PURPOSE:
  Enforce required constraints when generating phase compilation briefs.

DO:
  - REQUIRE each brief includes only what the phase needs
  - REQUIRE line counts are provided via wc -l or a reasonable estimate
  - RUN one brief per phase with context boundary applied between briefs
  - SET brief_filename = "brief-{NN}-{slug}.md"
  - REQUIRE inline content does not exceed ~500 lines; if so, narrow load scope or move items to runtime reads

RULES:
  - ALWAYS generate exactly one brief per phase
  - ALWAYS apply the context boundary between briefs
  - NEVER drop rules even when the Rules section exceeds 300 lines; narrow scope instead
  - NEVER inline content exceeding ~500 lines without first narrowing load scope or moving items to runtime reads
```
