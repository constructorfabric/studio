---
cf: true
type: workflow
name: cf-pdsl
description: "Use when the user wants prompt/workflow/skill/agent instruction files authored, transformed, compressed, normalized, or reviewed as compact state-machine-like PDSL contracts. Triggers include creating a new prompt file, converting prose instructions to DSL, reviewing prompts for state/menu/UX/STOP_TURN safety, or making Constructor Studio prompt files more compact and explicit."
version: 0.1
purpose: Dedicated workflow for authoring, transforming, and auditing compact PDSL prompt contracts
---

# PDSL Workflow

This workflow creates and reviews prompt-facing instruction files written in
PDSL. It is for files such as `skills/**/*.md`, `workflows/**/*.md`,
`requirements/**/*.md`, agent contracts, and prompt configuration documents.

## Bootstrap

```text
UNIT PdslBootstrap

PURPOSE:
  Load required files before any phase work begins.

RULES:
  - ALWAYS open and follow `{cf-studio-path}/.core/skills/studio/SKILL.md` WHEN `{cfs_mode}` == off
  - ALWAYS open and follow `skills/studio/protocol.md` FIRST
  - ALWAYS open and follow `{cf-studio-path}/.core/architecture/specs/PDSL.md`
  - ALWAYS open and follow `workflows/shared/stop-token-policy.md`
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
  IF user intent matches a mode alias:
    SET PDSL_MODE = matched mode
    LOAD matching mode file
  ELSE:
    EMIT_MENU PdslModeMenu
    WAIT user.reply
    STOP_TURN

MENU PdslModeMenu:
  TITLE: Choose PDSL mode
  OPTIONS:
    1 new -> SET PDSL_MODE = new
             LOAD workflows/pdsl/new.md
             STOP_TURN
    2 transform -> SET PDSL_MODE = transform
                   LOAD workflows/pdsl/transform.md
                   STOP_TURN
    3 review -> SET PDSL_MODE = review
                LOAD workflows/pdsl/review.md
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
  Enforce Sub-Agent Approval Gate semantics before any DISPATCH.

WHEN:
  SUB_AGENT_SESSION_APPROVED == unset
  AND host.supports_native_subagents == true

DO:
  EMIT_MENU SubAgentApprovalMenu
  WAIT user.reply
  STOP_TURN

MENU SubAgentApprovalMenu:
  TITLE: This workflow can use Constructor Studio sub-agents for isolated/parallel work.
  OPTIONS:
    1 -> SET SUB_AGENT_SESSION_APPROVED = true
         SET INLINE_FALLBACK = false
         CONTINUE PdslDispatchGate
    2 -> SET INLINE_FALLBACK = true
         CONTINUE PdslDispatchGate
  INVALID:
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN

DO (after approval resolved):
  IF INLINE_FALLBACK == true OR host.supports_native_subagents == false:
    inline the matching contract:
      cf-pdsl-author      -> {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-author.md
      cf-pdsl-transformer -> {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-transformer.md
      cf-pdsl-reviewer    -> {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-reviewer.md
  ELSE:
    DISPATCH named sub-agent

RULES:
  - MUST apply Sub-Agent Approval Gate (SKILL.md) before any DISPATCH
  - MUST apply dispatch protocol from sub-agent-dispatch.md before any DISPATCH
  - MUST_NOT dispatch write-capable modes (new, transform) until write summary is user-approved
  - MUST_NOT default INLINE_FALLBACK from host capability or missing approval

NOTES:
  Full approval gate semantics defined in SKILL.md § Session Sub-Agent Approval Gate
  and sub-agent-dispatch.md.
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
