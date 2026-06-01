---
cf: true
type: workflow
name: cf-pdsl
description: "Invoke for requests to author, transform, compress, normalize, or review prompt, workflow, skill, or agent instruction files as compact state-machine-like PDSL contracts."
version: 0.1
purpose: Dedicated workflow for authoring, transforming, and auditing compact PDSL prompt contracts
---

# PDSL Workflow

This workflow creates and reviews prompt-facing instruction files written in
PDSL. It is for files such as `skills/**/*.md`, `workflows/**/*.md`,
`requirements/**/*.md`, agent contracts, and prompt configuration documents.

## Bootstrap

```text
UNIT RootSkillEntrypointBootstrap
PURPOSE: Prevent direct workflow entry from bypassing the root cf skill.
DO:
  1. REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md is loaded completely
     and followed FIRST.
  2. REQUIRE CfSkillInit, Bootstrap, HardRules, and
     WorkflowProtocolNonSubstitution from SKILL.md have completed.
  3. CONTINUE this workflow only after the root cf skill routing/entrypoint
     selects it.
RULES:
  - MUST execute before any workflow-specific unit in this file.
  - MUST_NOT treat protocol.md, routing.md, or a thin proxy skill as a
    substitute for loading and following SKILL.md.
  - If this workflow file is opened directly, STOP workflow phases until
    SKILL.md has been loaded completely and followed.
  - This gate applies to the top-level controller only; dispatched sub-agents
    consume the synthesized final prompt and supplied context slices.
```

```text
UNIT PdslBootstrap

PURPOSE:
  Load required files before any phase work begins.

RULES:
  - The top-level controller loads or reuses `{cf-studio-path}/.core/skills/studio/SKILL.md`
    WHEN `{cfs_mode}` == off, and follows it before any workflow-local
    bootstrap or protocol asset
  - The top-level controller loads or reuses `{cf-studio-path}/.core/skills/studio/protocol.md`
    only after SKILL.md bootstrap/routing has completed
  - The top-level controller loads or reuses `{cf-studio-path}/.core/architecture/specs/PDSL.md`
  - The top-level controller loads or reuses `{cf-studio-path}/.core/workflows/shared/stop-token-policy.md`
  - The top-level controller loads `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md`
    before any cf-pdsl-* dispatch decision
  - Any cf-pdsl-* sub-agent receives required slices through prompt_context_view
    and MUST_NOT reopen SKILL, workflow, requirement, spec, AGENTS, or kit
    prompt files from disk
```

```text
UNIT PdslSharedContextPack

PURPOSE:
  Keep PDSL prompt loading controller-owned and pack-aware.

RULES:
  - Mode files and PDSL helper contracts are controller-owned prompt assets
    loaded from {cf-studio-path}/.core/...
  - Before any cf-pdsl-* dispatch, the controller MUST reuse or extend
    SHARED_CONTEXT_PACK, load the agent prompt source, and synthesize the
    final dispatch prompt with only the task-relevant instruction context
  - PDSL sub-agents MUST NOT self-bootstrap by reopening SKILL, workflow, spec,
    or AGENTS prompt files directly
```

## Intent Routing

```text
UNIT PdslModeRouter

PURPOSE:
  Select and load exactly one PDSL mode file.

STATE:
  PDSL_MODE: unset | new | transform | review
    default: unset
    scope: workflow_run

WHEN:
  PDSL_MODE == unset

DO:
  IF user intent matches a new alias:
    SET PDSL_MODE = new
    LOAD {cf-studio-path}/.core/workflows/pdsl/new.md
    STOP_TURN
  ELSE IF user intent matches a transform alias:
    SET PDSL_MODE = transform
    LOAD {cf-studio-path}/.core/workflows/pdsl/transform.md
    STOP_TURN
  ELSE IF user intent matches a review alias:
    SET PDSL_MODE = review
    LOAD {cf-studio-path}/.core/workflows/pdsl/review.md
    STOP_TURN
  ELSE:
    EMIT_MENU PdslModeMenu
    WAIT user.reply
    STOP_TURN

MENU PdslModeMenu:
  TITLE: Choose PDSL mode
  OPTIONS:
    1 new -> SET PDSL_MODE = new
             LOAD {cf-studio-path}/.core/workflows/pdsl/new.md
             STOP_TURN
    2 transform -> SET PDSL_MODE = transform
                   LOAD {cf-studio-path}/.core/workflows/pdsl/transform.md
                   STOP_TURN
    3 review -> SET PDSL_MODE = review
                LOAD {cf-studio-path}/.core/workflows/pdsl/review.md
                STOP_TURN
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN

NOTES:
  Mode aliases:
    new:       create | author | new prompt | new file
    transform: convert | rewrite | migrate | dsl transform
    review:    check | audit | validate | inspect

  Only one mode file is loaded per workflow run unless the user explicitly
  starts a new PDSL request.
```

