---
cf: true
type: workflow
name: cf-workspace
description: Invoke when the user asks to set up, configure, or modify a multi-repo workspace — discover repos, configure sources, generate workspace config, validate, and add/sync cross-repo references.
version: 1.0
purpose: Guide workspace federation setup for cross-repo traceability
---

# Constructor Studio Workspace Workflow

```pdsl
UNIT WorkspaceRootSkillEntrypointBootstrap
PURPOSE: Load the shared root cf skill entrypoint bootstrap and preserve workspace routing invariants.
DO:
  - RUN WHEN {cfs_mode} == off:
    - ALWAYS open and follow {cf-studio-path}/.core/skills/studio/SKILL.md
  - LOAD {cf-studio-path}/.core/workflows/shared/root-skill-entrypoint-bootstrap.md
  - CONTINUE RootSkillEntrypointBootstrap
RULES:
  - ALWAYS follow routing.md § CanonicalRoutingPrecedenceState for workflow
    entry, workspace quick commands, AGENTS prompt-asset order, and
    prompt-context ownership.
```

```pdsl
UNIT WorkspaceModeDirective
PURPOSE: Set cf skill mode and capture original intent before any phase work begins.
DO:
  - SET CF_MODE = "cf-workspace"
  - SET ORIGINAL_INTENT = user's triggering request (verbatim or shortest faithful summary)
RULES:
  - ALWAYS SET CF_MODE = "cf-workspace" as the first action after bootstrap
  - ALWAYS capture ORIGINAL_INTENT from the user's triggering message before any sub-agent dispatch
  - ALWAYS carry ORIGINAL_INTENT into Phase 1 discovery as the task field
  - ALWAYS include ORIGINAL_INTENT in every workspace phase and sub-agent dispatch payload as task context
  - NEVER leave CF_MODE unset when entering this workflow
```

```pdsl
UNIT WorkspaceBootstrap

PURPOSE:
  Load required files before any workspace phase work begins.

DO:
  - RUN WHEN {cfs_mode} == off:
    - ALWAYS open and follow {cf-studio-path}/.core/skills/studio/SKILL.md
  - RUN WHEN WorkspaceOverview quick-command skip-rule applies:
    - SKIP AGENTS.md loads
  - RUN WHEN WorkspaceOverview quick-command skip-rule does not apply:
    - REQUIRE {cf-studio-path}/.gen/AGENTS.md is loaded and followed
    - REQUIRE {cf-studio-path}/config/AGENTS.md is loaded and followed after .gen/AGENTS.md
  - REQUIRE {cf-studio-path}/.core/workflows/shared/stop-token-policy.md is loaded and followed
    WHEN any workspace decision prompt is emitted

RULES:
  - ALWAYS load {cf-studio-path}/.core/skills/studio/SKILL.md first when cfs_mode is off
  - ALWAYS load {cf-studio-path}/.gen/AGENTS.md before {cf-studio-path}/config/AGENTS.md
  - ALWAYS load {cf-studio-path}/config/AGENTS.md after .gen/AGENTS.md
  - ALWAYS match ProtocolGuard bootstrap order for AGENTS prompt assets
  - ALWAYS load {cf-studio-path}/.core/workflows/shared/stop-token-policy.md before any workspace decision prompt
  - ALWAYS respect WorkspaceOverview quick-command skip-rule for prompt assets

NOTES:
  Type: Operation. Role: Any.
  Output: .studio-workspace.toml or inline [workspace] in config/core.toml
```

```pdsl
UNIT WorkspaceSharedContextPack

PURPOSE:
  Keep workspace bootstrap prompt loading controller-owned and pack-aware.

DO:
  - LOAD {cf-studio-path}/.core/workflows/shared/shared-context-pack-ownership.md
  - CONTINUE SharedContextPackOwnership

RULES:
  - ALWAYS {cf-studio-path}/config/AGENTS.md and {cf-studio-path}/.gen/AGENTS.md
    remain the workspace-specific prompt-asset family for this shared ownership
    contract
  - ALWAYS Workspace router fragments ALWAYS remain compact controller-owned
    loads from {cf-studio-path}/.core/workflows/workspace/...
```

