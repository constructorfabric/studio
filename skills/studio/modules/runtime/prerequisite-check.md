# Prerequisite Check

```pdsl
UNIT PrerequisiteCheckContract
PURPOSE: Evaluate declared artifact prerequisites and branch to ready or blocked using shared contracts.
STATE:
  SET REQUIRED_ARTIFACT_SPECS: list | unset (default unset, scope unit_run)
  SET AVAILABLE_ARTIFACTS: list | unset (default unset, scope unit_run)
  SET MISSING_ARTIFACTS: list | unset (default unset, scope unit_run)
  SET MISSING_INPUTS_REPORT: list | unset (default unset, scope unit_run)
  SET PREREQUISITE_STATUS: ready | blocked | unset (default unset, scope unit_run)
WHEN:
  REQUIRE REQUIRED_ARTIFACT_SPECS is provided
  REQUIRE AVAILABLE_ARTIFACTS is provided
DO:
  RUN PrerequisiteDeclarationContract
  RUN PrerequisiteArtifactTypeContract
  RUN PrerequisiteMissingArtifactCollection
  CONTINUE PrerequisiteBlockedBranch WHEN MISSING_ARTIFACTS is non-empty
  CONTINUE PrerequisiteReadyBranch WHEN MISSING_ARTIFACTS is empty
RULES:
  ALWAYS treat REQUIRED_ARTIFACT_SPECS as the canonical machine-readable declaration for prerequisite evaluation
  ALWAYS compare required artifact_type entries against AVAILABLE_ARTIFACTS before any skill-local authoring or review work starts
  NEVER auto-run a producer skill while evaluating prerequisites
```

```pdsl
UNIT PrerequisiteDeclarationContract
PURPOSE: Define the minimum shape for each required artifact declaration.
RULES:
  ALWAYS require each REQUIRED_ARTIFACT_SPECS entry to include artifact_type, why_needed, accepted_shapes, suggested_producers, and override_allowed
  ALWAYS allow each REQUIRED_ARTIFACT_SPECS entry to include override_summary when override_allowed == true
  ALWAYS require why_needed to stay one-line and user-visible
  ALWAYS require accepted_shapes to use shape names recognized by ArtifactAcceptedShapeContract or a narrower skill-local subset
  ALWAYS require suggested_producers to list zero-or-more producer skill hints explicitly
  NEVER hide prerequisite semantics only in prose outside the declaration
```

```pdsl
UNIT PrerequisiteArtifactTypeContract
PURPOSE: Keep prerequisite artifact names aligned to the canonical registry.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/artifact-contract-load.md WHEN ArtifactRegistryContract is not yet loaded
  RUN ArtifactRegistryContract
RULES:
  ALWAYS validate each required artifact_type against ArtifactRegistryContract unless the skill explicitly declares a non-canonical extension artifact
  NEVER treat an unknown artifact_type as canonical by implication
```

```pdsl
UNIT PrerequisiteMissingArtifactCollection
PURPOSE: Produce the canonical missing_artifacts payload inputs for blocked reporting.
DO:
  RUN compare REQUIRED_ARTIFACT_SPECS against AVAILABLE_ARTIFACTS by artifact_type and accepted shape
  SET MISSING_ARTIFACTS = every REQUIRED_ARTIFACT_SPECS entry whose artifact_type is absent or whose available shape is outside accepted_shapes
  SET MISSING_INPUTS_REPORT = every REQUIRED_ARTIFACT_SPECS entry whose artifact_type is absent or whose available shape is outside accepted_shapes, preserving artifact_type, why_needed, accepted_shapes, suggested_producers, override_allowed, and override_summary while adding input_key = artifact_type and missing_reason = missing or rejected-shape as appropriate
RULES:
  ALWAYS preserve artifact_type, why_needed, accepted_shapes, suggested_producers, override_allowed, and override_summary from the missing prerequisite entries
  ALWAYS collect missing entries in the same shape expected by blocked-report
  ALWAYS keep MISSING_INPUTS_REPORT compatible with HandoffSuggestionsContract and missing-input reporting modules when prerequisite evaluation blocks execution
  NEVER mutate missing prerequisite entries into workflow-specific prose summaries during collection
```

```pdsl
UNIT PrerequisiteBlockedBranch
PURPOSE: Hand blocked prerequisite state to the shared blocked-report contract.
DO:
  SET PREREQUISITE_STATUS = blocked
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/handoff-suggestions.md WHEN HandoffSuggestionsContract is not yet loaded
  RUN HandoffSuggestionsContract
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-report.md WHEN BlockedReportContract is not yet loaded
  RUN BlockedReportContract
RULES:
  ALWAYS use this branch when one or more required artifacts are missing or rejected by shape
  ALWAYS expose producer skill hints through the blocked payload instead of invoking them
  NEVER continue authoring, review, or CI execution from this branch without an explicit override path handled elsewhere
```

```pdsl
UNIT PrerequisiteReadyBranch
PURPOSE: Mark prerequisite evaluation as satisfied.
DO:
  SET PREREQUISITE_STATUS = ready
RULES:
  ALWAYS use this branch only when every required artifact is present in an accepted shape
  NEVER emit blocked-envelope fields from this branch
```
