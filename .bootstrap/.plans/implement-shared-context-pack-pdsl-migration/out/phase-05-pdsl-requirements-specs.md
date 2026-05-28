# Phase 05 Requirements And Specs Migration

## Migrated File Inventory

| File | Why it was targeted | Main transformation | Deferred follow-up |
| --- | --- | --- | --- |
| `requirements/storytelling.md` | Router-level prompt asset still expressed its gate flow in prose and carried a root-relative shared-module load. | Added explicit PDSL router units for activation, E0/E5 gate sequencing, and controller-owned module loading; normalized the shared-module load to `{cf-studio-path}/.core/requirements/...`. | The deeper storytelling phase modules (`storytelling-phases.md`, `storytelling-modes.md`, `storytelling-preferences.md`, `storytelling-export.md`) still contain large prose-heavy execution surfaces and should be migrated in a later tranche. |
| `requirements/reverse-engineering.md` | Active methodology prompt with ordered runtime phases and deterministic recovery paths expressed only in prose. | Added PDSL units for activation, layer ordering, and error handling while preserving the detailed layer reference tables as prose. | The per-layer checklists remain prose-first reference content by design. |
| `requirements/auto-config.md` | Brownfield auto-config prompt carried phase sequencing, write boundaries, and stop conditions only in prose. | Added PDSL units for activation, phase sequencing, write boundaries, and recovery/stop behavior; preserved the phase-specific methodology detail as prose/reference content. | The generated rule examples and long-form phase guidance remain prose-first reference material. |
| `architecture/specs/shared-context-pack.md` | Canonical shared-context spec needed explicit PDSL contracts for controller lifecycle, prompt-context views, validation, and consumer rules. | Added operational PDSL units that formalize session-pack reuse, fail-closed validation, and prompt-consuming agent invariants; retained the schema/reference sections as prose. | Broader example and migration-guidance sections remain prose-first reference content. |
| `architecture/specs/sysprompts.md` | Project sysprompt spec still described loading/validation behavior in prose and did not explicitly state the shared-context-pack handoff model. | Added PDSL units for prompt-asset classification, controller-owned loading, and warning/error handling; updated the loading algorithm prose to publish prompt text into `SHARED_CONTEXT_PACK` and `prompt_context_view`. | Example project files remain illustrative prose/examples. |
| `architecture/specs/artifacts-registry.md` | Prompt-bearing registry spec still relied on prose for controller activation, mutation boundaries, and deterministic failures. | Added PDSL units for activation, registry operations, and failure handling while preserving schema/reference sections as prose. | The long schema sections remain prose-first reference material. |

## Scope Notes

- This phase intentionally stayed within the prompt-bearing files that still mixed active runtime behavior with prose-only control flow or stale shared-context assumptions.
- No source code, workflow files, skill files, tests, or bootstrap mirrors were edited in this phase.

## Deferred Follow-Up

- `requirements/storytelling-{phases,modes,preferences,export}.md`
- `architecture/specs/{CDSL,CLISPEC,cli,traceability}.md`
- `architecture/specs/kit/{checklist,constraints,example,kit,rules,template}.md`

These surfaces remain in the broader Phase 01 scope map, but they were not required to complete the Phase 05 controller/runtime-contract migration slice executed here.
