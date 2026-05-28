# Phase 03 Orchestrator Migration Inventory

## Scope

Phase 3 migrates only the top-level orchestration surface:

- `AGENTS.md`
- `.bootstrap/config/AGENTS.md`
- `skills/studio/SKILL.md`
- `skills/studio/protocol.md`
- `skills/studio/routing.md`
- `workflows/generate.md`
- `workflows/analyze.md`
- `workflows/plan.md`
- `workflows/pdsl.md`
- `workflows/workspace.md`

Leaf sub-agent contracts, workflow fragments, and runtime mirrors under
`.bootstrap/.core/` and `.bootstrap/.gen/` remain out of scope for this phase.

## Migration Inventory

| File | Current behavior before Phase 3 | Target behavior after Phase 3 | Shared-loader ownership / direct-load action |
| --- | --- | --- | --- |
| `AGENTS.md` | Declared only `cf-studio-path`, leaving session-pack ownership implicit | States that top-level controllers own prompt loading and leaf consumers rely on `prompt_context_view` | No controller load removed; adds top-level ownership boundary |
| `.bootstrap/config/AGENTS.md` | Mixed controller rules with no shared-pack statement; one canonical spec path remained | Declares session-pack reuse/etag refresh rules and normalizes core spec reference to `{cf-studio-path}` runtime path | Controller-only runtime loads remain legal; leaf self-bootstrap implication removed |
| `skills/studio/SKILL.md` | Enforced phase gates and dispatch flow without explicit shared-pack authority unit | Defines session-scoped `SHARED_CONTEXT_PACK`, controller-only loader authority, `etag` revalidation, and consumer reliance on `prompt_context_view` | Keeps controller-owned loads; forbids consumer direct loads |
| `skills/studio/protocol.md` | Protocol Guard loaded runtime instruction surfaces but did not classify them as shared-pack assets | Treats Protocol Guard loads as controller-owned prompt assets that reuse/refresh the session pack with runtime logging | Direct runtime loads retained only for top-level controller/bootstrap work |
| `skills/studio/routing.md` | Routed into canonical workflow paths such as `workflows/*.md` | Routes through `{cf-studio-path}/.core/...` runtime mirrors and states routing is shared-pack-aware | Removes legacy root-relative prompt loads from routing surface |
| `workflows/generate.md` | Loaded workflow fragments via canonical `workflows/...` paths and left pack reuse implicit | Uses `{cf-studio-path}/.core/workflows/...` for controller-owned loads and requires pack reuse before author/reviewer dispatch | Direct loads retained only in controller workflow; consumer reload assumption removed |
| `workflows/analyze.md` | Loaded workflow fragments via canonical `workflows/...` paths and left pack reuse implicit | Uses `{cf-studio-path}/.core/workflows/...` for controller-owned loads and requires pack reuse before reviewer dispatch | Direct loads retained only in controller workflow; consumer reload assumption removed |
| `workflows/plan.md` | Loaded shared/workflow fragments via canonical `workflows/...` paths and did not state pack reuse for phase compiler/runner routing | Uses `{cf-studio-path}/.core/workflows/...` runtime paths and defines plan-phase shared-pack ownership before downstream dispatch | Keeps controller-owned plan loads only |
| `workflows/pdsl.md` | Mixed runtime and root-relative loads; left cf-pdsl dispatch dependent on later leaf self-loading | Normalizes workflow/protocol paths to runtime mirrors and requires `prompt_context_view` before any cf-pdsl dispatch | Removes top-level reliance on leaf direct prompt loads |
| `workflows/workspace.md` | Loaded AGENTS/workspace fragments without stating session-pack ownership | Treats AGENTS surfaces as controller-owned prompt assets and routes phase fragments via `{cf-studio-path}/.core/workflows/workspace/...` | Keeps controller-owned AGENTS loads only |

## Direct-Load Hotspots Removed Or Rewritten

- Root-relative workflow references in `skills/studio/routing.md` now use
  `{cf-studio-path}/.core/workflows/...` or
  `{cf-studio-path}/.core/skills/studio/...`.
- Root-relative workflow-fragment references in `workflows/generate.md`,
  `workflows/analyze.md`, `workflows/plan.md`, `workflows/pdsl.md`, and
  `workflows/workspace.md` now use `{cf-studio-path}/.core/...` runtime paths.
- The remaining direct prompt loads in touched files are limited to
  orchestrator-owned bootstrap, routing, or workflow-fragment loading.

## Session-Reuse Points

- `skills/studio/SKILL.md` now declares the session-scoped
  `SHARED_CONTEXT_PACK` and controller reuse/refresh rules.
- `skills/studio/protocol.md` makes Protocol Guard responsible for reusing,
  refreshing, or extending runtime prompt assets during bootstrap.
- `skills/studio/routing.md` requires reuse or extension of the session pack
  before downstream dispatch that needs prompt assets.
- Each touched top-level workflow now states that prompt-consuming dispatches
  must derive `prompt_context_view` from the shared pack rather than reopen
  prompt files.

## Project And Bootstrap AGENTS Changes

- `AGENTS.md` now declares the repository-wide prompt-loading ownership model.
- `.bootstrap/config/AGENTS.md` now describes session-pack reuse, `etag`
  refresh, and the no-direct-load rule for prompt-consuming sub-agents.
- `.bootstrap/config/AGENTS.md` also normalizes `CLISPEC.md` to its runtime
  mirror path under `{cf-studio-path}/.core/...`.

## Runtime Mirror Refresh Requirement

Phase 3 updates only canonical source files plus phase `out/` artifacts. The
runtime mirrors under `.bootstrap/.core/` and `.bootstrap/.gen/` remain
unchanged until the dedicated refresh and validation work in Phase 6. No
hand-edited runtime mirror changes are allowed in this phase.

## Downstream Dependencies For Later Phases

- Phase 4 must add concrete `prompt_context_requirements` declarations to
  leaf sub-agent contracts and `skills/studio/agents.toml`.
- Phase 4 must remove remaining leaf direct-load instructions from
  `skills/studio/agents/**/*.md`.
- Phase 5 must migrate prompt-bearing requirements and specs that are still
  consumed directly as prompt assets.
- Phase 6 must refresh `.bootstrap/.core/` and `.bootstrap/.gen/`, then verify
  that runtime mirrors and generated prompt surfaces reflect the canonical
  top-level changes from Phase 3.
