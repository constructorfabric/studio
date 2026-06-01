---
cf: true
type: workflow-phase
name: plan-phase-2-decompose
description: "Invoke when cf-plan enters Phase 2 to decompose the assessed task into phases: lifecycle selection, data-flow analysis, review gate placement, and execution-context budget prediction."
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

```text
UNIT Phase2Init

PURPOSE:
  Load decomposition requirements and split compilation to minimize context.

STATE:
  task_type: generate | analyze | implement
    scope: workflow_run

  lifecycle: gitignore | cleanup | archive | manual
    scope: workflow_run

DO:
  OPEN {cf-studio-path}/.core/requirements/plan-decomposition.md
  FOLLOW plan-decomposition.md
  CONTINUE Phase2LifecycleSelection

NOTES:
  Compilation is split to minimize context: write the manifest, write briefs,
  then compile one phase at a time.
```

## 2.1 Select Plan Lifecycle (before finalizing phases)

```text
UNIT Phase2LifecycleSelection

PURPOSE:
  Select a lifecycle strategy before finalizing phase boundaries.

DO:
  OPEN {cf-studio-path}/.core/workflows/plan/plan-lifecycle.md
  FOLLOW plan-lifecycle.md (presents lifecycle menu, records selection, defines normative rules)
  CONTINUE Phase2DecomposeByStrategy
```

```text
UNIT Phase2DecomposeByStrategy

PURPOSE:
  Group work into phases using a task-type-specific strategy.

DO:
  MATCH task_type:
    generate ->
      LOAD target template
      LIST H2 sections
      GROUP into phases of 2-4 sections
      RECORD phase boundaries
    analyze ->
      LOAD target checklist
      LIST checklist categories
      GROUP by validation pipeline order:
        structural → semantic → cross-ref → traceability → synthesis
      RECORD phase boundaries
    implement ->
      LOAD FEATURE spec
      LIST CDSL blocks
      ASSIGN one block + tests per phase
      ADD scaffolding and final integration phases
      RECORD boundaries

  IF lifecycle = cleanup:
    APPEND reserved final Cleanup phase after all delivery phases
    MAKE Cleanup phase depend on the last non-cleanup phase

  OUTPUT phase list containing:
    phase number and title
    covered sections / categories / blocks
    dependencies
    input_files
    output_files
    assigned interaction points
    intermediate results needed by later phases

  IF input/manifest.json package exists AND its input_signature matches plan.input_signature:
    ASSIGN relevant input/*.md chunk files into input_files for phases that need them
    IF full raw-input package would overflow one phase:
      ADD dedicated ingestion or consolidation phases
      FORBID attaching every chunk to every phase
```

## Intermediate Results Analysis

```text
UNIT Phase2IntermediateResultsAnalysis

PURPOSE:
  Map data flow between phases to define intermediate artifact storage.

RULES:
  - IF any later phase needs a phase result:
      SAVE to {cf-studio-path}/.plans/{task-slug}/out/{filename}
  - IF only the final artifact depends on a result:
      WRITE directly to the project path
  - IF the final phase assembles prior outputs:
      LIST ALL required inputs
  - MUST use names like out/phase-{NN}-{what}.md
```

## Review Phases

```text
UNIT Phase2ReviewPhases

PURPOSE:
  Insert review gates when the source workflow requires user approval before writing.

RULES:
  - IF source workflow requires review before writing:
      ADD review gates inside the relevant phase
      Output Format MUST present content for inspection
      Acceptance Criteria MUST include user approval
  - IF source workflow requires a major consolidated review:
      ADD a dedicated Review phase that:
        loads prior outputs
        asks required review questions
        blocks further progress until approved
```

## Execution Context Prediction

```text
UNIT Phase2ExecutionContextPrediction

PURPOSE:
  Verify all phases fit within the 2000-line context budget and obtain
  user confirmation before writing any files.

DO:
  FOR each phase:
    COMPUTE estimated_lines = phase_file_lines + sum(input_files lines) + sum(inputs lines) + estimated_output_lines
    INCLUDE plan raw-input chunks from input/ in sum(input_files lines) exactly as read at runtime
    CLASSIFY:
      > 2000 -> OVERFLOW (MUST split further)
      1501-2000 -> WARNING

  RE-SPLIT all overflow phases until all are within budget

  EMIT:
    Decomposition ({strategy} strategy):
      Phase 1: {title} — ~{N} lines (phase: {P}, runtime: {R})
      Phase 2: {title} — ~{N} lines (phase: {P}, runtime: {R})
      ...
      Phase N: {title} — ~{N} lines (phase: {P}, runtime: {R})

      Total phases: {N}
      Overflow phases: 0
      Budget: 2000 lines max per phase

  EMIT_MENU DecompositionConfirmMenu
  WAIT user.reply
  STOP_TURN

MENU DecompositionConfirmMenu:
  TITLE: Explicit confirmation is required before writing `plan.toml` and brief files to disk.
  PREAMBLE:
    Proceed with manifest + brief generation after any required raw-input materialization? [y/n]
  OPTIONS:
    y -> CONTINUE Phase3Compile
    n -> EMIT "Decomposition declined — rework the phase boundaries and re-run Invoke skill `cf-plan` when ready."
         STOP_TURN  (valid completion state for cf-plan; no files created)
  INVALID:
    EMIT "Reply with y or n."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST wait for user confirmation before proceeding to Phase 3
  - MUST NOT hide raw-input chunk estimates inside vague totals
```
