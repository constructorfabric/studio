---
cf: true
type: requirement
name: Storytelling Dimensions
version: 0.1
purpose: Flow-neutral definitions, per-flow resolution rules, and anti-contracts for the three cross-cutting storytelling dimensions — audience, narrator/role, and diagram — reused by storytelling delivery and by review and authoring flows
---

# Storytelling Dimensions

<!-- toc -->

- [Audience Dimension](#audience-dimension)
- [Narrator / Role Dimension](#narrator--role-dimension)
- [Diagram Dimension](#diagram-dimension)
- [Cross-Cutting Anti-Contracts](#cross-cutting-anti-contracts)
- [References and Anchor Index](#references-and-anchor-index)
- [Change Log](#change-log)

<!-- /toc -->

Three cross-cutting dimensions first formalized by the storytelling methodology —
**audience**, **narrator/role**, and **diagram** — are reusable beyond explanatory
delivery. Review and authoring flows benefit from resolving the same dimensions, but
they resolve and apply them differently from interactive storytelling.

This file is the **single source of truth** for the *neutral definitions* of these
dimensions plus their *per-flow resolution rules* and *anti-contracts*. It is
**contract-neutral**: it defines what each dimension means and how each flow resolves
it, but it never defines a flow's output shape or validation verdict. Rich delivery
detail (the full audience-adaptation table, narrator-panel synthesis, the
visualize-by-default marker and lazy-ask) stays in the storytelling modules and is
referenced by anchor, never duplicated here.

**Loading.** Storytelling loads the sections it needs lazily, by section. Review and
authoring flows load this file eagerly at Bootstrap so audience and narrator are
resolved before sub-agent selection.

**Flow classes.** The rules below are written per flow class, not per skill name:

- **delivery** — `storytelling` (interactive, per-portion).
- **review** — the review-fix loop of `cf-write-docs` (document/prose review);
  `cf-analyze` routes document-review intent here.
- **authoring** — the artifact-production step of `cf-write-docs` (and `cf-generate`
  when it produces prose/document artifacts).

`cf-write-docs` is the hybrid consumer among the skills: it applies review-class rules
during its review-fix loop and authoring-class rules while producing the document.

**Out of scope.** Source-code and PDSL-skill flows (`cf-coding`, `cf-write-skills`) do
not consume these dimensions. Their audience is effectively fixed (engineers, or the
consuming agent), their narrator already maps onto reviewer/author sub-agents those
skills select deterministically, and their artifacts do not carry diagrams — so adding
the dimensions there would duplicate existing dispatch and add no adaptation value.

## Audience Dimension

The audience is the intended recipient(s) of the work product; it sets depth,
vocabulary, emphasis, and diagram detail. Values: one audience (engineers, product,
leadership, mixed, new joiners, customers) or a mixed set. The full adaptation
heuristics (amplify / soften / jargon / depth per audience) live in
`{cf-studio-path}/.core/requirements/storytelling-modes.md` (§ Audience adaptation
heuristics) and are referenced, not copied.

```pdsl
UNIT AudienceResolution
PURPOSE: Define how each flow class resolves and applies the audience dimension, and what it must never do.
RULES:
  - ALWAYS resolve the audience before producing audience-shaped output, using this default chain when it is not given explicitly: explicit user/request value, then artifact kind plus project context, then the flow's own named fallback (delivery uses the storytelling preferences default; review/authoring uses the artifact's primary reader)
  - ALWAYS in delivery: resolve interactively via the always-ask role/audience gate, per portion
  - ALWAYS in review: resolve once at Bootstrap and use audience only to scope emphasis (depth, vocabulary, what to surface first), never to change a finding's severity or the verdict
  - ALWAYS in authoring: resolve once at Bootstrap and use audience to set the authored document's level (language-complexity, depth), never as an acceptance gate
  - NEVER treat audience as a validation criterion or a gate on output; when audience is unknown, proceed with the named fallback and state which fallback was used
  - NEVER let audience adaptation alter verbatim source quotes; keep the quote unchanged and adapt only the surrounding framing, adding a labelled paraphrase when the quote is too dense for the audience
```

## Narrator / Role Dimension

The narrator is the voice or perspective that delivers or evaluates the work: a
single role or a multi-role panel. Storytelling synthesizes the role(s) per mode;
review flows map the panel onto reviewer sub-agents. Panel synthesis detail lives in
`{cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-panel.md`, and the per-mode
role composition in `{cf-studio-path}/.core/requirements/storytelling-modes.md`
(§ Modes table).

```pdsl
UNIT NarratorResolution
PURPOSE: Define how each flow class resolves and applies the narrator/role dimension, and what it must never do.
RULES:
  - ALWAYS resolve the narrator before producing narrated or reviewed output, defaulting deterministically when not given: derive the role(s) from the artifact kind and task, then map them onto the flow's own actors, never pausing for an interactive role pick in a non-interactive flow
  - ALWAYS in delivery: use a single chosen role (presentation) or a synthesized role panel (review/decision/onboarding), per mode and portion
  - ALWAYS in review: map the narrator onto the reviewer sub-agents the flow already selects deterministically at Bootstrap — a role panel maps to the per-methodology/per-layer reviewer set, a single role maps to a single reviewer
  - ALWAYS in authoring: map the narrator onto the author agent the flow selects and onto the voice of the authored artifact
  - NEVER let the narrator or persona introduce facts beyond the grounded source; omit unsupported claims instead
  - NEVER let narrator selection change a deterministic-gate result or a review verdict; when a persona's view would alter a verdict, record it as a separate perspective or finding, not as the verdict
```

## Diagram Dimension

A visualization is warranted when content is multi-entity, multi-step, multi-aspect,
comparative, transformational, or decision-bearing. Diagrams are constructed fresh
from source-grounded facts (never transcribed from the input), with detail adapted to
the audience. Diagram-shape selection and entity/step thresholds follow
`{cf-studio-path}/.core/requirements/storytelling-phases.md` (§ Phase E4:
Visualize-by-Default), which also owns the storytelling-only per-portion marker and
the one-time lazy-ask format prompt.

Text-only is legitimate **only** with an articulable reason — one that cites a
specific structural property of the content (for example: a single linear sequence
with no branches; one entity with no relationships; or an audience already fluent in
the pattern so a diagram would be redundant). Generic reasons ("the prose is fine",
"the input is small", "I don't feel like it") do not qualify.

```pdsl
UNIT DiagramResolution
PURPOSE: Define the flow-neutral diagram criteria and how each flow class applies them, and what it must never do.
RULES:
  - ALWAYS apply the neutral diagram criteria above before choosing text-only vs text+diagram, in every flow class
  - ALWAYS in delivery: visualize by default and surface the decision via the per-portion marker and the one-time lazy-ask format choice (Phase E4)
  - ALWAYS in review: use the criteria to decide whether a missing or unclear diagram is worth flagging as a finding; do not auto-generate diagrams
  - ALWAYS in authoring: embed a freshly constructed, audience-adapted diagram in the authored artifact when the criteria warrant one
  - ALWAYS state the qualifying articulable reason whenever a portion or artifact goes text-only
  - NEVER auto-generate diagrams outside a delivery or authoring output; review-class flows flag, they do not generate
  - NEVER accept text-only without a qualifying reason, and NEVER transcribe an input diagram verbatim — construct a fresh one
```

## Cross-Cutting Anti-Contracts

```pdsl
UNIT StorytellingDimensionsAntiContracts
PURPOSE: Bind the boundaries that keep these dimensions reusable without leaking storytelling's delivery contract into review or authoring output contracts.
RULES:
  - NEVER treat storytelling output as a validation report; when a verdict is needed, route to a review-class flow instead
  - NEVER treat these three dimensions as validation criteria or as gates on any flow's verdict; use them only to shape emphasis, voice, and visuals
  - NEVER require interactive resolution (per-portion gates, lazy-ask) in a non-interactive review or authoring flow; use the Bootstrap-time deterministic defaults defined above
  - ALWAYS keep each consuming flow's own output contract authoritative; this file adds dimensions, never output shape
```

## References and Anchor Index

- Audience Dimension — full heuristics: `{cf-studio-path}/.core/requirements/storytelling-modes.md` § Audience adaptation heuristics
- Narrator / Role Dimension — panel synthesis: `{cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-panel.md`; per-mode roles: `{cf-studio-path}/.core/requirements/storytelling-modes.md` § Modes table
- Diagram Dimension — shape thresholds and delivery mechanics: `{cf-studio-path}/.core/requirements/storytelling-phases.md` § Phase E4: Visualize-by-Default
- Cross-Cutting Anti-Contracts — boundaries shared by all three dimensions

## Change Log

- v0.1 — initial extraction of the audience, narrator/role, and diagram dimensions from the storytelling methodology: neutral definitions, per-flow-class resolution rules, and anti-contracts.
