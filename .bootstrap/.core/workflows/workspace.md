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

ALWAYS open and follow `{cf-studio-path}/config/AGENTS.md` FIRST.
ALWAYS open and follow `{cf-studio-path}/.gen/AGENTS.md` after
config/AGENTS.md.
ALWAYS open and follow `{cf-studio-path}/.core/skills/studio/SKILL.md` FIRST WHEN cfs_mode is off.
ALWAYS open and follow `workflows/shared/stop-token-policy.md` WHEN any workspace decision prompt is emitted.
**Type**: Operation
**Role**: Any
**Output**: `.studio-workspace.toml` or inline `[workspace]` in
`config/core.toml`

## Overview

Use this workflow to discover workspace sources, confirm roles/settings, write
workspace config, and validate cross-repo traceability.

| User intent | Route |
|---|---|
| Create/configure workspace | `generate.md` → `workspace.md` |
| Check workspace status | `analyze.md` with workspace target |

Direct workspace quick commands — `workspace-info`, `workspace-add`, `workspace-sync` invoked directly via {cfs_cmd} for read-only or single-source-add use — skip the full Protocol Guard chain (do not require {cf-studio-path}/.gen/AGENTS.md load); they still require write-confirmation when write-capable. The full workspace setup workflow (Phase 0–4) is unaffected and uses the standard Protocol Guard.

## Phase 0: Router

Load only the phase fragment needed for the current step:

| Phase | Load WHEN |
|---|---|
| `workflows/workspace/phase-1-discover.md` | discovering candidate repositories or presenting zero-results guidance |
| `workflows/workspace/phase-2-configure.md` | confirming selected source settings and workspace location |
| `workflows/workspace/phase-3-generate.md` | writing standalone or inline workspace configuration |
| `workflows/workspace/phase-4-validate.md` | validating reachability, adapters, and cross-repo behavior |
| `workflows/workspace/next-steps.md` | presenting post-setup next steps |

Run phases in order for workspace setup. For status-only requests, route to the
analyze workflow with the workspace target instead of loading all setup phases.

## Runtime Loading Rule

This router must remain compact. Do not inline phase bodies here. If a future
workspace phase grows, create or update a `workflows/workspace/phase-*.md`
fragment and add only a router row above.
