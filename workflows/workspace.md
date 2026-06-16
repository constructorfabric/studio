---
cf: true
type: workflow
name: cf-workspace
description: "Invoke when the user asks to set up, configure, or modify a multi-repo workspace — discover repos, configure sources, generate workspace config, validate, and add/sync cross-repo references."
version: 0.1
purpose: Drive the cfs workspace CLI to set up multi-repo federation for cross-repo traceability, confirming every source and write before touching config.
---

# cf-workspace

This skill drives the `{cfs_cmd}` workspace CLI to set up multi-repo federation
for cross-repo traceability, with confirmation before source selection,
configuration writes, and validation follow-up.

```pdsl
UNIT WorkspaceBootstrap
PURPOSE: Load the runtime and workspace setup rules before any workspace work begins.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/workspace-router-quick.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN WorkflowBootstrapCommandTemplateContext
  LOAD {cf-studio-path}/.core/requirements/workspace-setup.md as the setup detail reference (framing, source fields, storage modes, validation checks, terminal-record shapes)
  SET ORIGINAL_INTENT = the user's triggering workspace request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET CURRENT_WORKFLOW = cf-workspace, SET COMPANION_CONTINUE = WorkspaceIntentRouter and LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md and CONTINUE CompanionSkillOffer WHEN ORIGINAL_INTENT != unset
  CONTINUE WorkspaceIntentRouter WHEN ORIGINAL_INTENT == unset
RULES:
  ALWAYS run StudioInstructionsMemoryGate before workspace routing, setup, validation, or writes
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, writes, git use, or delegation
  ALWAYS load command-resolution before invoking `{cfs_cmd}` workspace commands
  ALWAYS load template-vars before resolving workspace source paths or unknown template variables
  ALWAYS load and follow the workspace-setup reference for field lists, decision framing, suggested defaults, and terminal-record shapes
  NEVER require cf or CFS_INIT before workspace; this workflow owns its prerequisite loads
```
