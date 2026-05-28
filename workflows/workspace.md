---
cf: true
type: workflow
name: cf-workspace
description: Invoke when the user asks to set up, configure, or modify a multi-repo workspace — discover repos, configure sources, generate workspace config, validate, and add/sync cross-repo references.
version: 1.0
purpose: Guide workspace federation setup for cross-repo traceability
---

# Constructor Studio Workspace Workflow

<!-- toc -->

- [Overview](#overview)
- [Phase 0: Router](#phase-0-router)
- [Runtime Loading Rule](#runtime-loading-rule)

<!-- /toc -->

```text
UNIT WorkspaceBootstrap

PURPOSE:
  Load required files before any workspace phase work begins.

DO:
  REQUIRE {cf-studio-path}/config/AGENTS.md is loaded and followed FIRST
  REQUIRE {cf-studio-path}/.gen/AGENTS.md is loaded and followed after config/AGENTS.md
  IF {cfs_mode} == off:
    REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md is loaded and followed FIRST
  REQUIRE {cf-studio-path}/.core/workflows/shared/stop-token-policy.md is loaded and followed
    WHEN any workspace decision prompt is emitted

RULES:
  - MUST load config/AGENTS.md first
  - MUST load .gen/AGENTS.md after config/AGENTS.md
  - MUST load SKILL.md first when cfs_mode is off
  - MUST load stop-token-policy.md before any workspace decision prompt

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
  - Workspace helpers MUST receive needed instruction text through
    prompt_context_view rather than reopening AGENTS or workflow prompt files
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
  - Generate map of current project: route generate.md → workspace.md
  - Check workspace status: route analyze.md with workspace target
  - Direct workspace quick commands (workspace-info, workspace-add, workspace-sync)
    invoked via {cfs_cmd} for read-only or single-source-add use:
      MUST skip full Protocol Guard chain
      MUST NOT require {cf-studio-path}/.gen/AGENTS.md load
      MUST still require write-confirmation when write-capable
  - Full workspace setup workflow (Phase 0–4) is unaffected and uses standard Protocol Guard
```

## Phase 0: Router

```text
UNIT WorkspaceRouter

PURPOSE:
  Load only the phase fragment needed for the current step.

MENU WorkspacePhaseRouter:
  TITLE: Load phase by current step (machine reference — not a user-facing menu)
  OPTIONS:
    discovering candidate repositories or presenting zero-results guidance ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-1-discover.md
    confirming selected source settings and workspace location ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-2-configure.md
    writing standalone or inline workspace configuration ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-3-generate.md
    validating reachability, adapters, and cross-repo behavior ->
      LOAD {cf-studio-path}/.core/workflows/workspace/phase-4-validate.md
    presenting post-setup next steps ->
      LOAD {cf-studio-path}/.core/workflows/workspace/next-steps.md

  INVALID:
    EMIT "Unrecognised phase step. Reply with one of: discovering candidate repositories, confirming selected source settings, writing workspace configuration, validating reachability, or presenting post-setup next steps."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST run phases in order for workspace setup
  - MUST route to analyze workflow with workspace target for status-only requests
    (do NOT load all setup phases)
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
