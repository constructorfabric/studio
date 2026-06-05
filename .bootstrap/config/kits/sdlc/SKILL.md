---
name: cf
description: "Invoke when the user asks to author or review any SDLC artifact or run an SDLC kit operation — write/revise a PRD, ADR, DESIGN, DECOMPOSITION, or FEATURE; implement a FEATURE in code; review or report status on a GitHub PR; or migrate OpenSpec artifacts. Kit `sdlc` extensions — artifacts: ADR, CODEBASE, DECOMPOSITION, DESIGN, FEATURE, PRD (+ PR review/status templates); workflows: doc-prd, doc-adr, doc-design, decompose, doc-feature, implement, change-impact-analysis, reverse-engineer, migrate-openspec, pr-review, pr-status."
---

# Constructor Studio Skill — Kit `sdlc`

Kit `sdlc` skill extensions.

## Authoring & Implementation Workflows

Each SDLC artifact has a thin preset workflow that delegates to a core engine
(`cf-write-docs` for documents, `cf-coding` for code) while binding the artifact
KIND and injecting that artifact's rules, template, checklist, and example.

| Skill | Artifact KIND | Engine | Workflow |
|-------|---------------|--------|----------|
| `cf-sdlc-doc-prd` | PRD | cf-write-docs | `{workflow_doc_prd}` |
| `cf-sdlc-doc-adr` | ADR | cf-write-docs | `{workflow_doc_adr}` |
| `cf-sdlc-doc-design` | DESIGN | cf-write-docs | `{workflow_doc_design}` |
| `cf-sdlc-decompose` | DECOMPOSITION | cf-write-docs | `{workflow_decompose}` |
| `cf-sdlc-doc-feature` | FEATURE | cf-write-docs | `{workflow_doc_feature}` |
| `cf-sdlc-implement` | CODE | cf-coding | `{workflow_implement}` |

ALWAYS route to the matching preset workflow WHEN the user intent is authoring,
revising, or implementing the corresponding artifact:

- `cf-sdlc-doc-prd` — write/revise a PRD (`generate PRD`, `write the PRD`)
- `cf-sdlc-doc-adr` — write/revise an ADR (`generate ADR`, `record a decision`)
- `cf-sdlc-doc-design` — write/revise a DESIGN (`generate DESIGN`, `design the system`)
- `cf-sdlc-decompose` — write/revise a DECOMPOSITION (`decompose`, `break into features`)
- `cf-sdlc-doc-feature` — write/revise a FEATURE (`generate FEATURE`, `spec the feature`)
- `cf-sdlc-implement` — implement a FEATURE in code (`implement`, `write the code`)

When routed to a preset workflow:
1. Read the matched workflow file and follow it.
2. The preset binds the artifact KIND + references, then delegates the full
   author/coder -> deterministic-gate -> semantic-review loop to its core engine.

## Analysis & Reconstruction Workflows (Phase-1)

| Skill | Engine | Workflow | Output |
|-------|--------|----------|--------|
| `cf-sdlc-change-impact-analysis` | cf-analyze | `{workflow_change_impact_analysis}` | `.change-impact/{id}/report.md` |
| `cf-sdlc-reverse-engineer` | cf-write-docs | `{workflow_reverse_engineer}` | `docs/sdlc/{kind}/` |

ALWAYS route to the matching workflow WHEN the user intent matches:

- `cf-sdlc-change-impact-analysis` — analyze the downstream impact of an
  upstream artifact change (`impact of changing PRD-001`, `what breaks if I
  change this DESIGN`). Read-only; modes `cascade-tracking` and
  `release-readiness-estimation`; thresholds in `{change_impact_config}`.
- `cf-sdlc-reverse-engineer` — reconstruct SDLC artifacts from existing code via
  `@cpt-*` markers (`reverse engineer FEATURE from this module`,
  `rebuild the DESIGN from code`). Distinct from `cf-sdlc-migrate-openspec`,
  which converts from the OpenSpec format.

## ADR

### ADR Commands
- `cfs validate --artifact <ADR.md>` — validate ADR structure and IDs
- `cfs list-ids --kind adr` — list all ADRs
- `cfs where-defined --id <id>` — find where an ADR ID is defined
- `cfs where-used --id <id>` — find where an ADR ID is referenced in DESIGN
### ADR Workflows
- **Generate ADR**: create a new ADR from template with guided prompts per section
- **Analyze ADR**: validate structure (deterministic) then semantic quality (checklist-based)

## CODEBASE

### CODE Commands
- `cfs validate --artifact <code-path>` — validate code traceability and quality
- `cfs where-defined --id <id>` — find where an ID is defined in artifacts
- `cfs where-used --id <id>` — find where an ID is referenced in code via `@cpt-*` markers
### CODE Workflows
- **Generate CODE**: implement FEATURE design with optional `@cpt-*` traceability markers
- **Analyze CODE**: validate implementation coverage, traceability, tests, and quality

## DECOMPOSITION

### DECOMPOSITION Commands
- `cfs validate --artifact <DECOMPOSITION.md>` — validate DECOMPOSITION structure and IDs
- `cfs list-ids --kind feature` — list all features
- `cfs list-ids --kind status` — list status indicators
- `cfs where-defined --id <id>` — find where a feature ID is defined
- `cfs where-used --id <id>` — find where a feature ID is referenced in FEATURE artifacts
### DECOMPOSITION Workflows
- **Generate DECOMPOSITION**: create feature manifest from DESIGN with guided prompts
- **Analyze DECOMPOSITION**: validate structure (deterministic) then decomposition quality (checklist-based)

