---
status: accepted
date: 2026-06-26
decision-makers: project maintainer
---

# ADR-0022: Thin Standalone Skills with Module-First Runtime

**ID**: `cpt-studio-adr-thin-skills-module-first`

<!-- toc -->

- [Context and Problem Statement](#context-and-problem-statement)
- [Decision Drivers](#decision-drivers)
- [Considered Options](#considered-options)
- [Decision Outcome](#decision-outcome)
  - [Runtime Shape](#runtime-shape)
  - [Standalone Skill Registry](#standalone-skill-registry)
  - [Shared Module Registry](#shared-module-registry)
  - [Canonical Artifact Registry](#canonical-artifact-registry)
  - [Prerequisite and Override Behavior](#prerequisite-and-override-behavior)
  - [Unified Result Contract](#unified-result-contract)
  - [Consequences](#consequences)
  - [Confirmation](#confirmation)
- [Explore Discovery Pattern: `{domain}-discovery-run.md`](#explore-discovery-pattern-domain-discovery-runmd)
  - [Context](#context)
  - [Decision](#decision)
  - [Consequences](#consequences-1)
- [Pros and Cons of the Options](#pros-and-cons-of-the-options)
  - [Thin standalone skills plus module-first runtime (chosen)](#thin-standalone-skills-plus-module-first-runtime-chosen)
  - [Heavy per-skill orchestration](#heavy-per-skill-orchestration)
  - [One central orchestration workflow](#one-central-orchestration-workflow)
- [Related ADRs](#related-adrs)

<!-- /toc -->

## Context and Problem Statement

Constructor Studio currently embeds large amounts of orchestration inside a few
heavy workflows such as `coding`, `write-docs`, and `write-skills`. Those
workflows mix authoring, deterministic validation, semantic review loops,
findings browsing, fix approval, git policy handling, and completion reporting.

That shape makes the runtime hard to reason about, hard to reuse from kits, and
hard to decompose into smaller user-facing capabilities. It also encourages the
LLM to solve whole tasks from inside a single skill instead of using explicit
artifact handoffs.

The desired model is the opposite:

- every standalone skill is thin and single-purpose
- substantive behavior lives in reusable modules
- skills exchange explicit artifacts and a shared result envelope
- missing prerequisites produce visible `blocked` results and suggested next
  steps instead of hidden orchestration
- skills may still continue in an explicit override mode when the user allows it

## Decision Drivers

- **Thin user-facing entrypoints** — standalone skills must remain narrow and
  predictable.
- **Module reuse** — kits must be able to compose the same runtime building
  blocks without copying heavy workflow logic.
- **Explicit handoff** — the next step after missing prerequisites must be
  suggested visibly rather than inferred silently.
- **Artifact-centered flow** — skills must consume and produce explicit
  artifacts, not vague prose context.
- **Symmetry across domains** — code, docs, and prompt/skill workflows should
  follow the same runtime model.
- **Override safety** — user-approved degraded execution must be possible for
  authoring/planning-style work without weakening review or CI integrity.

## Considered Options

- **Thin standalone skills plus module-first runtime (chosen)** — standalone
  skills become thin entrypoints; shared modules own prerequisite checks,
  blocked reporting, handoff suggestions, review/report loops, and other common
  behavior.
- **Heavy per-skill orchestration** — keep `coding`, `write-docs`,
  `write-skills`, and related routes as self-contained end-to-end workflows.
- **One central orchestration workflow** — move sequencing into a dedicated
  global orchestrator and keep domain skills mostly passive.

## Decision Outcome

### Runtime Shape

Constructor Studio adopts a module-first thin-skill runtime:

- standalone skills are thin entrypoints
- shared modules contain substantive runtime behavior
- canonical artifacts are the data exchanged between skills
- every standalone skill returns the same top-level result envelope

Skills are allowed to suggest other skills when inputs are missing, but they
must not silently auto-route unless the user explicitly enables that behavior.

### Standalone Skill Registry

The canonical standalone skill set is:

- shared:
  - `explore`
  - `brainstorm`
  - `planning`
  - `git-commit`
- code:
  - `code-planning`
  - `coding-gen`
  - `coding-tests`
  - `coding-review`
  - `coding-fix`
  - `coding-ci`
- docs:
  - `documenting-planning`
  - `documenting-gen`
  - `documenting-review`
  - `documenting-fix`
  - `documenting-ci`
- prompt / skill / workflow:
  - `prompting-planning`
  - `prompting-gen`
  - `prompting-review`
  - `prompting-fix`
  - `prompting-ci`

The registry is explicit and source-controlled. Kits may add their own thin
entrypoints, but they must reuse the canonical result envelope and canonical
artifact names instead of redefining core runtime statuses or artifact classes.

### Shared Module Registry

The runtime uses shared modules, not standalone skills, for:

- prerequisite resolution
- blocked reporting
- missing-input reporting
- handoff suggestions
- assumption override handling
- artifact input-shape checks
- artifact DoD checks
- phase close and phase status updates
- findings rendering and aggregation
- CI report rendering
- commit policy loading, trailer preparation, and commit preflight
- shared skill/result contract loading
- shared artifact contract loading

All new substantive runtime logic should enter the system through modules first.
A standalone skill may remain only a thin wrapper around those modules.

The shared-module registry is likewise explicit: generated shims and kit-owned
thin skills are expected to load the canonical runtime contract modules before
they interpret skill-local prerequisite, blocked, override, report, or handoff
behavior.

### Canonical Artifact Registry

The canonical artifact registry is:

- design / decision:
  - `design-doc`
  - `design-decisions`
  - `unresolved-questions`
  - `acceptance-criteria`
  - `constraints`
- exploration:
  - `resource-context`
  - `relevant-files-map`
  - `dependency-map`
  - `test-surfaces`
- planning:
  - `phase-plan`
  - `phase-brief`
  - `phase-dod`
  - `phase-status`
- testing:
  - `unit-tests`
  - `e2e-tests`
  - `test-spec`
- authoring:
  - `code-changes`
  - `doc-changes`
  - `skill-changes`
- review / CI:
  - `review-findings`
  - `ci-findings`
  - `deterministic-report`
- git:
  - `commit-intent`
  - `commit-result`

The artifact registry is authoritative for cross-skill exchange. Kits may
introduce additional domain artifacts, but they must not repurpose canonical
artifact names with conflicting semantics.

### Prerequisite and Override Behavior

Every standalone skill must declare a prerequisite contract:

- required artifacts
- accepted input shapes
- stop conditions
- allowed override behavior
- suggested producers for missing artifacts

Missing prerequisites do not behave like hidden orchestration gates. Instead,
the skill returns a visible `blocked` result containing the missing artifacts,
why they matter, accepted shapes, suggested producers, and optional override
path.

Override behavior is allowed only for planning/authoring/explore/brainstorm
style skills. Review and CI skills must return deterministic results or
`blocked` / `failed`; they must not use assumption-based success states.

### Unified Result Contract

Every standalone skill returns the same top-level result envelope with the
canonical statuses:

- `ready`
- `blocked`
- `completed`
- `completed-with-assumptions`
- `failed`

The envelope separates artifact outputs from report outputs and includes:

- type
- skill
- status
- produced artifacts
- report outputs
- missing artifacts
- assumptions
- suggested next skills

Blocked results must make override semantics explicit. When degraded execution
is legal, the blocked payload must say so directly and identify the user-visible
override path rather than burying it inside prose.

### Consequences

**Positive**:

- skill responsibilities become explicit and narrow
- kits can reuse runtime modules directly
- artifact handoffs become visible and easier to validate
- review and CI can be separated cleanly from authoring
- runtime composition becomes more deterministic and inspectable

**Neutral**:

- some prior workflow behavior moves from a few large files into many smaller
  modules

**Negative / risk**:

- the migration is mechanically large because the current heavy workflows
  already embed review, validation, and reporting behavior
- the runtime must avoid ending up with both legacy heavy flows and new thin
  flows active at once

### Confirmation

Confirmed when:

- every standalone skill in the canonical registry is a thin wrapper
- substantive logic lives in shared modules, not embedded in standalone skills
- code, docs, and prompt/skill domains all follow the same
  skill-module-artifact-result model
- missing prerequisites produce visible blocked envelopes with suggested
  producers
- review and CI skills are separate from authoring skills
- generated bootstraps load the shared thin-skill contracts for all workflows
  and skill entrypoints

## Explore Discovery Pattern: `{domain}-discovery-run.md`

### Context

Several thin skills and shared modules invoke `cf-explore` to produce a
`resource-context` or similar exploration artifact and then check that artifact
through `PrerequisiteCheckContract` before continuing. When this invocation is
inlined directly inside a standalone skill or a general-purpose shared module,
the skill drifts toward owning orchestration logic that should live in a
dedicated reusable unit. Two existing callers — `CodingExploreGate` inside
`coding-ci` and `WriteSkillsExploreGate` inside `write-skills-ci` — already
exhibit this drift and are grandfathered pending their next significant change.

### Decision

When a `cf-explore` invocation produces a result that is subsequently evaluated
by `PrerequisiteCheckContract` as a required artifact, that invocation MUST be
extracted into a dedicated shared module named
`{workflow-family}-discovery-run.md`, placed in `skills/studio/modules/`.

**Extraction criterion** (all three conditions must hold):

1. The unit invokes `cf-explore` (directly or via a thin wrapper).
2. The result is stored in a named artifact or state variable.
3. That named artifact or state variable is later evaluated by
   `PrerequisiteCheckContract` as a required artifact.

Immediate-consumption inline explore calls — where the result is consumed and
discarded in the same unit without entering the prerequisite check pipeline —
are exempt from mandatory extraction.

The definitive 3-condition form is in `ExploreDiscoveryExtractionCriterion` in
`skills/studio/modules/runtime/explore-discovery-pattern.md`; this summary is
informational.

**Naming convention**:

| Component | Pattern |
|---|---|
| File | `skills/studio/modules/{workflow-family}-discovery-run.md` |
| Primary UNIT | `{WorkflowFamily}DiscoveryRunStart` |
| Classify UNIT | `{WorkflowFamily}DiscoveryRunClassifyResult` |
| Failure UNIT | `{WorkflowFamily}DiscoveryRunFailure` |
| Failure menu | `{WorkflowFamily}DiscoveryFailureMenu` |

**Canonical reference implementation**: `kit-discovery-run.md` is the reference
for structure (start, classify-result, failure, failure-menu), return-context
invocation mode, read-only constraint, and DISCOVERY_STATUS classification.

**Rule location**: The precise extraction criterion and naming convention are
codified in `skills/studio/modules/runtime/explore-discovery-pattern.md`
(`ExploreDiscoveryPattern` UNIT). `ThinSkillModuleFirstLaw` in
`thin-skill-contracts.md` carries a NOTES pointer to that module.

### Consequences

**Positive**:

- explore orchestration becomes a first-class reusable module rather than
  embedded inline in standalone skills
- new CI and domain skills can compose discovery behavior without duplicating
  the classify-result and failure-menu logic
- `PrerequisiteCheckContract` evaluation remains decoupled from discovery
  orchestration details

**Neutral**:

- authors must create a companion `{domain}-discovery-run.md` module alongside
  any new thin skill whose CI or review gate requires explore-sourced context

**Migration**:

- `ci-discovery-run.md` is the first new instance following this pattern,
  introduced with the CI skills explore-first discovery feature
- `CodingExploreGate` and `WriteSkillsExploreGate` are grandfathered; extraction
  becomes mandatory when either is next significantly changed

## Pros and Cons of the Options

### Thin standalone skills plus module-first runtime (chosen)

* Good, because user-facing capabilities stay narrow and predictable.
* Good, because kits can reuse modules instead of copying orchestration.
* Good, because artifact handoff becomes explicit and inspectable.
* Good, because authoring, review, and CI can evolve independently.
* Bad, because the initial migration is broad and touches many files.

### Heavy per-skill orchestration

* Good, because behavior is concentrated in fewer files.
* Bad, because it makes skill boundaries blurry and hard to reuse.
* Bad, because the LLM can drift into solving unrelated steps from inside one
  skill.
* Bad, because code/docs/skills runtime behavior becomes harder to align.

### One central orchestration workflow

* Good, because sequencing can be centralized.
* Bad, because it introduces a new mandatory orchestration surface that can be
  forgotten or bypassed by domain skills.
* Bad, because it weakens the goal that skills should be able to run
  independently with visible blocked results.

## Related ADRs

- `cpt-studio-adr-two-workflow-model`
- `cpt-studio-adr-execution-plans`
- `cpt-studio-adr-ai-cli-extensibility-subagents`
- `cpt-studio-adr-skill-md-entry-point`
