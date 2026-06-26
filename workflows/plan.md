---
cf: true
type: workflow
name: cf-plan
description: "Invoke when the user or another skill or workflow needs or asks to decompose a large task, break work into phases, make a standalone execution plan, or turn a big multi-step request into self-contained phase files with briefs and compiled forms."
version: 0.1
purpose: Preserve the standalone phased planning workflow that assesses scope, decomposes a large task into self-contained phase files, and hands off to execution — only planning, never implementing, and confirming before every write.
---

# cf-plan

This skill is the backward-compatible standalone planner. It assesses scope,
decomposes work, writes `plan.toml` plus briefs and phase files under
`{cf-studio-path}/.plans/`, and then hands off to analysis or execution.

For thin integrable planning inside prerequisite-driven pipelines, use
`cf-planning` and its domain presets instead.

```pdsl
UNIT PlanBootstrap
PURPOSE: Load the runtime rules needed before any plan work begins.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/planning-runtime.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/plan-discovery.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN PlanningLegacySeparationContract
  SET ORIGINAL_INTENT = the user's triggering plan request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN WorkflowBootstrapCommandDispatchTemplateContext
  SET CURRENT_WORKFLOW = cf-plan WHEN ORIGINAL_INTENT != unset
  SET COMPANION_CONTINUE = PlanPhase0Discover WHEN ORIGINAL_INTENT != unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN ORIGINAL_INTENT != unset
  CONTINUE CompanionSkillOffer WHEN ORIGINAL_INTENT != unset
  CONTINUE PlanPhase0Discover WHEN ORIGINAL_INTENT == unset
RULES:
  ALWAYS run StudioInstructionsMemoryGate before plan discovery, decomposition, compilation, or execution
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, phase dispatch, git use, or delegation
  ALWAYS load command-resolution before invoking `{cfs_cmd}` plan-discovery commands
  ALWAYS load template-vars before resolving plan paths or unknown template variables
  ALWAYS load context-memory before carrying resource_context into phase assessment
  ALWAYS load sub-agent dispatch before compiling or running phase agents
  ALWAYS load git-commit-mode before passing git policy to phase compiler or phase runner agents
  ALWAYS capture ORIGINAL_INTENT before planning gates, and offer companion cf-* workflows first when the request spans domains
  ALWAYS reuse shared planning contracts where standalone packaging does not require plan-specific lifecycle semantics
  ALWAYS only generate execution plans here, never implement, and ALWAYS LOAD the relevant requirement doc per phase rather than all docs upfront
  NEVER hold all phase files in context at once — compile one at a time
  ALWAYS write plan.toml before compiling phase files
  NEVER require cf or CFS_INIT before plan; this workflow owns its prerequisite loads
```
