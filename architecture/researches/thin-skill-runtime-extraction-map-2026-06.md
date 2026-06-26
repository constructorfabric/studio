# Thin Skill Runtime Extraction Map — 2026-06

<!-- toc -->

- [Overview](#overview)
- [Current Heavy Workflow Concerns](#current-heavy-workflow-concerns)
  - [Coding](#coding)
  - [Write Docs](#write-docs)
  - [Write Skills](#write-skills)
- [Target Runtime Split](#target-runtime-split)
  - [Standalone Skills](#standalone-skills)
  - [Shared Modules](#shared-modules)
  - [Canonical Artifacts](#canonical-artifacts)
- [Extraction Map](#extraction-map)
  - [Intent and Entry Routing](#intent-and-entry-routing)
  - [Prerequisite and Input Resolution](#prerequisite-and-input-resolution)
  - [Authoring / Execution](#authoring--execution)
  - [Deterministic Validation / CI](#deterministic-validation--ci)
  - [Semantic Review](#semantic-review)
  - [Findings and Fix Approval](#findings-and-fix-approval)
  - [Git Finalization and Phase State](#git-finalization-and-phase-state)
- [Planned Rewrite Sequence](#planned-rewrite-sequence)
- [Notes and Risks](#notes-and-risks)

<!-- /toc -->

## Overview

This note records the concrete extraction map from today's heavy runtime
workflows to the target thin-skill/module-first runtime.

It is a migration aid for the one-PR rewrite described by:

- [ADR-0022](../ADR/0022-cpt-studio-adr-thin-skills-module-first-v1.md)
- [Thin Skill Runtime Specification](../specs/thin-skill-runtime.md)

The goal is not to finalize deep artifact schemas here. The goal is to make the
next implementation slice mechanically obvious:

- what stays a standalone skill
- what must move into a shared module
- what artifact boundary each step should use

## Current Heavy Workflow Concerns

### Coding

Today [workflows/coding.md](../../workflows/coding.md) mixes:

- intent capture and review-first classification
- companion routing and workflow-prep gates
- authoring dispatch
- deterministic validation
- semantic review granularity and reviewer dispatch
- findings aggregation
- findings browser and fix approval
- fix dispatch and loop control
- completion reporting

### Write Docs

Today [workflows/write-docs.md](../../workflows/write-docs.md) mixes:

- intent capture and review-first classification
- context/rule loading and storytelling dimensions
- authoring dispatch
- deterministic validation
- semantic review dispatch and aggregation
- fix approval and fix routing
- completion

### Write Skills

Today [workflows/write-skills.md](../../workflows/write-skills.md) mixes:

- intent capture and review-first classification
- PDSL reference loading
- authoring dispatch
- deterministic validation
- semantic review dispatch and aggregation
- fix approval and fix routing
- completion

## Target Runtime Split

### Standalone Skills

Shared:

- `explore`
- `brainstorm`
- `planning`
- `git-commit`

Code:

- `code-planning`
- `coding-gen`
- `coding-tests`
- `coding-review`
- `coding-fix`
- `coding-ci`

Docs:

- `documenting-planning`
- `documenting-gen`
- `documenting-review`
- `documenting-fix`
- `documenting-ci`

Prompt / skill / workflow:

- `prompting-planning`
- `prompting-gen`
- `prompting-review`
- `prompting-fix`
- `prompting-ci`

### Shared Modules

Core modules required by the split:

- `skill-io-contract-load`
- `artifact-contract-load`
- `prerequisite-check`
- `resource-context-check`
- `design-input-check`
- `artifact-input-shape-check`
- `blocked-report`
- `missing-inputs-report`
- `handoff-suggestions`
- `assumption-override`
- `artifact-dod-check`
- `findings-render`
- `findings-aggregate`
- `ci-report-render`
- `phase-close`
- `phase-status-mark`
- `phase-artifact-linking`
- `commit-policy-load`
- `commit-trailer-prepare`
- `commit-preflight-check`

### Canonical Artifacts

The split relies most directly on these artifact boundaries:

- `resource-context`
- `design-doc`
- `design-decisions`
- `unresolved-questions`
- `acceptance-criteria`
- `constraints`
- `phase-plan`
- `phase-brief`
- `phase-dod`
- `phase-status`
- `unit-tests`
- `e2e-tests`
- `test-spec`
- `code-changes`
- `doc-changes`
- `skill-changes`
- `review-findings`
- `ci-findings`
- `deterministic-report`
- `commit-intent`
- `commit-result`

## Extraction Map

### Intent and Entry Routing

Keep as thin standalone-skill entry behavior:

- capture the user intent
- classify high-level mode when unavoidable for that specific skill
- load shared contracts and route to the first relevant module

Extract from existing heavy workflows into shared modules:

- review-first classification helpers that are structurally identical across
  artifact types
- shared companion-skill offer behavior
- shared workflow-prep gates
- shared blocked-envelope emission

Target:

- `coding` becomes code-authoring entry only
- `coding-review` becomes semantic review entry only
- `coding-ci` becomes deterministic CI entry only
- same pattern for docs and skills

### Prerequisite and Input Resolution

Current heavy workflows mostly ask for intent and optionally `explore` /
`brainstorm`, but they do not yet treat upstream artifacts as a first-class
contract.

Extract into shared modules:

- `prerequisite-check`
- `resource-context-check`
- `design-input-check`
- `artifact-input-shape-check`
- `blocked-report`
- `missing-inputs-report`
- `handoff-suggestions`
- `assumption-override`

Target contract examples:

- `coding-gen` requires `phase-plan`, `phase-dod`, relevant file map or
  `resource-context`, and tests or `test-spec`
- `coding-tests` requires `phase-plan` or testable brief plus acceptance
  criteria
  and test surfaces
- `code-planning` requires design intent, constraints, and expected behavior

### Authoring / Execution

Keep as artifact-specific standalone skills:

- `coding-gen`
- `documenting-gen`
- `prompting-gen`
- `coding-tests`
- `code-planning`
- `documenting-planning`
- `prompting-planning`

Extract into shared modules:

- authoring-independent prerequisite gates
- assumption/override handling
- phase artifact linking
- thin result-envelope shaping

Target:

- authoring skills produce `code-changes`, `doc-changes`, or `skill-changes`
- planning skills produce `phase-plan`, `phase-brief`, `phase-dod`
- `coding-tests` produces `unit-tests`, `e2e-tests`, or `test-spec`

### Deterministic Validation / CI

Current heavy workflows embed deterministic validation inline.

Split into standalone skills:

- `coding-ci`
- `documenting-ci`
- `prompting-ci`

Extract into shared modules:

- `ci-report-render`
- artifact-specific check selection helpers
- shared result-envelope shaping for deterministic reports

Target:

- CI skills only find and run relevant deterministic checks
- CI skills produce `deterministic-report` and optionally `ci-findings`
- CI skills do not own semantic review or fix loops

### Semantic Review

Current heavy workflows embed semantic review setup, reviewer dispatch, and
aggregation.

Split into standalone skills:

- `coding-review`
- `documenting-review`
- `prompting-review`

Keep shared infrastructure in modules:

- `review/finding-contract.md`
- `review/semantic-loop-skeleton.md`
- future `findings-aggregate`
- future `findings-render`

Target:

- review skills produce `review-findings`
- review skills do not own authoring or CI
- fix approval remains explicit and visible

### Findings and Fix Approval

Current runtime already centralizes part of this in:

- `review/fix-approval.md`
- `review/finding-contract.md`
- `review/semantic-loop-skeleton.md`

Further extraction target:

- findings browser/rendering should become clearly shared and artifact-agnostic
- artifact-specific review skills should only prepare reviewer payloads and feed
  findings into the shared approval path

Do not make `findings-report` a mandatory standalone skill. Keep it as a module
or thin wrapper capability.

### Git Finalization and Phase State

Keep `git-commit` as a thin standalone skill entrypoint.

Keep as shared modules:

- `commit-policy-load`
- `commit-trailer-prepare`
- `commit-preflight-check`
- `phase-close`
- `phase-status-mark`
- `phase-artifact-linking`

Target:

- artifact skills do not own commit policy logic
- phase closing is not a domain skill; it is shared lifecycle behavior

## Planned Rewrite Sequence

Recommended mechanical order:

1. finalize architecture and runtime contracts
2. introduce shared runtime modules for thin-skill contracts and prerequisite
   behavior
3. introduce thin `planning` plus domain presets such as `code-planning`,
   `documenting-planning`, and `prompting-planning`
4. split deterministic validation into `coding-ci`, `documenting-ci`,
   `prompting-ci`
5. split semantic review into `coding-review`, `documenting-review`,
   `prompting-review`
6. keep `coding`, `testing`, `write-docs`, `write-skills`, `docs-*`, and
   `skills-*` only as compatibility aliases over canonical thin entrypoints
7. keep `plan` as the backward-compatible standalone planner, but converge its
   reusable logic onto shared planning/runtime modules where possible
8. update generated skill/workflow bootstrap and agent integration assumptions
9. run deterministic validation and prompt-semantic review over the rewrite

Current implementation status in canonical sources:

- integrable planning exists as `planning` plus `code-planning`,
  `documenting-planning`, and `prompting-planning`
- standalone deterministic execution entrypoints exist as `coding-ci`,
  `documenting-ci`, and `prompting-ci`
- standalone semantic review entrypoints exist as `coding-review`,
  `documenting-review`, and `prompting-review`
- standalone fix entrypoints exist as `coding-fix`, `documenting-fix`, and
  `prompting-fix`
- standalone git finalization entrypoint exists as `git-commit`
- `coding`, `testing`, `write-docs`, `write-skills`, `docs-*`, `skills-*`, and
  `plan` remain compatibility entrypoints while reuse is progressively moved
  into shared modules

## Notes and Risks

- The current heavy runtime reuses some logic already, but the reuse is uneven
  and often hidden behind workflow-local units.
- A temporary dual runtime should be avoided; once a thin replacement is ready
  for one domain, the corresponding heavy path should stop being authoritative.
- `.bootstrap/.core` mirrors must continue to be regenerated from canonical
  sources rather than edited directly.
