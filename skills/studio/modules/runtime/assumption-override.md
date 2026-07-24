# Assumption Override

```pdsl
UNIT AssumptionOverrideContract
PURPOSE: Define the explicit degraded-execution path for skill classes that allow assumptions.
DO:
  RUN AssumptionOverrideEligibilityContract
  RUN AssumptionOverrideActivationContract
  RUN AssumptionOverrideCompletionContract
RULES:
  ALWAYS require the override path to remain visible, explicit, and user-approved
  NEVER silently degrade execution because prerequisites are missing or weak
```

```pdsl
UNIT AssumptionOverrideEligibilityContract
PURPOSE: Restrict override eligibility to the allowed thin-skill classes.
RULES:
  ALWAYS require SKILL_CLASS and OVERRIDE_ALLOWED to be known before an override path is offered or accepted
  ALWAYS allow override eligibility only when SKILL_CLASS is planning, authoring, fix, explore, or brainstorm and OVERRIDE_ALLOWED == true
  ALWAYS reject override eligibility when SKILL_CLASS is review or ci
  NEVER advertise a hidden or implicit override path for an ineligible skill class
```

```pdsl
UNIT AssumptionOverrideActivationContract
PURPOSE: Require an explicit activation signal before degraded execution begins.
RULES:
  ALWAYS require OVERRIDE_REQUESTED == explicit-user-approval before continuing past a blocked prerequisite state in degraded mode
  ALWAYS require the visible blocked path to identify which missing artifacts are being overridden
  ALWAYS require the caller to initialize ASSUMPTIONS as a machine-readable list before degraded execution completes
  NEVER treat silence, ambiguity, or generic task continuation as override approval
```

```pdsl
UNIT AssumptionOverrideCompletionContract
PURPOSE: Bind explicit override usage to canonical completion semantics.
RULES:
  ALWAYS use status = completed-with-assumptions when degraded execution completes under an active override
  ALWAYS record each assumption with artifact_or_gate, summary, and risk
  ALWAYS keep missing_artifacts visible or otherwise traceable until the skill produces replacement artifacts or exits
  NEVER emit status = completed when degraded execution materially depended on unresolved assumptions
```
