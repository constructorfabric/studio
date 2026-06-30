# Artifact DoD Check

```pdsl
UNIT ArtifactDodCheckContract
PURPOSE: Validate shallow coverage of phase-dod or acceptance-criteria items against produced or reviewed artifacts.
STATE:
  SET DOD_INPUT_ITEMS: list | unset (default unset, scope unit_run)
  SET TARGET_ARTIFACTS: list | unset (default unset, scope unit_run)
  SET ARTIFACT_DOD_COVERAGE: list | unset (default unset, scope unit_run)
  SET ARTIFACT_DOD_STATUS: ready | blocked | unset (default unset, scope unit_run)
WHEN:
  REQUIRE DOD_INPUT_ITEMS is provided
  REQUIRE TARGET_ARTIFACTS is provided
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/artifact-contract-load.md WHEN ArtifactContractLoad is not yet loaded
  RUN ArtifactContractLoad WHEN ArtifactContractLoad is not yet loaded
  RUN ArtifactDodInputContract
  RUN ArtifactDodCoverageContract
  RUN ArtifactDodStatusContract
RULES:
  ALWAYS keep this check shallow and contract-level
  ALWAYS allow callers to use phase-dod items, acceptance-criteria items, or a merged normalized list as DOD_INPUT_ITEMS
  NEVER treat this module as semantic proof that the underlying artifact implementation is correct
```

```pdsl
UNIT ArtifactDodInputContract
PURPOSE: Define the minimum DOD item and target-artifact shapes.
RULES:
  ALWAYS require each DOD_INPUT_ITEMS entry to include item_id, summary, and required
  ALWAYS allow each DOD_INPUT_ITEMS entry to include source_artifact and coverage_hints
  ALWAYS require each TARGET_ARTIFACTS entry to satisfy ArtifactDescriptorContract
  NEVER require deep domain schemas for DOD items inside this module
```

```pdsl
UNIT ArtifactDodCoverageContract
PURPOSE: Produce a shallow coverage map from DOD items to target artifacts.
DO:
  RUN match each DOD_INPUT_ITEMS entry against TARGET_ARTIFACTS using explicit coverage_hints, caller-supplied trace references, or normalized artifact summaries only
  SET ARTIFACT_DOD_COVERAGE = one entry per DOD_INPUT_ITEMS item with item_id, coverage_status, artifact_refs, and rationale
RULES:
  ALWAYS use coverage_status values covered, uncovered, or unclear only
  ALWAYS keep artifact_refs as artifact descriptors or refs, not copied artifact bodies
  ALWAYS treat missing trace references or absent matching summaries as uncovered or unclear rather than silently covered
  NEVER invent deep semantic coverage claims beyond the supplied shallow hints
```

```pdsl
UNIT ArtifactDodStatusContract
PURPOSE: Reduce shallow coverage into one contract-level status.
DO:
  SET ARTIFACT_DOD_STATUS = ready WHEN every required DOD_INPUT_ITEMS entry has coverage_status = covered
  SET ARTIFACT_DOD_STATUS = blocked WHEN one-or-more required DOD_INPUT_ITEMS entries have coverage_status = uncovered or unclear
RULES:
  ALWAYS keep uncovered or unclear required items visible through ARTIFACT_DOD_COVERAGE
  NEVER collapse blocked DOD coverage into a success status only because some optional items were covered
```
