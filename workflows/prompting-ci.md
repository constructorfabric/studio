---
cf: true
type: workflow
name: cf-prompting-ci
description: "Invoke when the user or another skill or workflow needs or asks to validate prompts or skills, run deterministic checks for workflows or system instructions, or make sure prompt and PDSL artifacts pass their configured validation."
version: 0.1
---

# cf-prompting-ci

This workflow is the canonical thin deterministic validation entrypoint for
prompt artifacts.

```pdsl
UNIT PromptingCiPreset
PURPOSE: Run deterministic prompt validation without semantic review or authoring.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET SKILL_FILE_WRITTEN: true | false (default true, scope workflow_run)
  SET REVIEW_FIXES_APPLIED: true | false | unset (default false, scope workflow_run)
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN WorkflowBootstrapCommandResolution
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  SET ORIGINAL_INTENT = the user's triggering prompting-ci request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET SKILL_FILE_WRITTEN = true
  SET REVIEW_FIXES_APPLIED = false WHEN REVIEW_FIXES_APPLIED == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-bootstrap-refs.md
  RUN WriteSkillsExecutionContextPrep
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN SubAgentDispatch for the cf-deterministic-validator dispatch group before launching deterministic PDSL validation
  LOAD {cf-studio-path}/.core/skills/studio/modules/ci-discovery-run.md
  SET CI_DISCOVERY_INTENT = "ci-prompting"
  RUN CiDiscoveryRunStart
  RUN the deterministic PDSL check — dispatch cf-deterministic-validator for `{cfs_cmd} pdsl validate` on REVIEW_TARGET_PATHS; caller must provide REVIEW_TARGET_PATHS for validation-only runs
  EMIT the validation findings
  RUN NextActionsOffer
```
