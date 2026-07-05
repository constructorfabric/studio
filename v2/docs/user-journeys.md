# Studio v2 — User Journeys

## Introduction

This document describes the twenty-two primary cross-cutting user journeys in Studio v2.
Each journey traces the full path a user takes from intent to outcome, showing which
Objects, Workers, Flows, Validators, Connectors, and WorkerInteractions are involved.

**How to read ALGORITHM blocks**

Each block follows a fixed schema:

- `ACTOR` — the role that initiates the journey
- `GOAL` — the outcome they are trying to reach
- `INPUTS` — what must already exist before the journey begins; `[sync: name]` marks
  Objects synced from external systems via Connectors
- `OUTPUTS` — what is produced when the journey ends; `[write-back: name]` marks
  Objects written back to external systems
- `COST TIER` — approximate AI cost: `low` (script only), `medium` (hybrid Workers),
  `high` (chain of 2+ LLM Workers)
- `AUTOMATION GATE` — `none` (readonly or Validator-only; any automationLevel) or
  `approved_automation` (action Workers; requires `automationLevel >= approved_automation
  AND category in approvedWorkerCategories`)
- `STEPS` — the ordered sequence of actions, Workers, Flows, and Validator gates invoked
- `DECISION_POINTS` — named forks where the user or Studio chooses a path
- `GUARDS` — invariants that must hold throughout; violation halts the journey
- `NEXT` — optional handoff to a downstream journey or external process

**Studio v2 architecture note**

Studio v2 is Object- and Worker-centric. Objects live in the shadow SDLC graph. Workers
consume and produce Objects. Flows add mandatory-step constraints over Workers. Connectors
sync Objects from external systems (via Gears OAGW). Action Workers write back to external
systems through `WriteBackPolicy`. Validators run regardless of `automationLevel`; action
Workers require `approved_automation`. WorkerInteractions pause a WorkerRun mid-run and
resume on user response. Evidence is immutable proof attached to Objects.

---

## Journey Index

| # | Journey | Actor | Goal | Workers / Flows / Validators | Cost Tier | Automation Gate |
|---|---------|-------|------|------------------------------|-----------|-----------------|
| 1 | Plan and Implement a Feature | Developer | decompose intent → code → PR with traceability | `decompose_feature_worker` → `implement_code_worker` → `create_pr_worker` + `pr_design_validator` | high | approved_automation |
| 2 | Onboard a Project to Studio v2 | Tech Lead / DevOps | Kit install + Connector setup + Workspace config | Kit install + Connector setup + WorkerInteraction (menu) | low | approved_automation |
| 3 | Explore Design Options and Author an ADR | Architect / Tech Lead | WorkerInteraction free_form_intent → `create_adr_worker` → adr Object | `object_graph_retriever` + `create_adr_worker` | medium | approved_automation |
| 4 | Review and Fix Code via PR Validator | Developer / Reviewer | `pr_design_validator` findings → WorkerInteraction (menu) per finding → fix PR | `pr_design_validator` + `implement_code_worker` + `create_pr_worker` | high | approved_automation |
| 5 | Create and Publish a Kit | Platform Engineer | Kit manifest authoring + Kit Registry publish | Kit manifest authoring + WorkerInteraction (menu) | low | approved_automation |
| 6 | Generate Project Documentation | Technical Writer / Developer | `document_retriever` → `create_design_worker` (docs variant) → ValidationSession | `document_retriever` + `create_design_worker` + `gap_analysis_validator` | high | approved_automation |
| 7 | Author a PRD | Product Manager | `create_prd_worker` → prd Object + `gap_analysis_validator` | `create_prd_worker` + `gap_analysis_validator` | high | approved_automation |
| 8 | Record an Architecture Decision | Architect / Tech Lead | `create_adr_worker` → adr Object + ValidationSession | `create_adr_worker` + `pr_design_validator` | medium | approved_automation |
| 9 | Author a System Design | Architect / Tech Lead | `create_design_worker` → design Object + `gap_analysis_validator` | `create_design_worker` + `gap_analysis_validator` | high | approved_automation |
| 10 | Decompose Design into Tasks | Tech Lead / PM | `decompose_feature_worker` → decomposition + task[] [write-back: jira] | `decompose_feature_worker` + `gap_analysis_validator` | high | approved_automation |
| 11 | Author a Feature Specification | Tech Lead / Developer | `create_feature_spec_worker` → feature_spec Object + ValidationSession | `create_feature_spec_worker` + `gap_analysis_validator` | high | approved_automation |
| 12 | Implement a Feature with Traceability | Developer | `implement_code_worker` → source_file[] + `create_pr_worker` + `pr_design_validator` | `implement_code_worker` + `create_pr_worker` + `pr_design_validator` | high | approved_automation |
| 13 | Analyze Change Impact | Tech Lead / PM / Release Manager | `traceability_analysis` + `stale_artifact_detection` → impact report | `traceability_analysis` + `stale_artifact_detection` | medium | none |
| 14 | Review a Pull Request | Tech Lead / Reviewer | `pr_design_validator` + `security_impact_analysis` + `gap_analysis` → findings | `pr_design_validator` + `security_impact_analysis` + `gap_analysis` | medium | none |
| 15 | Reconstruct SDLC Artifacts from Code | Tech Lead / Architect | `reverse_engineer_worker` reading `code_retriever` output → SDLC Objects | `code_retriever` + `reverse_engineer_worker` | high | approved_automation |
| 16 | Full SDLC Pipeline End-to-End | PM, Architect, Developer | All Workers in PRD → ADR → DESIGN → DECOMPOSITION → FEATURE → CODE order | all SDLC Workers in sequence | high | approved_automation |
| 17 | Release Readiness Estimation | Release Manager / Tech Lead | `traceability_analysis` + `release_readiness_review` Flow → Approval gate | `traceability_analysis` + `release_readiness_review` Flow | medium | none |
| 18 | PR Status Monitoring | Team Lead / PM / Release Manager | Connector sync (GitHub) + status Analyzer Worker → status report | `traceability_analysis` + Connector GitHub sync | low | none |
| 19 | Traceability Coverage Gate in CI | Tech Lead / Developer / DevOps | `traceability_analysis` Analyzer + CI Connector → coverage gate | `traceability_analysis` + CI Connector | low | none |
| 20 | Cross-Workspace Traceability Navigation | Tech Lead / Architect | Workspace Object + `object_graph_retriever` scoped to workspace | `object_graph_retriever` + `traceability_analysis` | low | none |
| 21 | Interactive Kit Update | Developer / Tech Lead | Kit version check + WorkerInteraction (menu) per changed file | Kit version check + WorkerInteraction (menu) | low | approved_automation |
| 22 | Object Graph Navigation | Developer / Architect | `object_graph_retriever` + `traceability_analysis` before making a change | `object_graph_retriever` + `traceability_analysis` | low | none |

---

## Journeys

### Journey 1: Plan and Implement a Feature

```text
ALGORITHM PlanAndImplementFeature
  ACTOR: Developer
  GOAL: Deliver a working, reviewed, and write-back PR implementing a
        feature, with optional upfront exploration, design decomposition,
        and automatic design conformance validation
  INPUTS: [
    Feature intent described (natural language or task Object),
    feature_spec (optional; linked to task),
    design[] — for conformance check,
    repository [sync: github],
    workspace configured with approved Kit
  ]
  OUTPUTS: [
    decomposition + task[] (if planning phase executed),
    source_file[] — implementation with traceability markers,
    pull_request (state: review) [write-back: github],
    ValidationSession (pr_design_validator) + Evidence
  ]
  COST TIER: high (decompose_feature_worker llm + implement_code_worker llm
             + create_pr_worker hybrid)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. DECISION: Explore context first?
       YES (target area unclear):
         invoke object_graph_retriever (workspace scope):
           Input: feature intent as query
           Output: relevant Objects (design, feature_spec, component refs)
         WorkerRun created; state: pending → running → done
         Worker requests clarification:
           WorkerInteraction (kind: free_form_intent) created
           WorkerRun.state → awaiting_input
           Developer scopes intent → WorkerRun resumes
       NO (target known): skip to step 2.
    2. DECISION: Plan first?
       YES (feature spans multiple components or is ambiguous):
         invoke decompose_feature_worker (llm, on_demand):
           Input: feature intent, design[] (from graph/chain)
           Output: decomposition + task[]
           WorkerRun created; state: pending → running → done
         Worker requests clarification (scope/ordering):
           WorkerInteraction (kind: menu) created
           Developer selects ordering strategy (dependency/risk/value)
           WorkerRun resumes
         gap_analysis_validator fires (realtime):
           ValidationSession created
           On pass: Evidence attached to decomposition
           On fail (within maxRetries): WorkerInteraction for gap resolution
       NO (single-scope, feature_spec already exists): skip to step 3.
    3. DECISION: automationLevel dial?
       WorkerInteraction (kind: menu) at Flow start:
         Options: [recommended_automation, approved_automation, enterprise]
         Developer selects → FlowRun.automationLevel set for this run
    4. invoke implement_code_worker (llm, on_demand):
         Input: feature_spec or task, design[] (from Worker.inputBindings:
                source graph/chain)
         Output: source_file[] with traceability markers
         WorkerRun created; state: pending → running → done
         If clarification needed mid-run:
           WorkerInteraction (kind: input_request) created
           WorkerRun.state → awaiting_input
           Developer responds → WorkerRun resumes
    5. invoke create_pr_worker (hybrid, on_demand):
         Input: source_file[], branch
         Output: pull_request [write-back: github]
         pull_request.implementsRequirements populated from feature_spec IDs
         Connector write-back via [write-back: github]:
           Gate 2 check: WriteBackPolicy.requiresApproval
           If true: Approval Object created; developer/lead approves
           If approved: connector_outbound_sync_worker executes
    6. pr_design_validator fires automatically (realtime, onEvent: PR → review):
         ValidationSession created
         Input: pull_request, design[], acceptance_criteria[]
         On pass: Evidence attached to pull_request; PR ready for review
         On fail (within maxRetries): WorkerInteraction (kind: menu) with
           options per finding; developer amends source_file[]; loop repeats
         On fail (retries exhausted): Approval (kind: risk_acceptance) created
    7. DECISION: Cancel Worker at any step?
       YES: cancel(workerRunId, cascade: true) → WorkerRun.state: aborted
       NO: continue
  DECISION_POINTS:
    - ExploreFirst: skip (target known) / run object_graph_retriever (unclear)
    - PlanFirst: skip (single-scope) / run decompose_feature_worker (multi-step)
    - AutomationLevel: WorkerInteraction (kind: menu) at Flow start
    - WriteBackApproval: Gate 2 (github write-back) per Tenant policy
    - ConformanceResult: pass immediately / fail-and-fix loop / escalate
  GUARDS: [
    automationLevel >= approved_automation for implement_code_worker,
      create_pr_worker, and decompose_feature_worker,
    decomposition must be reviewed (WorkerInteraction resolved) before
      implement_code_worker is invoked on any derived task,
    pr_design_validator Evidence must be attached to pull_request before
      it can advance to state: approved,
    source_file traceability markers must reference IDs from feature_spec,
    Gate 2 (WriteBackPolicy) must be satisfied before github write-back
  ]
  NEXT: Journey 13 (change impact) or Journey 17 (release readiness)
        after PR is merged
```

