# Explore Discovery Pattern

Use this module when a thin skill or shared module needs the canonical rule for
where `cf-explore` invocations that produce prerequisite artifacts must live.

```pdsl
UNIT ExploreDiscoveryPattern
PURPOSE: Define the canonical extraction rule for cf-explore invocations that produce prerequisite artifacts used by the thin-skill runtime.
RULES:
  ALWAYS extract a cf-explore invocation into a dedicated shared module when its
    result is subsequently checked as a required artifact by PrerequisiteCheckContract
  ALWAYS name the shared module `{workflow-family}-discovery-run.md` and place it
    under `skills/studio/modules/`
  ALWAYS name the primary UNIT inside that module `{WorkflowFamily}DiscoveryRunStart`
    following UpperCamelCase of the workflow family prefix
  ALWAYS treat `kit-discovery-run.md` as the canonical reference implementation
    for naming, UNIT structure, classification result, and failure menu shape
  ALWAYS model new `{domain}-discovery-run.md` modules after the reference
    implementation structure: a start UNIT (`{WorkflowFamily}DiscoveryRunStart`),
    a classify-result UNIT (`{WorkflowFamily}DiscoveryRunClassifyResult`), a
    failure UNIT (`{WorkflowFamily}DiscoveryRunFailure`), and a failure-menu MENU
    block (`{WorkflowFamily}DiscoveryFailureMenu`)
  ALWAYS apply the extraction criterion defined in ExploreDiscoveryExtractionCriterion
    when deciding whether to extract a cf-explore call into a shared module
  NEVER inline a cf-explore call that produces a prerequisite-checked artifact
    directly inside a standalone skill or inside a module whose primary purpose
    is not discovery orchestration
  NEVER treat the extraction rule as retroactive: existing inline explore calls
    such as CodingExploreGate and WriteSkillsExploreGate are grandfathered until
    each is next significantly changed, at which point extraction becomes mandatory
NOTES:
  Immediate-consumption inline explore calls — those whose result is consumed
  and discarded within the same unit without entering the prerequisite check
  pipeline — are exempt from mandatory extraction. Examples include a brainstorm
  pre-panel context gather whose result is displayed inline and never stored as a
  named artifact or state variable.
```

```pdsl
UNIT ExploreDiscoveryExtractionCriterion
PURPOSE: Define the precise threshold that triggers mandatory extraction of a cf-explore call into a shared discovery module.
RULES:
  ALWAYS apply the mandatory extraction rule when ALL of the following are true:
    (1) the unit invokes cf-explore or a wrapper around cf-explore,
    (2) the result of that invocation is stored in a named artifact or state variable,
    (3) that named artifact or state variable is later evaluated by
        PrerequisiteCheckContract as a required artifact
  ALWAYS treat extraction as optional when the explore result is consumed
    immediately within the same unit and is never referenced by
    PrerequisiteCheckContract or any downstream prerequisite gate
  NEVER use call frequency as the extraction trigger
  ALWAYS treat a single cf-explore invocation as sufficient to mandate extraction
    when it meets all three conditions in the ALWAYS rules above
```

```pdsl
UNIT ExploreDiscoveryNamingConvention
PURPOSE: Specify the file and UNIT naming rules for shared discovery modules.
RULES:
  ALWAYS use the workflow-family prefix as the file stem:
    `{workflow-family}-discovery-run.md`
  ALWAYS place the file in `skills/studio/modules/`
  ALWAYS use `{WorkflowFamily}DiscoveryRunStart` as the name of the primary UNIT
  ALWAYS use `{WorkflowFamily}DiscoveryRunClassifyResult` for the classify UNIT
  ALWAYS use `{WorkflowFamily}DiscoveryRunFailure` for the failure-handling UNIT
  ALWAYS use `{WorkflowFamily}DiscoveryFailureMenu` for the failure recovery menu
  NEVER deviate from the four-component pattern (start, classify, failure,
    failure-menu) without documenting the deviation in a NOTES block in the first
    UNIT of the module
NOTES:
  Examples: `kit-discovery-run.md` → KitInitDiscoveryRunStart (reference);
  `ci-discovery-run.md` → CiDiscoveryRunStart (first new domain instance).
```

```pdsl
UNIT ExploreDiscoveryReferenceImplementation
PURPOSE: Point authors to the canonical reference implementation for shared discovery modules.
RULES:
  ALWAYS consult `kit-discovery-run.md` before authoring a new
    `{domain}-discovery-run.md` module
  ALWAYS replicate the return-context mode invocation pattern:
    `INVOKE skill cf-explore with intent=<domain-specific intent> and
    return_context=true, scoped to <domain-specific scope> and known_paths =
    <domain-specific scope>`
  ALWAYS carry forward the read-only constraint: discovery modules must never
    write, mutate, or commit any artifact
  ALWAYS include a DISCOVERY_STATUS classification step (provided / empty / error)
  ALWAYS set RESOURCE_CONTEXT = provided when DISCOVERY_STATUS == provided,
    following the reference implementation's happy-path-only population pattern
  NEVER use cf-explore in write or mutate mode inside a discovery module
```

```pdsl
UNIT ExploreDiscoveryCIGatePolicy
PURPOSE: Enforce the ci-explore-gate-mandatory policy for CI-domain discovery runs.
RULES:
  ALWAYS run CI-domain discovery before resolving CI gate commands; the discovery
    run is mandatory by default
  ALWAYS offer an explicit user-facing skip option as a numbered menu choice when
    the discovery run is presented; the skip must never be a silent fallback
  ALWAYS proceed with caller-supplied REVIEW_TARGET_PATHS or inline heuristic
    when the user explicitly chooses to skip discovery
  ALWAYS use `completed-with-assumptions` as the result status when the CI skill
    produces output after a user-initiated discovery skip
  ALWAYS use `blocked` as the result status when the user skips discovery and
    REVIEW_TARGET_PATHS is missing and no inline heuristic is available
  NEVER silently skip the discovery run without an explicit user action
  NEVER treat a missing REVIEW_TARGET_PATHS as a reason to silently proceed;
    surface it as a `blocked` result
```
