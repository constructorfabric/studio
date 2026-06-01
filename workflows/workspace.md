---
cf: true
type: workflow
name: cf-workspace
description: Invoke when the user asks to set up, configure, or modify a multi-repo workspace — discover repos, configure sources, generate workspace config, validate, and add/sync cross-repo references.
version: 1.0
purpose: Guide workspace federation setup for cross-repo traceability
---

# Constructor Studio Workspace Workflow

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
  - MUST follow routing.md § CanonicalRoutingPrecedenceState for workflow
    entry, workspace quick commands, AGENTS prompt-asset order, and
    prompt-context ownership.
  - If this workflow file is opened directly, STOP workflow phases until
    SKILL.md has been loaded completely and followed.
  - This gate applies to the top-level controller only; dispatched sub-agents
    consume the synthesized final prompt and supplied context slices.
```

```text
UNIT WorkspaceBootstrap

PURPOSE:
  Load required files before any workspace phase work begins.

DO:
  IF {cfs_mode} == off:
    REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md is loaded and followed FIRST
    REQUIRE {cf-studio-path}/.gen/AGENTS.md is loaded and followed after SKILL.md
    REQUIRE {cf-studio-path}/config/AGENTS.md is loaded and followed after .gen/AGENTS.md
  ELSE:
    REQUIRE {cf-studio-path}/.gen/AGENTS.md is loaded and followed FIRST
  REQUIRE {cf-studio-path}/config/AGENTS.md is loaded and followed after .gen/AGENTS.md
  REQUIRE {cf-studio-path}/.core/workflows/shared/stop-token-policy.md is loaded and followed
    WHEN any workspace decision prompt is emitted

RULES:
  - MUST load {cf-studio-path}/.core/skills/studio/SKILL.md first when cfs_mode is off
  - MUST load {cf-studio-path}/.gen/AGENTS.md before {cf-studio-path}/config/AGENTS.md
  - MUST load {cf-studio-path}/config/AGENTS.md after .gen/AGENTS.md
  - MUST match ProtocolGuard bootstrap order for AGENTS prompt assets
  - MUST load {cf-studio-path}/.core/workflows/shared/stop-token-policy.md before any workspace decision prompt

NOTES:
  Type: Operation. Role: Any.
  Output: .studio-workspace.toml or inline [workspace] in config/core.toml
```

```text
UNIT WorkspaceSharedContextPack

PURPOSE:
  Keep workspace bootstrap prompt loading controller-owned and pack-aware.

RULES:
  - {cf-studio-path}/config/AGENTS.md and {cf-studio-path}/.gen/AGENTS.md are
    controller-owned prompt assets when loaded as instructions and MUST be
    reused or refreshed in SHARED_CONTEXT_PACK before downstream dispatch
  - Workspace helpers MUST receive needed instruction text through a
    controller-synthesized final dispatch prompt rather than reopening AGENTS
    or workflow prompt files
  - Workspace router fragments MUST remain compact controller-owned loads from
    {cf-studio-path}/.core/workflows/workspace/...
```

## Overview

```text
UNIT WorkspaceOverview

PURPOSE:
  Discover workspace sources, confirm roles/settings, write workspace config,
  and validate cross-repo traceability.

RULES:
  - Generate map of current project: route generate.md -> workspace.md
  - Check workspace status: route analyze.md with workspace target
  - Direct workspace quick commands (workspace-info, workspace-add,
    workspace-sync) invoked as narrow {cfs_cmd} CLI fast paths for read-only or
    single-source-add use:
      MUST skip workspace setup phases and this workflow's explore gate
      MUST NOT require {cf-studio-path}/.gen/AGENTS.md load unless the direct
      CLI command itself requires workspace prompt assets
      MUST still require write-confirmation when write-capable
  - Full cf workspace setup workflow (Phase 0-4) is unaffected and uses
    standard RootSkillEntrypointBootstrap and Protocol Guard
```

## Phase 0: Router

```text
UNIT WorkspaceRouter

PURPOSE:
  Load only the phase fragment needed for the current step.

MENU WorkspacePhaseRouter:
  TITLE: Load phase by current step (machine reference — not a user-facing menu)
  OPTIONS:
    WS_DISCOVER ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-1-discover.md
    WS_CONFIGURE ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-2-configure.md
    WS_GENERATE ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-3-generate.md
    WS_VALIDATE ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-4-validate.md
    WS_NEXT_STEPS ->
      LOAD {cf-studio-path}/.core/workflows/workspace/next-steps.md

  INVALID:
    EMIT "Unrecognized workspace route. Expected WS_DISCOVER, WS_CONFIGURE, WS_GENERATE, WS_VALIDATE, or WS_NEXT_STEPS."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST run phases in order for workspace setup
  - MUST route to analyze workflow with workspace target for status-only requests
    (do NOT load all setup phases)
  - Each phase fragment MUST emit one of these terminal records before STOP_TURN
    or continuation:
      { "type": "WORKSPACE_STATUS", "phase": "<id>", "status": "pending|complete|invalid|failed", "next_route": "<WS_*|null>" }
      { "type": "WORKSPACE_VALIDATION", "status": "PASS|FAIL|WARN", "checked_sources": [], "issues": [] }
      { "type": "WORKSPACE_FAILURE", "phase": "<id>", "reason": "<one-line>", "recovery": "<next action>" }
```

## Phase 0.a: Explore / Brainstorm Applicability

```text
UNIT WorkspaceExploreBrainstormGate

PURPOSE:
  Ensure workspace setup has repository/resource discovery before configuring
  federation, and offer brainstorm for policy-heavy choices.

WHEN:
  full workspace setup or config generation starts
  AND before workspace Phase 1

DO:
  REQUIRE {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md is loaded and followed

RULES:
  - MUST delegate explore/brainstorm applicability, replacement, and skip
    decisions to shared/explore-brainstorm-gate.md
  - MUST skip this gate for direct quick commands documented in
    WorkspaceOverview (`workspace-info`, `workspace-add`, `workspace-sync`);
    write-capable quick commands still require their own write-confirmation
  - SHOULD offer cf-brainstorm when precedence, ownership, rollout, or conflict
    resolution policy is ambiguous
```

## Runtime Loading Rule

```text
UNIT WorkspaceRuntimeLoading

PURPOSE:
  Keep this router compact and prevent phase-body inlining.

RULES:
  - MUST NOT inline phase bodies in this router file
  - MUST create or update a {cf-studio-path}/.core/workflows/workspace/phase-*.md fragment for any new phase
    and add only a router row in WorkspacePhaseRouter above
```