---

### Journey 2: Onboard a Project to Studio v2

```text
ALGORITHM OnboardProjectToStudioV2
  ACTOR: Tech Lead or DevOps engineer
  GOAL: Bring an existing codebase under Studio v2 governance by installing
        a Kit, configuring Connectors, setting up Workspace, and declaring
        Tenant.approvedWorkerCategories
  INPUTS: [
    Existing source repository accessible on disk,
    User has write access to repository root and Studio Tenant admin rights,
    Optional: Kit Registry URL + Kit identifier to install
  ]
  OUTPUTS: [
    .bootstrap/ directory (cf-studio-path) populated with Studio config,
    Kit installed and validated,
    Connector(s) configured (GitHub, Jira, etc.),
    Workspace Object created with registered sources,
    Tenant.approvedWorkerCategories declared,
    automationLevel set (default: recommendations)
  ]
  COST TIER: low (script Workers + WorkerInteraction menu; no LLM Workers required)
  AUTOMATION GATE: approved_automation (Kit install + Connector setup write to graph)
  STEPS:
    1. Tech Lead initializes Studio v2 in the repository root.
       Studio creates the .bootstrap/ scaffold and reads any existing
       configuration fragments. WorkerRun created for init Worker.
    2. DECISION: Kit to install?
       WorkerInteraction (kind: menu) created:
         Options: [install from Kit Registry, install from local path,
                   install from GitHub ref, skip (configure manually)]
         Tech Lead selects → WorkerRun resumes
    3. Kit install Worker executes:
         Input: Kit Registry reference or local path
         Output: Kit installed; Worker[], Flow[], Connector[] templates available
         WorkerRun created; state: pending → running → done
         DECISION: Per-file conflicts?
           For each file that would be overwritten:
             WorkerInteraction (kind: menu) per file:
               Options: [accept upstream, keep existing, diff and decide]
           WorkerRun resumes after all per-file decisions resolved
    4. Kit validation Worker runs (script, realtime):
         Checks manifest schema, resolves all declared component references,
         confirms no dangling dependencies
         ValidationSession created
         On fail: WorkerInteraction (kind: input_request) for gap resolution
         On pass: Evidence attached to Kit install WorkerRun
    5. Connector setup per external system:
         For each system (GitHub, Jira, etc.) identified:
           WorkerInteraction (kind: menu) created:
             Options: [configure now, skip (configure later)]
           If configure now:
             connector_inbound_sync_worker template instantiated;
             FieldMappings declared; syncProtocol (push/pull) set;
             WriteBackPolicy.requiresApproval set per Tenant policy
    6. Workspace Object created:
         registered sources: [current repo + any cross-repo refs]
         object_graph_retriever scoped to workspace
         DECISION: Multi-repo workspace?
           YES: additional sources registered; cross-repo traceability enabled
           NO: single-repo workspace finalized
    7. Tenant.approvedWorkerCategories declared:
         WorkerInteraction (kind: menu):
           Options: [sdlc, coding, security, ops, all]
           Tech Lead selects approved categories
         automationLevel set (default: recommendations; raise via Journey 8
         once team is comfortable)
    8. Onboarding complete: all Workers in approved categories available;
       Connectors syncing; Workspace queries resolving.
  DECISION_POINTS:
    - KitSource: Registry / local path / GitHub ref / skip
    - PerFileConflict: accept upstream / keep existing / diff and decide
    - ConnectorSetup: configure now / skip per system
    - MultiRepoWorkspace: yes (add sources) / no (single repo)
    - ApprovedCategories: WorkerInteraction (kind: menu) selection
  GUARDS: [
    Kit validation (ValidationSession) must pass before any Kit Worker
      can be invoked in the project,
    Connector FieldMappings must not map external fields to Object.id
      or Object.tenantId,
    Tenant.approvedWorkerCategories must be non-empty before action Workers
      can execute,
    automationLevel defaults to recommendations; raising requires Journey 8,
    Per-file conflict WorkerInteractions must all resolve before Kit install
      WorkerRun reaches state: done
  ]
  NEXT: Project ready for day-to-day v2 journeys (1, 3, 7, 9, 12)
```

---

### Journey 3: Explore Design Options and Author an ADR

```text
ALGORITHM ExploreDesignOptionsAndAuthorADR
  ACTOR: Architect or Tech Lead
  GOAL: Explore design options via free-form WorkerInteraction, produce a
        structured decision summary, and author a persisted adr Object
        grounded in that exploration
  INPUTS: [
    ADR topic or decision question stated by the user,
    design[] (optional; for cross-reference),
    adr[] (optional; existing ADRs for context),
    workspace configured
  ]
  OUTPUTS: [
    adr Object (state: draft → approved) with decision, options, consequences,
    ValidationSession + Evidence (adr_structure_validator),
    WorkerRun audit trail
  ]
  COST TIER: medium (object_graph_retriever hybrid + create_adr_worker llm)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. Architect describes the ADR topic.
       WorkerInteraction (kind: free_form_intent) created:
         WorkerRun.state → awaiting_input
         Architect elaborates: decision drivers, constraints, alternatives,
         stakeholder concerns, any prior ADR context
         WorkerRun resumes with enriched intent
    2. invoke object_graph_retriever (workspace scope, hybrid, on_demand):
         Input: ADR topic query
         Output: relevant Objects — existing design[], adr[], component refs
         WorkerRun created; state: pending → running → done
       DECISION: Explore further?
         YES: WorkerInteraction (kind: free_form_intent) for additional scoping
              (e.g., add competing options, constrain scope)
         NO: proceed to step 3 with retrieved context
    3. invoke create_adr_worker (llm, on_demand):
         Input: ADR topic, retrieved context (design[], adr[]),
                free_form_intent output (from Worker.inputBindings: source user)
         Output: adr Object (state: draft) containing:
           Context and Problem Statement,
           Decision Drivers,
           Considered Options (≥ 2) with pros/cons,
           Decision Outcome with rationale,
           Consequences (positive, negative, neutral),
           Object ID assigned
         WorkerRun created; state: pending → running → done
         If clarification needed mid-run:
           WorkerInteraction (kind: input_request) created
           WorkerRun.state → awaiting_input
           Architect responds → WorkerRun resumes
    4. adr_structure_validator fires (realtime | on_demand):
         ValidationSession created
         On pass: Evidence attached to adr Object
         On fail (within maxRetries): WorkerInteraction (kind: menu) with
           options per structural gap; Architect resolves; validator retries
         On fail (retries exhausted): Approval (kind: risk_acceptance) created
    5. DECISION: adr acceptable?
       YES: adr.state → approved (StatePolicy transition; requires Evidence
            from adr_structure_validator)
       NO: Architect edits adr directly; re-runs create_adr_worker with
           amended intent; validator re-fires
    6. DECISION: Cross-reference in design Object?
       YES: object_graph_retriever locates parent design;
            Architect adds adr Object ref to design.architectureDrivers
       NO: adr remains standalone
  DECISION_POINTS:
    - ExploreDepth: single retrieval / additional free_form_intent rounds
    - AdrAcceptance: approve as-is / re-run with amendments
    - CrossReference: register in design / standalone
  GUARDS: [
    free_form_intent WorkerInteraction must resolve before create_adr_worker
      is invoked — intent must be explicit,
    adr Object must contain at least two considered options before
      ValidationSession can pass,
    adr_structure_validator Evidence must be attached before adr.state
      can advance to approved,
    adr Object ID must be unique within the Tenant namespace
  ]
  NEXT: Journey 9 (Author System Design referencing this ADR)
```

---

### Journey 4: Review and Fix Code via PR Validator

```text
ALGORITHM ReviewAndFixCodeViaPRValidator
  ACTOR: Developer or Reviewer
  GOAL: Systematically identify issues in a PR via pr_design_validator,
        obtain per-finding approval via WorkerInteraction, apply targeted
        fixes, and produce a clean PR with Evidence
  INPUTS: [
    pull_request (state: review) [sync: github],
    design[] — linked via pull_request.conformsToDesign refs,
    feature_spec or acceptance_criteria[] — from task/feature_spec,
    repository [sync: github]
  ]
  OUTPUTS: [
    ValidationSession (state: pass) + Evidence attached to pull_request,
    source_file[] — fixed implementation,
    pull_request (state: review, updated) [write-back: github],
    WorkerRun audit trail per fix applied
  ]
  COST TIER: high (pr_design_validator hybrid + implement_code_worker llm
             + create_pr_worker hybrid)
  AUTOMATION GATE: approved_automation (fix Workers); none (Validator only)
  STEPS:
    1. invoke object_graph_retriever scoped to PR target area (hybrid, on_demand):
         Input: pull_request + workspace
         Output: relevant design[], component[], feature_spec Objects
         WorkerRun created; state: pending → running → done
    2. pr_design_validator fires (realtime | on_demand):
         ValidationSession created
         Input: pull_request diff, design[], acceptance_criteria[]
         Output: ValidationResult with structured findings list
           (severity: critical | major | minor | info per finding)
         WorkerRun created; state: pending → running → done
    3. DECISION: Conformance result?
       PASS: Evidence attached to pull_request; proceed to step 6.
       FAIL: findings list surfaced; proceed to step 4.
    4. Per-finding WorkerInteraction (kind: menu) for each finding:
         WorkerRun.state → awaiting_input
         For each finding: Options: [fix, skip, accept risk]
           fix: finding queued for implement_code_worker
           skip: finding dismissed; reason recorded
           accept risk: Approval (kind: risk_acceptance) created
         WorkerRun resumes after all findings reviewed
    5. For each finding approved for fix:
         invoke implement_code_worker (llm, on_demand):
           Input: finding (location, description), source_file[], feature_spec
           Output: source_file[] (amended)
           WorkerRun created; state: pending → running → done
         invoke create_pr_worker (hybrid, on_demand) to update PR:
           Input: source_file[], existing pull_request branch
           Output: pull_request (updated) [write-back: github]
           Gate 2: WriteBackPolicy.requiresApproval checked
         pr_design_validator re-fires on updated PR (step 2 loop)
    6. All risk_acceptance Approvals resolved (approved or rejected):
         ValidationSession state → pass (all approved) | escalated (any rejected)
         Evidence attached to pull_request
    7. DECISION: Cancel any Worker mid-run?
       YES: cancel(workerRunId, cascade: true) → WorkerRun.state: aborted
       NO: continue
  DECISION_POINTS:
    - ConformanceResult: pass / fail (proceed to findings)
    - PerFindingDecision: fix / skip / accept risk (WorkerInteraction per finding)
    - WriteBackApproval: Gate 2 (github write-back) per Tenant policy
    - EscalationDecision: approve exception / reject PR
  GUARDS: [
    object_graph_retriever must complete before pr_design_validator fires,
    implement_code_worker may only touch locations referenced by approved
      findings — no out-of-scope edits,
    Each risk_acceptance Approval must be resolved before ValidationSession
      can close,
    pr_design_validator re-fires on every push to the PR branch; no skipping,
    Evidence is immutable once attached; revocation requires explicit
      revokedBy + revokedAt
  ]
  NEXT: Journey 17 (release readiness) after PR merged
```

