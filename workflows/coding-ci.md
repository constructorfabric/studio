---
cf: true
type: workflow
name: cf-coding-ci
description: "Invoke when the user or another skill or workflow needs or asks to run checks for code changes, make sure CI passes, validate the implementation, run tests, lint, typecheck, build, or verify that the code is green."
version: 0.1
purpose: Run deterministic validation for code changes without owning authoring or semantic review.
---

# cf-coding-ci

This workflow is a thin entrypoint for deterministic code validation. It
produces deterministic-report or ci-findings outputs.

```pdsl
UNIT CodingCiEntry
PURPOSE: Run code deterministic validation without authoring or semantic review.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default false, scope workflow_run)
  SET GATE_STATUS: pass | fail | not-run (default not-run, scope workflow_run)
  SET CI_RESULT_STATUS: completed | failed | blocked | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN WorkflowBootstrapCommandResolution
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  SET ORIGINAL_INTENT = the user's triggering coding-ci request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-bootstrap-methodologies.md
  RUN CodingValidationContextPrep
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN SubAgentDispatch for the cf-deterministic-validator dispatch group before launching studio-applicable deterministic validation
  LOAD {cf-studio-path}/.core/skills/studio/modules/ci-discovery-run.md
  SET CI_DISCOVERY_INTENT = "ci-coding"
  RUN CiDiscoveryRunStart
  RUN resolve the deterministic gate commands from project config (package.json / Makefile / pyproject.toml / build files) or remembered {cfs_cmd}/project commands
  RUN the resolved deterministic gate commands in order
  RUN SubAgentDispatch for cf-deterministic-validator on studio-applicable checks (validate / validate-toc / check-language)
  SET GATE_STATUS = fail WHEN any gate reports failures or errors
  SET GATE_STATUS = pass WHEN every applicable gate passes
  SET GATE_STATUS = not-run WHEN no applicable gate commands were resolved or executed
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/ci-report-render.md
  SET CI_RESULT_STATUS = completed WHEN GATE_STATUS == pass
  SET CI_RESULT_STATUS = failed WHEN GATE_STATUS == fail
  SET CI_RESULT_STATUS = blocked WHEN GATE_STATUS == not-run
  RUN CiReportRenderContract
  EMIT the gate results
  RUN NextActionsOffer
RULES:
  ALWAYS use this workflow only for deterministic validation of code changes
  ALWAYS keep semantic review and authoring outside this thin entrypoint
  NEVER treat this workflow as permission to dispatch coding authoring by itself
NOTES:
  WorkflowBootstrapSimpleModeGate is intentionally omitted from coding-ci because this workflow is typically invoked programmatically after authoring, not interactively.
```
