---
cf: true
type: workflow
name: cf-brainstorm
description: "Invoke when the user or another skill or workflow needs or asks to brainstorm, think through options, compare approaches, explore tradeoffs, shape a design, clarify requirements, figure out what to do, or work through an uncertain decision before implementation."
version: 0.1
purpose: Run an expert panel that explores a topic over rounds, walks questions one at a time, consolidates decisions, and routes to a next step.
---

# cf-brainstorm

This skill assembles an expert panel, runs topic and challenge rounds, walks
questions one at a time, and consolidates the result into a next-step handoff or
session-only outcome.

```pdsl
UNIT BrainstormBootstrap
PURPOSE: Load the local rules needed before any brainstorm work.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/brainstorm-bootstrap-refs.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/brainstorm-offer.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  SET ORIGINAL_INTENT = the user's triggering brainstorm request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  SET CURRENT_WORKFLOW = cf-brainstorm WHEN ORIGINAL_INTENT != unset
  SET COMPANION_CONTINUE = BrainstormOffer WHEN ORIGINAL_INTENT != unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN ORIGINAL_INTENT != unset
  CONTINUE CompanionSkillOffer WHEN ORIGINAL_INTENT != unset
  CONTINUE BrainstormTopicCapture WHEN ORIGINAL_INTENT == unset
RULES:
  ALWAYS run StudioInstructionsMemoryGate before brainstorm routing, panel setup, or rounds
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, writes, or delegation
  ALWAYS load workflow-resolution before BrainstormWrap can synthesize routed next steps
  ALWAYS load template-vars only when the wrap flow resolves a checkpoint path
  ALWAYS load context-memory only before storing or passing resource_context to panel/expert execution
  ALWAYS load sub-agent dispatch only before BrainstormPanel or BrainstormRounds may dispatch a panel agent in `single-agent` or `fan-out` mode
  ALWAYS capture ORIGINAL_INTENT before offering the brainstorm panel, and offer companion cf-* workflows first when the request spans domains
  NEVER require cf or CFS_INIT before brainstorm; this workflow owns its prerequisite loads
```