## Explore / Brainstorm Applicability

```text
UNIT PdslExploreBrainstormGate

PURPOSE:
  Decide whether PDSL authoring needs related prompt-resource discovery or
  design exploration before dispatch.

WHEN:
  PDSL_MODE is selected
  AND before mode-specific dispatch

DO:
  REQUIRE {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md is loaded and followed

RULES:
  - SHOULD offer cf-explore for transform/review when source_paths omit related
    workflows, requirements, agent prompts, or specs needed for consistency
  - SHOULD offer cf-brainstorm for new prompt architecture, state/menu policy,
    dispatch semantics, or cross-agent contract changes
  - MUST NOT require brainstorm for mechanical compacting or direct review when
    target_paths and source_paths are explicit
```

## Shared Inputs

All modes use this shared context.

```json
{
  "mode": "new|transform|review",
  "target_paths": ["<path>", "..."],
  "source_paths": ["<optional related prompt/workflow/spec paths>", "..."],
  "pdsl_spec_path": "{cf-studio-path}/.core/architecture/specs/PDSL.md",
  "rules_mode": "STRICT|RELAXED"
}
```

Input rules:

- `target_paths` MUST be explicit for `transform` and `review`.
- `target_paths[0]` MUST be explicit for `new` when the workflow writes a file.
- `source_paths` MAY include related workflows, requirements, existing prompt
  files, specs, or notes.
- Missing required inputs MUST trigger a scoped question and `STOP_TURN`.

## Dispatch Gate

```text
UNIT PdslDispatchGate

PURPOSE:
  Resolve canonical inline-fallback state before any cf-pdsl-* dispatch or
  inline contract.

WHEN:
  before any mode-specific cf-pdsl-* dispatch decision

DO:
  REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md is loaded
  RUN InlineFallbackProbe
  REQUIRE returned.state == resolved
  REQUIRE INLINE_FALLBACK_PROBED == true
  IF INLINE_FALLBACK == true:
    inline the matching contract:
      cf-pdsl-author      -> {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-author.md
      cf-pdsl-transformer -> {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-transformer.md
      cf-pdsl-reviewer    -> {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-reviewer.md
  ELSE:
    DISPATCH named sub-agent

RULES:
  - MUST route Sub-Agent Approval Gate, HostNoNativeSubAgentMenu, and
    NativeSubAgentPolicyConflict handling through shared
    inline-fallback-probe.md
  - MUST treat NativeSubAgentPolicyConflict as a distinct approval boundary
    owned by the shared probe
  - MUST apply dispatch protocol from `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md` before any DISPATCH
  - MUST synthesize the dispatched agent's final prompt from
    SHARED_CONTEXT_PACK plus the agent prompt source before any cf-pdsl-*
    dispatch or inline contract
  - MUST_NOT dispatch write-capable modes (new, transform) until write summary is user-approved
  - MUST_NOT read or branch on INLINE_FALLBACK unless
    INLINE_FALLBACK_PROBED == true for the active workflow run
  - MUST_NOT emit local approval or fallback menus in this workflow
  - MUST_NOT default INLINE_FALLBACK from host capability, policy conflict, or
    missing approval

NOTES:
  Full approval gate semantics and the INLINE_FALLBACK_PROBED /
  NativeSubAgentPolicyConflict state machine are defined in
  {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md,
  {cf-studio-path}/.core/skills/studio/SKILL.md § Session Sub-Agent Approval
  Gate, and {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md.
```

## Completion

```text
UNIT PdslCompletion

PURPOSE:
  Define terminal conditions for all PDSL modes.

INVARIANTS:
  - MUST NOT claim completion for new or transform mode until a manifest is returned
  - MUST NOT claim completion for review mode until a validation report is returned
  - MUST NOT claim PASS for any unread target path
  - Review validation report MUST include all six sections:
      1. Summary
      2. Files Reviewed
      3. Findings
      4. Compactness Opportunities
      5. Residual Risks
      6. Recommended Fixes
  - If the workflow cannot read all requested files it MUST return a partial
    checkpoint and MUST NOT claim PASS for unread paths
```
