# CI Report Render

```pdsl
UNIT CiReportRenderContract
PURPOSE: Render deterministic CI outputs into the canonical thin-skill result envelope.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/thin-skill-contracts.md WHEN ThinSkillRuntimeContracts is not yet loaded
  RUN ThinSkillRuntimeContracts
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/artifact-contract-load.md WHEN ArtifactContractLoad is not yet loaded
  RUN ArtifactContractLoad
  RUN CiReportStatusContract
  RUN CiReportProducedArtifactsContract
  RUN CiReportOutputsContract
RULES:
  ALWAYS use this module only to shape deterministic CI results after command or validator execution is already complete
  ALWAYS keep deterministic-report and ci-findings in report_outputs instead of produced_artifacts
  NEVER let this module choose, run, or retry CI commands
```

```pdsl
UNIT CiReportStatusContract
PURPOSE: Keep CI result statuses aligned with the canonical thin-skill status set.
RULES:
  ALWAYS require CI_RESULT_STATUS to be one of ready, blocked, completed, or failed
  ALWAYS reject completed-with-assumptions for CI reporting
  ALWAYS keep CI_RESULT_STATUS explicit instead of inferring it from prose summaries alone
  NEVER invent a CI-local top-level status alias
```

```pdsl
UNIT CiReportProducedArtifactsContract
PURPOSE: Keep produced artifact entries distinct from CI report outputs.
RULES:
  ALWAYS represent any produced_artifacts entry with artifact_type, ref, and summary
  ALWAYS keep produced_artifacts limited to canonical artifact descriptors supplied by the caller
  ALWAYS forbid deterministic-report and ci-findings artifact types inside produced_artifacts for this contract
  NEVER treat findings or validator logs as produced artifacts
```

```pdsl
UNIT CiReportOutputsContract
PURPOSE: Define the machine-readable CI report_outputs payload.
RULES:
  ALWAYS represent each report_outputs entry with report_type, ref, and summary
  ALWAYS allow report_type values deterministic-report and ci-findings in this contract
  ALWAYS require at least one report_outputs entry when CI_RESULT_STATUS is completed or failed
  ALWAYS keep report_outputs deterministic with respect to the supplied command results and report refs
  NEVER require a specific executor, validator, or workflow path to populate report_outputs
```
