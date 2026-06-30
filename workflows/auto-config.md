---
cf: true
type: workflow
name: cf-auto-config
description: "Invoke when the user or another skill or workflow needs or asks to bootstrap or auto-config a project, initialize Constructor Studio, discover existing setup, wire agent integration, set up a kit, configure a workspace, or scan a brownfield repo to generate project rules."
version: 0.1
purpose: Scan a brownfield project and generate per-topic rule files plus AGENTS.md navigation and registry entries, confirming at every checkpoint and never writing without approval.
---

# cf-auto-config

This skill scans a brownfield project via `cf-explore`, then generates
controller-owned rule, navigation, and registry changes with explicit
confirmation at every write checkpoint.

```pdsl
UNIT AutoConfigBootstrap
PURPOSE: Load the runtime rules and auto-config methodology before any auto-config work.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/auto-config-precheck.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN WorkflowBootstrapCommandTemplateContext
  LOAD {cf-studio-path}/.core/requirements/auto-config.md as the phase-by-phase methodology reference
  RUN verify the methodology loaded; EMIT "Auto-config cannot proceed — the methodology file was not found at {cf-studio-path}/.core/requirements/auto-config.md. To fix: run 'cfs sync' to restore studio kit files, then retry." and RETURN a failed AUTO_CONFIG_RESULT with reason="Auto-config methodology not found at {cf-studio-path}/.core/requirements/auto-config.md" and recovery="reinstall or sync the studio kit, then retry auto-config" and STOP_TURN WHEN the load fails
  SET ORIGINAL_INTENT = the user's triggering auto-config request (verbatim or shortest faithful summary)
  SET PLAN_FIRST_CONTINUE = AutoConfigPrecheckGate
  SET CURRENT_WORKFLOW = cf-auto-config
  SET COMPANION_CONTINUE = PlanFirstGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md
  CONTINUE CompanionSkillOffer
RULES:
  ALWAYS run StudioInstructionsMemoryGate before auto-config prechecks, routing, scanning, or writes
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, writes, or delegation
  ALWAYS load command-resolution before invoking `{cfs_cmd}` auto-config prechecks
  ALWAYS load template-vars before resolving config paths or unknown template variables
  ALWAYS load context-memory before storing scan output as resource_context
  ALWAYS load and follow the auto-config methodology for phase detail
  NEVER continue past bootstrap when the methodology reference fails to load
  NEVER require cf or CFS_INIT before auto-config; this workflow owns its prerequisite loads
```