## DESIGN

### DESIGN Commands
- `cfs validate --artifact <DESIGN.md>` — validate DESIGN structure and IDs
- `cfs list-ids --kind component` — list all components
- `cfs list-ids --kind principle` — list all design principles
- `cfs where-defined --id <id>` — find where a DESIGN ID is defined
- `cfs where-used --id <id>` — find where a DESIGN ID is referenced downstream
### DESIGN Workflows
- **Generate DESIGN**: create a new DESIGN from template with guided prompts per section
- **Analyze DESIGN**: validate structure (deterministic) then semantic quality (checklist-based)

## FEATURE

### FEATURE Commands
- `cfs validate --artifact <FEATURE.md>` — validate FEATURE structure and IDs
- `cfs list-ids --kind flow` — list all flows
- `cfs list-ids --kind algo` — list all algorithms
- `cfs list-ids --kind state` — list all state machines
- `cfs list-ids --kind dod` — list all definitions of done
- `cfs where-defined --id <id>` — find where a FEATURE ID is defined
- `cfs where-used --id <id>` — find where a FEATURE ID is referenced in code
### FEATURE Workflows
- **Generate FEATURE**: create a new FEATURE from template with guided CDSL prompts
- **Analyze FEATURE**: validate structure (deterministic) then semantic quality (checklist-based)

## PR-REVIEW

## PR Review & Status (Shortcut Routing)

ALWAYS re-fetch and re-analyze from scratch WHEN a PR review or status request is detected — even if the same PR was reviewed earlier in this conversation. Previous results are stale the moment a new request arrives. NEVER skip fetch or reuse earlier analysis.

ALWAYS run `python3 {scripts}/pr.py list` WHEN user intent matches PR list patterns:
- `list PRs`, `list open PRs`, `cf-studio list PRs`, `cf list PRs`
- `show PRs`, `show open PRs`, `what PRs are open`
- `cf-sdlc-pr-status list PRs` — kit-level invocation (routes here, not to status workflow)
- Any request to enumerate or browse open pull requests

AVOID use `gh pr list` directly — ALWAYS use `pr.py list` for listing PRs.

ALWAYS route to the `cf-sdlc-pr-review` workflow WHEN user intent matches PR review patterns:
- `review PR {number}`, `review PR #{number}`, `review PR https://...`
- `cf-studio review PR {number}`, `cf review PR {number}`, `PR review {number}`
- `code review PR {number}`, `check PR {number}`

ALWAYS route to the `cf-sdlc-pr-status` workflow WHEN user intent matches PR status patterns:
- `PR status {number}`, `cf-studio PR status {number}`, `cf PR status {number}`
- `status of PR {number}`, `check PR status {number}`
- `cf-sdlc-pr-status {number}` — kit-level direct invocation

### PR List (Quick Command)

When routed to list PRs:
1. Run `python3 {scripts}/pr.py list`
2. Present the output to the user (respects `.prs/config.yaml` exclude list)
3. No Protocol Guard or workflow loading required — this is a quick command

### PR Review Workflow

When routed to PR review:
1. **ALWAYS fetch fresh data first** — run `pr.py fetch` even if data exists from a prior run
2. Read `{workflow_pr_review}` and follow its steps
3. Use `python3 {scripts}/pr.py` as the script
4. When target is `ALL` or no PR number given, run `pr.py list` first to show available PRs
5. Select prompt and checklist from `{cf-studio-path}/config/pr-review.toml` → `prompts`
6. Load prompt from `prompt_file` and checklist from `checklist` in matched entry
7. Use templates from `{pr_code_review_template}` and `{pr_status_report_template}`

### PR Status Workflow

When routed to PR status:
1. **ALWAYS fetch fresh data first** — `pr.py status` auto-fetches, but never assume prior data is current
2. Read `{workflow_pr_status}` and follow its steps
3. Use `python3 {scripts}/pr.py` as the script
4. When target is `ALL` or no PR number given, run `pr.py list` first to show available PRs

## MIGRATION

### Migration Commands
- `cf-studio migrate-openspec` — migrate OpenSpec artifacts to Constructor Studio SDLC documents

### Migration Workflows

ALWAYS route to the `cf-sdlc-migrate-openspec` workflow WHEN user intent matches OpenSpec migration patterns:
- `migrate openspec`, `migrate from openspec`, `convert openspec`
- `cf-studio migrate-openspec`, `openspec to Constructor Studio`
- Any request to convert OpenSpec artifacts to Constructor Studio SDLC format

When routed to OpenSpec migration:
1. Read `{workflow_migrate_openspec}` and follow its steps
2. The workflow handles all configuration discovery and user interaction

## PRD

### PRD Commands
- `cfs validate --artifact <PRD.md>` — validate PRD structure and IDs
- `cfs list-ids --kind fr` — list all functional requirements
- `cfs list-ids --kind actor` — list all actors
- `cfs where-defined --id <id>` — find where a PRD ID is defined
- `cfs where-used --id <id>` — find where a PRD ID is referenced downstream
### PRD Workflows
- **Generate PRD**: create a new PRD from template with guided prompts per section
- **Analyze PRD**: validate structure (deterministic) then semantic quality (checklist-based)