---

### Journey 5: Create and Publish a Kit

```text
ALGORITHM CreateAndPublishKit
  ACTOR: Platform Engineer
  GOAL: Package reusable Studio v2 behaviors (Workers, Flows, Connectors,
        GTS types) into a validated Kit, publish to Kit Registry, and
        install in one or more consumer Tenants
  INPUTS: [
    Kit source directory with Worker definitions, Flow definitions,
    Connector templates, GTS type schemas, and rule files,
    Optional: existing .cf-studio-kit.toml for update scenario,
    Kit Registry credentials
  ]
  OUTPUTS: [
    Validated Kit artifact with .cf-studio-kit.toml manifest,
    Workers, Flows, Connectors, GTS types registered in Kit Registry,
    Consumer Tenant Kit install confirmed + ValidationSession Evidence
  ]
  COST TIER: low (script Workers + WorkerInteraction menu; manifest authoring)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. Platform Engineer invokes Kit manifest authoring Worker:
         Worker scans source directory; identifies all candidate:
           Worker definitions, Flow definitions, Connector templates,
           GTS type schemas, WorkerImplementation configs
         WorkerRun created; state: pending → running → done
    2. DECISION: Kit target path?
       WorkerInteraction (kind: menu) created:
         Options: [current directory, custom path]
         Platform Engineer selects → WorkerRun resumes
    3. Manifest proposal generated:
         Worker produces proposed .cf-studio-kit.toml listing all
         discovered components with metadata (name, version, dependencies,
         exposed entry points, GTS type IDs)
         WorkerInteraction (kind: menu):
           Options: [approve default, show preview, edit interactively,
                     rerun discovery, cancel]
         Platform Engineer selects → WorkerRun resumes
    4. DECISION: Edit manifest?
       YES (edit interactively): WorkerInteraction (kind: input_request)
           for each section; Platform Engineer adjusts components,
           versions, dependencies
       NO (approve default or show preview confirmed): proceed to step 5
    5. Kit validation Worker runs (script, realtime):
         Checks: manifest schema, all declared component references
         resolve, no dangling GTS type dependencies, Worker contracts
         reference only registered GTS types
         ValidationSession created
         On pass: Evidence attached to Kit manifest WorkerRun
         On fail: WorkerInteraction (kind: input_request) for gap resolution;
                  manifest edited; validation re-runs
    6. Kit publish to Registry:
         connector_outbound_sync_worker executes (write-back: Kit Registry)
         Gate 2: WriteBackPolicy.requiresApproval checked for registry write
         If approved: Kit registered with semantic version
    7. In consumer Tenant:
         Kit install Worker executes (Journey 2, step 3 pattern)
         Per-file conflict WorkerInteractions resolved
         Kit validation ValidationSession passes
         Tenant.approvedWorkerCategories updated to include Kit categories
  DECISION_POINTS:
    - KitTargetPath: current directory / custom path
    - ManifestApproval: approve / preview / edit / rerun discovery / cancel
    - RegistryWriteBackApproval: Gate 2 per Tenant policy
    - PerFileConflict: accept upstream / keep existing / diff and decide
  GUARDS: [
    Kit discovery must complete before manifest proposal is generated,
    Manifest must be approved (not cancelled) before Kit validation runs,
    Kit ValidationSession must pass (Evidence attached) before publish,
    Consumer Tenant Kit validation must pass before Workers from the Kit
      can be invoked,
    GTS type IDs in Kit must be unique within the Registry namespace
  ]
  NEXT: Consumer Tenant teams invoke Kit Workers in their journeys
```

---

### Journey 6: Generate Project Documentation

```text
ALGORITHM GenerateProjectDocumentation
  ACTOR: Technical Writer or Developer
  GOAL: Produce audience-tuned, reviewed, and validated project documentation
        grounded in an exploration of Objects in the Studio graph and source
  INPUTS: [
    Documentation scope defined (module, API, architecture, onboarding, etc.),
    design[] — for accuracy grounding,
    feature_spec[] — for API/behavior grounding,
    source_file[] [sync: github] (optional; for code-level accuracy),
    workspace configured
  ]
  OUTPUTS: [
    document Object (state: draft → approved) — documentation artifact,
    ValidationSession + Evidence (gap_analysis_validator),
    WorkerRun audit trail
  ]
  COST TIER: high (document_retriever hybrid + create_design_worker llm)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. invoke document_retriever (document_index, workspace scope, on_demand):
         Input: documentation scope as query
         Output: relevant Objects — design[], feature_spec[], existing docs,
                 architectural context for the target area
         WorkerRun created; state: pending → running → done
       DECISION: Scope clarification needed?
         YES: WorkerInteraction (kind: free_form_intent) created
              Writer elaborates: audience, narrator style, diagram preference
              WorkerRun resumes
         NO: proceed with retrieved context
    2. invoke code_retriever (code_index, workspace scope, on_demand):
         Input: scope query → source_file[] content for factual accuracy
         WorkerRun created; state: pending → running → done
    3. invoke create_design_worker (llm, on_demand) in documentation mode:
         Input: document_retriever output, code_retriever output,
                design[], feature_spec[]
                (from Worker.inputBindings: source graph/chain)
         Output: document Object (state: draft) with:
           Audience-tuned content (developer / PM / newcomer / mixed),
           Narrator style (first-person / third-person / neutral),
           Diagrams (Mermaid embedded / suggested / skipped),
           TOC, section structure
         WorkerRun created; state: pending → running → done
         If clarification needed mid-run:
           WorkerInteraction (kind: input_request) created
           WorkerRun.state → awaiting_input; Writer responds; resumes
    4. gap_analysis_validator fires (realtime):
         Checks: TOC consistency, required sections present, no broken
         cross-references, language complexity within audience target
         ValidationSession created
         On pass: Evidence attached to document Object
         On fail (within maxRetries): WorkerInteraction (kind: menu) with
           options per gap; Writer resolves; validator retries
         On fail (retries exhausted): Approval (kind: risk_acceptance) created
    5. DECISION: Document acceptable?
       YES: document.state → approved (StatePolicy; requires Evidence)
       NO: Writer edits document directly or re-runs create_design_worker
           with amended scope; gap_analysis_validator re-fires
  DECISION_POINTS:
    - ScopeClarity: proceed / WorkerInteraction free_form_intent
    - AudienceDimension: developer / PM / newcomer / mixed
    - NarratorDimension: first-person / third-person / neutral
    - DiagramDimension: auto-embed / suggest / skip
    - DocumentAcceptance: approve / re-run with amendments
  GUARDS: [
    document_retriever must complete before create_design_worker begins,
    gap_analysis_validator Evidence must be attached before document.state
      can advance to approved,
    Fix-loop must not alter factual content without re-running
      document_retriever if significant structural changes are made,
    Audience dimension must be resolved (WorkerInteraction) before authoring
  ]
  NEXT: Documentation Object available in graph; share or embed in design
```

---

### Journey 7: Author a PRD

```text
ALGORITHM AuthorPRD
  ACTOR: Product Manager
  GOAL: Produce a validated prd Object with requirements, actors, use
        cases, success criteria, and Object IDs that gate downstream
        SDLC artifact authoring
  INPUTS: [
    Product concept or problem description,
    Stakeholder context,
    design[] or feature_spec[] (optional; for grounding),
    Optional: prd [sync: jira/confluence] if imported via Connector
  ]
  OUTPUTS: [
    prd Object (state: draft → approved) with fr[], nfr[], use_case[],
      success_criteria[] sub-Objects each with unique IDs,
    ValidationSession + Evidence (gap_analysis_validator),
    WorkerRun audit trail
  ]
  COST TIER: high (create_prd_worker llm + gap_analysis_validator hybrid)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. PM describes the product or feature area.
       WorkerInteraction (kind: free_form_intent) created:
         WorkerRun.state → awaiting_input
         PM elaborates: actors, goals, key requirements, success conditions
         WorkerRun resumes
    2. DECISION: Import PRD from external system?
       YES (prd exists in Confluence/Jira):
         connector_inbound_sync_worker imports prd [sync: confluence/jira]
         prd Object created with externalRef populated
         Proceed to step 4 for gap validation
       NO: proceed to step 3
    3. invoke create_prd_worker (llm, on_demand):
         Input: free_form_intent output, optional design[], feature_spec[]
                (from Worker.inputBindings: source user/graph)
         Output: prd Object (state: draft) with sections:
           Overview, Actors, Goals,
           fr[] (Functional Requirements, each with unique Object ID,
                 RFC 2119 MUST/SHALL language),
           nfr[] (Non-Functional Requirements, each with unique Object ID),
           use_case[] (actor-goal-scenario triples referencing fr IDs),
           success_criteria[] (measurable acceptance conditions per fr)
         WorkerRun created; state: pending → running → done
         If clarification needed mid-run:
           WorkerInteraction (kind: input_request) created
           WorkerRun.state → awaiting_input; PM responds; resumes
    4. gap_analysis_validator fires (realtime):
         Checks: fr[] non-empty, all fr have success_criteria, nfr[] present,
         use_case[] reference valid fr IDs, no orphaned sub-Objects
         ValidationSession created
         On pass: Evidence attached to prd Object
         On fail (within maxRetries): WorkerInteraction (kind: menu) with
           options per gap; PM resolves; validator retries
         On fail (retries exhausted): Approval (kind: risk_acceptance) created
    5. DECISION: PRD acceptable?
       YES: prd.state → approved (StatePolicy; requires Evidence)
       NO: PM edits prd directly or re-runs create_prd_worker with amended
           intent; gap_analysis_validator re-fires
  DECISION_POINTS:
    - ImportVsAuthor: import via Connector / author with create_prd_worker
    - PRDAcceptance: approve / re-run with amendments
    - GapResolution: WorkerInteraction (kind: menu) per gap
  GUARDS: [
    create_prd_worker cannot be invoked without resolved free_form_intent,
    fr[] Object IDs must be unique within the Tenant namespace,
    All fr must use RFC 2119 MUST/SHALL/SHOULD language,
    gap_analysis_validator Evidence must be attached before prd.state → approved,
    Imported prd via Connector must still pass gap_analysis_validator
  ]
  NEXT: Journey 8 (Record ADR) or Journey 9 (Author System Design)
```

