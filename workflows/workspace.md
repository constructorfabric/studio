---
cf: true
type: workflow
name: cf-workspace
description: "Invoke when the user or another skill or workflow needs or asks to set up or modify a multi-repo workspace, connect repositories, configure workspace sources, federate projects, sync cross-repo references, or validate a Studio workspace layout."
version: 0.1
purpose: Act as the LLM entrypoint for Studio workspaces: inspect, edit, sync, validate, and shape multi-repo federation with minimal gates and targeted operations.
---

# cf-workspace

This workflow is the primary LLM entrypoint for Studio workspaces. It should
understand the full workspace surface area: setup, source management, config
editing, targeted sync, and workspace-aware diagnostics.

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
  SET CURRENT_WORKFLOW = cf-workspace WHEN ORIGINAL_INTENT != unset
  SET COMPANION_CONTINUE = WorkspaceIntentRouter WHEN ORIGINAL_INTENT != unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN ORIGINAL_INTENT != unset
  CONTINUE CompanionSkillOffer WHEN ORIGINAL_INTENT != unset
  CONTINUE WorkspaceIntentRouter WHEN ORIGINAL_INTENT == unset
RULES:
  ALWAYS run StudioInstructionsMemoryGate before workspace routing, setup, validation, or writes
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, writes, git use, or delegation
  ALWAYS load command-resolution before invoking `{cfs_cmd}` workspace commands
  ALWAYS load template-vars before resolving workspace source paths or unknown template variables
  ALWAYS load and follow the workspace-setup reference for field lists, decision framing, suggested defaults, and terminal-record shapes
  ALWAYS treat the workspace workflow as an intent router first, not a menu-first wizard
  ALWAYS prefer the narrowest sufficient operation: read-only CLI for inspection, targeted write CLI when available, direct config edit when the CLI has no matching mutation
  ALWAYS prefer `workspace-sync --source <name>` when the user names a Git URL source or one relevant Git URL source can be inferred from the request; run full sync only when explicitly requested or no narrower Git URL target exists
  ALWAYS inspect the current workspace config shape before editing it, then update only the smallest required section or source entry
  ALWAYS validate after a workspace write with at least `workspace-info`, and additionally use `list-ids`, `validate`, `where-defined`, or `map` when the request or edited fields affect cross-repo resolution
  NEVER force a setup menu, approval menu, or phase gate when the user's intent already specifies a safe read-only operation or a non-destructive edit with complete inputs
  NEVER use `--force` for `workspace-init`, `workspace-add`, or `workspace-sync` without an explicit user request or a dedicated destructive confirmation step
  NEVER require cf or CFS_INIT before workspace; this workflow owns its prerequisite loads
```
