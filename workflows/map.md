---
cf: true
type: workflow
name: cf-map
description: "Invoke when the user asks to build a dependency map, visualize cross-references, scan markdown/code, detect phantom cpts, or render the HTML map viewer."
version: 0.1
purpose: Drive the cfs map CLI to scan markdown and source for dependencies and cpt cross-references, render an interactive HTML map or JSON graph, and detect dangling references, confirming scope before scanning and never writing config without approval.
---

# cf-map

This skill drives the `{cfs_cmd} map` CLI to scan markdown and source for
dependencies and cpt cross-references, render HTML or JSON output, and guide
follow-up analysis or config assistance without writing config implicitly.

```pdsl
UNIT MapBootstrap
PURPOSE: Load the runtime rules needed before any map work begins.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/map-intent.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN WorkflowBootstrapCommandTemplateContext
  SET ORIGINAL_INTENT = the user's triggering map request (verbatim or shortest faithful summary)
  SET CURRENT_WORKFLOW = cf-map, SET COMPANION_CONTINUE = MapIntentRouter and LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md and CONTINUE CompanionSkillOffer
RULES:
  ALWAYS run StudioInstructionsMemoryGate before map routing, preflight, scanning, config assist, or handoff
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, writes, git use, or delegation
  ALWAYS load command-resolution before invoking `{cfs_cmd}` map/info commands
  ALWAYS load template-vars before resolving map output paths or unknown template variables
  ALWAYS load context-memory before passing a generated map artifact as resource_context to another workflow
  NEVER require cf or CFS_INIT before map; this workflow owns its prerequisite loads
UNIT MapNextActions
PURPOSE: Load terminal next actions after map scan/render work is complete.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  RUN NextActionsOffer
```