---

### Journey 8: Record an Architecture Decision

```text
ALGORITHM RecordArchitectureDecision
  ACTOR: Architect or Tech Lead
  GOAL: Capture a technology or design decision as an adr Object with
        context, options, consequences, and a unique ID that can be
        cross-referenced in the system design
  INPUTS: [
    Decision description,
    Considered alternatives,
    design Object (optional; for cross-reference),
    prd Object (optional; for requirement grounding)
  ]
  OUTPUTS: [
    adr Object (state: draft → approved) with unique ID, options,
      decision outcome, consequences,
    ValidationSession + Evidence (adr_structure_validator),
    adr ID registered in design.architectureDrivers (if design linked)
  ]
  COST TIER: medium (object_graph_retriever hybrid + create_adr_worker llm)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. invoke object_graph_retriever (workspace scope, hybrid, on_demand):
         Input: decision topic query
         Output: relevant Objects — related adr[], design[], component refs
         WorkerRun created; state: pending → running → done
    2. invoke create_adr_worker (llm, on_demand):
         Input: decision description, retrieved context
                (from Worker.inputBindings: source graph/chain/user)
         Output: adr Object (state: draft) with:
           Context and Problem Statement,
           Decision Drivers,
           Considered Options (≥ 2) with pros/cons per option,
           Decision Outcome with rationale,
           Consequences (positive, negative, neutral),
           unique Object ID assigned
         WorkerRun created; state: pending → running → done
         If clarification needed mid-run:
           WorkerInteraction (kind: input_request) created
           WorkerRun.state → awaiting_input; Architect responds; resumes
    3. adr_structure_validator fires (realtime | on_demand):
         ValidationSession created
         Checks: ≥ 2 options present, decision outcome non-empty,
         consequences section non-empty, Object ID assigned
         On pass: Evidence attached to adr Object
         On fail (within maxRetries): WorkerInteraction (kind: menu) per gap
         On fail (retries exhausted): Approval (kind: risk_acceptance) created
    4. DECISION: ADR acceptable?
       YES: adr.state → approved (StatePolicy; requires Evidence)
       NO: Architect edits adr; create_adr_worker re-runs; validator re-fires
    5. DECISION: Cross-reference in design?
       YES: object_graph_retriever locates parent design;
            adr Object ref added to design.architectureDrivers
       NO: adr remains standalone
  DECISION_POINTS:
    - ADRAcceptance: approve / re-run with amendments
    - CrossReference: register in design / standalone
  GUARDS: [
    adr Object must contain at least two considered options,
    Consequences section must be non-empty before ValidationSession passes,
    adr Object ID must be unique within the Tenant namespace,
    adr_structure_validator Evidence must be attached before adr.state → approved
  ]
  NEXT: Journey 9 (Author System Design referencing this ADR)
```

---

### Journey 9: Author a System Design

```text
ALGORITHM AuthorSystemDesign
  ACTOR: Architect or Tech Lead
  GOAL: Document system architecture covering components, interfaces,
        boundaries, principles, and constraints as a design Object,
        with IDs that downstream decomposition and implementation reference
  INPUTS: [
    prd Object (for fr[] and nfr[] to satisfy),
    adr[] (for architecture drivers),
    High-level architecture knowledge
  ]
  OUTPUTS: [
    design Object (state: draft → approved) with component[], principle[],
      constraint[], interface[] sub-Objects each with unique IDs,
    ValidationSession + Evidence (gap_analysis_validator)
  ]
  COST TIER: high (create_design_worker llm + gap_analysis_validator hybrid)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. invoke object_graph_retriever (workspace scope, hybrid, on_demand):
         Input: design scope query
         Output: relevant Objects — prd, adr[], existing design refs
         WorkerRun created; state: pending → running → done
    2. invoke create_design_worker (llm, on_demand):
         Input: prd, adr[] (from Worker.inputBindings: source graph/chain)
         Output: design Object (state: draft) with sections:
           Architecture Vision — purpose, scope, quality attributes,
           Architecture Drivers — links to adr Object IDs and prd nfr IDs,
           principle[] (each with unique Object ID),
           constraint[] (each with unique Object ID),
           component[] (each with unique Object ID; responsibilities, boundaries),
           interface[] — contracts between components (input/output schemas,
             protocols, error semantics)
         WorkerRun created; state: pending → running → done
         If clarification needed mid-run:
           WorkerInteraction (kind: input_request) created
           WorkerRun.state → awaiting_input; Architect responds; resumes
    3. DECISION: Include sequence diagrams?
       YES: create_design_worker generates Mermaid diagrams for key
            interaction flows and embeds inline in design Object
       NO: diagram placeholders inserted; Architect authors separately
    4. gap_analysis_validator fires (realtime):
         Checks: all prd fr[] referenced in component[] or interface[],
         all major technology choices linked to adr Object IDs,
         component[] IDs unique, principle[] and constraint[] non-empty
         ValidationSession created
         On pass: Evidence attached to design Object
         On fail (within maxRetries): WorkerInteraction (kind: menu) per gap
         On fail (retries exhausted): Approval (kind: risk_acceptance) created
    5. DECISION: Design acceptable?
       YES: design.state → approved (StatePolicy; requires Evidence)
       NO: Architect edits design; create_design_worker re-runs with
           amended context; gap_analysis_validator re-fires
  DECISION_POINTS:
    - SequenceDiagrams: auto-embed Mermaid / placeholders
    - DesignAcceptance: approve / re-run with amendments
  GUARDS: [
    prd Object must be in state: approved before create_design_worker runs,
    All component[] Object IDs must be unique within the Tenant namespace,
    design must reference existing adr Object IDs for every major
      technology choice,
    gap_analysis_validator Evidence must be attached before design.state → approved
  ]
  NEXT: Journey 10 (Decompose Design into Tasks)
```

---

### Journey 10: Decompose Design into Tasks

```text
ALGORITHM DecomposeDesignIntoTasks
  ACTOR: Tech Lead or PM
  GOAL: Break a design Object into an ordered, dependency-linked
        decomposition + task[] with full prd and design coverage, and
        write task[] back to Jira
  INPUTS: [
    design Object (state: approved),
    prd Object (for fr[] coverage links),
    workspace [sync: jira] configured
  ]
  OUTPUTS: [
    decomposition Object — ordered feature list with dependency graph,
    task[] (state: planned) [write-back: jira] — each with unique Object ID,
      dependency links, coverage links to prd fr[] and design component[],
      Definition of Done,
    ValidationSession + Evidence (gap_analysis_validator)
  ]
  COST TIER: high (decompose_feature_worker llm + gap_analysis_validator hybrid)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. invoke decompose_feature_worker (llm, on_demand):
         Input: design, prd (from Worker.inputBindings: source graph/chain)
         Output: decomposition Object + task[] (state: planned)
           Each task entry:
             unique Object ID,
             one-paragraph description of scope and boundaries,
             dependency links to other task Object IDs,
             coverage links to prd fr[] IDs and design component[] IDs,
             initial status: planned,
             measurable Definition of Done
         WorkerRun created; state: pending → running → done
         Worker requests ordering clarification:
           WorkerInteraction (kind: menu) created
             Options: [dependency order, risk-first, value-first]
           WorkerRun resumes after selection
    2. gap_analysis_validator fires (realtime):
         Checks: every task references ≥ 1 prd fr[], dependency graph
         acyclic, all tasks have non-empty Definition of Done,
         design component[] coverage ≥ threshold
         ValidationSession created
         On pass: Evidence attached to decomposition Object
         On fail (within maxRetries): WorkerInteraction (kind: menu) per gap
         On fail (retries exhausted): Approval (kind: risk_acceptance) created
    3. DECISION: Review tasks before write-back?
       YES: Tech Lead reviews task[] in Studio; edits names, priorities,
            owners via WorkerInteraction (kind: input_request)
       NO: proceed directly to step 4
    4. Connector write-back via [write-back: jira]:
         connector_outbound_sync_worker writes task[] to Jira
         Gate 2 check: WriteBackPolicy.requiresApproval
         If true: Approval Object created; PM/Lead approves
         If approved: write-back executes; task[].externalRef populated
  DECISION_POINTS:
    - OrderingStrategy: dependency order / risk-first / value-first
    - TaskReviewBeforeWriteBack: review first / write-back immediately
    - WriteBackApproval: Gate 2 (jira write-back) per Tenant policy
  GUARDS: [
    design Object must be in state: approved before decompose_feature_worker runs,
    Every task must reference at least one prd fr[] Object ID,
    Dependency graph must have no cycles,
    All tasks must have a non-empty Definition of Done,
    gap_analysis_validator Evidence must be attached before decomposition
      is considered complete,
    Gate 2 (WriteBackPolicy) must be satisfied before jira write-back
  ]
  NEXT: Journey 11 (Author Feature Specification) per task entry
```

---

### Journey 11: Author a Feature Specification

