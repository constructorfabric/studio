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

```pdsl
UNIT PdslRootSkillEntrypointBootstrap
PURPOSE: Load the shared root cf skill entrypoint bootstrap.
DO:
  - LOAD {cf-studio-path}/.core/workflows/shared/root-skill-entrypoint-bootstrap.md
  - CONTINUE RootSkillEntrypointBootstrap
```

```pdsl
UNIT PdslModeDirective
PURPOSE: Set cf skill mode and capture original intent before any phase work begins.
DO:
  - SET CF_MODE = "cf-pdsl"
  - SET ORIGINAL_INTENT = user's triggering request (verbatim or shortest faithful summary)
RULES:
  - ALWAYS SET CF_MODE = "cf-pdsl" as the first action after bootstrap
  - ALWAYS capture ORIGINAL_INTENT from the user's triggering message before PdslModeRouter evaluates intent
  - ALWAYS carry ORIGINAL_INTENT into PdslModeDispatch and every cf-pdsl-* dispatch payload as task context
  - NEVER leave CF_MODE unset when entering this workflow
```

```pdsl
UNIT PdslBootstrap

PURPOSE:
  Load required files before any phase work begins.

RULES:
  - ALWAYS The top-level controller loads or reuses `{cf-studio-path}/.core/skills/studio/SKILL.md`
    WHEN `{cfs_mode}` == off, and follows it before any workflow-local
    bootstrap or protocol asset
  - ALWAYS The top-level controller loads or reuses `{cf-studio-path}/.core/skills/studio/protocol.md`
    only after {cf-studio-path}/.core/skills/studio/SKILL.md bootstrap/routing has completed
  - ALWAYS The top-level controller loads or reuses `{cf-studio-path}/.core/architecture/specs/PDSL.md`
  - ALWAYS The top-level controller loads or reuses `{cf-studio-path}/.core/workflows/shared/stop-token-policy.md`
  - ALWAYS The top-level controller loads `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md`
    before any cf-pdsl-* dispatch decision
  - ALWAYS Any cf-pdsl-* sub-agent receives required slices through prompt_context_view
    and NEVER reopen SKILL, workflow, requirement, spec, AGENTS, or kit
    prompt files from disk
```

```pdsl
UNIT PdslSharedContextPack

PURPOSE:
  Keep PDSL prompt loading controller-owned and pack-aware.

DO:
  - LOAD {cf-studio-path}/.core/workflows/shared/shared-context-pack-ownership.md
  - CONTINUE SharedContextPackOwnership

RULES:
  - ALWAYS Mode files and PDSL helper contracts remain the workflow-specific
    prompt-asset family for this shared ownership contract
```

## Intent Routing

```pdsl
UNIT PdslModeRouter

PURPOSE:
  Select and load exactly one PDSL mode file.

STATE:
  - SET PDSL_MODE: unset | new | transform | review
    default: unset
    scope: workflow_run

WHEN:
  - REQUIRE PDSL_MODE == unset

DO:
  - REQUIRE user intent matches a new alias:
    - SET PDSL_MODE = new
    - CONTINUE PdslExploreBrainstormGate
  - RUN otherwise IF user intent matches a transform alias:
    - SET PDSL_MODE = transform
    - CONTINUE PdslExploreBrainstormGate
  - RUN otherwise IF user intent matches a review alias:
    - SET PDSL_MODE = review
    - CONTINUE PdslExploreBrainstormGate
  - RUN otherwise
    - EMIT_MENU PdslModeMenu
    - WAIT user.reply
    - STOP_TURN

MENU PdslModeMenu:
  TITLE: Choose PDSL mode
  OPTIONS:
    1 new -> SET PDSL_MODE = new; CONTINUE PdslExploreBrainstormGate
    2 transform -> SET PDSL_MODE = transform; CONTINUE PdslExploreBrainstormGate
    3 review -> SET PDSL_MODE = review; CONTINUE PdslExploreBrainstormGate
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

```pdsl
UNIT PdslExploreBrainstormGate

PURPOSE:
  Decide whether PDSL authoring needs related prompt-resource discovery or
  design exploration before dispatch.

WHEN:
  - REQUIRE PDSL_MODE is selected
  - AND before mode-specific dispatch

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md is loaded and followed
  - CONTINUE PdslModeDispatch

RULES:
  - ALWAYS offer cf-explore for transform/review when source_paths omit related
    workflows, requirements, agent prompts, or specs needed for consistency
  - ALWAYS offer cf-brainstorm for new prompt architecture, state/menu policy,
    dispatch semantics, or cross-agent contract changes
  - NEVER require brainstorm for mechanical compacting or direct review when
    target_paths and source_paths are explicit
```

```pdsl
UNIT PdslModeDispatch

PURPOSE:
  Load exactly one mode file after explore/brainstorm applicability has resolved.

DO:
  - REQUIRE PDSL_MODE == new:
    - LOAD {cf-studio-path}/.core/workflows/pdsl/new.md
    - STOP_TURN
  - REQUIRE PDSL_MODE == transform:
    - LOAD {cf-studio-path}/.core/workflows/pdsl/transform.md
    - STOP_TURN
  - REQUIRE PDSL_MODE == review:
    - LOAD {cf-studio-path}/.core/workflows/pdsl/review.md
    - STOP_TURN
  - REQUIRE PDSL_MODE == unset:
    - EMIT_MENU PdslModeMenu
    - WAIT user.reply
    - STOP_TURN
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

