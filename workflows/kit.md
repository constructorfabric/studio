---
cf: true
type: workflow
name: cf-kit
description: "Invoke when user intent is initializing a kit folder, creating or validating .cf-studio-kit.toml, converting legacy manifest.toml, normalizing conf.toml + layout, or discovering resources for a new kit manifest."
version: 0.1
purpose: Initialize a kit root into a canonical .cf-studio-kit.toml through explicit preview, approval, write, and validation gates.
---
# cf-kit
This workflow initializes a target kit folder into a canonical `.cf-studio-kit.toml` through explicit source routing, preview, approval, write, and validation gates.

```pdsl
UNIT KitInitBootstrap
PURPOSE: Load the runtime rules and verify kit CLI support before any kit work.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/skill-invocation-art.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-bootstrap-runtime.md
  RUN SkillInvocationArt
  RUN KitInitBootstrapLoadRuntime
  RUN KitInitBootstrapVerifyNormalize
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-entry-router.md
  CONTINUE KitInitBootstrapNormalizeUnavailable WHEN the normalize capability check fails
  CONTINUE KitInitEntry WHEN the normalize capability check passes
RULES:
  ALWAYS run StudioInstructionsMemoryGate before kit target routing, preflight, discovery, or writes
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, writes, git use, or delegation
  ALWAYS load command-resolution before invoking `{cfs_cmd}` kit commands
  ALWAYS load template-vars before resolving kit resource paths or unknown template variables
  ALWAYS load context-memory before storing or consuming kit discovery resource_context
  ALWAYS verify the kit normalize command surface before previewing, writing, or validating a kit manifest
  NEVER require cf or CFS_INIT before kit; this workflow owns its prerequisite loads
UNIT KitInitEntry
PURPOSE: Load the entry router and hand off into the current cf-kit session branch.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-entry-router.md
  CONTINUE KitInitEntryRoute
UNIT KitInitPreflight
PURPOSE: Load the preflight branch before validating and routing the target directory.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-target-preflight-route.md
  CONTINUE KitInitPreflightRun
UNIT KitInitDiscoveryRun
PURPOSE: Load the discovery branch before invoking read-only candidate discovery.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-discovery-run.md
  CONTINUE KitInitDiscoveryRunStart
UNIT KitInitDiscoveryProposal
PURPOSE: Load the discovery proposal modules before synthesizing a canonical manifest preview.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-generated-name-preview.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-discovery-classify.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-discovery-synthesize.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-discovery-proposal.md
  CONTINUE KitInitDiscoveryProposalRun
UNIT KitInitValidateWrittenManifest
PURPOSE: Load the post-write validation branch before reporting deterministic status.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-target-validation.md
  CONTINUE KitInitValidateWrittenManifestRun
```