## Overview

```pdsl
UNIT WorkspaceOverview

PURPOSE:
  Discover workspace sources, confirm roles/settings, write workspace config,
  and validate cross-repo traceability.

RULES:
  - ALWAYS Generate map of current project: route generate.md -> workspace.md
  - ALWAYS Check workspace status: route analyze.md with workspace target
  - ALWAYS Direct workspace quick commands (workspace-info, workspace-add,
    workspace-sync) invoked as narrow {cfs_cmd} CLI fast paths for read-only or
    single-source-add use:
      ALWAYS skip workspace setup phases and this workflow's explore gate
      NEVER require {cf-studio-path}/.gen/AGENTS.md load unless the direct
      CLI command itself requires workspace prompt assets
      ALWAYS still require write-confirmation when write-capable
  - ALWAYS Full cf workspace setup workflow (Phase 0-4) is unaffected and uses
    standard RootSkillEntrypointBootstrap and Protocol Guard
```

## Phase 0.a: Explore / Brainstorm Applicability

```pdsl
UNIT WorkspaceExploreBrainstormGate

PURPOSE:
  Ensure workspace setup has repository/resource discovery before configuring
  federation, and offer brainstorm for policy-heavy choices.

WHEN:
  - REQUIRE full workspace setup or config generation starts
  - AND before workspace Phase 1

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md is loaded and followed

RULES:
  - ALWAYS delegate explore/brainstorm applicability, replacement, and skip
    decisions to shared/explore-brainstorm-gate.md
  - ALWAYS skip this gate for direct quick commands documented in
    WorkspaceOverview (`workspace-info`, `workspace-add`, `workspace-sync`);
    write-capable quick commands still require their own write-confirmation
  - ALWAYS offer cf-brainstorm when precedence, ownership, rollout, or conflict
    resolution policy is ambiguous
```

## Phase 0: Router

```pdsl
UNIT WorkspaceRouter

PURPOSE:
  Load only the phase fragment needed for the current step.

MENU WorkspacePhaseRouter:
  TITLE: Load phase by current step (machine reference — not a user-facing menu)
  OPTIONS:
    1 WS_DISCOVER ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-1-discover.md
    2 WS_CONFIGURE ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-2-configure.md
    3 WS_GENERATE ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-3-generate.md
    4 WS_VALIDATE ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-4-validate.md
    5 WS_NEXT_STEPS ->
      LOAD {cf-studio-path}/.core/workflows/workspace/next-steps.md

  INVALID:
    EMIT "Unrecognized workspace route. Please ensure the workspace setup is initialized correctly."
    WAIT user.reply
    STOP_TURN

RULES:
  - ALWAYS run phases in order for workspace setup
  - ALWAYS route to analyze workflow with workspace target for status-only requests
    (do NOT load all setup phases)
  - ALWAYS Each phase fragment ALWAYS emit one of these terminal records before STOP_TURN
    or continuation:
      { "type": "WORKSPACE_STATUS", "phase": "<id>", "status": "pending|complete|invalid|failed", "next_route": "<WS_*|null>" }
      { "type": "WORKSPACE_VALIDATION", "status": "PASS|FAIL|WARN", "checked_sources": [], "issues": [] }
      { "type": "WORKSPACE_FAILURE", "phase": "<id>", "reason": "<one-line>", "recovery": "<next action>" }
```

## Runtime Loading Rule

```pdsl
UNIT WorkspaceRuntimeLoading

PURPOSE:
  Keep this router compact and prevent phase-body inlining.

RULES:
  - NEVER inline phase bodies in this router file
  - ALWAYS create or update a {cf-studio-path}/.core/workflows/workspace/phase-*.md fragment for any new phase
    and add only a router row in WorkspacePhaseRouter above
```
