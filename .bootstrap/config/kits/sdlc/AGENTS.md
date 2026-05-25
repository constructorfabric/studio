# Constructor Studio Kit: SDLC (`sdlc`)

Agent quick reference.

## What it is

Artifact-first SDLC pipeline (PRD → ADR + DESIGN → DECOMPOSITION → FEATURE → CODE) with templates, checklists, examples, and per-artifact `rules.md` for deterministic validation + traceability.

## Artifact kinds

| Kind | Semantic intent (when to use) | References |
| --- | --- | --- |
| PRD | Product intent: actors + problems + FR/NFR + use cases + success criteria. | `{prd_rules}`, `{prd_template}`, `{prd_checklist}`, `{prd_example}` |
| ADR | Decision log: why an architecture choice was made (context/options/decision/consequences). | `{adr_rules}`, `{adr_template}`, `{adr_checklist}`, `{adr_example}` |
| DESIGN | System design: architecture, components, boundaries, interfaces, drivers, principles/constraints. | `{design_rules}`, `{design_template}`, `{design_checklist}`, `{design_example}` |
| DECOMPOSITION | Executable plan: FEATURE list, ordering, dependencies, and coverage links back to PRD/DESIGN. | `{decomposition_rules}`, `{decomposition_template}`, `{decomposition_checklist}`, `{decomposition_example}` |
| FEATURE | Precise behavior + DoD: CDSL flows/algos/states + test scenarios for implementability. | `{feature_rules}`, `{feature_template}`, `{feature_checklist}`, `{feature_example}` |
| CODE | Implementation of FEATURE with optional `@cpt-*` markers and checkbox cascade/coverage validation. | `{codebase_rules}`, `{codebase_checklist}` |