```text
ALGORITHM AuthorFeatureSpecification
  ACTOR: Tech Lead or Developer
  GOAL: Write a precise, implementable feature_spec Object with CDSL flows,
        algorithms, state diagrams, and test scenarios that developers can
        implement with full traceability
  INPUTS: [
    task Object (from decomposition; with unique ID and description),
    design Object (for interface contracts),
    prd Object (for acceptance criteria)
  ]
  OUTPUTS: [
    feature_spec Object (state: draft → approved) with flow[], algo[],
      state_diagram[] sub-Objects (each with unique ID) and test_scenario[],
    ValidationSession + Evidence (gap_analysis_validator)
  ]
  COST TIER: high (create_feature_spec_worker llm + gap_analysis_validator hybrid)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. invoke object_graph_retriever (workspace scope, hybrid, on_demand):
         Input: task Object ID + scope query
         Output: relevant Objects — design interface contracts, prd fr[],
                 related feature_spec[] for consistency
         WorkerRun created; state: pending → running → done
    2. invoke create_feature_spec_worker (llm, on_demand):
         Input: task, design, prd
                (from Worker.inputBindings: source graph/chain)
         Output: feature_spec Object (state: draft) with sections:
           Overview — feature purpose, scope, link to task,
           flow[] — each with unique Object ID; GIVEN/WHEN/THEN scenarios
             covering nominal path and primary alternates,
           algo[] — each with unique Object ID; pseudocode or ALGORITHM block,
           test_scenario[] — ≥ 1 happy-path + ≥ 1 error/edge-case per flow,
           Definition of Done — measurable, checkable criteria from prd
         WorkerRun created; state: pending → running → done
         If clarification needed mid-run:
           WorkerInteraction (kind: input_request) created
           WorkerRun.state → awaiting_input; Developer responds; resumes
    3. DECISION: Include state diagrams?
       YES: create_feature_spec_worker generates Mermaid state diagrams
            for stateful entities; each state assigned unique Object ID
       NO: state_diagram section omitted
    4. gap_analysis_validator fires (realtime):
         Checks: flow[] Object IDs unique, test_scenario[] cover ≥ 1 happy
         + ≥ 1 error case per flow, Definition of Done measurable,
         prd acceptance criteria addressed
         ValidationSession created
         On pass: Evidence attached to feature_spec Object
         On fail (within maxRetries): WorkerInteraction (kind: menu) per gap
         On fail (retries exhausted): Approval (kind: risk_acceptance) created
    5. DECISION: Feature spec acceptable?
       YES: feature_spec.state → approved (StatePolicy; requires Evidence)
       NO: Developer edits feature_spec; create_feature_spec_worker re-runs;
           gap_analysis_validator re-fires
  DECISION_POINTS:
    - StateDiagrams: include Mermaid state diagrams / omit
    - SpecAcceptance: approve / re-run with amendments
  GUARDS: [
    task Object must exist and be linked to decomposition before
      create_feature_spec_worker runs,
    All flow[] Object IDs must be unique within the Tenant namespace,
    test_scenario[] must cover ≥ 1 happy-path and ≥ 1 error case per flow,
    Definition of Done must be measurable and checkable,
    gap_analysis_validator Evidence must be attached before feature_spec.state
      → approved
  ]
  NEXT: Journey 12 (Implement a Feature with Traceability)
```

---

### Journey 12: Implement a Feature with Traceability

```text
ALGORITHM ImplementFeatureWithTraceability
  ACTOR: Developer
  GOAL: Write production code implementing a feature_spec Object, with
        traceability markers linking every code unit back to feature_spec
        flow[] and algo[] IDs, produce a PR, and pass design conformance
  INPUTS: [
    feature_spec Object (state: approved; with flow[] and algo[] IDs),
    design[] — for conformance check,
    repository [sync: github]
  ]
  OUTPUTS: [
    source_file[] — implementation with traceability markers,
    pull_request (state: review) [write-back: github] with
      conformsToDesign[] and implementsRequirements[],
    ValidationSession (pr_design_validator) + Evidence,
    WorkerRun audit trail
  ]
  COST TIER: high (implement_code_worker llm + create_pr_worker hybrid)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. invoke object_graph_retriever (workspace scope, hybrid, on_demand):
         Input: feature_spec Object ID + codebase scope
         Output: relevant source_file[], component[], interface[] Objects
         WorkerRun created; state: pending → running → done
    2. DECISION: Write tests first?
       YES (test-first): WorkerInteraction (kind: menu):
         Developer (or Worker) writes failing tests per flow[] test_scenario[]
         before implementation code; WorkerRun resumes
       NO: implementation code written first; tests added in same WorkerRun
    3. invoke implement_code_worker (llm, on_demand):
         Input: feature_spec, task, code_retriever context
                (from Worker.inputBindings: source graph/chain)
         Output: source_file[] with traceability markers:
           Every function/class/block satisfying a flow[] or algo[] Object ID
           carries a marker referencing that Object ID
         WorkerRun created; state: pending → running → done
         If clarification needed mid-run:
           WorkerInteraction (kind: input_request) created
           WorkerRun.state → awaiting_input; Developer responds; resumes
    4. stale_artifact_detection Analyzer fires (realtime):
         Checks traceability markers reference IDs in current feature_spec
         (not stale/renamed IDs)
         On fail: WorkerInteraction to resolve stale references
    5. invoke create_pr_worker (hybrid, on_demand):
         Input: source_file[], branch
         Output: pull_request [write-back: github]
         pull_request.implementsRequirements = [feature_spec flow[] IDs]
         pull_request.closesIssues = [task Object]
         Gate 2: WriteBackPolicy.requiresApproval checked for github write-back
    6. pr_design_validator fires automatically (realtime, onEvent: PR → review):
         ValidationSession created
         On pass: Evidence attached to pull_request; PR ready for review
         On fail (within maxRetries): WorkerInteraction (kind: menu) per
           finding; Developer amends source_file[]; create_pr_worker re-runs;
           pr_design_validator re-fires
         On fail (retries exhausted): Approval (kind: risk_acceptance) created
  DECISION_POINTS:
    - TestFirstPath: yes (test-first) / no (implementation-first)
    - StaleMarkerResolution: WorkerInteraction per stale reference
    - WriteBackApproval: Gate 2 (github write-back) per Tenant policy
    - ConformanceResult: pass / fail-and-fix loop / escalate
  GUARDS: [
    feature_spec must be in state: approved before implement_code_worker runs,
    Traceability markers in source_file[] must reference IDs from the
      source feature_spec — no orphaned or invented IDs,
    stale_artifact_detection must pass (or be acknowledged) before PR creation,
    pr_design_validator Evidence must be attached before pull_request can
      advance to state: approved,
    Gate 2 (WriteBackPolicy) must be satisfied before github write-back
  ]
  NEXT: Journey 13 (Change Impact) or Journey 17 (Release Readiness)
```

---

### Journey 13: Analyze Change Impact

```text
ALGORITHM AnalyzeChangeImpact
  ACTOR: Tech Lead, PM, or Release Manager
  GOAL: Understand which downstream Objects and traceability markers are
        affected by a change to an upstream artifact, and surface stale
        or uncovered dependencies before they reach production
  INPUTS: [
    Changed Object ID (e.g., prd fr[] ID),
    Baseline Object state (prior version or snapshot),
    Current Object state (HEAD)
  ]
  OUTPUTS: [
    Impact report WorkerRun output: cascade tree of affected Objects,
    Recommendation[] (state: pending) — one per stale or uncovered Object,
    stale_artifact_detection findings — Objects not updated within threshold
  ]
  COST TIER: medium (traceability_analysis hybrid + stale_artifact_detection script)
  AUTOMATION GATE: none (Analyzer Workers; read-only)
  STEPS:
    1. traceability_analysis Analyzer Worker runs (hybrid, on_demand):
         Input: changed Object ID + workspace scope
         Maps: prd → design → decomposition → feature_spec → source_file[]
               pull_request chains
         Identifies: all downstream Objects referencing the changed ID
         Creates Recommendation per broken or unresolved downstream link
         WorkerRun created; state: pending → running → done
    2. stale_artifact_detection Analyzer Worker runs (script, realtime):
         Input: downstream Object set identified in step 1
         Checks: Objects not updated within Tenant staleness threshold
           since the upstream Object changed
         Creates Recommendation (severity: warning | critical) per stale Object
         WorkerRun created; state: pending → running → done
    3. DECISION: Analysis mode?
       CASCADE-TRACKING: report cascade tree and Recommendations only
       RELEASE-READINESS: additionally produce version bump recommendation
         (patch/minor/major) based on breadth and depth of impact
         (connects to Journey 17)
    4. User reviews Recommendation[] in Studio UI:
         severity: info | warning | critical
         DECISION: Per Recommendation action?
           ACCEPT: user triggers downstream artifact update Workers
           DISMISS: Recommendation dismissed with reason
           SNOOZE: re-check scheduled
    5. Impact report WorkerRun output aggregated:
         cascade tree, stale Object list, coverage gaps, optional
         version bump recommendation
  DECISION_POINTS:
    - AnalysisMode: cascade-tracking / release-readiness-estimation
    - PerRecommendationAction: accept / dismiss / snooze
  GUARDS: [
    Read-only operation — traceability_analysis and stale_artifact_detection
      never modify Objects,
    Recommendations created only if gap/staleness persists after re-check;
      stale Recommendations invalidated when gap closes,
    confidence: partial allowed when Connector is unavailable (Analyzers
      continue with available graph data)
  ]
  NEXT: Update affected downstream Objects, or Journey 14 (Review PR)
```

---

### Journey 14: Review a Pull Request

