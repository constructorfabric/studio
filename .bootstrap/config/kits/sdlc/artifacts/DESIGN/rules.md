# DESIGN Rules

**Artifact**: DESIGN
**Kit**: sdlc

**Dependencies** (lazy-loaded):
- `{design_template}` — structural reference (load WHEN validating structure)
- `{design_checklist}` — semantic quality criteria (load WHEN checking semantic quality)
- `{design_example}` — reference implementation (load WHEN needing content depth reference)

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Requirements](#requirements)
   - [Structural](#structural)
   - [Versioning](#versioning)
   - [Semantic](#semantic)
   - [Scope](#scope)
   - [Traceability](#traceability)
   - [Constraints](#constraints)
   - [Deliberate Omissions (MUST NOT HAVE)](#deliberate-omissions-must-not-have)
   - [Technology Stack & Capacity](#technology-stack-capacity)
3. [Tasks](#tasks)
   - [Phase 1: Setup](#phase-1-setup)
   - [Phase 2: Content Creation](#phase-2-content-creation)
   - [Phase 3: IDs and References](#phase-3-ids-and-references)
   - [Phase 4: Quality Check](#phase-4-quality-check)
   - [Phase 5: Table of Contents](#phase-5-table-of-contents)
4. [Validation](#validation)
   - [Phase 1: Structural Validation (Deterministic)](#phase-1-structural-validation-deterministic)
   - [Phase 2: Semantic Validation (Checklist-based)](#phase-2-semantic-validation-checklist-based)
   - [Phase 3: Validation Report](#phase-3-validation-report)
   - [Phase 4: Applicability Context](#phase-4-applicability-context)
   - [Phase 5: Report Format](#phase-5-report-format)
   - [Compact Report Format (Quick Reviews)](#compact-report-format-quick-reviews)
   - [Phase 6: Reporting Commitment](#phase-6-reporting-commitment)
   - [Phase 7: PR Review Focus (Design)](#phase-7-pr-review-focus-design)
   - [Phase 8: Table of Contents Validation](#phase-8-table-of-contents-validation)
5. [Error Handling](#error-handling)
   - [Missing Prd](#missing-prd)
   - [Incomplete Prd](#incomplete-prd)
   - [Escalation](#escalation)
6. [Next Steps](#next-steps)
   - [Options](#options)

---

## Prerequisites

Read parent PRD for context (if exists).

---

## Requirements

### Structural

**Load on demand**: `{design_template}` — WHEN validating structure

- [ ] DESIGN follows `{design_template}` structure
- [ ] Artifact frontmatter (optional): use `cpt:` format for document metadata
- [ ] All required sections present and non-empty
- [ ] All IDs follow `cpt-{hierarchy-prefix}-{kind}-{slug}` convention (see artifacts.toml for hierarchy)
- [ ] References to PRD are valid
- [ ] No placeholder content (TODO, TBD, FIXME)
- [ ] No duplicate IDs within document

### Versioning

- [ ] When editing existing DESIGN: increment version in frontmatter
- [ ] When changing type/component definition: add `-v{N}` suffix to ID or increment existing version
- [ ] Format: `cpt-{hierarchy-prefix}-type-{slug}-v2`, `cpt-{hierarchy-prefix}-comp-{slug}-v3`, etc.
- [ ] Keep changelog of significant changes

### Semantic

**Load on demand**: `{design_checklist}` — WHEN checking semantic quality

- [ ] Architecture overview is complete and clear
- [ ] Domain model defines all core types
- [ ] Components have clear responsibilities and boundaries
- [ ] Integration points documented
- [ ] ADR references provided for key decisions
- [ ] PRD capabilities traced to components

### Scope

**One DESIGN per system/subsystem**. Match scope to architectural boundaries.

| Scope | Examples | Guideline |
|-------|----------|-----------|
| **Too broad** | "Entire platform design" for 50+ components | Split into subsystem DESIGNs |
| **Right size** | "Auth subsystem design" covering auth components | Clear boundary, manageable size |
| **Too narrow** | "Login button component design" | Implementation detail, use SPEC |

**DESIGN-worthy content**:
- System/subsystem architecture overview
- Domain model (core types, relationships)
- Component responsibilities and boundaries
- Integration points and contracts
- Key architectural decisions (reference ADRs)

**NOT DESIGN-worthy** (use SPEC instead):
- Individual spec implementation details
- UI flows and interactions
- Algorithm pseudo-code
- Test scenarios

**Relationship to other artifacts**:
- **PRD** → DESIGN: PRD defines WHAT, DESIGN defines HOW (high-level)
- **DESIGN** → DECOMPOSITION: DESIGN defines architecture, DECOMPOSITION lists implementations
- **DESIGN** → SPEC: DESIGN provides context, SPEC details implementation

### Traceability

**Load on demand**: `{cf-studio-path}/.core/architecture/specs/traceability.md` — WHEN checking ID formats

- [ ] When component fully implemented → mark component `[x]` in DESIGN
- [ ] When all components for ADR implemented → update ADR status (PROPOSED → ACCEPTED)
- [ ] When all design elements for PRD capability implemented → mark capability `[x]` in PRD

### Constraints

**Load on demand**:
- `{constraints}` — WHEN validating cross-references
- `{cf-studio-path}/.core/architecture/specs/kit/constraints.md` — WHEN resolving constraint rules
- `{cf-studio-path}/.core/schemas/kit-constraints.schema.json` — WHEN validating constraints schema

- [ ] ALWAYS open and follow `{constraints}` (kit root)
- [ ] Treat `constraints.toml` as primary validator for:
  - where IDs are defined
  - where IDs are referenced
  - which cross-artifact references are required / optional / prohibited

**References**:
- `{cf-studio-path}/.core/requirements/kit-constraints.md`
- `{cf-studio-path}/.core/schemas/kit-constraints.schema.json`

**Validation Checks**:
- `cfs validate` enforces `identifiers[<kind>].references` rules (required / optional / prohibited)
- `cfs validate` enforces headings scoping for ID definitions and references
- `cfs validate` enforces "checked ref implies checked def" consistency

### Deliberate Omissions (MUST NOT HAVE)

DESIGN documents must NOT contain the following — report as violation if found:

- **ARCH-DESIGN-NO-001**: No Spec-Level Details (CRITICAL) — DESIGN captures architecture, not feature specs
- **ARCH-DESIGN-NO-002**: No Decision Debates (HIGH) — debates belong in ADR
- **BIZ-DESIGN-NO-003**: No Product Requirements (HIGH) — requirements belong in PRD
- **BIZ-DESIGN-NO-004**: No Implementation Tasks (HIGH) — tasks belong in DECOMPOSITION
- **DATA-DESIGN-NO-001**: No Code-Level Schema Definitions (MEDIUM) — code schemas belong in implementation
- **INT-DESIGN-NO-001**: No Complete API Specifications (MEDIUM) — full API specs belong in FEATURE
- **OPS-DESIGN-NO-001**: No Infrastructure Code (MEDIUM) — infra code belongs in implementation
- **TEST-DESIGN-NO-001**: No Test Code (MEDIUM) — test code belongs in implementation
- **MAINT-DESIGN-NO-001**: No Code Snippets (HIGH) — code belongs in implementation
- **SEC-DESIGN-NO-001**: No Security Secrets (CRITICAL) — secrets must never appear in documentation

### Technology Stack & Capacity

**ARCH-DESIGN-009: Technology Stack Alignment** (MEDIUM):
- [ ] Technology choices documented (if applicable)
- [ ] Choices align with constraints
- [ ] Choices align with team capabilities
- [ ] Choices support NFRs
- [ ] Choices are maintainable long-term
- [ ] Technology risks identified

**ARCH-DESIGN-010: Capacity and Cost Budgets** (HIGH):
- [ ] Capacity planning approach documented
- [ ] Cost estimation approach documented
- [ ] Budget allocation strategy documented
- [ ] Cost optimization patterns documented

---

## Tasks

### Phase 1: Setup

- [ ] Read parent PRD for context (if exists)
- [ ] Identify artifact output path from `{cf-studio-path}/config/artifacts.toml`

### Phase 2: Content Creation

**Load on demand**:
- `{design_template}` — WHEN generating artifact structure
- `{design_example}` — WHEN needing reference for content depth

**Apply checklist.md semantics during creation:**

| Checklist Section | Generation Task |
|-------------------|-----------------|
| ARCH-DESIGN-001: Architecture Overview | Document system purpose, high-level architecture, context diagram |
| ARCH-DESIGN-002: Principles Coherence | Define actionable, non-contradictory principles |
| DOMAIN-DESIGN-001: Domain Model | Define types, relationships, boundaries |
| COMP-DESIGN-001: Component Design | Define responsibilities, interfaces, dependencies |

**Partial Completion Handling**:

If DESIGN cannot be completed in a single session:
1. **Checkpoint progress**:
   - Note completed sections (Architecture, Domain, Components, etc.)
   - Note current section being worked on
   - List remaining sections
2. **Ensure valid intermediate state**:
   - All completed sections must be internally consistent
   - Add `status: DRAFT` to frontmatter
   - Mark incomplete sections with `INCOMPLETE: {reason}`
3. **Document resumption point**:
   ```
   DESIGN checkpoint:
   - Completed: Architecture Overview, Domain Model
   - In progress: Component Design (3/7 components)
   - Remaining: Sequences, Data Model
   - Resume: Continue with component cpt-{hierarchy-prefix}-comp-{slug}
   ```
4. **On resume**:
   - Verify PRD unchanged since last session
   - Continue from documented checkpoint
   - Remove incomplete markers as sections are finished

### Phase 3: IDs and References

- [ ] Generate type IDs: `cpt-{hierarchy-prefix}-type-{slug}` (e.g., `cpt-myapp-type-user-entity`)
- [ ] Generate component IDs (if needed)
- [ ] Link to PRD actors/capabilities
- [ ] Reference relevant ADRs
- [ ] Verify uniqueness with `cfs list-ids`

### Phase 4: Quality Check

- [ ] Self-review against `{design_checklist}` MUST HAVE items
- [ ] Ensure no MUST NOT HAVE violations
- [ ] Verify PRD traceability

### Phase 5: Table of Contents

- [ ] Run `cfs toc <artifact-file>` to generate/update Table of Contents
- [ ] Verify TOC is present and complete with `cfs validate-toc <artifact-file>`

---

## Validation

### Phase 1: Structural Validation (Deterministic)

- [ ] Run `cfs validate --artifact <path>` for:
  - Template structure compliance
  - ID format validation
  - Cross-reference validity
  - No placeholders

### Phase 2: Semantic Validation (Checklist-based)

**Load on demand**: `{design_checklist}` — required for this phase

- [ ] Read `{design_checklist}` in full
- [ ] For each MUST HAVE item: check if requirement is met
  - If not met: report as violation with severity
  - If not applicable: verify explicit "N/A" with reasoning
- [ ] For each MUST NOT HAVE item: scan document for violations

### Phase 3: Validation Report

```
DESIGN Validation Report
══════════════════════════

Structural: PASS/FAIL
Semantic: PASS/FAIL (N issues)

Issues:
- [SEVERITY] CHECKLIST-ID: Description
```

### Phase 4: Applicability Context

Before evaluating each checklist item, the expert MUST:

1. **Understand the artifact's domain** — What kind of system/project is this DESIGN for? (e.g., web service, CLI tool, data pipeline, methodology framework)

2. **Determine applicability for each requirement** — Not all checklist items apply to all designs:
   - A CLI tool design may not need Security Architecture analysis
   - A methodology framework design may not need Performance Architecture analysis
   - A local development tool design may not need Operations Architecture analysis

3. **Require explicit handling** — For each checklist item:
   - If applicable: The document MUST address it (present and complete)
   - If not applicable: The document MUST explicitly state "Not applicable because..." with reasoning
   - If missing without explanation: Report as violation

4. **Never skip silently** — Either:
   - The requirement is met (document addresses it), OR
   - The requirement is explicitly marked not applicable (document explains why), OR
   - The requirement is violated (report it with applicability justification)

**Key principle**: The reviewer must be able to distinguish "author considered and excluded" from "author forgot"

### Phase 5: Report Format

Report **only** problems (do not list what is OK).

For each issue include:

- **Why Applicable**: Explain why this requirement applies to this specific DESIGN's context
- **Checklist Item**: `{CHECKLIST-ID}` — {Checklist item title}
- **Severity**: CRITICAL|HIGH|MEDIUM|LOW
- **Issue**: What is wrong (requirement missing or incomplete)
- **Evidence**: Quote the exact text or "No mention found"
- **Why it matters**: Impact (risk, cost, user harm, compliance)
- **Proposal**: Concrete fix with clear acceptance criteria

### Compact Report Format (Quick Reviews)

For quick reviews, use this condensed table format:

```markdown
## DESIGN Review Summary

| ID | Severity | Issue | Proposal |
|----|----------|-------|----------|
| ARCH-DESIGN-001 | HIGH | Missing context diagram | Add system context diagram to Section A |
| ARCH-DESIGN-005 | MEDIUM | No schema location | Add path to domain types in Section C.1 |

**Applicability**: {System type} — checked {N} priority domains, {M} marked N/A
```

### Phase 6: Reporting Commitment

- [ ] I reported all issues I found
- [ ] I used the exact report format defined in this checklist (no deviations)
- [ ] I included Why Applicable justification for each issue
- [ ] I included evidence and impact for each issue
- [ ] I proposed concrete fixes for each issue
- [ ] I did not hide or omit known problems
- [ ] I verified explicit handling for all major checklist categories
- [ ] I am ready to iterate on the proposals and re-review after changes

### Phase 7: PR Review Focus (Design)

When reviewing PRs that add or change design documents, additionally focus on:

- [ ] Alignment with existing architecture (see project DESIGN artifacts)
- [ ] Trade-off analysis — are alternatives considered and justified?
- [ ] API contract consistency with existing endpoints and conventions
- [ ] Security considerations — authentication, authorization, data protection
- [ ] Compliance with `{design_template}` structure
- [ ] Identify antipatterns — god objects, leaky abstractions, tight coupling
- [ ] Compare proposed design with existing industry patterns in SaaS platforms
- [ ] Compare proposed design with IEEE, ISO, and other industry standards where applicable
- [ ] Critical assessment of design decisions — challenge assumptions and gaps
- [ ] Split findings by checklist category and rate each 1-10

### Phase 8: Table of Contents Validation

- [ ] Table of Contents section exists (`## Table of Contents` or `<!-- toc -->` markers)
- [ ] All TOC anchors point to actual headings in the document
- [ ] All headings are represented in the TOC
- [ ] TOC order matches document heading order
- [ ] Run `cfs validate-toc <artifact-file>` — must report PASS

---

## Error Handling

### Missing Prd

- [ ] If parent PRD not found:
  - Option 1: Run `/cf-studio-generate PRD` first (recommended)
  - Option 2: Continue without PRD (DESIGN will lack traceability)
  - If Option 2: document "PRD pending" in DESIGN frontmatter, skip PRD reference validation

### Incomplete Prd

- [ ] If PRD exists but is outdated: review PRD before proceeding
- [ ] If PRD needs updates: `/cf-studio-generate PRD UPDATE`
- [ ] If PRD is current: proceed with DESIGN

### Escalation

- [ ] Ask user when uncertain about component boundaries
- [ ] Ask user when architecture decisions require ADR but none exists
- [ ] Ask user when PRD requirements are ambiguous or contradictory

---

## Next Steps

### Options

- [ ] DESIGN complete → `/cf-studio-generate DECOMPOSITION` — create specs manifest
- [ ] Need architecture decision → `/cf-studio-generate ADR` — document key decision
- [ ] PRD missing/incomplete → `/cf-studio-generate PRD` — create/update PRD first
- [ ] DESIGN needs revision → continue editing DESIGN
- [ ] Want checklist review only → `/cf-studio-analyze semantic` — semantic validation
