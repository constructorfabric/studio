---
studio: true
type: spec
name: Thin Skill Runtime Specification
version: 1.0
purpose: Define the module-first runtime contracts for thin standalone skills
drivers:
  - cpt-studio-fr-core-workflows
  - cpt-studio-fr-core-agents
  - cpt-studio-fr-core-config
---

# Thin Skill Runtime Specification

<!-- toc -->

- [Overview](#overview)
- [Goals](#goals)
- [Non-Goals](#non-goals)
- [Canonical Registries](#canonical-registries)
  - [Standalone Skills](#standalone-skills)
  - [Shared Modules](#shared-modules)
  - [Canonical Artifacts](#canonical-artifacts)
- [Runtime Rules](#runtime-rules)
  - [Module-First Law](#module-first-law)
  - [Prerequisite Resolution](#prerequisite-resolution)
  - [Blocked and Override Behavior](#blocked-and-override-behavior)
  - [Artifact and Report Separation](#artifact-and-report-separation)
- [Unified Result Envelope](#unified-result-envelope)
  - [Status Set](#status-set)
  - [Envelope Shape](#envelope-shape)
  - [Blocked Payload Rules](#blocked-payload-rules)
  - [Assumption Rules](#assumption-rules)
- [Artifact Contracts](#artifact-contracts)
  - [Design and Decision Artifacts](#design-and-decision-artifacts)
  - [Exploration Artifacts](#exploration-artifacts)
  - [Planning Artifacts](#planning-artifacts)
  - [Testing Artifacts](#testing-artifacts)
  - [Authoring Artifacts](#authoring-artifacts)
  - [Review and CI Artifacts](#review-and-ci-artifacts)
  - [Git Artifacts](#git-artifacts)
- [Operational Semantics](#operational-semantics)
- [Reference PDSL Contracts](#reference-pdsl-contracts)

<!-- /toc -->

## Overview

This specification defines the target runtime model for Constructor Studio
skills after the thin-skill/module-first split.

The model has three registries:

- standalone skills
- shared modules
- canonical artifacts

Standalone skills are user-facing entrypoints. Shared modules contain the
substantive runtime behavior. Canonical artifacts are the common currency that
flows between skills.

## Goals

- make every standalone skill narrow and predictable
- move reusable logic into shared modules
- replace hidden orchestration with explicit prerequisite contracts
- standardize how skills report blocked/completed/failed results
- allow kits to compose Studio runtime behavior from modules

## Non-Goals

- forcing every task through one mandatory orchestration workflow
- removing user-approved degraded execution for planning/authoring-style work
- making review or CI assumption-based
- defining every artifact's deep domain schema in this document

## Canonical Registries

The runtime registries are explicit and source-controlled. Standalone skills,
shared modules, and canonical artifacts are named contracts, not conventions
inferred from whatever a local workflow happens to do.

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

Kits:

- `kit-planning`
- `kit-gen`
- `kit-review`
- `kit-fix`
- `kit-ci`

Kits MAY add additional thin entrypoints, but kit-owned entrypoints MUST reuse
the canonical result envelope and MUST NOT redefine the canonical top-level
status set.

The legacy standalone planner remains available as `plan`, but it is a
backward-compatible package planner rather than the canonical thin planning
entrypoint for pipeline composition.

Compatibility aliases remain available as `coding`, `testing`, `write-docs`,
`write-skills`, `docs-planning`, `docs-review`, `docs-ci`,
`skills-planning`, `skills-review`, and `skills-ci`, but pipeline-oriented
callers SHOULD prefer the canonical thin entrypoints (`coding-gen`,
`coding-tests`, `coding-review`, `coding-fix`, `coding-ci`,
`documenting-planning`, `documenting-gen`, `documenting-review`,
`documenting-fix`, `documenting-ci`, `prompting-planning`, `prompting-gen`,
`prompting-review`, `prompting-fix`, `prompting-ci`, `kit-planning`,
`kit-gen`, `kit-review`, `kit-fix`, `kit-ci`).

### Shared Modules

Prerequisite and input modules:

- `prerequisite-check`
- `resource-context-check`
- `design-input-check`
- `artifact-input-shape-check`

Blocked and handoff modules:

- `blocked-report`
- `handoff-suggestions`
- `assumption-override`
- `missing-inputs-report`

Planning and phase modules:

- `artifact-dod-check`
- `phase-close`
- `phase-status-mark`
- `phase-artifact-linking`

Reporting modules:

- `findings-render`
- `findings-aggregate`
- `ci-report-render`

Git modules:

- `commit-policy-load`
- `commit-trailer-prepare`
- `commit-preflight-check`

Cross-cutting contract modules:

- `skill-io-contract-load`
- `artifact-contract-load`

Generated shims and kit-owned thin skills MUST load the shared contract modules
before interpreting skill-local prerequisite, blocked, override, report, or
handoff behavior.

### Canonical Artifacts

Design / decision:

- `design-doc`
- `design-decisions`
- `unresolved-questions`
- `acceptance-criteria`
- `constraints`

Exploration:

- `resource-context`
- `relevant-files-map`
- `dependency-map`
- `test-surfaces`

Planning:

- `phase-plan`
- `phase-brief`
- `phase-dod`
- `phase-status`

Testing:

- `unit-tests`
- `e2e-tests`
- `test-spec`

Authoring:

- `code-changes`
- `doc-changes`
- `skill-changes`

Review / CI:

- `review-findings`
- `ci-findings`
- `deterministic-report`

Git:

- `commit-intent`
- `commit-result`

Kits MAY add domain-specific artifact types, but canonical artifact names are
reserved and MUST keep the semantics defined in this specification.

## Runtime Rules

### Module-First Law

- standalone skills MUST stay thin
- shared modules MUST own substantive runtime logic
- new reusable behavior MUST enter through modules first
- kits SHOULD compose runtime behavior from modules rather than copying large
  workflows
- standalone skill `description` fields MUST be trigger instructions for LLM
  routing only
- standalone skill `description` fields MUST start with `Invoke when`
- standalone skill `description` fields MUST describe invocation intent hints,
  not compatibility notes, implementation details, or internal status
- standalone skill `description` fields SHOULD cover free-form user phrasing,
  not only exact workflow names or internal artifact jargon
- standalone skill `description` fields SHOULD also match requests coming from
  another skill or workflow when the next step is delegated internally
- standalone skill `description` fields SHOULD combine likely intent verbs,
  artifact nouns, and outcome phrasing so the route still matches when the user
  writes informally
- standalone skill `description` fields SHOULD prefer common user language such
  as "fix", "review", "write tests", "explain what changed", or "plan the
  work" when that language is clearer than internal runtime terminology
- compatibility-alias workflows MAY keep exact-name-oriented descriptions so
  they do not compete with canonical thin entrypoints
- generic router workflows SHOULD keep fallback-oriented descriptions so they do
  not compete with concrete domain workflows during intent matching
- standalone skill `purpose` fields MUST describe the workflow's internal
  responsibility and execution role
- standalone skill `purpose` fields MUST NOT be used as routing hints for the
  LLM
- standalone skill `purpose` fields MUST NOT be used for compatibility,
  canonical, legacy, or alias labeling when the same point is not required to
  explain runtime behavior
- user-returning blocked, completed, completed-with-assumptions, and failed
  states MUST provide a clear numbered next-actions menu or equivalent explicit
  numbered choice list
- every user-facing menu MUST include an explicit `back` option
- `back` MUST return to the nearest previous workflow-owned decision point, or
  resolve to a safe terminal return when no earlier decision point exists
- when a terminal state leaves behind produced artifacts, plans, findings,
  decisions, or completed changes, the next-actions menu SHOULD offer
  `cf-explain` as a final-step handoff so the agent can explain what was done
  and how to read the result

### Prerequisite Resolution

Every standalone skill MUST define:

- required artifacts
- accepted input shapes
- why each required artifact matters
- what producer skills may provide each missing artifact
- whether an override path is legal

### Blocked and Override Behavior

Missing prerequisites do not act as hidden orchestration gates.

Instead, the skill returns a visible `blocked` result describing:

- missing artifacts
- why execution is blocked
- accepted artifact shapes
- suggested producer skills
- optional override path
- explicit numbered next actions

When both a generic producer skill and a domain-specific producer skill can
resolve the same blocked capability class, the domain-specific producer SHOULD
be suggested in preference to the generic one. The generic producer MAY remain
available as fallback, but it SHOULD NOT appear as an equal-ranked sibling in
the same blocked next-actions menu.

Override is legal only for:

- planning
- authoring
- explore
- brainstorm

Override is not legal for:

- semantic review skills
- CI skills

### Artifact and Report Separation

The top-level result envelope separates:

- produced artifacts
- report outputs

This prevents authoring results from being conflated with findings or
diagnostics.

## Unified Result Envelope

### Status Set

The canonical status set is:

- `ready`
- `blocked`
- `completed`
- `completed-with-assumptions`
- `failed`

### Envelope Shape

```json
{
  "type": "SKILL_RESULT",
  "skill": "<cf-* skill name>",
  "status": "ready|blocked|completed|completed-with-assumptions|failed",
  "produced_artifacts": [
    {
      "artifact_type": "<canonical artifact name>",
      "ref": "<path|id|handle>",
      "summary": "<short summary>"
    }
  ],
  "report_outputs": [
    {
      "report_type": "<deterministic-report|review-findings|ci-findings|other>",
      "ref": "<path|id|handle>",
      "summary": "<short summary>"
    }
  ],
  "missing_artifacts": [
    {
      "artifact_type": "<canonical artifact name>",
      "why_needed": "<one-line reason>",
      "accepted_shapes": ["<shape>", "..."],
      "suggested_producers": ["<skill>", "..."],
      "override_allowed": true,
      "override_summary": "<optional visible override path>"
    }
  ],
  "assumptions": [
    {
      "summary": "<assumption>",
      "risk": "low|medium|high"
    }
  ],
  "suggested_next_skills": ["<skill>", "..."]
}
```

Standalone skills SHOULD emit empty arrays rather than omitting envelope
collections so downstream shims and kits can consume one stable shape.

### Blocked Payload Rules

`blocked` results MUST include:

- `missing_artifacts`
- `why_needed`
- `accepted_shapes`
- `suggested_producers`
- `override_allowed`
- visible override path when override is legal

### Assumption Rules

`completed-with-assumptions` is allowed only for:

- `*-planning`
- `coding-gen`
- `coding-tests`
- `documenting-gen`
- `prompting-gen`
- `explore`
- `brainstorm`

It MUST NOT be used by:

- `*-review`
- `*-ci`

## Artifact Contracts

### Design and Decision Artifacts

`design-doc`, `design-decisions`, `unresolved-questions`,
`acceptance-criteria`, and `constraints` provide the design-level inputs for
planning and downstream authoring/testing.

### Exploration Artifacts

`resource-context`, `relevant-files-map`, `dependency-map`, and `test-surfaces`
are discovery outputs owned by `explore`.

### Planning Artifacts

`phase-plan`, `phase-brief`, `phase-dod`, and `phase-status` define what one
phase is allowed to do and when it is complete.

### Testing Artifacts

`unit-tests`, `e2e-tests`, and `test-spec` capture executable and
pre-executable test intent.

### Authoring Artifacts

`code-changes`, `doc-changes`, and `skill-changes` represent the concrete
artifact deltas produced by authoring skills.

### Review and CI Artifacts

`review-findings`, `ci-findings`, and `deterministic-report` capture semantic
and deterministic diagnostics independently from authoring output.

### Git Artifacts

`commit-intent` and `commit-result` capture explicit git finalization state.

## Operational Semantics

- `explore` is an artifact provider, not a mandatory universal step
- `brainstorm` is an artifact provider, not a mandatory universal step
- a skill may suggest another skill, but by default it MUST wait for user
  confirmation before handoff
- kits may add their own thin entrypoints as long as they reuse the shared
  result envelope, canonical status set, and canonical artifact contracts
- generated skill and workflow shims MUST load the canonical runtime contract
  modules before any skill-local prerequisite or result-envelope logic runs

## Reference PDSL Contracts

```pdsl
UNIT ThinSkillModuleFirstLaw
PURPOSE: Keep standalone skills thin and shared modules authoritative.
RULES:
  - ALWAYS treat standalone skills as thin user-facing entrypoints
  - ALWAYS keep substantive reusable logic in shared modules
  - NEVER embed a reusable review loop, CI runner, or prerequisite resolver
    inside a standalone skill when a shared module can own it
```

```pdsl
UNIT ThinSkillBlockedContract
PURPOSE: Standardize blocked results across standalone skills.
RULES:
  - ALWAYS when a required artifact is missing, return status = blocked
  - ALWAYS include missing_artifacts, why_needed, accepted_shapes, and
    suggested_producers in the blocked result
  - ALWAYS make override_allowed explicit in blocked payloads
  - ALWAYS expose a visible override path when degraded execution is legal
  - NEVER silently invoke a producer skill by default
```

```pdsl
UNIT ThinSkillAssumptionContract
PURPOSE: Restrict assumption-based completion to safe skill classes.
RULES:
  - ALWAYS allow completed-with-assumptions only for planning, authoring,
    explore, and brainstorm skill classes
  - NEVER allow completed-with-assumptions for review or CI skill classes
```

```pdsl
UNIT ThinSkillResultEnvelopeContract
PURPOSE: Keep top-level skill results machine-readable and stable across domains.
RULES:
  - ALWAYS emit type, skill, status, produced_artifacts, report_outputs,
    missing_artifacts, assumptions, and suggested_next_skills in the top-level
    result envelope
  - ALWAYS keep produced_artifacts separate from report_outputs
  - NEVER replace canonical envelope fields with skill-local aliases
```
