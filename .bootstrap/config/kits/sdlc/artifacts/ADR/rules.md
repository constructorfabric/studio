# ADR Rules

**Artifact**: ADR
**Kit**: sdlc

```pdsl
UNIT AdrAuthoring

PURPOSE:
  Author or revise one ADR (one decision per record) that follows the template,
  has a unique well-formed ID, valid status, and complete rationale.

STATE:
  - SET adr_status: PROPOSED | ACCEPTED | REJECTED | DEPRECATED | SUPERSEDED
    default: PROPOSED

WHEN:
  - REQUIRE authoring or revising an ADR

DO:
  - LOAD {cf-studio-path}/config/artifacts.toml to resolve ADR directory and next number
  - RUN assign next sequential number NNNN+1 from existing artifacts where kind == "ADR"
  - SET default path {artifacts_dir}/ADR/{NNNN}-{slug}.md and register in artifacts.toml with FULL path
  - LOAD {adr_template} for structure
  - LOAD {adr_example} for content depth reference
  - RUN author sections: context/problem, options (>=2 distinct viable), decision + rationale, consequences (pros/cons), status
  - SET ID cpt-{hierarchy-prefix}-adr-{slug} (e.g. cpt-myapp-adr-use-postgresql) with priority marker p1-p9
  - RUN verify ID uniqueness with cfs list-ids
  - RUN link to DESIGN when applicable
  - LOAD {adr_checklist} for self-review of semantic quality

RULES:
  - ALWAYS follow {adr_template} structure with required frontmatter
  - ALWAYS use ID form cpt-{hierarchy-prefix}-adr-{slug} with a p1-p9 priority marker
  - ALWAYS version in filename NNNN-{slug}-v{N}.md
  - ALWAYS keep one decision per ADR (split bundled decisions; skip implementation-detail decisions)
  - ALWAYS treat {adr_checklist} as the semantic source of truth
  - ALWAYS keep ADR-worthy scope: technology/pattern/integration/security/infrastructure choices, not naming, file layout, lib versions, or UI styling
  - NEVER include placeholder content (TODO, TBD, FIXME)
  - NEVER create duplicate IDs
  - NEVER duplicate {adr_checklist} semantic criteria in this file
```

```pdsl
UNIT AdrStatusLifecycle

PURPOSE:
  Govern ADR status transitions and immutability of accepted decisions.

RULES:
  - ALWAYS use status vocabulary PROPOSED, ACCEPTED, REJECTED, DEPRECATED, SUPERSEDED
  - ALWAYS allow minor edits only while PROPOSED
  - ALWAYS treat ACCEPTED ADRs as immutable for decision and rationale
  - ALWAYS create a NEW ADR with a SUPERSEDES reference to change an accepted decision; mark original SUPERSEDED and add superseded_by: cpt-{hierarchy-prefix}-adr-{new-slug}
  - ALWAYS on transition update frontmatter status, append status history "{date}: {OLD} -> {NEW} ({reason})" when present
  - ALWAYS on REJECTED add rejection_reason and keep the record for history
  - NEVER edit decision or rationale of an ACCEPTED ADR

NOTES:
  Transitions: PROPOSED->ACCEPTED (approved), PROPOSED->REJECTED (declined),
  ACCEPTED->DEPRECATED (no longer applies), ACCEPTED->SUPERSEDED (replaced by new ADR).
```

```pdsl
UNIT AdrOmissions

PURPOSE:
  Enforce MUST NOT HAVE content; report any occurrence as a violation.

RULES:
  - NEVER ARCH-ADR-NO-001 (CRITICAL): complete architecture description — belongs in system/architecture design docs
  - NEVER ARCH-ADR-NO-002 (HIGH): spec implementation details (how, not why) — belongs in spec/implementation design
  - NEVER BIZ-ADR-NO-001 (HIGH): product requirements — belong in PRD
  - NEVER BIZ-ADR-NO-002 (HIGH): implementation tasks — belong in DECOMPOSITION/FEATURE
  - NEVER DATA-ADR-NO-001 (MEDIUM): complete schema definitions — belong in DESIGN
  - NEVER MAINT-ADR-NO-001 (HIGH): code implementation — belongs in implementation
  - NEVER SEC-ADR-NO-001 (CRITICAL): security secrets — must never appear in documentation
  - NEVER TEST-ADR-NO-001 (MEDIUM): test implementation — belongs in code
  - NEVER OPS-ADR-NO-001 (MEDIUM): operational procedures — belong in runbooks
  - NEVER ARCH-ADR-NO-003 (MEDIUM): trivial decisions — ADRs are for significant decisions only
  - NEVER ARCH-ADR-NO-004 (HIGH): incomplete decisions — ADR must have a clear decision, not "TBD"
```

```pdsl
UNIT AdrValidate

PURPOSE:
  Validate the ADR deterministically and semantically, then report.

DO:
  - RUN cfs validate --artifact <path> for template structure, ID format, no placeholders
  - LOAD {adr_checklist} for semantic validation, applicability context, review scope, and report format
  - RUN cfs toc <artifact-file> to generate/update Table of Contents
  - RUN cfs validate-toc <artifact-file> — must report PASS
  - RETURN validation report (Structural PASS/FAIL, Semantic PASS/FAIL with issues)

RULES:
  - ALWAYS use {adr_checklist} as the source for semantic criteria, applicability handling, and the review report format
  - NEVER mark validation done while any check reports FAIL or error
  - NEVER duplicate checklist semantic criteria or report templates here
```

```pdsl
UNIT AdrErrorHandling

PURPOSE:
  Recover from setup failures and escalate ambiguous decisions.

ON_ERROR:
  adr_number_conflict ->
    EMIT "ADR number conflict: {NNNN} already exists"
    RUN verify existing ADRs (ls architecture/ADR/)
    SET number = NNNN+1
    EMIT "If duplicate content: consider updating existing ADR instead"

  adr_directory_missing ->
    EMIT "ADR directory not found"
    RUN mkdir -p architecture/ADR
    SET number = 0001

RULES:
  - ALWAYS ask the user when decision significance is unclear
  - ALWAYS ask the user when options require domain expertise to evaluate
  - ALWAYS ask the user when compliance or security implications are uncertain
```

```pdsl
UNIT AdrNextSteps

PURPOSE:
  Offer next actions based on ADR state.

DO:
  - EMIT "ADR PROPOSED -> share for review, then update status to ACCEPTED"
  - EMIT "ADR ACCEPTED -> /cf-studio-generate DESIGN (incorporate decision)"
  - EMIT "Related ADR needed -> /cf-studio-generate ADR"
  - EMIT "ADR supersedes another -> update original ADR status to SUPERSEDED"
  - EMIT "Checklist review only -> /cf-studio-analyze semantic"
```
