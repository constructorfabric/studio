# Phase 03 Shared Context Pack Builder Contract

## Purpose

Define the controller-owned contract that the Phase 3 top-level orchestration
surface implements for shared-context-pack loading and prompt-context delivery.

## Session Scope

- A chat session owns exactly one logical `SHARED_CONTEXT_PACK`.
- The pack is session-scoped, not workflow-run-scoped.
- Workflow runs MUST reuse the existing pack before discovering any new prompt
  asset.
- The pack MAY be extended incrementally when a later workflow run requires new
  prompt assets.
- The controller MUST NOT rebuild the full pack by default for each workflow
  run.

## Asset Freshness

- Every reused asset MUST be revalidated by `etag` before it contributes to a
  new `prompt_context_view`.
- When `etag` revalidation marks an asset stale, the controller MUST refresh or
  replace that asset in the session pack before reuse.
- `etag` freshness checks are independent of workflow-run boundaries.

## Loader Roles

| Role | Allowed behavior |
| --- | --- |
| Dispatching controller | Reuse or extend `SHARED_CONTEXT_PACK`, revalidate `etag`, derive `prompt_context_view`, and block dispatch on missing required prompt context |
| Dedicated pack builder | Load only the prompt assets delegated by a controller, classify them, compute `etag`, and return pack-ready assets |
| Top-level runtime controller | Load runtime bootstrap/config instruction surfaces, reuse or extend the pack, and hand resulting prompt assets to the dispatching controller |
| Prompt-consuming sub-agent | Consume `prompt_context_view` only; never reload prompt assets from disk |

No other role may discover or reload prompt assets from disk.

## Prompt Context Requirements Resolution

- Each prompt-consuming sub-agent is expected to declare
  `prompt_context_requirements`.
- The controller resolves those requirements semantically against the current
  session pack plus any missing controller-loaded assets.
- Resolution preserves `asset_id`, `asset_type`, `origin`, `kit_id`, `path`,
  `etag`, tags, and executable prompt text.
- When a runtime mirror exists, controller-owned loads MUST use the
  `{cf-studio-path}`-prefixed runtime path.

## Prompt Context View Derivation

- The controller MUST derive one minimal `prompt_context_view` per dispatch.
- The view MUST contain all required prompt assets and only the assets needed
  for that dispatch.
- The view MUST include executable prompt text, either as whole-asset `body`
  content or section-level slices.
- `asset_refs` remain audit metadata and do not replace executable prompt text.

## Pre-Dispatch Validation

Before dispatching a prompt-consuming sub-agent, the controller MUST verify:

1. The sub-agent declares `prompt_context_requirements`.
2. `SHARED_CONTEXT_PACK` exists for the session.
3. Every required asset resolves to an allowed type and origin.
4. Reused assets passed `etag` revalidation or were refreshed/replaced.
5. No required asset remains missing.
6. No non-prompt resource was inserted into the pack as executable prompt
   content.

If any check fails, dispatch MUST stop before the sub-agent runs.

## Failure Handling

- Missing required prompt context is a controller-owned orchestration error.
- The controller MUST fail closed and MUST NOT degrade to direct prompt-file
  reads by the consumer.
- Failure output MUST identify the missing semantic asset key or resolved asset
  id and the controller role that attempted dispatch.
- Existing checkpoint or partial-return semantics in the surrounding workflow
  remain in force.

## Runtime Logging Expectations

- Runtime logging MUST record whether a workflow reused, refreshed, or extended
  `SHARED_CONTEXT_PACK`.
- Logging MUST occur at controller-owned bootstrap/routing points before
  downstream dispatch.
- Logging should remain compact and deterministic so it survives context
  compaction and status handoffs.

## Compaction-Safe Session Reuse

- Session-pack state is authoritative across workflow runs in the same chat.
- Workflow routers remain compact and do not inline downstream phase bodies or
  leaf prompt contracts.
- Compaction recovery may discard prose summaries, but it MUST preserve the
  session-pack invariants, prompt-context requirements contract, and the rule
  that consumers use `prompt_context_view` rather than direct file loads.

## Phase 3 Top-Level Surfaces Bound To This Contract

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
