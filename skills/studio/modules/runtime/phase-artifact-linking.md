# Phase Artifact Linking

```pdsl
UNIT PhaseArtifactLinkingContract
PURPOSE: Associate produced artifacts with an explicit current-phase context.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/artifact-contract-load.md WHEN ArtifactContractLoad is not yet loaded
  RUN ArtifactContractLoad
  RUN PhaseArtifactContextContract
  RUN PhaseArtifactLinkRecordContract
RULES:
  ALWAYS use this module only to attach phase context to already-produced artifacts
  ALWAYS keep the linking contract artifact-agnostic apart from canonical phase context artifacts
  NEVER treat this module as permission to generate, mutate, or validate artifact content
```

```pdsl
UNIT PhaseArtifactContextContract
PURPOSE: Keep current-phase context explicit and machine-readable.
RULES:
  ALWAYS require CURRENT_PHASE_ID before linking artifacts to a phase context
  ALWAYS allow PHASE_CONTEXT_ARTIFACTS to reference zero-or-more of phase-plan, phase-brief, and phase-dod
  ALWAYS represent each PHASE_CONTEXT_ARTIFACTS entry with artifact_type, ref, and summary
  ALWAYS keep phase context references separate from produced_artifacts so callers can reuse either independently
  NEVER infer CURRENT_PHASE_ID solely from artifact paths or filenames
```

```pdsl
UNIT PhaseArtifactLinkRecordContract
PURPOSE: Define the shared link record between phase context and produced artifacts.
RULES:
  ALWAYS represent each PHASE_ARTIFACT_LINKS entry with phase_id, context_refs, artifact_type, ref, and summary
  ALWAYS derive artifact_type, ref, and summary from the caller-supplied produced artifact descriptors
  ALWAYS keep context_refs as a list of shallow refs back to the active phase context artifacts
  ALWAYS allow produced artifact types to remain domain-specific or canonical without changing the link shape
  NEVER embed workflow-local routing or closure state into a phase artifact link record
```
