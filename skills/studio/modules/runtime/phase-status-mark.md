# Phase Status Mark

```pdsl
UNIT PhaseStatusMarkContract
PURPOSE: Record a machine-readable phase-status update for a specific phase.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/artifact-contract-load.md WHEN ArtifactContractLoad is not yet loaded
  RUN ArtifactContractLoad
  RUN PhaseStatusRecordContract
  RUN PhaseStatusArtifactContract
RULES:
  ALWAYS use this module only to shape a phase-status update, not to decide the surrounding workflow
  ALWAYS keep phase-status updates explicit about phase id, state, and result summary
  NEVER hide a phase-status transition only in freeform prose
```

```pdsl
UNIT PhaseStatusRecordContract
PURPOSE: Define the minimum shared record for a phase-status update.
RULES:
  ALWAYS require PHASE_ID, PHASE_STATE, and PHASE_RESULT_SUMMARY
  ALWAYS keep PHASE_RESULT_SUMMARY one-line and user-visible
  ALWAYS allow PHASE_STATE to be ready, in-progress, blocked, completed, failed, or skipped
  ALWAYS keep PHASE_STATE distinct from the top-level thin-skill status field
  NEVER infer PHASE_STATE from a commit result, CI report, or review finding without an explicit caller decision
```

```pdsl
UNIT PhaseStatusArtifactContract
PURPOSE: Bind a phase-status update to the canonical artifact registry.
RULES:
  ALWAYS emit any produced phase-status artifact with artifact_type = phase-status, ref, and summary
  ALWAYS allow the underlying phase-status payload shape to be status-record or phase-status-doc
  ALWAYS permit an optional linked_artifacts list so the caller can point to relevant produced artifacts or reports
  NEVER repurpose phase-status to carry full workflow logs or unrelated diagnostics
```
