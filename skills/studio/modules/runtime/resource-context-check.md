# Resource Context Check

```pdsl
UNIT ResourceContextCheckContract
PURPOSE: Validate whether resource-context style inputs are required, sufficient, or block execution.
STATE:
  SET RESOURCE_CONTEXT_REQUIREMENT: required | optional | not-needed | unset (default unset, scope unit_run)
  SET AVAILABLE_ARTIFACTS: list | unset (default unset, scope unit_run)
  SET RESOURCE_CONTEXT_SCOPE_HINTS: list | unset (default unset, scope unit_run)
  SET RESOURCE_CONTEXT_STATUS: ready | blocked | skipped | unset (default unset, scope unit_run)
  SET REQUIRED_INPUT_SPECS: list | unset (default unset, scope unit_run)
  SET MISSING_INPUTS_REPORT: list | unset (default unset, scope unit_run)
WHEN:
  REQUIRE RESOURCE_CONTEXT_REQUIREMENT != unset
  REQUIRE AVAILABLE_ARTIFACTS is provided
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/artifact-contract-load.md WHEN ArtifactContractLoad is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/missing-inputs-report.md WHEN MissingInputsReportContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/handoff-suggestions.md WHEN HandoffSuggestionsContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-report.md WHEN BlockedReportContract is not yet loaded
  RUN ArtifactContractLoad
  RUN ResourceContextRequirementContract
  RUN ResourceContextAcceptedInputContract
  RUN ResourceContextNarrowingContract
  CONTINUE ResourceContextBlockedBranch WHEN RESOURCE_CONTEXT_REQUIREMENT == required AND MISSING_INPUTS_REPORT is non-empty
  CONTINUE ResourceContextReadyBranch WHEN RESOURCE_CONTEXT_REQUIREMENT == required AND MISSING_INPUTS_REPORT is empty
  CONTINUE ResourceContextOptionalBranch WHEN RESOURCE_CONTEXT_REQUIREMENT == optional
  CONTINUE ResourceContextSkippedBranch WHEN RESOURCE_CONTEXT_REQUIREMENT == not-needed
RULES:
  ALWAYS treat resource-context as helpful context evidence, not as universal workflow authority
  ALWAYS allow a caller to satisfy this check with either canonical resource-context or canonical relevant-files-map when the caller declared that narrower acceptance policy
  NEVER force an explore step only because resource-context is absent when the caller declared the requirement optional or not-needed
```

```pdsl
UNIT ResourceContextRequirementContract
PURPOSE: Declare the accepted requirement modes for resource-context inputs.
RULES:
  ALWAYS use RESOURCE_CONTEXT_REQUIREMENT values required, optional, or not-needed only
  ALWAYS represent the required input declaration with input_key = resource-context and artifact_type = resource-context when canonical context is accepted
  ALWAYS allow the caller to declare relevant-files-map in the same check when narrower path targeting is sufficient
  NEVER treat skipped explore history as proof that context is not needed
```

```pdsl
UNIT ResourceContextAcceptedInputContract
PURPOSE: Validate accepted resource-context style inputs without deep exploration semantics.
DO:
  SET REQUIRED_INPUT_SPECS = [resource-context declaration in context-ref or context-map shape] WHEN RESOURCE_CONTEXT_REQUIREMENT != not-needed AND caller declared resource-context as the required input
  SET REQUIRED_INPUT_SPECS = [relevant-files-map declaration in path-map or path-list shape] WHEN RESOURCE_CONTEXT_REQUIREMENT != not-needed AND caller declared relevant-files-map as the required input
  SET REQUIRED_INPUT_SPECS = [resource-context declaration, relevant-files-map declaration] WHEN RESOURCE_CONTEXT_REQUIREMENT != not-needed AND caller declared both as independently required
  RUN MissingInputsReportContract WHEN RESOURCE_CONTEXT_REQUIREMENT != not-needed
RULES:
  ALWAYS accept canonical resource-context only in ArtifactAcceptedShapeContract shapes context-ref or context-map
  ALWAYS treat relevant-files-map as a distinct canonical artifact, never as an implied second name for resource-context
  ALWAYS allow either resource-context or relevant-files-map inputs to satisfy the check when the caller declared that narrower acceptance policy explicitly
  NEVER require this module to inspect or synthesize the full explorer payload
```

```pdsl
UNIT ResourceContextNarrowingContract
PURPOSE: Permit callers to narrow already-supplied context to a relevant subset.
RULES:
  ALWAYS allow RESOURCE_CONTEXT_SCOPE_HINTS to narrow an accepted resource-context or relevant-files-map input to a task-scoped subset
  ALWAYS keep narrowed context as a read-only reference, manifest, or path map rather than inline copied file contents
  ALWAYS treat insufficient-scope as a valid missing_reason when the supplied context exists but does not cover the requested files or surfaces
  NEVER require re-exploration when a caller can narrow an existing accepted context artifact deterministically
```

```pdsl
UNIT ResourceContextBlockedBranch
PURPOSE: Report required resource-context blockers through the shared blocked envelope.
DO:
  SET RESOURCE_CONTEXT_STATUS = blocked
  RUN HandoffSuggestionsContract
  SET missing_artifacts = MISSING_INPUTS_REPORT with input_key and missing_reason removed
  RUN BlockedReportContract
RULES:
  ALWAYS expose explore or another declared producer only as a suggestion
  NEVER auto-run explore from this branch
  NEVER use Bash, Grep, Read, Glob, or any inline tool call as a substitute for a missing required resource-context input; ALWAYS emit the blocked result and STOP_TURN instead
```

```pdsl
UNIT ResourceContextReadyBranch
PURPOSE: Mark required resource-context input as satisfied.
DO:
  SET RESOURCE_CONTEXT_STATUS = ready
RULES:
  ALWAYS use this branch only when at least one accepted resource-context style input is present in accepted shape and scope
```

```pdsl
UNIT ResourceContextOptionalBranch
PURPOSE: Permit execution to continue when context was declared optional.
DO:
  SET RESOURCE_CONTEXT_STATUS = ready
RULES:
  ALWAYS keep any MISSING_INPUTS_REPORT visible to the caller when optional context would still improve quality
  NEVER block execution solely because optional resource-context was absent
```

```pdsl
UNIT ResourceContextSkippedBranch
PURPOSE: Record that the caller intentionally does not require resource-context.
DO:
  SET RESOURCE_CONTEXT_STATUS = skipped
RULES:
  ALWAYS use this branch only when RESOURCE_CONTEXT_REQUIREMENT == not-needed
  NEVER emit a blocked result from this branch
```
