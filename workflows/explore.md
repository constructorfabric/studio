---
cf: true
type: workflow
name: cf-explore
description: "Invoke when the user or another skill or workflow needs or asks to explore the codebase, figure out where something lives, find relevant files, locate docs or artifacts, search references or call sites, map dependencies, or gather context before planning, writing, or reviewing."
version: 0.1
purpose: Discover task-relevant project resource context via a read-only sub-agent and return a controller-owned resource map without polluting the shared context pack.
---

# cf-explore

This skill discovers task-relevant project resource context via one or more
cf-explorer sub-agents. It returns a controller-owned resource map plus a
context summary kept as resource_context, then optionally offers persistence and
next steps.

```pdsl
UNIT ExploreBootstrap
PURPOSE: Load the local rules needed before any explore work.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/explore-bootstrap-refs.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/explore-entry.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  CONTINUE ExploreEntry
RULES:
  ALWAYS run StudioInstructionsMemoryGate before explore entry routing, scanning, or saved-context handling
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, writes, or delegation
  ALWAYS load the sub-agent dispatch module before ExploreRun can dispatch cf-explorer
  ALWAYS load template-vars before resolving exploration bundle paths or unknown template variables
  ALWAYS load context-memory before storing or returning resource_context
  NEVER require cf or CFS_INIT before explore; this workflow owns its prerequisite loads
```
