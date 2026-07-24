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
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_SLICES: list | unset (default unset, scope workflow_run)
  SET GATE_STATUS: pass | fail | not-run (default not-run, scope workflow_run)
  SET VALIDATION_STATUS: pass | fail | not-run | unset (default unset, scope workflow_run)
  SET CI_RESULT_STATUS: completed | failed | blocked | unset (default unset, scope workflow_run)
  SET FINDINGS_REPORT_TYPE: review-findings | ci-findings | other | unset (default unset, scope workflow_run)
  SET FINDINGS_RESULT_STATUS: completed | failed | blocked | unset (default unset, scope workflow_run)
  SET FINDINGS: list | unset (default unset, scope workflow_run)
  SET FINDINGS_REPORT_REF: ref | unset (default unset, scope workflow_run)
  SET report_outputs: list | unset (default unset, scope workflow_run)
  SET NEXT_ACTION_PINNED_SKILL: cf-skill-name | unset (default unset, scope workflow_run)
  SET NEXT_ACTION_PAYLOAD: object | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN WorkflowBootstrapCommandResolution
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  SET ORIGINAL_INTENT = the user's triggering prompting-ci request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-bootstrap-refs.md
  RUN WriteSkillsExecutionContextPrep
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN SubAgentDispatch for the cf-deterministic-validator dispatch group before launching deterministic PDSL validation
  LOAD {cf-studio-path}/.core/skills/studio/modules/ci-discovery-run.md
  SET CI_DISCOVERY_INTENT = "ci-prompting"
  RUN CiDiscoveryRunStart
  SET REVIEW_TARGET_SLICES = full-file slices for every REVIEW_TARGET_PATHS entry WHEN REVIEW_TARGET_PATHS != unset AND REVIEW_TARGET_SLICES == unset
  RUN the deterministic PDSL check — dispatch cf-deterministic-validator for `{cfs_cmd} pdsl validate` on REVIEW_TARGET_PATHS; caller must provide REVIEW_TARGET_PATHS for validation-only runs
  SET GATE_STATUS = fail WHEN any validation reports errors
  SET GATE_STATUS = pass WHEN every validation check passes
  SET GATE_STATUS = not-run WHEN no applicable PDSL checks were resolved or executed
  SET VALIDATION_STATUS = pass WHEN GATE_STATUS == pass
  SET VALIDATION_STATUS = fail WHEN GATE_STATUS == fail
  SET VALIDATION_STATUS = not-run WHEN GATE_STATUS == not-run
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/findings-render.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/ci-report-render.md
  SET CI_RESULT_STATUS = completed WHEN GATE_STATUS == pass
  SET CI_RESULT_STATUS = failed WHEN GATE_STATUS == fail
  SET CI_RESULT_STATUS = blocked WHEN GATE_STATUS == not-run
  SET FINDINGS_REPORT_TYPE = ci-findings
  SET FINDINGS_RESULT_STATUS = completed WHEN CI_RESULT_STATUS == completed
  SET FINDINGS_RESULT_STATUS = failed WHEN CI_RESULT_STATUS == failed
  SET FINDINGS_RESULT_STATUS = blocked WHEN CI_RESULT_STATUS == blocked
  SET FINDINGS = normalized CI findings from the executed validation results
  SET FINDINGS = [] WHEN FINDINGS == unset
  SET FINDINGS_REPORT_REF = a stable ci-findings report ref derived from the current deterministic validation run
  RUN FindingsRenderContract
  SET report_outputs = one entry with report_type = deterministic-report, ref = a stable deterministic-report ref derived from the current deterministic validation run, and summary = a deterministic summary of the executed or skipped PDSL validation gate, plus the current top-level report_outputs after FindingsRenderContract
  RUN CiReportRenderContract
  EMIT the validation findings
  SET NEXT_ACTION_PINNED_SKILL = cf-prompting-review
  SET NEXT_ACTION_PAYLOAD = REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, report_outputs, GATE_STATUS, VALIDATION_STATUS, CI_RESULT_STATUS
  RUN NextActionsOffer
```
