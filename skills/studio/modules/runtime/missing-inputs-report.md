# Missing Inputs Report

```pdsl
UNIT MissingInputsReportContract
PURPOSE: Normalize missing or rejected prerequisite inputs into one machine-readable report.
STATE:
  SET REQUIRED_INPUT_SPECS: list | unset (default unset, scope unit_run)
  SET AVAILABLE_INPUTS: list | unset (default unset, scope unit_run)
  SET MISSING_INPUTS_REPORT: list | unset (default unset, scope unit_run)
WHEN:
  REQUIRE REQUIRED_INPUT_SPECS is provided
  REQUIRE AVAILABLE_INPUTS is provided
DO:
  RUN MissingInputsReportDeclarationContract
  RUN MissingInputsReportCollectionContract
  RUN MissingInputsReportOrderingContract
RULES:
  ALWAYS use this contract to shape missing-input summaries before blocked-report, prerequisite, or handoff logic consumes them
  ALWAYS keep missing-input entries machine-readable and artifact-oriented
  NEVER collapse missing-input state into prose-only status text
```

```pdsl
UNIT MissingInputsReportDeclarationContract
PURPOSE: Define the minimum declaration shape for a required input.
RULES:
  ALWAYS require each REQUIRED_INPUT_SPECS entry to include input_key, artifact_type, why_needed, accepted_shapes, suggested_producers, and override_allowed
  ALWAYS allow each REQUIRED_INPUT_SPECS entry to include override_summary and missing_reason_hint
  ALWAYS keep input_key stable within the current check so downstream modules can reference the same missing input deterministically
  ALWAYS keep artifact_type aligned to ArtifactRegistryContract when canonical, or caller-declared when using an explicit extension artifact
  NEVER hide accepted_shapes, producer hints, or override policy outside the declaration entry
```

```pdsl
UNIT MissingInputsReportCollectionContract
PURPOSE: Collect every required input that is absent or rejected by shape.
DO:
  RUN compare REQUIRED_INPUT_SPECS against AVAILABLE_INPUTS by input_key or artifact_type and accepted shape
  SET MISSING_INPUTS_REPORT = every REQUIRED_INPUT_SPECS entry whose matching available input is absent or outside accepted_shapes, preserving input_key, artifact_type, why_needed, accepted_shapes, suggested_producers, override_allowed, and override_summary while adding missing_reason
RULES:
  ALWAYS set missing_reason to one of missing, rejected-shape, or insufficient-scope
  ALWAYS use missing_reason_hint as the visible explanation suffix when the caller supplied one
  ALWAYS keep MISSING_INPUTS_REPORT entries compatible with blocked-report missing_artifacts entries after dropping input_key and missing_reason
  NEVER mutate missing-input entries into workflow-specific handoff prose during collection
```

```pdsl
UNIT MissingInputsReportOrderingContract
PURPOSE: Keep missing-input reports deterministic across callers.
RULES:
  ALWAYS preserve REQUIRED_INPUT_SPECS declaration order in MISSING_INPUTS_REPORT unless the caller explicitly supplies a stricter priority
  ALWAYS keep duplicate missing entries collapsed to one entry per input_key
  NEVER reorder missing inputs opportunistically from user-facing prose preferences alone
```
