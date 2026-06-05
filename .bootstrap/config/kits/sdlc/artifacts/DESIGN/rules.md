# DESIGN Rules

**Artifact**: DESIGN
**Kit**: sdlc

```pdsl
UNIT DesignAuthoring

PURPOSE:
  Author or revise a DESIGN capturing system/subsystem architecture, domain model,
  components, interfaces, drivers, principles, and constraints.

WHEN:
  - REQUIRE authoring a new DESIGN OR revising an existing DESIGN

DO:
  - LOAD {design_template} for structure
  - LOAD {design_example} when content-depth reference is needed
  - RUN read parent PRD for context (if exists)
  - RUN identify output path from {cf-studio-path}/config/artifacts.toml
  - RUN author sections: Architecture Overview, Domain Model, Component Design,
    Interfaces/API Contracts, Interaction Sequences, Architecture Drivers,
    Principles, Constraints, Technology Stack, Capacity/Cost
  - SET type IDs: cpt-{hierarchy-prefix}-type-{slug}
  - SET component IDs: cpt-{hierarchy-prefix}-comp-{slug} (as needed)
  - RUN link to PRD actors/capabilities and reference relevant ADRs
  - RUN verify ID uniqueness with `cfs list-ids`
  - RUN on partial completion: set frontmatter status: DRAFT, mark sections
    INCOMPLETE: {reason}, record resumption checkpoint, verify PRD unchanged on resume

RULES:
  - ALWAYS follow {design_template} structure with all required sections non-empty
  - ALWAYS use ID convention cpt-{hierarchy-prefix}-{kind}-{slug} (see artifacts.toml)
  - ALWAYS version on edit: increment frontmatter version; on type/component change
    add -v{N} suffix (e.g. cpt-{hierarchy-prefix}-comp-{slug}-v3) and keep changelog
  - ALWAYS treat {design_checklist} as the source of semantic criteria
  - NEVER duplicate {design_checklist} semantic content into this file
  - NEVER include placeholder content (TODO, TBD, FIXME)
  - NEVER create duplicate IDs within the document
```

```pdsl
UNIT DesignOmissions

PURPOSE:
  Enforce DESIGN MUST NOT HAVE boundaries; report any occurrence as a violation.

RULES:
  - NEVER include Spec-Level Details (ARCH-DESIGN-NO-001, CRITICAL) — belongs in feature specs
  - NEVER include Decision Debates (ARCH-DESIGN-NO-002, HIGH) — belong in ADR
  - NEVER include Product Requirements (BIZ-DESIGN-NO-003, HIGH) — belong in PRD
  - NEVER include Implementation Tasks (BIZ-DESIGN-NO-004, HIGH) — belong in DECOMPOSITION
  - NEVER include Code-Level Schema Definitions (DATA-DESIGN-NO-001, MEDIUM) — belong in implementation
  - NEVER include Complete API Specifications (INT-DESIGN-NO-001, MEDIUM) — belong in FEATURE
  - NEVER include Infrastructure Code (OPS-DESIGN-NO-001, MEDIUM) — belongs in implementation
  - NEVER include Test Code (TEST-DESIGN-NO-001, MEDIUM) — belongs in implementation
  - NEVER include Code Snippets (MAINT-DESIGN-NO-001, HIGH) — code belongs in implementation
  - NEVER include Security Secrets (SEC-DESIGN-NO-001, CRITICAL) — secrets must never appear in docs
```

```pdsl
UNIT DesignValidate

PURPOSE:
  Gate DESIGN completion on deterministic structural checks plus checklist-based
  semantic review.

DO:
  - RUN `cfs validate --artifact <path>` for template structure, ID format,
    cross-reference validity, and no-placeholder checks
  - RUN `cfs toc <artifact-file>` to generate/update Table of Contents
  - RUN `cfs validate-toc <artifact-file>` — must report PASS
  - LOAD {design_checklist} and read in full for semantic validation
  - RUN evaluate each MUST HAVE item (met / explicit N/A / violation) and scan
    each MUST NOT HAVE item

RULES:
  - NEVER mark DESIGN done while any validation reports FAIL or error
  - ALWAYS use {design_checklist} for semantic criteria, applicability context,
    review priority, severity, and report format (do not duplicate here)
  - ALWAYS mark a component [x] in DESIGN when it is fully implemented
  - ALWAYS update the related ADR status (PROPOSED → ACCEPTED) when all its components are implemented
  - ALWAYS mark a PRD capability [x] when all its design elements are implemented
```

```pdsl
UNIT DesignErrorHandling

PURPOSE:
  Handle missing/incomplete prerequisites and escalate ambiguity.

ON_ERROR:
  missing_prd ->
    EMIT "Parent PRD not found."
    RUN option 1: `/cf-studio-generate PRD` first (recommended)
    RUN option 2: continue without PRD — document "PRD pending" in frontmatter,
      skip PRD reference validation (DESIGN will lack traceability)

  incomplete_prd ->
    RUN if PRD outdated: review before proceeding
    RUN if PRD needs updates: `/cf-studio-generate PRD UPDATE`
    RUN if PRD current: proceed with DESIGN

  uncertain ->
    EMIT escalation question to user
    RUN escalate when: component boundaries unclear; architecture decision needs
      an ADR but none exists; PRD requirements ambiguous or contradictory
```

```pdsl
UNIT DesignNextSteps

PURPOSE:
  Offer next actions after a DESIGN is authored or revised.

DO:
  - EMIT options:
    1 DESIGN complete -> `/cf-studio-generate DECOMPOSITION` (specs manifest)
    2 Need architecture decision -> `/cf-studio-generate ADR`
    3 PRD missing/incomplete -> `/cf-studio-generate PRD`
    4 DESIGN needs revision -> continue editing DESIGN
    5 Checklist review only -> `/cf-studio-analyze semantic`
```
