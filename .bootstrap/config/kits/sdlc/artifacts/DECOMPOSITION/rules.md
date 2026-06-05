# DECOMPOSITION Rules

**Artifact**: DECOMPOSITION
**Kit**: sdlc

```pdsl
UNIT DecompositionAuthoring

PURPOSE:
  Author or revise a DECOMPOSITION that breaks DESIGN into implementable features with full coverage.

WHEN:
  - REQUIRE intent == author_or_revise_decomposition

DO:
  - LOAD {decomposition_template}
  - LOAD DESIGN to identify components, sequences, data entities to decompose
  - LOAD PRD to identify FR/NFR requirements to cover
  - LOAD {cf-studio-path}/config/artifacts.toml to determine artifact paths
  - RUN group related design elements into features (high cohesion, loose coupling)
  - RUN author FEATURE list with per-feature Purpose, Scope, Out of Scope, Depends On, Requirements Covered, Design Components
  - RUN assign feature IDs cpt-{hierarchy-prefix}-feature-{slug}; set priority markers p1-p9 by dependency order; set initial status NOT_STARTED
  - RUN author coverage links back to PRD/DESIGN element IDs and forward to FEATURE
  - RUN verify ID uniqueness with `cfs list-ids`
  - LOAD {decomposition_example} to compare content depth

RULES:
  - ALWAYS follow {decomposition_template} structure with all required sections present and non-empty
  - ALWAYS give each feature a unique ID cpt-{hierarchy-prefix}-feature-{slug}, a priority marker p1-p9, and a valid status
  - ALWAYS define checkbox IDs per {constraints}: kind `status` (cpt-{hierarchy-prefix}-status-overall, checked when ALL features checked) and kind `feature` (cpt-{hierarchy-prefix}-feature-{slug}, checked when FEATURE spec complete)
  - ALWAYS treat cpt-... occurrences outside an **ID** definition line as references (kinds: fr, nfr, principle, constraint, component, seq, dbtable)
  - ALWAYS achieve 100% coverage: every DESIGN component, sequence, data entity, principle, constraint assigned to >=1 feature; all PRD FR/NFR covered transitively
  - ALWAYS keep features mutually exclusive with clear boundaries (each design element in exactly one feature, or explicit documented reason for sharing)
  - ALWAYS make dependencies explicit (Depends On), acyclic (valid DAG); foundation features have no dependencies
  - ALWAYS apply ID versioning per traceability spec; IDs are stable and won't change during implementation
  - ALWAYS treat {decomposition_checklist} as the source of semantic acceptance criteria
  - NEVER include placeholder content (TODO, TBD, FIXME)
  - NEVER create duplicate feature IDs
  - NEVER duplicate {decomposition_checklist} semantic criteria into this file
```

```pdsl
UNIT DecompositionOmissions

PURPOSE:
  Keep DECOMPOSITION scoped; forbidden content belongs in other artifacts.

RULES:
  - NEVER include implementation details — code snippets, algorithms, technical specs, user flows, state machines, API request/response schemas (DECOMP-NO-001, CRITICAL) -> belongs in FEATURE artifact
  - NEVER define requirements — FR-xxx, NFR-xxx, use cases, actors (DECOMP-NO-002, HIGH) -> belongs in PRD artifact
  - NEVER include architecture decisions — "why we chose X", technology rationales, pros/cons analysis (DECOMP-NO-003, HIGH) -> belongs in ADR artifact
  - NEVER leave silent omissions — if a design element is intentionally not covered or features intentionally overlap, state it explicitly with reasoning (DOC-001, CRITICAL)
```

```pdsl
UNIT DecompositionValidate

PURPOSE:
  Gate the DECOMPOSITION through deterministic and semantic validation.

DO:
  - RUN `cfs validate --artifact <path>` for template structure, ID format, priority markers, valid status, no placeholders
  - RUN `cfs toc <artifact-file>` to generate/update Table of Contents
  - RUN `cfs validate-toc <artifact-file>` — must report PASS
  - LOAD {decomposition_checklist} and apply systematically (COV, EXC, ATTR, LEV, CFG, TRC, DEP, CHK, DOC)

RULES:
  - ALWAYS use {decomposition_checklist} as the source for semantic criteria, severity, domain disposition, and the issues-only report format
  - NEVER consider the artifact done while any cfs validate check fails or errors
  - NEVER consider semantic validation done while any checklist domain is unaddressed and not explicitly dispositioned
  - ALWAYS maintain progress/cascade rules — a `feature` ID is not checked until that feature is fully implemented; `status-overall` is not checked until ALL `feature` entries are checked
```

```pdsl
UNIT DecompositionErrorHandling

PURPOSE:
  Recover from missing inputs and ambiguity.

ON_ERROR:
  design_not_accessible ->
    EMIT "DESIGN not accessible"
    REQUIRE user provides DESIGN location
  template_not_found ->
    EMIT "Template not found — cannot proceed"
    STOP_TURN
  coverage_gap ->
    RUN add design element to appropriate feature or document exclusion with reasoning
  scope_overlap ->
    RUN assign to single feature or document sharing with reasoning

RULES:
  - ALWAYS escalate to the user when design elements are ambiguous, decomposition granularity is unclear, or dependency ordering is unclear
```

```pdsl
UNIT DecompositionNextSteps

PURPOSE:
  Offer follow-on actions after a valid DECOMPOSITION.

DO:
  - EMIT_MENU DecompositionNextStepsMenu

MENU DecompositionNextStepsMenu:
  TITLE: DECOMPOSITION next steps
  OPTIONS:
    1 -> CONTINUE /cf-studio-generate FEATURE (design first/next feature)
    2 -> RUN update feature status in decomposition (feature IMPLEMENTED)
    3 -> CONTINUE /cf-studio-analyze DESIGN (all features IMPLEMENTED — validate design completion)
    4 -> RUN add new feature to decomposition, then CONTINUE /cf-studio-generate FEATURE
    5 -> CONTINUE /cf-studio-analyze semantic (checklist review only — decomposition quality)
  INVALID:
    EMIT "Reply with 1, 2, 3, 4, or 5."
    WAIT user.reply
    STOP_TURN
```
