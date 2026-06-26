# Design Input Check

```pdsl
UNIT DesignInputCheckContract
PURPOSE: Validate that a planning, authoring, or review skill received sufficient design intent inputs.
STATE:
  SET AVAILABLE_ARTIFACTS: list | unset (default unset, scope unit_run)
  SET DESIGN_REQUIRED_INPUT_SPECS: list | unset (default unset, scope unit_run)
  SET DESIGN_PRIMARY_INPUT_KEYS: list | unset (default unset, scope unit_run)
  SET DESIGN_INPUT_STATUS: ready | blocked | unset (default unset, scope unit_run)
  SET MISSING_INPUTS_REPORT: list | unset (default unset, scope unit_run)
WHEN:
  REQUIRE AVAILABLE_ARTIFACTS is provided
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/artifact-contract-load.md WHEN ArtifactContractLoad is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/missing-inputs-report.md WHEN MissingInputsReportContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/handoff-suggestions.md WHEN HandoffSuggestionsContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-report.md WHEN BlockedReportContract is not yet loaded
  RUN ArtifactContractLoad
  RUN DesignInputRequirementContract
  RUN DesignInputSufficiencyContract
  CONTINUE DesignInputBlockedBranch WHEN DESIGN_INPUT_STATUS == blocked
  CONTINUE DesignInputReadyBranch WHEN DESIGN_INPUT_STATUS == ready
RULES:
  ALWAYS use this contract before planning, authoring, or review work that depends on design intent
  ALWAYS keep blocked reporting explicit when required design intent is insufficient
  NEVER treat unresolved design questions alone as sufficient positive design intent
```

```pdsl
UNIT DesignInputRequirementContract
PURPOSE: Declare the default design-input requirement set and accepted shapes.
DO:
  SET DESIGN_REQUIRED_INPUT_SPECS = caller-provided declarations WHEN DESIGN_REQUIRED_INPUT_SPECS is provided
  SET DESIGN_REQUIRED_INPUT_SPECS = design-doc accepted as doc-ref or doc-bundle, design-decisions accepted as decision-list or doc-bundle, acceptance-criteria accepted as criteria-list or doc-bundle, and constraints accepted as constraint-list or doc-bundle WHEN DESIGN_REQUIRED_INPUT_SPECS is unset
  SET DESIGN_PRIMARY_INPUT_KEYS = caller-provided primary-input list WHEN DESIGN_PRIMARY_INPUT_KEYS is provided
  SET DESIGN_PRIMARY_INPUT_KEYS = design-doc, design-decisions, acceptance-criteria WHEN DESIGN_PRIMARY_INPUT_KEYS is unset
RULES:
  ALWAYS keep at least one of design-doc, design-decisions, or acceptance-criteria as a primary design-intent source unless the caller declares a narrower replacement contract explicitly
  ALWAYS allow constraints to remain mandatory or optional according to the caller's declaration
  NEVER redefine a canonical design artifact with skill-local meaning
```

```pdsl
UNIT DesignInputSufficiencyContract
PURPOSE: Decide whether design intent is sufficient for execution.
DO:
  SET REQUIRED_INPUT_SPECS = DESIGN_REQUIRED_INPUT_SPECS
  SET AVAILABLE_INPUTS = AVAILABLE_ARTIFACTS
  RUN MissingInputsReportContract
  SET DESIGN_INPUT_STATUS = ready WHEN every caller-mandatory design input is present in accepted shape AND at least one DESIGN_PRIMARY_INPUT_KEYS entry is satisfied
  SET DESIGN_INPUT_STATUS = blocked WHEN DESIGN_INPUT_STATUS != ready
RULES:
  ALWAYS treat accepted-shape validation as part of design sufficiency
  ALWAYS block when no primary design-intent artifact is present, even if only supporting artifacts such as constraints are available
  ALWAYS allow a caller to mark a design input optional by excluding it from the mandatory declaration set
  NEVER infer design intent from target filenames, diffs, or resource-context alone
```

```pdsl
UNIT DesignInputBlockedBranch
PURPOSE: Report insufficient design intent through the shared blocked envelope.
DO:
  RUN HandoffSuggestionsContract
  SET missing_artifacts = MISSING_INPUTS_REPORT with input_key and missing_reason removed
  RUN BlockedReportContract
RULES:
  ALWAYS keep why_needed specific to the downstream planning, authoring, or review task
  NEVER continue substantive execution from this branch without a separate explicit override contract
```

```pdsl
UNIT DesignInputReadyBranch
PURPOSE: Mark design intent as sufficient for downstream execution.
DO:
  SET DESIGN_INPUT_STATUS = ready
RULES:
  ALWAYS use this branch only after primary design intent and every mandatory design input passed the sufficiency check
```
