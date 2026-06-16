---
cf: true
type: workflow
name: cf-explain
version: 0.1
description: "Invoke for requests to explain, walk through, teach, onboard, give a code tour, produce a source-grounded narrative, or summarize a decision."
purpose: Run an interactive, pedagogically-paced storytelling walkthrough of an artifact, codebase, or document via sub-agents — resolving mode/disposition/audience/plan through four gates before any answer-style content, and optionally exporting a Markdown package.
---

# cf-explain

This skill runs a source-grounded storytelling walkthrough of an artifact,
codebase, or document. It resolves the required E0 and E1 gates before any
answer-style content and can optionally export a Markdown package.

```pdsl
UNIT ExplainBootstrap
PURPOSE: Arm explain mode and load the storytelling methodology before any explain work.
STATE:
  SET EXPLAIN_EXPORT: true | false (default false, scope workflow_run)
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/explain-bootstrap-refs.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/explain-bootstrap-helpers.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/explain-intent-explore.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate WHEN CF_HELP_PRESET != true
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN ExplainBootstrapIntentRuntime
  RUN ExplainBootstrapModeState
  RUN ExplainBootstrapStorytelling
  CONTINUE ExplainIntentCapture WHEN ORIGINAL_INTENT == unset
  CONTINUE ExplainExploreGate WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS skip SimpleModeGate when CF_HELP_PRESET == true so cf-help remains exempt after delegating to cf-explain
  ALWAYS run StudioInstructionsMemoryGate before explain preflight, routing, storytelling gates, or delivery
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, export, or delegation
  ALWAYS load storytelling requirements only after a concrete explanation target exists
  ALWAYS load sub-agent dispatch and context-memory only on the execution paths that actually launch storytelling agents or carry resource_context
  ALWAYS load template-vars before resolving explanation export package paths or unknown template variables
  ALWAYS capture ORIGINAL_INTENT before explanation context discovery, target preflight, or storytelling dispatch
  NEVER offer companion cf-* workflows from cf-explain; explain owns its target and storytelling gates directly
  NEVER offer cf-brainstorm from cf-explain; explanation narrative choices are resolved by the storytelling gates
  NEVER emit any answer-style, portion, or summary content before the four E1 gates (mode -> disposition -> audience -> plan approval) resolve — this is the critical AP#0 violation
  NEVER require cf or CFS_INIT before explain; this workflow owns its prerequisite loads
```
