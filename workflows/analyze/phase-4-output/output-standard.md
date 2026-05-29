---
name: analyze-phase-4-output-standard
description: "Invoke when rendering the Phase 4 Standard Analysis Output schema (sections 1-6) or Semantic-Only output."
purpose: Phase 4 Standard Analysis Output schema (sections 1-6) plus Semantic-Only output
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->

- [Standard Analysis Output (non-prompt review)](#standard-analysis-output-non-prompt-review)
- [Semantic-Only Output (`/cf-analyze semantic`)](#semantic-only-output-cf-analyze-semantic)

<!-- /toc -->

```text
UNIT AnalyzePhase4OutputStandard

PURPOSE:
  Render the six-section Standard Analysis Output (or Semantic-Only variant)
  and enforce the remediation-prompt policy.

WHEN:
  EXPLAIN_MODE == false AND PROMPT_REVIEW == false AND PROMPT_BUG_REVIEW == false

DO:
  Render the six sections below (both STRICT and RELAXED modes use the same titles).
  IF SEMANTIC_ONLY == true:
    SET section 2 Deterministic Gate: Status=SKIPPED, Invocation=not run,
      Notes=semantic-only invocation
    FORBID describing semantic-only findings as deterministic, validator-backed,
      or tool-validated
  IF actionable issues exist:
    FORBID emitting Fix Prompt or Plan Prompt here
    REQUIRE `{cf-studio-path}/.core/workflows/analyze/phase-4-output/remediation-handoff.md` to be appended

RULES:
  - MUST use the same six section titles in both STRICT and RELAXED modes
  - In STRICT mode: section titles MUST match exactly
  - In RELAXED mode: content may be lighter but MUST_NOT substitute alternate
    headings (e.g. "## Analysis" or "### Category Review")
  - MUST_NOT emit Fix Prompt or Plan Prompt from this schema
  - MUST append remediation-handoff.md when actionable issues exist
```

### Standard Analysis Output (non-prompt review)
```markdown
## Validation Report

### 1. Protocol Compliance
- Rules Mode: {STRICT|RELAXED}
- Target: {TARGET_TYPE}
- Kind: {KIND}
- Name: {name}
- Path: {PATH}
- Artifact/Code Read: {PATH} ({N} lines)
- Checklist Loaded: {path or "none"} ({N} lines or "n/a")

### 2. Deterministic Gate

Reproduce the canonical `Validation Results` block returned by `cf-deterministic-validator` (Phase 2 dispatch) verbatim — the block schema is owned by the validator agent file (`{cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md` § Output) and is NOT redefined here. Embed every field the agent emitted, in the same order, without selecting or filtering.

### 3. Semantic Review
- This section is mandatory in completed analysis output even when category outcomes include `PASS`, `FAIL`, `PARTIAL`, or `N/A`.
- Checklist Progress:
| Category | Status | Evidence |
|----------|--------|----------|
| {category} | PASS/FAIL/PARTIAL/N/A | {line refs, quotes, or violation description} |

- Categories Summary: Total {N}; PASS {N}; FAIL {N}; PARTIAL {N}; N/A {N}; Unsupported-N/A violations {N} (AP-003 violations — see `{cf-studio-path}/.core/requirements/agent-compliance.md`)

### 4. Agent Self-Test
- Open, load, and follow `{cf-studio-path}/.core/workflows/analyze/agent-self-test.md` § Agent Self-Test (STRICT mode — AFTER completing work) and copy its canonical questions into this table; if RELAXED mode uses a justified subset, state that explicitly.
| Question | Answer | Evidence |
|----------|--------|----------|
| {question} | YES/NO | {evidence} |

### 5. Final Status
- Deterministic: {PASS|FAIL|SKIPPED}
- Semantic: {PASS|FAIL|PARTIAL}
- Overall: {PASS|FAIL|PARTIAL}

### 6. Issues (if any)
- **High**: {issue with location}
- **Medium**: {issue with location}
- **Low**: {issue with location}
```

Use these same six section titles in both STRICT and RELAXED standard analysis output. In STRICT mode the titles must match exactly; in RELAXED mode content may be lighter, but do **not** substitute alternate headings such as `## Analysis` or `### Category Review`.

Do not emit `Fix Prompt` or `Plan Prompt` blocks from this schema. When actionable issues exist, append the terminal `Remediation Handoff` menu from `workflows/analyze/phase-4-output/remediation-handoff.md`; that file owns the on-demand prompt templates for the next-turn option `2` / `3` emissions.

### Semantic-Only Output (`/cf-analyze semantic`)
For non-prompt-review semantic-only analysis, reuse the `Standard Analysis Output (non-prompt review)` six-section schema.

Set `### 2. Deterministic Gate` to `Status: SKIPPED`, `Invocation: not run`, and `Notes: semantic-only invocation`.

Do **not** describe semantic-only findings as deterministic, validator-backed, or tool-validated.

If actionable issues exist in semantic-only mode, append the same final `Remediation Handoff` menu defined in `{cf-studio-path}/.core/workflows/analyze/phase-4-output/remediation-handoff.md` (3 options: in-session fix continuation, Fix Prompt on demand, Plan Prompt on demand). The same EXPLAIN_MODE exception applies.