```pdsl
UNIT PdslSharedInputRules

PURPOSE:
  Define shared input constraints for all PDSL modes.

RULES:
  - ALWAYS require target_paths for transform and review modes
  - ALWAYS require target_paths[0] for new mode when the workflow writes a file
  - ALWAYS fence PDSL instruction blocks in generated or transformed Markdown with `pdsl`, not `text`
  - ALWAYS emit a scoped question and STOP_TURN when required inputs are missing

NOTES:
  source_paths may include related workflows, requirements, existing prompt files, specs, or notes.
```

## Shared PDSL Validation

```pdsl
UNIT PdslCommandValidationReuse

PURPOSE:
  Reuse the deterministic `cfs pdsl validate` command as the shared PDSL
  quality gate for cf-pdsl modes.

DO:
  - REQUIRE PDSL_MODE == review AND target_paths is non-empty:
    - RUN `cfs pdsl validate <target_paths>` as read-only preflight
    - RUN Attach findings to ReviewPromptInputs without redefining reviewer
      success semantics
  - REQUIRE PDSL_MODE == transform AND target_paths is non-empty:
    - RUN `cfs pdsl validate <target_paths>` as read-only preflight
    - RUN Attach findings to TransformPromptInputs before transformer dispatch
  - REQUIRE PDSL_MODE == new OR PDSL_MODE == transform:
    - RUN After a manifest returns written PDSL paths, run
      `cfs pdsl validate <written_paths>` as blocking postflight
    - REQUIRE postflight result is PASS before claiming clean completion

RULES:
  - ALWAYS `cfs pdsl validate` remains the source of truth for PDSL parsing,
    rule identifiers, normalized findings, ordering, and PASS/FAIL/ERROR
    source status
  - NEVER cf-pdsl modes define separate PDSL parser rules, rule IDs, or
    success semantics
  - NEVER validation hints emit scaffold text, autofix patches, or rewrite
    templates
  - ALWAYS JSON output is requested only when the orchestrator needs a machine
    payload; user-facing mode may use human output
```

## Dispatch Gate

```pdsl
UNIT PdslDispatchGate

PURPOSE:
  Resolve canonical inline-fallback state before any cf-pdsl-* dispatch or
  inline contract.

WHEN:
  - REQUIRE before any mode-specific cf-pdsl-* dispatch decision

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md is loaded
  - RUN InlineFallbackProbe
  - REQUIRE returned.state == resolved
  - REQUIRE INLINE_FALLBACK_PROBED == true
  - REQUIRE INLINE_FALLBACK == true:
    inline the matching contract:
      cf-pdsl-author      -> {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-author.md
      cf-pdsl-transformer -> {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-transformer.md
      cf-pdsl-reviewer    -> {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-reviewer.md
  - RUN otherwise
    - DISPATCH named sub-agent

RULES:
  - ALWAYS route Sub-Agent Approval Gate, HostNoNativeSubAgentMenu, and
    NativeSubAgentPolicyConflict handling through shared
    inline-fallback-probe.md
  - ALWAYS treat NativeSubAgentPolicyConflict as a distinct approval boundary
    owned by the shared probe
  - ALWAYS apply dispatch protocol from `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md` before any DISPATCH
  - ALWAYS synthesize the dispatched agent's final prompt from
    SHARED_CONTEXT_PACK plus the agent prompt source before any cf-pdsl-*
    dispatch or inline contract
  - NEVER dispatch write-capable modes (new, transform) until write summary is user-approved
  - NEVER read or branch on INLINE_FALLBACK unless
    INLINE_FALLBACK_PROBED == true for the active workflow run
  - NEVER emit local approval or fallback menus in this workflow
  - NEVER default INLINE_FALLBACK from host capability, policy conflict, or
    missing approval

NOTES:
  Full approval gate semantics and the INLINE_FALLBACK_PROBED /
  NativeSubAgentPolicyConflict state machine are defined in
  {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md,
  {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md § Session Sub-Agent Approval
  Gate, and {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md.
```

## Completion

```pdsl
UNIT PdslCompletion

PURPOSE:
  Define terminal conditions for all PDSL modes.

INVARIANTS:
  - NEVER claim completion for new or transform mode until a manifest is returned
  - NEVER claim completion for review mode until a validation report is returned
  - ALWAYS After a successful manifest or validation report, ALWAYS emit
    PdslCompletionMenu unless the invoked sub-mode has already emitted an
    equivalent terminal handoff menu
  - NEVER claim PASS for any unread target path
  - ALWAYS Review validation report ALWAYS includes all six sections:
      1. Summary
      2. Files Reviewed
      3. Findings
      4. Compactness Opportunities
      5. Residual Risks
      6. Recommended Fixes
  - ALWAYS If the workflow cannot read all requested files it ALWAYS returns a partial
    checkpoint and NEVER claims PASS for unread paths

MENU PdslCompletionMenu:
  TITLE: "PDSL workflow complete. What next?"
  OPTIONS:
    1 revise -> Revise the current PDSL output in the same mode
    2 switch -> SET PDSL_MODE = unset; Return to PdslModeMenu to choose new, transform, or review
    3 handoff -> Hand off to another cf workflow such as generate, analyze, or plan
    4 stop -> End the PDSL workflow here
  INVALID:
    EMIT "Reply `1`, `2`, `3`, or `4`."
    WAIT user.reply
    STOP_TURN
```
