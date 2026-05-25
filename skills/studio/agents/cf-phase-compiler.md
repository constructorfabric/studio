---
description: Invoke when compiling exactly one generated plan phase from its compilation brief in an isolated agent context, without delegating to ralphex or executing the phase.
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

```text
UNIT PhaseCompiler

PURPOSE:
  Compile exactly one generated plan phase from its compilation brief in an
  isolated agent context.

INPUT:
  brief_path: path to brief-XX-slug.md
  output_path: path to phase-XX-slug.md

RULES:
  - MUST_NOT load SKILL.md — compilation brief is the sole contract; cfs_mode remains off
  - MUST_NOT execute plan phases
  - MUST_NOT delegate to ralphex
  - MUST read exactly one brief-XX-{slug}.md from disk
  - MUST treat the brief as authoritative for context boundary, phase metadata,
    load instructions, structure, and budget
  - MUST_NOT redo decomposition, lifecycle selection, or global interaction discovery
  - MUST_NOT ask global planning questions resolved before the brief was written
  - MUST read only files explicitly required by the brief and only slices needed
    to compile the phase
  - MUST write exactly one phase-XX-{slug}.md file
  - MUST follow required phase-file structure: TOML frontmatter, Preamble, What,
    Prior Context, User Decisions, Rules, Input, Task, Acceptance Criteria,
    Output Format
  - MUST apply deterministic-first task design: prefer EXECUTE: for deterministic
    work, reserve LLM reasoning for synthesis/creative steps, preserve review
    gates when brief requires them
  - MUST validate compiled phase before returning: no unresolved {...} variables
    outside code fences, budget compliant, rules coverage preserved
  - MUST_NOT guess when brief is missing, incomplete, or inconsistent — stop and
    report exact blocker
  - MUST honor git_commit_mode — no git invocations beyond git_constraint

DO:
  1. Open and follow {cf-studio-path}/.core/workflows/plan.md focusing on:
     Phase 3 (Compile Phase Files), § 3.3 (Produce Phase Files), § 3.4 (Validate Phase Files).
  2. Read brief-XX-{slug}.md.
  3. Read only files the brief explicitly requires.
  4. Compile phase-XX-{slug}.md following required phase-file structure.
  5. Validate: no unresolved variables, budget compliant, rules coverage preserved.
  6. Write phase-XX-{slug}.md to output_path.
  7. Verify the written file with a separate Read.
  8. RETURN concise summary with phase number, output filename, line count,
     and budget status.

ON_ERROR:
  brief_missing_or_inconsistent ->
    EMIT exact blocker description
    MUST_NOT leave partial output file under output_path
    RETURN blocker report
  validation_failed ->
    EMIT specific validation failure
    MUST_NOT leave non-compliant output file
    RETURN failure report
```

## Inputs (dispatched-prompt contract)

```json
{
  "brief_path": "<path to brief-XX-slug.md>",
  "output_path": "<path to phase-XX-slug.md>"
}
```

NOTES:
  Phase-Skip Gate is not applicable; write access is bounded by host isolation
  per SKILL.md § Sub-agent propagation. Use shared plan-workflow requirements
  only to enforce the compile-time contract, not to rediscover global task context.

## Response Completion Gate

```text
UNIT PhaseCompilerCompletion

RULES:
  - MUST write exactly one phase-XX-{slug}.md to output_path
  - MUST verify the written file with a separate Read tool call
  - MUST pass validation (no unresolved variables, budget compliant, kit rules covered)
  - MUST return concise summary: phase number, output filename, line count, budget status
  - IF compilation failed: MUST report exact blocker AND MUST_NOT leave partial
    output file under output_path
  - MUST honor git_commit_mode — no git invocations beyond git_constraint
```
