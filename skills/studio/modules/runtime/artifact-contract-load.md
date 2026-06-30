# Artifact Contract Load

```pdsl
UNIT ArtifactContractLoad
PURPOSE: Load the canonical artifact registry and shallow shape expectations for thin-skill exchange.
DO:
  RUN ArtifactRegistryContract
  RUN ArtifactDescriptorContract
  RUN ArtifactAcceptedShapeContract
RULES:
  ALWAYS load these artifact contracts before a thin skill validates artifact names, accepted_shapes, or produced_artifacts entries
  NEVER treat this module as a deep domain schema or workflow-specific artifact policy
```

```pdsl
UNIT ArtifactRegistryContract
PURPOSE: Reserve the canonical artifact names used by the thin-skill runtime.
RULES:
  ALWAYS treat only these names as the canonical shared artifact registry for this runtime slice: resource-context, relevant-files-map, dependency-map, test-surfaces, design-doc, design-decisions, unresolved-questions, acceptance-criteria, constraints, phase-plan, phase-brief, phase-dod, phase-status, unit-tests, e2e-tests, test-spec, code-changes, doc-changes, skill-changes, review-findings, ci-findings, deterministic-report, commit-intent, commit-result
  ALWAYS preserve the canonical meaning of each listed artifact name across Studio and kit-owned thin skills
  NEVER repurpose a canonical artifact name for a conflicting skill-local payload
```

```pdsl
UNIT ArtifactDescriptorContract
PURPOSE: Keep artifact references shallow, stable, and machine-readable.
RULES:
  ALWAYS represent an exchanged artifact or a produced_artifacts entry with artifact_type, ref, and summary
  ALWAYS use artifact_type values from ArtifactRegistryContract when the artifact is canonical
  ALWAYS keep artifact descriptors reference-oriented; downstream modules may validate the referenced content separately
  NEVER require deep per-artifact field schemas in this module
```

```pdsl
UNIT ArtifactAcceptedShapeContract
PURPOSE: Define contract-level accepted shape classes for canonical artifacts.
RULES:
  ALWAYS accept resource-context as context-ref or context-map
  ALWAYS accept relevant-files-map as path-map or path-list
  ALWAYS accept dependency-map as graph-ref or graph-doc
  ALWAYS accept test-surfaces as surface-list or doc-bundle
  ALWAYS accept design-doc as doc-ref or doc-bundle
  ALWAYS accept design-decisions as decision-list or doc-bundle
  ALWAYS accept unresolved-questions as question-list or doc-bundle
  ALWAYS accept acceptance-criteria as criteria-list or doc-bundle
  ALWAYS accept constraints as constraint-list or doc-bundle
  ALWAYS accept phase-plan as phase-plan-doc or phase-plan-bundle
  ALWAYS accept phase-brief as phase-brief-doc or phase-brief-bundle
  ALWAYS accept phase-dod as dod-list or phase-dod-doc
  ALWAYS accept phase-status as status-record or phase-status-doc
  ALWAYS accept unit-tests as test-delta or test-bundle
  ALWAYS accept e2e-tests as test-delta or test-bundle
  ALWAYS accept test-spec as test-spec-doc or test-spec-bundle
  ALWAYS accept code-changes as change-bundle or diff-ref
  ALWAYS accept doc-changes as change-bundle or diff-ref
  ALWAYS accept skill-changes as change-bundle or diff-ref
  ALWAYS accept review-findings as findings-report or findings-list
  ALWAYS accept ci-findings as findings-report or findings-list
  ALWAYS accept deterministic-report as deterministic-report or check-report
  ALWAYS accept commit-intent as intent-record or intent-doc
  ALWAYS accept commit-result as result-record or result-doc
  NEVER infer a deeper schema obligation from these accepted shape classes alone
```