```text
ALGORITHM ReviewPullRequest
  ACTOR: Tech Lead, Reviewer, or Team Lead
  GOAL: Obtain a structured review of a GitHub PR against code quality,
        design, adr, and prd standards, with severity-rated findings
        persisted as ValidationSession + Evidence
  INPUTS: [
    pull_request (state: review) [sync: github],
    design[] — linked via pull_request.conformsToDesign refs,
    adr[] — for architecture decision consistency,
    prd fr[] — for requirements traceability,
    feature_spec[] — for acceptance criteria
  ]
  OUTPUTS: [
    ValidationSession (pr_design_validator) — findings grouped by domain,
    Evidence attached to pull_request (on pass),
    Recommendation[] (state: pending) — per non-critical finding,
    security_impact_analysis report (WorkerRun output)
  ]
  COST TIER: medium (pr_design_validator hybrid + security_impact_analysis hybrid)
  AUTOMATION GATE: none (Validators and Analyzers run at any automationLevel)
  STEPS:
    1. pr_design_validator fires automatically (realtime, onEvent: PR → review)
       or is invoked on_demand:
         ValidationSession created
         Input: pull_request diff, design[], acceptance_criteria[]
         Checks (per domain):
           Code — correctness, style, patterns per codebase rules,
           Design — consistency with design component[] and interface[],
           ADR — implementation consistent with adr decision outcomes;
                  no silent overrides,
           PRD — changed behavior traceable to prd fr[]; no scope creep
         Output: ValidationResult with findings rated:
           critical (blocks merge) / major (should fix before merge) /
           minor (can fix post-merge) / info (observation only)
         WorkerRun created; state: pending → running → done
    2. security_impact_analysis Analyzer runs (hybrid, on_demand | scheduled):
         Input: pull_request[], vulnerability[], security_finding[]
         Output: Recommendation[] per security finding in PR scope
         WorkerRun created; state: pending → running → done
    3. gap_analysis Analyzer runs (hybrid, on_demand):
         Input: pull_request, prd fr[], feature_spec[]
         Checks: changed behavior traceable to requirements
         Creates Recommendation per coverage gap
         WorkerRun created; state: pending → running → done
    4. Tech Lead reviews ValidationResult + Recommendation[] in Studio UI
       (or via GitHub comment from Connector write-back if configured).
    5. DECISION: Conformance outcome?
       PASS: Evidence attached to pull_request; pull_request can advance
       FAIL (within maxRetries): Developer notified; pushes fix;
         pr_design_validator re-fires
       FAIL (retries exhausted): Approval (kind: risk_acceptance) created;
         Tech Lead approves exception or rejects PR
    6. DECISION: Single PR or all open PRs?
       SINGLE: process as above
       ALL: traceability_analysis Analyzer scans all open pull_request[]
            [sync: github]; produces per-PR ValidationSession summary
  DECISION_POINTS:
    - ReviewScope: single PR / all open PRs
    - ConformanceOutcome: pass / fail-and-retry / escalate
    - EscalationDecision: approve exception / reject PR
  GUARDS: [
    Read-only validation — Validators never modify source_file[] or design[],
    PR diff always re-fetched from GitHub Connector; no cached data reused,
    Evidence is immutable once attached to pull_request,
    security_impact_analysis Recommendation[] must be reviewed before
      ValidationSession can close
  ]
  NEXT: Journey 13 (change impact) or address findings in a fix branch
```

---

### Journey 15: Reconstruct SDLC Artifacts from Code

```text
ALGORITHM ReconstructSDLCArtifactsFromCode
  ACTOR: Tech Lead or Architect (working with legacy or undocumented code)
  GOAL: Reconstruct missing prd, design, decomposition, and feature_spec
        Objects from existing code using code_retriever output as primary
        evidence, flagging gaps where evidence is insufficient
  INPUTS: [
    Code scope (directory or file list) [sync: github],
    Existing traceability markers in code (optional),
    workspace configured
  ]
  OUTPUTS: [
    Reconstructed SDLC Objects (prd | design | decomposition | feature_spec)
      grounded in actual code behavior,
    gap_marker annotations in Objects where code evidence is missing or
      ambiguous,
    ValidationSession + Evidence per reconstructed Object
  ]
  COST TIER: high (code_retriever hybrid + reverse_engineer_worker llm chain)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. invoke code_retriever (code_index, workspace scope, on_demand):
         Input: code scope query
         Output: source_file[] content, function signatures, test cases,
                 module boundaries, existing traceability markers
         WorkerRun created; state: pending → running → done
    2. DECISION: Marker strategy?
       WorkerInteraction (kind: menu) created:
         Options: [marker-first (extract existing traceability markers as
                   artifact skeleton), pattern-inference (infer from code
                   structure — module names, function names, test names)]
         Architect selects → WorkerRun resumes
    3. DECISION: Target artifact kinds?
       WorkerInteraction (kind: menu) created:
         Options: [feature_spec only (default), full pipeline (prd + design
                   + decomposition + feature_spec in order)]
         Architect selects → WorkerRun resumes
    4. Flow X activates (entryConstraints: code_retriever output, marker
       strategy, target kinds):
         FlowRun created
         mandatorySteps executed in sequence per target kind:
    5. invoke reverse_engineer_worker (llm, on_demand) per target Object kind:
         Input: code_retriever output (source_file[], markers, test cases)
                (from Worker.inputBindings: source chain)
         Output: reconstructed Object (state: draft) with:
           Content grounded in code evidence (marker locations, function
           signatures, test cases, module interfaces),
           gap_marker annotations where code evidence is absent or ambiguous
             (description of what is missing and why it could not be inferred)
         WorkerRun created; state: pending → running → done
         If clarification needed mid-run:
           WorkerInteraction (kind: input_request) created
           WorkerRun.state → awaiting_input; Architect responds; resumes
    6. gap_analysis_validator fires per reconstructed Object (realtime):
         ValidationSession created
         On pass: Evidence attached to Object
         On fail (within maxRetries): WorkerInteraction (kind: menu) per gap
         On fail (retries exhausted): Approval (kind: risk_acceptance) created
    7. DECISION: Object acceptable?
       YES: Object.state → approved (StatePolicy; requires Evidence)
       NO: Architect edits Object; reverse_engineer_worker re-runs for
           that kind; gap_analysis_validator re-fires
    8. Repeat steps 5–7 for each target artifact kind in pipeline order.
  DECISION_POINTS:
    - MarkerStrategy: marker-first / pattern-inference
    - TargetArtifactKinds: feature_spec only / full pipeline
    - PerObjectAcceptance: approve / re-run with amendments
  GUARDS: [
    Every reconstructed requirement or flow must be grounded in actual
      code behavior observable in the code scope,
    Discrepancies between inferred spec and actual code must be flagged
      as gap_marker annotations — never silently omitted,
    gap_analysis_validator Evidence must be attached before Object.state
      → approved,
    reverse_engineer_worker must never delete or overwrite existing approved
      SDLC Objects without explicit WorkerInteraction confirmation
  ]
  NEXT: Journey 13 (change impact) or Journey 12 (implement missing features)
```

---

### Journey 16: Full SDLC Pipeline End-to-End

```text
ALGORITHM FullSDLCPipelineEndToEnd
  ACTOR: Product Manager, Architect, Developer (team)
  GOAL: Deliver a fully traced feature from product requirement to
        production code, with every Object linked by IDs and validated
        at each stage via ValidationSession + Evidence
  INPUTS: [
    Product idea or problem statement,
    Studio v2 initialized with SDLC Kit and Connectors (Journey 2),
    repository [sync: github], workspace [sync: jira]
  ]
  OUTPUTS: [
    prd + adr[] + design + decomposition + feature_spec[] + source_file[]
      — all Objects with unique IDs and traceability links,
    pull_request[] [write-back: github] — all passing pr_design_validator,
    ValidationSession[] + Evidence — one per Object at each stage,
    task[] [write-back: jira] — with traceability to prd fr[]
  ]
  COST TIER: high (full chain of LLM + hybrid Workers)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. PM invokes create_prd_worker (Journey 7):
         prd Object (state: approved) — fr[], nfr[], use_case[],
         success_criteria[] each with unique IDs;
         gap_analysis_validator Evidence attached.
    2. Architect invokes create_adr_worker for each major technology decision
       (Journey 8):
         adr[] Objects (state: approved) — options, decision outcome,
         consequences; adr_structure_validator Evidence attached;
         adr IDs registered in design.architectureDrivers.
    3. Architect invokes create_design_worker (Journey 9):
         design Object (state: approved) — component[], principle[],
         constraint[], interface[] each with unique IDs;
         gap_analysis_validator Evidence attached; prd fr[] and adr[]
         coverage confirmed.
    4. Tech Lead invokes decompose_feature_worker (Journey 10):
         decomposition Object + task[] (state: planned) — each task with
         unique ID, dependency links, prd fr[] coverage links;
         gap_analysis_validator Evidence attached;
         task[] [write-back: jira] via Gate 2.
    5. For each task: Developer invokes create_feature_spec_worker
       (Journey 11):
         feature_spec Object (state: approved) — flow[], algo[], state_diagram[],
         test_scenario[] each with unique IDs;
         gap_analysis_validator Evidence attached.
    6. Developer invokes implement_code_worker + create_pr_worker +
       pr_design_validator (Journey 12):
         source_file[] with traceability markers referencing feature_spec IDs;
         pull_request [write-back: github];
         pr_design_validator ValidationSession + Evidence attached to PR;
         Gate 2 satisfied for github write-back.
    7. traceability_analysis Analyzer runs (Journey 13):
         Confirms all prd → design → decomposition → feature_spec →
         source_file chains intact; Recommendation[] created for any gaps.
    8. pr_design_validator has already run on each PR (step 6);
       Tech Lead reviews ValidationResult summary per PR.
  DECISION_POINTS:
    - ADRCount: one create_adr_worker invocation per major decision
    - FeatureGranularity: adjust decompose_feature_worker task granularity
      via WorkerInteraction (kind: menu) ordering selection
    - TestFirst: write feature_spec test_scenario[] before implementation?
      (Journey 12 step 2)
  GUARDS: [
    Every feature_spec references its parent task Object ID,
    Every traceability marker in source_file[] traces to a flow[] Object ID
      in a feature_spec,
    gap_analysis_validator Evidence attached at every artifact stage before
      Object.state → approved,
    pr_design_validator Evidence attached to each pull_request before
      state: approved,
    Gate 2 (WriteBackPolicy) satisfied for jira and github write-backs
  ]
  NEXT: Journey 13 (change impact for future changes),
        Journey 18 (PR status monitoring)
```

---

### Journey 17: Release Readiness Estimation

