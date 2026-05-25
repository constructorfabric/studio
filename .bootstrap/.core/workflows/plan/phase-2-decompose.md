---
cf: true
type: workflow-phase
name: plan-phase-2-decompose
description: "Invoke when /cf-plan enters Phase 2 to decompose the assessed task into phases: lifecycle selection, data-flow analysis, review gate placement, and execution-context budget prediction."
loaded_by: workflows/plan.md
version: 1.0
---

# Phase 2: Decompose


<!-- toc -->

- [2.1 Select Plan Lifecycle (before finalizing phases)](#21-select-plan-lifecycle-before-finalizing-phases)
- [Intermediate Results Analysis](#intermediate-results-analysis)
- [Review Phases](#review-phases)
- [Execution Context Prediction](#execution-context-prediction)

<!-- /toc -->

Open and follow `{cf-studio-path}/.core/requirements/plan-decomposition.md`.

Compilation is split to minimize context: write the manifest, write briefs, then compile one phase at a time.

## 2.1 Select Plan Lifecycle (before finalizing phases)

OPEN and follow `workflows/plan/plan-lifecycle.md` WHEN selecting the plan lifecycle strategy — presents the lifecycle menu and defines per-strategy normative handling rules.

Select a strategy based on task type:
- **generate**: load the target template, list H2 sections, group them into phases of `2-4` sections, and record phase boundaries.
- **analyze**: load the target checklist, list checklist categories, group them by validation pipeline order (structural → semantic → cross-ref → traceability → synthesis), and record phase boundaries.
- **implement**: load the FEATURE spec, list CDSL blocks, assign one block + tests per phase, add scaffolding and final integration phases, and record boundaries.

Output a phase list containing phase number and title, covered sections / categories / blocks, dependencies, `input_files`, `output_files`, assigned interaction points, and intermediate results needed by later phases. If `lifecycle = cleanup`, append the reserved final Cleanup phase after all delivery phases and make it depend on the last non-cleanup phase.

When an `input/manifest.json` package exists and its `input_signature` matches `plan.input_signature`, assign the relevant `input/*.md` chunk files into `input_files` for the phases that need them. If the full raw-input package would overflow one phase, add dedicated ingestion or consolidation phases instead of attaching every chunk everywhere.

## Intermediate Results Analysis

Identify data flow between phases: incremental artifact output, extracted data, analysis notes, generated IDs, and decision logs.

Rules: if any later phase needs a phase result, save it to `{cf-studio-path}/.plans/{task-slug}/out/{filename}`; if only the final artifact depends on it, write directly to the project path; if the final phase assembles prior outputs, list ALL required `inputs`; use names like `out/phase-{NN}-{what}.md`.

## Review Phases

If the source workflow requires review before writing, add review gates inside the relevant phase: the Output Format must present content for inspection and the Acceptance Criteria must include user approval. If the source requires a major consolidated review, add a dedicated Review phase that loads prior outputs, asks the required review questions, and blocks further progress until approved.

## Execution Context Prediction

For each phase, estimate `phase_file_lines + sum(input_files lines) + sum(inputs lines) + estimated_output_lines`. Flags: `> 2000` = OVERFLOW → MUST split further; `1501-2000` = WARNING. Budget is `2000` lines max per phase. Re-split overflow phases until all are within budget, then report:
```text
Decomposition ({strategy} strategy):
  Phase 1: {title} — ~{N} lines (phase: {P}, runtime: {R}) 
  Phase 2: {title} — ~{N} lines (phase: {P}, runtime: {R}) 
  Phase 3: {title} — ~{N} lines (phase: {P}, runtime: {R}) 
  ...
  Phase N: {title} — ~{N} lines (phase: {P}, runtime: {R}) 
  
  Total phases: {N}
  Overflow phases: 0
  Budget: 2000 lines max per phase
  
  Explicit confirmation is required before writing `plan.toml` and brief files to disk.
  Proceed with manifest + brief generation after any required raw-input materialization? [y/n]
Reply with `y` or `n`.
`y` → Suggested when the decomposition looks correct; write `plan.toml` and the compilation briefs.
`n` → Stop before writing the manifest or briefs. No files are created. Report: "Decomposition declined — rework the phase boundaries and re-run `/cf-plan` when ready." This is a valid completion state for `/cf-plan`.
```
Wait for user confirmation before proceeding.

Include plan raw-input chunks from `input/` in `sum(input_files lines)` exactly as they will be read at runtime; do NOT hide them inside vague estimates.
