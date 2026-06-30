---
cf: true
type: workflow
name: cf-documenting-ci
description: "Invoke when the user or another skill or workflow needs or asks to validate docs, run document checks, verify artifact structure, check TOC or language rules, or make sure documentation passes the project's deterministic doc CI."
version: 0.1
---

# cf-documenting-ci

This workflow is the canonical thin deterministic validation entrypoint for
document artifacts.

```pdsl
UNIT DocumentingCiPreset
PURPOSE: Run deterministic document validation without semantic review or authoring.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET GATE_STATUS: pass | fail | not-run (default not-run, scope workflow_run)
  SET CI_RESULT_STATUS: completed | failed | blocked | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN WorkflowBootstrapCommandResolution
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  SET ORIGINAL_INTENT = the user's triggering documenting-ci request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN SubAgentDispatch for the cf-deterministic-validator dispatch group before launching deterministic validation
  LOAD {cf-studio-path}/.core/skills/studio/modules/ci-discovery-run.md
  SET CI_DISCOVERY_INTENT = "ci-documenting"
  RUN CiDiscoveryRunStart
  RUN the deterministic gate — dispatch cf-deterministic-validator for the applicable checks (validate --artifact / validate-toc / check-language) plus any project doc checks
  SET GATE_STATUS = fail WHEN any check reports failures or errors
  SET GATE_STATUS = pass WHEN every applicable check passes
  SET GATE_STATUS = not-run WHEN no applicable checks were resolved or executed
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/ci-report-render.md
  SET CI_RESULT_STATUS = completed WHEN GATE_STATUS == pass
  SET CI_RESULT_STATUS = failed WHEN GATE_STATUS == fail
  SET CI_RESULT_STATUS = blocked WHEN GATE_STATUS == not-run
  RUN CiReportRenderContract
  EMIT the gate results
  RUN NextActionsOffer
RULES:
  ALWAYS treat this workflow as deterministic validation only
NOTES:
  NOTE: documenting-ci does not set VALIDATION_STATUS or NEXT_ACTION_PAYLOAD because cf-documenting-review has its own review loop independent of CI output; see prompting-ci.md for an example of CI-to-review handoff via NEXT_ACTION_PAYLOAD.
```