```text
ALGORITHM ReleaseReadinessEstimation
  ACTOR: Release Manager, Tech Lead
  GOAL: Before a release, assess downstream impact of all artifact changes,
        gate on automated validators, produce a version bump recommendation,
        and obtain Tech Lead Approval
  INPUTS: [
    release Object (state: candidate),
    release_component[] — component versions in this release,
    pull_request[] [sync: github] — merged PRs for this release,
    Changed upstream Object ID(s),
    Baseline Object state (prior release tag)
  ]
  OUTPUTS: [
    release Object (state: approved | blocked),
    ValidationSession[] + Evidence — per mandatory Validator,
    Approval (kind: release_approval) — Tech Lead sign-off,
    Impact report (traceability_analysis WorkerRun output):
      cascade tree, stale Object list, coverage gaps,
      version bump recommendation (patch | minor | major)
  ]
  COST TIER: medium (traceability_analysis hybrid + release_readiness_review Flow)
  AUTOMATION GATE: none (Validators run at any automationLevel;
                   Approval is StatePolicy gate)
  STEPS:
    1. Release Manager creates release Object (state: candidate).
       Flow: release_readiness_review activates (entryConstraints: release,
       state: candidate).
       FlowRun created; mandatorySteps executed in sequence.
    2. traceability_analysis Analyzer Worker runs (hybrid, on_demand):
         Input: changed Object IDs + workspace scope
         Maps full cascade: prd → design → decomposition → feature_spec
           → source_file[] → pull_request[] chains
         Identifies stale Objects (stale_artifact_detection co-runs)
         Creates Recommendation per gap or stale Object
         WorkerRun created; state: pending → running → done
         FlowRun.completedSteps updated
    3. gap_analysis_validator (hybrid, realtime) — mandatoryStep:
         Checks all prd fr[] in release scope are implemented + tested
         ValidationSession created
         On pass: Evidence attached to release Object
         On fail: release blocked with gap list; PM/Dev must close gaps;
                  gap_analysis_validator re-runs
    4. DECISION: Version bump recommendation:
         traceability_analysis output determines:
           breaking changes → major
           new behavior (new fr[] or component[]) → minor
           fix only (no new IDs) → patch
         WorkerInteraction (kind: menu) for Release Manager to confirm
           or override the recommendation
    5. All mandatory Validators pass → Approval (kind: release_approval) created:
         requiredRole: tech_lead
         payload: { release Object, Evidence[] from all validators,
                    version bump recommendation, cascade tree summary }
    6. DECISION: Tech Lead Approval?
       APPROVE: release.state → approved
       REQUEST CHANGES: gaps identified; release.state remains: candidate
       REJECT: release.state → blocked
  DECISION_POINTS:
    - ValidatorFailureResolution: fix gaps / add tests / create security exception
    - VersionBumpConfirmation: WorkerInteraction (kind: menu) to confirm/override
    - TechLeadApprovalDecision: approve / request changes / reject
  GUARDS: [
    All mandatory Validators must reach ValidationSession.state: pass
      before Approval is created,
    Read-only analysis — traceability_analysis never modifies Objects,
    Approval is mandatory for release.state → approved; no bypass,
    Evidence from each Validator is immutable and attached to release
      audit trail
  ]
  NEXT: Journey 12 if gaps found (implement missing features),
        external deploy pipeline after release.state: approved
```

---

### Journey 18: PR Status Monitoring

```text
ALGORITHM PRStatusMonitoring
  ACTOR: Team Lead, PM, Release Manager
  GOAL: Get a current status snapshot of one or all open GitHub PRs —
        CI state, open findings from Validators, severity of unresolved
        feedback, resolved-finding audit
  INPUTS: [
    pull_request[] (state: review) [sync: github],
    ValidationSession[] — associated with each pull_request,
    workspace [sync: github] configured
  ]
  OUTPUTS: [
    Status report (traceability_analysis WorkerRun output) per PR:
      CI sync state, open Recommendation count, ValidationSession.state,
      severity assessment (critical / major / minor / info),
      resolved-finding audit
  ]
  COST TIER: low (connector_inbound_sync_worker script + traceability_analysis)
  AUTOMATION GATE: none (read-only Analyzer Workers)
  STEPS:
    1. connector_inbound_sync_worker syncs pull_request[] from GitHub
       [sync: github] (push webhook or scheduled pull):
         pull_request Objects updated with current CI state, comment counts,
         review decisions; externalRef.lastSyncedAt updated
         WorkerRun created; state: pending → running → done
    2. traceability_analysis Analyzer Worker runs (hybrid, on_demand):
         Input: pull_request[] + associated ValidationSession[] + design[]
         Checks: which PRs have passing Evidence, which have open findings,
                 which have unresolved Recommendations, CI check states
         Creates Recommendation per PR with stale or failing ValidationSession
         WorkerRun created; state: pending → running → done
    3. Resolved-finding audit:
         Analyzer checks: any ValidationSession finding marked resolved
         without a corresponding source_file[] update in the PR
         Creates Recommendation (severity: warning) per suspicious resolution
    4. DECISION: Single PR or all open PRs?
       SINGLE: Analyzer scoped to one pull_request Object
       ALL: Analyzer scans all pull_request[] with state: review
    5. Team Lead reviews status report:
         per-PR: CI state, ValidationSession.state, open Recommendation count,
         severity of unresolved findings, suspicious resolutions flagged
         DECISION: Action per PR?
           MERGE: PR passes all gates; merge decision made externally
           REQUEST CHANGES: findings need resolution; developer notified
           ESCALATE: critical findings unresolved; Approval escalation created
  DECISION_POINTS:
    - ReviewScope: single PR / all open PRs
    - ResolvedFindingAudit: surface all / only suspicious resolutions
    - PerPRAction: merge / request changes / escalate
  GUARDS: [
    Always re-synced from GitHub Connector fresh — no cached data reused,
    Read-only — no Object modifications during this journey,
    Recommendations created only for persistent gaps; auto-invalidated when
      gap closes
  ]
  NEXT: Journey 14 (deeper PR review) or Journey 4 (review-and-fix)
```

---

### Journey 19: Traceability Coverage Gate in CI

```text
ALGORITHM TraceabilityCoverageGateInCI
  ACTOR: Tech Lead, Developer, DevOps
  GOAL: Enforce a minimum traceability coverage threshold as a CI quality
        gate — fail the pipeline if Object ID coverage or marker depth
        drops below the configured floor
  INPUTS: [
    source_file[] [sync: github] — codebase with traceability markers,
    feature_spec[] — for required Object IDs,
    Configured min-coverage and min-granularity thresholds in Kit config,
    CI Connector configured (github_actions or jenkins)
  ]
  OUTPUTS: [
    ValidationSession (traceability_coverage_validator):
      exit: PASS (0) or FAIL (non-zero),
    Coverage report WorkerRun output:
      per-file coverage %, aggregate coverage %, granularity score,
    Recommendation[] per uncovered feature_spec Object ID
  ]
  COST TIER: low (script Worker + CI Connector; no LLM)
  AUTOMATION GATE: none (script Validator; read-only)
  STEPS:
    1. Developer implements feature with traceability markers (Journey 12).
    2. CI pipeline triggers traceability_coverage_validator via CI Connector
       (github_actions webhook event → connector_inbound_sync_worker →
       traceability_analysis Analyzer + coverage script):
         WorkerRun created; state: pending → running → done
    3. traceability_analysis Analyzer scans source_file[]:
         Computes per-file and aggregate coverage:
           (markers present / total feature_spec flow[] IDs required)
         Computes granularity score:
           (ratio of function-level markers to block-level markers)
         WorkerRun created; state: pending → running → done
    4. ValidationSession (traceability_coverage_validator) evaluates:
         If coverage >= min-coverage AND granularity >= min-granularity:
           ValidationSession.state → pass; Evidence created
           CI Connector write-back: [write-back: github_actions] → CI green
         If below threshold:
           ValidationSession.state → fail
           Recommendation per uncovered feature_spec Object ID
           CI Connector write-back: CI fail status
    5. DECISION: CI fail?
       YES: Developer identifies uncovered feature_spec IDs from
            Recommendation[]; adds missing markers; pushes fix;
            CI re-triggers step 2
       NO: CI green; PR can proceed
    6. DECISION: Scan scope?
       FULL CODEBASE: all source_file[] in workspace
       SCOPED: filter to specific feature_spec[] scope (faster CI)
  DECISION_POINTS:
    - ScanScope: full codebase / scoped to feature area
    - FailMode: hard fail (CI blocks merge) / warn only (advisory)
  GUARDS: [
    Thresholds must be configured in Kit config before enforcement,
    Coverage report always emitted even on failure for developer diagnosis,
    CI Connector write-back (Gate 2) must be configured before CI status
      can be updated,
    Analyzer is read-only — never modifies source_file[] or feature_spec[]
  ]
  NEXT: Add missing markers → push fix → CI re-runs → merge when PASS
```

---

### Journey 20: Cross-Workspace Traceability Navigation

```text
ALGORITHM CrossWorkspaceTraceabilityNavigation
  ACTOR: Tech Lead, Architect
  GOAL: In a multi-repo Workspace, trace an Object ID from its definition
        in one repo to all its usages across all registered Workspace sources,
        and assess blast radius before making a change
  INPUTS: [
    Workspace Object — initialized with registered sources (multi-repo),
    Object ID to investigate,
    All Workspace sources reachable via Connectors
  ]
  OUTPUTS: [
    Definition location (Object + source repo),
    All usage Objects across Workspace sources,
    Object content (full specification block),
    Recommendation[] per cross-workspace dependency gap
  ]
  COST TIER: low (object_graph_retriever hybrid; read-only)
  AUTOMATION GATE: none (read-only Retriever and Analyzer Workers)
  STEPS:
    1. Confirm Workspace Object is configured with registered sources synced
       (connector_inbound_sync_worker has run for all sources).
    2. invoke object_graph_retriever (object_graph scope: workspace, hybrid,
       on_demand):
         Input: Object ID query + Workspace scope
         Output: Object definition location (source repo, file, Object type),
                 all Objects referencing this ID across Workspace sources
         WorkerRun created; state: pending → running → done
    3. invoke document_retriever (document_index, workspace scope, on_demand):
         Input: Object ID
         Output: full specification content of the Object
         WorkerRun created; state: pending → running → done
    4. traceability_analysis Analyzer runs (hybrid, on_demand):
         Input: Object ID + Workspace scope
         Maps full dependency chain across all registered sources:
           prd → design → decomposition → feature_spec → source_file[]
           → pull_request[] chains (per repo)
         Identifies cross-repo dependencies and broken chains
         Creates Recommendation per unresolved cross-workspace link
         WorkerRun created; state: pending → running → done
    5. Assess blast radius:
         How many Objects and source repos reference this ID?
         Which repos have stale Objects (stale_artifact_detection output)?
         WorkerInteraction (kind: free_form_intent) — optional:
           Architect annotates findings for the team
    6. DECISION: Planning a change?
       YES: proceed to Journey 13 (change impact analysis) on the upstream
            Object containing this ID
       NO: navigation complete; use findings for review or documentation
    7. DECISION: Navigation scope?
       SINGLE ID DEEP-DIVE: full chain for one Object ID
       BREADTH SCAN: object_graph_retriever queries all IDs of a kind
         (e.g., all prd fr[] IDs) across Workspace
  DECISION_POINTS:
    - PlanningChange: yes (→ Journey 13) / no (navigation complete)
    - NavigationScope: single ID deep-dive / breadth scan of a kind
    - IncludeCodeScan: include source_file[] scan in workspace query
  GUARDS: [
    All Workspace sources must be synced (connector_inbound_sync_worker ran)
      before cross-workspace queries run,
    All operations are read-only — no Object modifications,
    object_graph_retriever scoped to Workspace boundary; cannot query
      outside registered sources
  ]
  NEXT: Journey 13 (if change is planned), or update Object referencing this ID
```

