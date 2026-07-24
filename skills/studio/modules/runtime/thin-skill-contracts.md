# Thin Skill Runtime Contracts

Use this module when a generated skill or workflow needs the shared
module-first runtime rules for thin standalone skills.

```pdsl
UNIT ThinSkillRuntimeContracts
PURPOSE: Load the canonical thin-skill runtime law for standalone skills.
DO:
  RUN ThinSkillModuleFirstLaw
  RUN ThinSkillRegistryContract
  RUN ThinSkillStatusContract
  RUN ThinSkillResultEnvelopeContract
  RUN ThinSkillBlockedContract
  RUN ThinSkillTerminalMenuContract
  RUN ThinSkillAssumptionContract
  RUN ThinSkillDescriptionContract
  RUN ThinSkillPurposeContract
RULES:
  ALWAYS load these rules before a generated standalone skill or workflow
  interprets skill-local prerequisite, blocked, override, report, or handoff
  behavior
```

```pdsl
UNIT ThinSkillModuleFirstLaw
PURPOSE: Keep standalone skills thin and move reusable behavior into shared modules.
RULES:
  ALWAYS treat standalone skills as thin user-facing entrypoints
  ALWAYS keep substantive reusable runtime behavior in shared modules
  ALWAYS prefer module loading over embedding reusable loops or policy blocks
    directly in a standalone skill
  ALWAYS treat executable modules as entrypoint-bearing assets: after `LOAD`
    of a procedural module, explicitly `RUN`, `CONTINUE`, `EMIT_MENU`, or
    otherwise consume at least one UNIT or MENU from that module on the active
    path
  ALWAYS keep reference-only and contract-only modules visibly named and
    limited to rules, schemas, templates, or static assets when they are
    loaded without an immediate UNIT or MENU handoff
  NEVER passive-load a procedural module only for implied future behavior when
    the current path can instead load it at the actual point of use
  NEVER treat a standalone skill as the canonical home for reusable
    prerequisite resolution, semantic review browsing, CI report rendering, or
    phase-close logic
NOTES:
  When a thin skill or shared module invokes cf-explore to produce an artifact
  that is later checked by PrerequisiteCheckContract, that invocation MUST live
  in a dedicated `{workflow-family}-discovery-run.md` shared module, not inline
  in the skill. See `runtime/explore-discovery-pattern.md` for the canonical
  extraction criterion, naming convention, and reference implementation.
```

```pdsl
UNIT ThinSkillRegistryContract
PURPOSE: Keep runtime registries explicit and stable across Studio and kit-owned skills.
RULES:
  ALWAYS treat standalone skills, shared modules, and canonical artifacts as
    explicit runtime registries
  ALWAYS reuse canonical status names and canonical artifact names when a kit
    adds its own thin entrypoint
  NEVER redefine a canonical artifact name with skill-local semantics
```

```pdsl
UNIT ThinSkillStatusContract
PURPOSE: Define the canonical top-level status set for standalone skill results.
RULES:
  ALWAYS use only these statuses for standalone skill result envelopes:
    ready, blocked, completed, completed-with-assumptions, failed
  ALWAYS separate produced artifacts from report outputs in result envelopes
  NEVER invent a skill-local top-level status when one of the canonical
    statuses already applies
```

```pdsl
UNIT ThinSkillResultEnvelopeContract
PURPOSE: Keep top-level skill results machine-readable and uniform.
RULES:
  ALWAYS emit type, skill, status, produced_artifacts, report_outputs,
    missing_artifacts, assumptions, and suggested_next_skills in the top-level
    result envelope
  ALWAYS prefer empty collections over omitted envelope fields
  NEVER replace canonical envelope field names with skill-local aliases
```

```pdsl
UNIT ThinSkillBlockedContract
PURPOSE: Standardize how a standalone skill reports missing prerequisites.
RULES:
  ALWAYS when a required artifact is missing, return status = blocked
  ALWAYS include missing_artifacts, why_needed, accepted_shapes, and
    suggested_producers in the blocked result
  ALWAYS make override_allowed explicit in blocked payloads
  ALWAYS expose a visible override path when degraded execution is legal
  ALWAYS expose an override path only when the skill class allows degraded
    execution
  NEVER silently invoke a producer skill by default from a blocked state
```

```pdsl
UNIT ThinSkillTerminalMenuContract
PURPOSE: Keep user-returning skill states actionable through explicit next-step menus.
RULES:
  ALWAYS when a standalone skill returns control to the user from blocked,
    completed, completed-with-assumptions, or failed state, provide a clear
    numbered next-actions menu or an equivalent explicit numbered choice list
  ALWAYS include an explicit `back` option in every user-facing menu
  ALWAYS treat `back` as returning to the nearest previous workflow-owned
    decision point; when no earlier decision point exists, `back` MUST resolve
    to a safe terminal return rather than doing nothing
  ALWAYS keep terminal menus aligned to the current result state and visible
    next-step options
  NEVER return control to the user from a thin skill with envelope-plus-prose
    only when the workflow can offer explicit next actions
```

```pdsl
UNIT ThinSkillAssumptionContract
PURPOSE: Restrict assumption-based completion to the permitted skill classes.
RULES:
  ALWAYS allow completed-with-assumptions only for planning, authoring, fix,
    explore, and brainstorm skill classes
  NEVER allow completed-with-assumptions for review or CI skill classes
```

```pdsl
UNIT ThinSkillDescriptionContract
PURPOSE: Keep standalone skill descriptions usable as routing hints for the LLM.
RULES:
  ALWAYS write standalone skill `description` fields as trigger instructions
    for when the skill should be invoked
  ALWAYS start standalone skill `description` fields with `Invoke when`
  ALWAYS describe invocation intent hints, inputs, or situations that should
    load the skill
  ALWAYS write descriptions so they can match both end-user requests and
    internal delegation requests from another skill or workflow
  ALWAYS prefer descriptions that still match free-form user phrasing, not
    only exact workflow names or internal artifact jargon
  ALWAYS combine likely intent verbs, artifact nouns, and expected outcomes
    when doing so improves routing recall
  ALWAYS prefer common user language such as "fix", "review", "write tests",
    "plan the work", or "explain what changed" when clearer than internal
    runtime terminology
  ALWAYS keep compatibility-alias descriptions narrow when broad matching
    would compete with a canonical thin entrypoint
  ALWAYS keep generic router descriptions fallback-oriented so they do not
    compete with concrete domain workflows during intent matching
  NEVER use standalone skill `description` fields for compatibility notes,
    canonical or legacy labeling, or implementation details
```

```pdsl
UNIT ThinSkillPurposeContract
PURPOSE: Keep standalone skill purposes focused on internal responsibility rather than routing.
RULES:
  ALWAYS write standalone skill `purpose` fields as internal descriptions of
    workflow responsibility, role, or execution boundary
  ALWAYS keep standalone skill `purpose` fields separate from user-intent
    routing hints
  NEVER use standalone skill `purpose` fields as the trigger instruction for
    when a skill should be invoked
  NEVER use standalone skill `purpose` fields for compatibility, canonical,
    legacy, or alias labeling unless the label is required to explain runtime
    behavior
```