---

### Journey 21: Interactive Kit Update

```text
ALGORITHM InteractiveKitUpdate
  ACTOR: Developer, Tech Lead
  GOAL: Update an installed Kit to the latest version, reviewing each
        changed Worker/Flow/GTS-type/Connector definition via
        WorkerInteraction (kind: menu) before accepting changes
  INPUTS: [
    Installed Kit (.cf-studio-kit.toml on disk),
    Upstream Kit source (Kit Registry, local path, or GitHub ref),
    Workspace with Kit installed
  ]
  OUTPUTS: [
    Updated Kit files on disk (only accepted changes),
    .cf-studio-kit.toml reflecting new Kit version,
    ValidationSession + Evidence (Kit validation after update),
    WorkerRun audit trail of per-file decisions
  ]
  COST TIER: low (Kit version check script + WorkerInteraction menus)
  AUTOMATION GATE: approved_automation (Kit install Worker writes to graph)
  STEPS:
    1. Kit version check Worker runs (script, on_demand):
         Compares installed Kit version against upstream Registry
         Output: update summary (new version, changed files, breaking changes)
         WorkerRun created; state: pending → running → done
    2. DECISION: Proceed with update?
       WorkerInteraction (kind: menu) created:
         Options: [proceed, skip (defer update), show changelog]
         Tech Lead selects → WorkerRun resumes
    3. For each changed file in the Kit update:
         WorkerInteraction (kind: menu) created per file:
           Shows diff of upstream vs local file
           Options: [accept upstream, keep existing, diff and edit merged result]
           WorkerRun.state → awaiting_input; Developer responds
           WorkerRun resumes; decision recorded in WorkerRun audit trail
    4. Kit install Worker writes only accepted / merged files:
         WorkerRun created; state: pending → running → done
         Only files with accept/merge decision are written;
         declined files preserved exactly as-is
    5. Kit validation Worker runs (script, realtime):
         ValidationSession created
         Checks: manifest schema valid, all component references resolve,
         no dangling GTS type dependencies, Worker contracts consistent
         On pass: Evidence attached to Kit install WorkerRun
         On fail: WorkerInteraction (kind: input_request) for resolution;
                  validation re-runs
    6. DECISION: Regenerate dependent Workers?
       YES (if Kit update changes WorkerImplementation configs):
         Affected Worker definitions updated in Tenant registry;
         active WorkerRuns not affected (in-flight runs use prior version)
       NO: Kit update complete without Worker regeneration
    7. Tech Lead tests updated Kit behavior in a representative journey run.
  DECISION_POINTS:
    - ProceedWithUpdate: proceed / skip / show changelog
    - PerFileDecision: accept upstream / keep existing / diff and edit
      (WorkerInteraction per file)
    - RegenerateWorkers: yes / no
  GUARDS: [
    Declined files are never overwritten — WorkerInteraction decision is binding,
    Merged/edited files written only after Developer confirms edit in
      WorkerInteraction,
    Kit ValidationSession must pass (Evidence attached) after update before
      Kit Workers can be invoked,
    Active in-flight WorkerRuns use the prior Kit version; no mid-run
      Kit hot-swap
  ]
  NEXT: Test updated Kit Workers in a representative journey
```

---

### Journey 22: Object Graph Navigation

```text
ALGORITHM ObjectGraphNavigation
  ACTOR: Developer, Architect
  GOAL: Understand the full traceability picture for a given feature area
        — enumerate Object IDs, find definitions, find usages, read content
        — before making a change or designing an extension
  INPUTS: [
    Feature area or subsystem of interest,
    Workspace with registered artifacts and sources,
    Object types of interest (prd fr[], design component[], feature_spec
      flow[], source_file[] markers)
  ]
  OUTPUTS: [
    List of all Object IDs in the area (by type),
    Definition Objects (source repo, type, content),
    Usage Objects across artifacts and source_file[],
    Content of relevant Object specification blocks,
    Recommendation[] per traceability gap found
  ]
  COST TIER: low (object_graph_retriever hybrid + traceability_analysis;
             read-only, no LLM authoring)
  AUTOMATION GATE: none (read-only Retriever and Analyzer Workers)
  STEPS:
    1. invoke object_graph_retriever (object_graph scope: workspace, hybrid,
       on_demand):
         Input: feature area query + Object type filter
         Output: all Objects in scope by type
           (prd fr[], design component[], feature_spec flow[], task[])
         WorkerRun created; state: pending → running → done
    2. For each Object ID of interest:
         invoke object_graph_retriever scoped to single Object ID:
           Output: definition Object (location, type, content preview)
           All Objects referencing this ID (usages across artifacts)
         WorkerRun created; state: pending → running → done
    3. invoke document_retriever (document_index, workspace scope, on_demand):
         Input: Object ID
         Output: full specification content of the Object block
         WorkerRun created; state: pending → running → done
    4. DECISION: Include source_file[] code-level scan?
       YES: invoke code_retriever (code_index, workspace scope, on_demand):
              Input: Object ID
              Output: source_file[] locations where this ID is referenced
                      (traceability markers, test cases)
              WorkerRun created; state: pending → running → done
       NO: artifact-level navigation complete
    5. traceability_analysis Analyzer runs (hybrid, on_demand):
         Input: Object IDs enumerated in step 1 + workspace scope
         Maps full artifact → code traceability chains
         Creates Recommendation per broken or missing link in the chain
         WorkerRun created; state: pending → running → done
    6. DECISION: Planning a change?
       YES: proceed to Journey 13 (change impact analysis) on the upstream
            Object; use graph navigation findings as baseline
       NO: navigation complete; findings used for review or documentation
    7. DECISION: Navigation depth?
       SINGLE ID DEEP-DIVE: full chain trace for one Object ID
       BREADTH SCAN: all Object IDs of a kind in the feature area
  DECISION_POINTS:
    - IncludeCodeScan: include code_retriever scan / artifact-level only
    - NavigationDepth: single ID deep-dive / breadth scan of a kind
    - PlanningChange: yes (→ Journey 13) / no (navigation complete)
  GUARDS: [
    All operations are read-only — no Object modifications,
    object_graph_retriever scoped to Workspace boundary,
    traceability_analysis Recommendations created only for persistent gaps;
      auto-invalidated when gap closes
  ]
  NEXT: Journey 13 (change impact), Journey 12 (implement missing markers),
        or Journey 15 (reconstruct missing SDLC artifacts)
```

---

## Cross-Journey Patterns

The twenty-two journeys above share a set of recurring structural patterns. Understanding
these patterns helps teams reason about how Studio v2 Workers compose and how quality
gates propagate across the system.

### Worker-Chain Pattern

Journeys 1, 9, 10, 11, 12, and 16 all chain multiple Workers sequentially where the
output Object of one Worker becomes the input to the next (via `Worker.inputBindings:
source chain`). The chain is explicit: `create_prd_worker` → `create_design_worker` →
`decompose_feature_worker` → `create_feature_spec_worker` → `implement_code_worker`
→ `create_pr_worker`. Each step creates a WorkerRun with a clear audit trail. If any
step fails or is cancelled, downstream Workers are not invoked until the upstream
WorkerRun reaches state: done.

### Validator-First Quality Gate

Every journey that advances an Object to a new state passes through a Validator gate
before the StatePolicy transition can occur. Validators (gap_analysis_validator,
pr_design_validator, adr_structure_validator, traceability_coverage_validator) produce
ValidationSessions and immutable Evidence attached to the Object. Evidence is the
precondition for state advancement. Retries are bounded by `Validator.maxRetries`; when
exhausted, an Approval (kind: risk_acceptance) is required. Validators run at any
automationLevel — they are never gated on approved_automation.

### automationLevel Dial

Journeys 1, 5, 7, 9, 10, 11, and 12 require `automationLevel >= approved_automation`
for action Workers (Workers that write Objects or write back to external systems).
Read-only Analyzers and Validators (Journeys 13, 14, 18, 19, 20, 22) run at any
automationLevel. Journey 21 (Kit Update) uses approved_automation for the Kit install
write. The automationLevel dial can be shown at Flow start via WorkerInteraction
(kind: menu) allowing the user to explicitly confirm the level for the current run
before any action Worker executes.

### Connector-Mediated Objects

Most journeys include Objects synced from external systems (`[sync: jira]`,
`[sync: github]`, `[sync: pagerduty]`, `[sync: confluence]`). These Objects carry
`externalRef` with `connectorId`, `externalId`, `externalUrl`, and `lastSyncedAt`.
Workers operate on Studio Objects regardless of origin — the Connector handles the
sync boundary. Connector inbound sync is performed by `connector_inbound_sync_worker`
(script, platform Worker). Outbound write-back uses `connector_outbound_sync_worker`
subject to Gate 2 (WriteBackPolicy).

### WorkerInteraction Mid-Run

All LLM and hybrid Workers can pause mid-run by emitting a WorkerInteraction
(kind: input_request | menu | free_form_intent). The WorkerRun transitions to
`awaiting_input`. The user responds. The WorkerRun resumes with the response injected
into context. This pattern replaces the v1 concept of "findings browsers" and
per-step modal dialogs — it is a uniform mid-run pause mechanism that works the
same way across all Worker types and all journeys.

### Evidence Audit Trail

Every Validator-gated transition produces Evidence attached to the Object. Every
WorkerRun records `externalEvents[]` write-ahead before execution. Every Approval
records `decidedBy` and `decidedAt`. Every WorkerInteraction records the user response
and timestamp. The combination forms a complete, immutable audit trail from initial
intent (WorkerInteraction free_form_intent) through every intermediate Object state
transition to the final write-back to external systems. This audit trail is always
persisted in the Object graph — there is no "session-only" mode for WorkerRun outputs.
