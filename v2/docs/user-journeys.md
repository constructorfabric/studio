# Studio v2 — User Journeys

## Introduction

This document describes the fourteen primary user journeys in Studio v2. Each journey
traces the full path a user takes from intent to outcome, showing which Objects, Workers,
Flows, and Connectors are involved.

**How to read ALGORITHM blocks**

Each block follows a fixed schema:

- `ACTOR` — the role that initiates the journey
- `GOAL` — the outcome they are trying to reach
- `INPUTS` — what must already exist before the journey begins; `[sync: name]` marks
  Objects synced from external systems via Connectors
- `OUTPUTS` — what is produced when the journey ends; `[write-back: name]` marks
  Objects written back to external systems
- `STEPS` — the ordered sequence of actions, Workers, and Flows invoked
- `COST TIER` — approximate AI cost: `low` (script only), `medium` (hybrid Workers),
  `high` (chain of 2+ LLM Workers)
- `AUTOMATION GATE` — `none` (readonly or Validator-only; any automationLevel) or
  `approved_automation` (action Workers; requires `automationLevel >= approved_automation
  AND category in approvedWorkerCategories`)
- `DECISION_POINTS` — named forks where the user or Studio chooses a path
- `GUARDS` — invariants that must hold throughout; violation halts the journey
- `NEXT` — optional handoff to a downstream journey or external process

**Studio v2 architecture note**

Studio v2 is Object- and Worker-centric. Objects live in the shadow SDLC graph.
Workers consume and produce Objects. Flows add mandatory-step constraints over Workers.
Connectors sync Objects from external systems (via Gears OAGW). Action Workers
write back to external systems through `WriteBackPolicy`. Validators run regardless
of `automationLevel`; action Workers require `approved_automation`.

---

## Journey Index

| # | Journey | Actor | Goal | Workers / Flows | Cost Tier | Automation Gate |
|---|---------|-------|------|-----------------|-----------|-----------------|
| 1 | Product intent → decomposed tasks | Product Manager | prd → design → task[] in Jira | `create_design_worker` → `decompose_feature_worker` | high | approved_automation |
| 2 | Requirement gap detection | Product Manager | Detect uncovered requirements | `gap_analysis`, `traceability_analysis` | medium | none |
| 3 | Bug report → Fix PR | Developer | bug → reproduction → failing test → PR | `bug_to_fix_pr_flow` | high | approved_automation |
| 4 | Feature task → Pull Request | Developer | task → code → PR with design conformance | `implement_code_worker`, `create_pr_worker`, `pr_design_validator` | high | approved_automation |
| 5 | Accept a Recommendation | Developer | Act on an Analyzer-created Recommendation | `validationWorker` + `suggestedWorker` | low–high | approved_automation |
| 6 | PR conformance to design | Tech Lead | Validate PR against design (automatic) | `pr_design_validator` | medium | none |
| 7 | Architecture drift detection | Architect | Detect component drift from design | `architecture_drift_detection` | medium | none |
| 8 | Raise automationLevel | Architect | Unlock action Workers for a Tenant | StatePolicy transition + Approval | low | none |
| 9 | Release readiness review | Release Manager | Gate release candidate on validators | `release_readiness_review` | medium | none |
| 10 | Incident → Postmortem | SRE / On-call | incident → postmortem + prevention tasks | `incident_to_postmortem_flow` | medium–high | approved_automation |
| 11 | Deploy to environment | DevOps | build_artifact → deployment | `deploy_worker` | low | approved_automation |
| 12 | Security exception approval | Security Lead | Approve a vulnerability exception | `security_impact_analysis` + Approval | low | none |
| 13 | SBOM security scan | Security Engineer | Scan build_artifact for vulnerable deps | `security_impact_analysis` | medium | none |
| 14 | External system inbound sync | (platform) | Connector event → Object in graph | `connector_inbound_sync_worker` | low | none |

---

## Journeys

### Journey 1: Product Intent → Decomposed Tasks

```text
ALGORITHM ProductIntentToDecomposedTasks
  ACTOR: Product Manager
  GOAL: Turn a product requirement document into a validated design and
        an ordered task list written back to Jira
  INPUTS: [
    prd (state: draft) — authored externally or in Studio,
    workspace configured with Jira Connector [sync: jira]
  ]
  OUTPUTS: [
    design (state: approved) — linked to prd,
    decomposition — ordered feature list,
    task[] [write-back: jira] — Jira issues with traceability to prd + design
  ]
  COST TIER: high (create_design_worker + decompose_feature_worker, both llm)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. PM selects prd Object in Studio UI or CLI.
    2. Studio invokes create_design_worker (llm, on_demand):
         - Input: prd, workspace, optional style (detailed | sketch)
         - Output: design (state: draft)
    3. gap_analysis_validator (hybrid, realtime) runs automatically:
         - Checks prd FR coverage in candidate design
         - ValidationSession created; on fail → design sent back with gaps
    4. DECISION: Design acceptable?
       - YES: design state → approved (StatePolicy transition)
       - NO: PM edits design manually or re-runs create_design_worker
             with amended prd
    5. Studio invokes decompose_feature_worker (llm, on_demand):
         - Input: design, prd, optional team capacity hint
         - Output: decomposition + task[] (state: planned)
    6. DECISION: Review tasks before write-back?
       - YES: PM reviews task[] in Studio; edits names, priorities, owners
       - NO: proceed directly to step 7
    7. connector_outbound_sync_worker writes task[] to Jira via
       WriteBackPolicy (requiresApproval based on Tenant automationLevel).
       DECISION: Approval required?
       - Gate 2 (WriteBackPolicy.requiresApproval = true):
         Approval Object created; PM or Tech Lead approves; write-back executes.
       - Gate 2 (requiresApproval = false): write-back executes immediately.
  DECISION_POINTS:
    - DesignAcceptance: approve design / re-run with amendments
    - TaskReviewBeforeWriteBack: review first / write-back immediately
    - WriteBackApproval: Approval required (Gate 2) / immediate
  GUARDS: [
    automationLevel >= approved_automation before create_design_worker
      or decompose_feature_worker can be invoked,
    gap_analysis_validator must pass (or PM explicitly overrides) before
      design state can advance to approved,
    task[] write-back to Jira must satisfy WriteBackPolicy.allowedActions,
    prd must have at least one requirement before create_design_worker runs
  ]
  NEXT: Journey 3 (bug fix) or Journey 4 (feature implementation) per task
```

---

### Journey 2: Requirement Gap Detection

```text
ALGORITHM RequirementGapDetection
  ACTOR: Product Manager
  GOAL: Identify requirements that lack design coverage, implementation
        tasks, or test cases, and receive actionable Recommendations
  INPUTS: [
    requirement[] — in Studio graph (may be [sync: jira] or native),
    task[] [sync: jira],
    test_case[] [sync: github / test management tool],
    pull_request[] [sync: github]
  ]
  OUTPUTS: [
    Recommendation[] (state: pending) — one per detected gap,
    traceability report — coverage links visualized
  ]
  COST TIER: medium (gap_analysis hybrid + traceability_analysis hybrid)
  AUTOMATION GATE: none
  STEPS:
    1. gap_analysis Analyzer Worker runs on schedule or on_demand:
         - Scans requirement[], task[], test_case[], pull_request[]
         - Creates Recommendation for each uncovered requirement
         - Example: "requirement R-17 has no task and no test_case"
    2. traceability_analysis Analyzer Worker runs in parallel:
         - Maps requirement → design → task → pull_request → test_case chains
         - Creates Recommendation for broken links in the chain
    3. PM views Recommendation[] in Studio UI:
         - severity: info | warning | critical
         - confidence: full | partial (when external system unavailable)
    4. DECISION: Act on Recommendations?
       - YES: PM accepts Recommendations → Journey 1 (create tasks) or
              assigns tasks to developers manually
       - DISMISS: PM dismisses with reason; Recommendation state → dismissed
       - SNOOZE: PM sets validationWorker re-check schedule
  DECISION_POINTS:
    - AnalysisTrigger: scheduled (default: nightly) / on_demand
    - RecommendationAction: accept / dismiss / snooze re-check
  GUARDS: [
    Read-only — Analyzers never modify Objects,
    Recommendations created only if gap persists after re-check;
      stale Recommendations invalidated automatically when gap closes,
    confidence: partial allowed when external Connectors unavailable
      (Analyzer continues with available data)
  ]
  NEXT: Journey 1 (create design + tasks), or Journey 4 (implement feature)
```

---

### Journey 3: Bug Report → Fix PR

```text
ALGORITHM BugToFixPR
  ACTOR: Developer
  GOAL: Turn an open bug report into a validated pull request with a
        reproduction test, a fix, and Evidence from all Validators
  INPUTS: [
    bug (state: open) [sync: jira],
    component[] — in Studio graph,
    repository [sync: github]
  ]
  OUTPUTS: [
    test_case — failing test proving reproduction,
    pull_request (state: review) [write-back: github],
    ValidationSession[] + Evidence — one per mandatory Validator,
    WorkerRun[] — full execution trail
  ]
  COST TIER: high (4 LLM Workers in chain)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. Developer selects bug Object in Studio UI.
       Flow: bug_to_fix_pr_flow activates (entryConstraints: bug, state: open).
    2. bug_description_validator (hybrid, realtime):
         - Validates bug has sufficient reproduction info
         - ValidationSession created; on fail → bug returned for enrichment
    3. find_suspected_component (hybrid, on_demand):
         - Input: bug → Output: component[] (ranked by suspicion)
    4. deploy_test_environment (script, on_demand):
         - Input: component → Output: environment (ephemeral test env)
    5. reproduce_bug (hybrid, on_demand):
         - Input: bug, environment → Output: WorkerRun with reproduction Evidence
    6. create_failing_test (llm, on_demand):
         - Input: bug, reproduce output → Output: test_case (state: failing)
    7. confirm_test_fails_validator (script, realtime):
         - Runs test_case against baseline; validates it fails
         - ValidationSession; on fail → loop back to create_failing_test
    8. implement_fix (llm, on_demand):
         - Input: bug, test_case → Output: source_file[] (fix)
    9. confirm_test_passes_validator (script, realtime):
         - Runs test_case against fix; validates it passes
         - ValidationSession; on fail → loop back to implement_fix
   10. create_pr_worker (hybrid, on_demand):
         - Input: source_file[], branch → Output: pull_request [write-back: github]
         - pull_request.verifiedBy = [test_case]
         - pull_request.closesIssues = [bug]
    DECISION: Write-back approval required?
       - Gate 2 applies if WriteBackPolicy.requiresApproval = true for github
  DECISION_POINTS:
    - BugDescriptionSufficiency: pass validator / enrich bug first
    - FixLoopRetry: confirm_test_passes fails → re-run implement_fix
                    (up to Validator.maxRetries; then Approval escalation)
    - WriteBackApproval: Gate 2 (github write-back) required / immediate
  GUARDS: [
    automationLevel >= approved_automation for all action Workers,
    bug_description_validator must pass before find_suspected_component runs,
    test_case must demonstrate failure on baseline before implement_fix runs,
    pull_request.verifiedBy must reference the test_case produced in step 6,
    all three Validator WorkerRuns must reach state: done with Evidence
      before pull_request is created
  ]
  NEXT: Journey 6 (pr_design_validator fires automatically on PR creation),
        or Journey 9 (release readiness) when PR is merged
```

---

### Journey 4: Feature Task → Pull Request

```text
ALGORITHM FeatureTaskToPullRequest
  ACTOR: Developer
  GOAL: Implement a feature from a task with feature_spec linked,
        produce a PR, and get automatic design conformance validation
  INPUTS: [
    task (state: in_progress) [sync: jira],
    feature_spec — linked to task,
    design[] — for conformance check,
    repository [sync: github]
  ]
  OUTPUTS: [
    source_file[] — implementation with traceability markers,
    pull_request (state: review) [write-back: github]
      with conformsToDesign[] and implementsRequirements[],
    ValidationSession (pr_design_validator) + Evidence
  ]
  COST TIER: high (implement_code_worker llm + create_pr_worker hybrid)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. Developer selects task Object linked to feature_spec in Studio UI.
    2. implement_code_worker (llm, on_demand):
         - Input: feature_spec, task → Output: source_file[]
         - Writes implementation; traceability markers link code to feature_spec IDs
    3. create_pr_worker (hybrid, on_demand):
         - Input: source_file[], branch → Output: pull_request [write-back: github]
         - pull_request.implementsRequirements = [requirement refs from feature_spec]
         - pull_request.closesIssues = [task]
    4. pr_design_validator fires automatically (realtime, onEvent: PR → review):
         - Input: pull_request, design[], acceptance_criteria[]
         - Output: ValidationSession + ValidationResult + Evidence
         - On fail: pull_request annotated with findings; developer fixes
    5. DECISION: Conformance pass?
       - PASS: pull_request.conformsToDesign[] populated with Evidence;
               PR ready for human review
       - FAIL: developer amends source_file[]; create_pr_worker re-runs;
               pr_design_validator re-fires (up to maxRetries; then Approval escalation)
  DECISION_POINTS:
    - ConformanceResult: pass immediately / fail-and-fix loop
    - WriteBackApproval: Gate 2 (github write-back) per Tenant policy
  GUARDS: [
    automationLevel >= approved_automation for implement_code_worker
      and create_pr_worker,
    feature_spec must be linked to task before implement_code_worker runs,
    pr_design_validator Evidence must be attached to pull_request before
      it can advance to state: approved,
    source_file traceability markers must reference IDs from feature_spec
  ]
  NEXT: Journey 6 (design conformance fires automatically),
        Journey 9 (release readiness after merge)
```

---

### Journey 5: Accept a Recommendation

```text
ALGORITHM AcceptRecommendation
  ACTOR: Developer (or PM / Tech Lead depending on Recommendation severity)
  GOAL: Act on an Analyzer-created Recommendation by running the
        suggested fix Worker, verifying the gap is closed, and reaching
        state: done
  INPUTS: [
    Recommendation (state: pending) — created by an Analyzer Worker,
    Objects referenced by Recommendation.suggestedInput
  ]
  OUTPUTS: [
    Recommendation (state: done),
    Object — updated by suggestedWorker output,
    WorkerRun — execution record of the fix
  ]
  COST TIER: low–high (depends on suggestedWorker runtime)
  AUTOMATION GATE: approved_automation (for suggestedWorker if kind: action)
  STEPS:
    1. User sees Recommendation in Studio UI (notification or dashboard).
       Recommendation shows: reason, severity, confidence, suggestedWorker,
       suggestedInput (pre-filled from last re-check).
    2. DECISION: Re-check before accepting?
       - YES: validationWorker runs; checks gap still exists; refreshes
              suggestedInput to current Object state; recomputes severity
              if severityWorker set.
              DECISION: Gap still present?
              - YES: proceed to step 3 with refreshed suggestedInput
              - NO: Recommendation state → invalidated (gap closed already)
       - NO (accept as-is): proceed to step 3
    3. DECISION: suggestedInput changed since Recommendation created?
       - YES: Studio shows diff of suggestedInput; user confirms or cancels
       - NO: proceed directly
    4. User accepts Recommendation → state: accepted.
       suggestedWorker invoked (automationLevel gate checked):
         - Recommendation state → executing
         - WorkerRun created for suggestedWorker
    5. suggestedWorker completes:
         - Recommendation state → done
         - Output Object updated with fix
    6. DECISION: Write-back to external system?
       - If suggestedWorker output triggers Connector write-back:
         Gate 2 (WriteBackPolicy) applies
  DECISION_POINTS:
    - ReCheckBeforeAccepting: yes / no
    - InputChangedConfirmation: confirm updated input / cancel
    - WriteBackApproval: Gate 2 if output touches external system
  GUARDS: [
    automationLevel >= approved_automation if suggestedWorker is kind: action,
    suggestedInput must be confirmed by user if it changed since Recommendation
      was created,
    Recommendation state machine: pending → accepted → executing → done;
      no skipping states,
    validationWorker re-check must complete before suggestedInput diff is shown
  ]
  NEXT: Depends on suggestedWorker output (may chain into Journey 3 or 4)
```

---

### Journey 6: PR Conformance to Design (Automatic)

```text
ALGORITHM PRConformanceToDesign
  ACTOR: Tech Lead (reviewer) — Studio triggers automatically
  GOAL: Validate a pull request against the linked design documents
        and acceptance criteria; attach Evidence to the PR
  INPUTS: [
    pull_request (state: review) [sync: github],
    design[] — linked via pull_request.conformsToDesign refs,
    acceptance_criteria[] — from feature_spec or task
  ]
  OUTPUTS: [
    ValidationSession (state: pass | fail | escalated),
    ValidationResult + Evidence attached to pull_request,
    Recommendation if non-critical conformance gaps found
  ]
  COST TIER: medium (pr_design_validator hybrid)
  AUTOMATION GATE: none (Validator runs at any automationLevel)
  STEPS:
    1. pr_design_validator fires automatically (realtime, onEvent):
         trigger: pull_request state_changed → review
    2. Validator reads pull_request diff, design[], acceptance_criteria[].
    3. DECISION: Conformance result?
       - PASS: ValidationResult (state: pass) + Evidence created;
               pull_request.conformsToDesign[] populated.
               Tech Lead notified (NotificationRule).
       - FAIL (within maxRetries): ValidationResult (state: fail);
               pull_request annotated with findings list;
               developer notified to amend.
               Developer pushes fix → pr_design_validator re-fires.
       - FAIL (retries exhausted): ValidationSession state → escalated;
               Approval (kind: risk_acceptance) created for Tech Lead;
               Tech Lead approves exception or rejects PR.
    4. Tech Lead reviews ValidationResult in Studio UI (or GitHub comment
       from Connector write-back if configured).
  DECISION_POINTS:
    - ConformanceOutcome: pass / fail-and-retry / escalate
    - EscalationDecision: approve exception / reject PR
  GUARDS: [
    pr_design_validator fires on every push to the PR branch, not just once,
    ValidationResult must be attached to pull_request before state can
      advance to approved,
    Escalation Approval must be resolved before ValidationSession closes,
    Evidence is immutable once created (state: valid); revocation requires
      explicit revokedBy + revokedAt
  ]
  NEXT: Journey 9 (release readiness) after PR merged
```

---

### Journey 7: Architecture Drift Detection

```text
ALGORITHM ArchitectureDriftDetection
  ACTOR: Chief Architect / Tech Lead
  GOAL: Detect components that have drifted from their design
        specification and receive prioritized Recommendations
  INPUTS: [
    component[] — in Studio graph,
    component_dependency[] — current dependency graph,
    design[] — reference architecture documents,
    repository [sync: github] — for code-level evidence
  ]
  OUTPUTS: [
    Recommendation[] (state: pending) — one per drifted component,
    architecture_drift report (WorkerRun output)
  ]
  COST TIER: medium (architecture_drift_detection hybrid, scheduled)
  AUTOMATION GATE: none
  STEPS:
    1. architecture_drift_detection Analyzer runs on schedule (or on_demand):
         - Compares current component[] + component_dependency[] against design[]
         - Detects: new dependencies not in design, missing components,
           interface contract violations, boundary violations
         - Creates Recommendation per drift with severity + evidence
    2. Architect reviews Recommendation[] in Studio UI.
    3. DECISION: Response per Recommendation?
       - ACCEPT: Architect triggers update of design[] to reflect
                 intentional drift (Journey not covered here — cf-write-docs)
       - FIX: Architect assigns task to developer to fix the drift
              (task created via create_tasks_worker or manually)
       - DISMISS: drift intentional; Recommendation dismissed with reason
       - ADR: drift requires an Architecture Decision Record before actioning
  DECISION_POINTS:
    - DriftTrigger: scheduled (default: nightly) / on_demand
    - DriftResponse: accept (update design) / fix (create task) /
                     dismiss / create ADR first
  GUARDS: [
    Read-only — architecture_drift_detection never modifies Objects,
    confidence: partial if repository Connector unavailable
      (Analyzer continues with graph data only),
    Recommendations invalidated automatically if drift closes before action taken
  ]
  NEXT: ADR authoring (if architecture_decision required),
        Journey 4 (implement fix), or Journey 2 (broader gap analysis)
```

---

### Journey 8: Raise automationLevel

```text
ALGORITHM RaiseAutomationLevel
  ACTOR: Architect / CTO
  GOAL: Unlock action Workers for a Tenant by raising automationLevel,
        gated by an Approval requiring an architecture decision
  INPUTS: [
    Tenant (current automationLevel: recommendations | readonly),
    proposed automationLevel: approved_automation | enterprise
  ]
  OUTPUTS: [
    Approval (kind: architecture_decision, state: approved),
    Tenant.automationLevel updated,
    Tenant.approvedWorkerCategories updated
  ]
  COST TIER: low (StatePolicy transition + Approval; human-driven)
  AUTOMATION GATE: none (this journey IS the gate)
  STEPS:
    1. Architect initiates automationLevel raise in Studio UI.
    2. Studio checks StatePolicy for Tenant.automationLevel transition:
         raising automationLevel → requiresApproval (always).
    3. Approval Object created:
         kind: architecture_decision
         payload: { proposedLevel, approvedWorkerCategories, rationale,
                    customerImpact? }
         requiredRole: CTO | VP Engineering (per Tenant policy)
    4. Approver receives notification (NotificationRule: Approval pending).
    5. DECISION: Approver action?
       - APPROVE: Tenant.automationLevel updated;
                  Tenant.approvedWorkerCategories updated;
                  action Workers of approved categories now available.
       - REJECT: Approval state → rejected; automationLevel unchanged.
       - EXPIRE: Approval.expiresAt reached without decision;
                 new Approval required.
    6. DECISION: Lowering automationLevel later?
       - No Approval required (narrowing, not expanding); immediate.
  DECISION_POINTS:
    - ApproverDecision: approve / reject / expire
    - CategoryScope: which Worker categories to approve
      (studio.category in approvedWorkerCategories)
    - LowerLater: immediate (no Approval needed)
  GUARDS: [
    Approval is mandatory for any automationLevel raise; no bypass,
    Tenant.approvedWorkerCategories must be set alongside automationLevel
      change — empty list blocks all action Workers even at approved_automation,
    Lowering automationLevel requires no Approval but immediately
      blocks action Workers in removed categories,
    customerImpact field required when automationLevel >= enterprise
  ]
  NEXT: Journeys 1, 3, 4, 10, 11 now available (action Workers unlocked)
```

---

### Journey 9: Release Readiness Review

```text
ALGORITHM ReleaseReadinessReview
  ACTOR: Release Manager / Tech Lead
  GOAL: Gate a release candidate on automated validators and a required
        Tech Lead approval, producing Evidence for the release audit trail
  INPUTS: [
    release (state: candidate),
    release_component[] — component versions in this release,
    test_run[] [sync: github / CI],
    pull_request[] [sync: github] — merged PRs for this release,
    vulnerability[] [sync: snyk / dependabot]
  ]
  OUTPUTS: [
    release (state: approved | blocked),
    ValidationSession[] + Evidence — per mandatory Validator,
    Approval (kind: release_approval) — Tech Lead sign-off
  ]
  COST TIER: medium (hybrid Validators; script test coverage check)
  AUTOMATION GATE: none (Validators run at any automationLevel;
                   Approval is StatePolicy gate, not automationLevel gate)
  STEPS:
    1. Release Manager creates release (state: candidate) in Studio.
       Flow: release_readiness_review activates.
    2. gap_analysis_validator (hybrid, realtime):
         - Checks all requirements in scope are implemented + tested
         - ValidationSession; on fail → release blocked with gap list
    3. test_coverage_validator (script, realtime):
         - Checks test coverage >= 80% for release_component[] scope
         - ValidationSession; on fail → release blocked
    4. security_scan_validator (hybrid, realtime):
         - Checks no critical/high vulnerability[] without approved Approval
           (kind: security_exception) in release scope
         - ValidationSession; on fail → release blocked unless security exceptions
           are in place with valid expiresAt
    5. All three Validators pass → Approval (kind: release_approval) created:
         requiredRole: tech_lead
         payload: { release, Evidence[] from all validators,
                    customerImpact if scope != internal }
    6. Tech Lead approves → release state: approved.
    7. DECISION: Any Validator failed?
       - gap_analysis: PM/Dev must close gaps; re-run gap_analysis_validator
       - test_coverage: Dev must add tests; re-run test_coverage_validator
       - security_scan: Security Lead must create security_exception Approval
                        for each outstanding vulnerability (Journey 12)
  DECISION_POINTS:
    - ValidatorFailureResolution: fix gaps / add tests / create security_exception
    - TechLeadApprovalDecision: approve / request changes / reject
  GUARDS: [
    All three mandatory Validators must reach ValidationSession.state: pass
      before Approval is created,
    security_exception Approvals must have valid expiresAt (not expired)
      before security_scan_validator accepts them,
    release state: approved requires Approval.state: approved;
      StatePolicy enforces this transition,
    Evidence from each Validator is immutable and attached to release audit trail
  ]
  NEXT: Journey 11 (deploy to environment)
```

---

### Journey 10: Incident → Postmortem

```text
ALGORITHM IncidentToPostmortem
  ACTOR: SRE / On-call Engineer
  GOAL: Automatically draft a postmortem and prevention tasks from a
        resolved incident
  INPUTS: [
    incident (state: resolved) [sync: pagerduty / datadog],
    WorkerRun[] — execution history during incident window,
    alert[] [sync: datadog / pagerduty],
    on_call_schedule — for postmortem ownership assignment
  ]
  OUTPUTS: [
    postmortem (→ document) — structured incident analysis,
    task[] (prevention) [write-back: jira] — action items,
    Evidence — from incident_summary_validator
  ]
  COST TIER: medium–high (incident_summary_validator hybrid +
             postmortem_draft_worker llm + prevention_tasks_worker hybrid)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. connector_inbound_sync_worker receives incident (state: resolved)
       from PagerDuty/Datadog via Gears OAGW.
       Flow: incident_to_postmortem_flow activates.
    2. incident_summary_validator (hybrid, realtime):
         - Validates incident has timeline, severity, affected systems
         - ValidationSession; on fail → on-call enriches incident data
    3. postmortem_draft_worker (llm, on_demand):
         - Input: incident, WorkerRun[] (execution history), alert[]
         - Output: postmortem (state: draft) with:
             timeline, root cause, contributing factors, impact assessment
    4. prevention_tasks_worker (hybrid, on_demand):
         - Input: postmortem → Output: task[] (prevention actions)
         - Tasks linked to postmortem.closedBy and relevant component[]
    5. On-call Engineer reviews postmortem in Studio UI:
         DECISION: Postmortem acceptable?
         - YES: postmortem state → published
         - EDIT: Engineer edits draft directly; re-runs prevention_tasks_worker
                 if root cause changes
    6. task[] [write-back: jira] via connector_outbound_sync_worker
       (Gate 2: WriteBackPolicy for jira write-back).
  DECISION_POINTS:
    - IncidentDataSufficiency: validator pass / enrich first
    - PostmortemAcceptance: publish as-is / edit draft
    - WriteBackApproval: Gate 2 (jira write-back)
  GUARDS: [
    automationLevel >= approved_automation for postmortem_draft_worker
      and prevention_tasks_worker,
    incident_summary_validator must pass before postmortem_draft_worker runs,
    postmortem must be reviewed and published by the on-call owner before
      prevention tasks are written to Jira,
    WorkerRun[] execution history read-only; never modified by this flow
  ]
  NEXT: Journey 2 (gap analysis on prevention tasks coverage),
        Journey 9 (if incident triggered a release rollback)
```

---

### Journey 11: Deploy to Environment

```text
ALGORITHM DeployToEnvironment
  ACTOR: DevOps / Release Manager
  GOAL: Deploy a validated build_artifact to a target environment
        with an optional Approval gate for production
  INPUTS: [
    build_artifact — produced by CI pipeline [sync: github actions / jenkins],
    environment (target: staging | prod),
    release (state: approved) — for production deploys
  ]
  OUTPUTS: [
    deployment (state: done | failed),
    deployment_status[] — one per deploy step,
    WorkerRun — execution record
  ]
  COST TIER: low (deploy_worker script only)
  AUTOMATION GATE: approved_automation
  STEPS:
    1. Release Manager selects build_artifact + environment in Studio.
    2. DECISION: Production deployment?
       - PROD: release must be in state: approved (Journey 9 completed);
               Approval (kind: release_approval) must be present.
               WriteBackPolicy.requiresApproval = true for prod environments
               (Gate 2) — if not yet approved, Approval created.
       - STAGING: proceed directly (WriteBackPolicy.requiresApproval = false)
    3. deploy_worker (script, on_demand):
         - Input: build_artifact, environment
         - Triggers CI/CD pipeline write-back [write-back: github actions / argocd]
         - Output: deployment Object + deployment_status[]
    4. deployment state transitions: pending → running → done | failed
    5. DECISION: Deployment failed?
       - YES: deployment state → failed; rollback decision required.
              Studio creates Recommendation (suggestedWorker: rollback_worker)
       - NO: deployment state → done; release state → deployed
  DECISION_POINTS:
    - EnvironmentTier: staging (no Approval) / production (Approval required)
    - FailureResponse: rollback / investigate / retry
  GUARDS: [
    automationLevel >= approved_automation for deploy_worker,
    Production deploy requires release.state: approved before deploy_worker
      can be invoked,
    WriteBackPolicy.allowedActions must include deploy action for the
      target environment,
    deployment_status[] appended on each step; never overwritten
  ]
  NEXT: Operations monitoring (SLO/SLI tracking outside Studio),
        Journey 10 if deployment triggers incident
```

---

### Journey 12: Security Exception Approval

```text
ALGORITHM SecurityExceptionApproval
  ACTOR: Security Lead
  GOAL: Formally accept a known vulnerability that cannot be immediately
        fixed, with a time-bounded exception and auto-review schedule
  INPUTS: [
    vulnerability or security_finding [sync: snyk / dependabot / pentest],
    risk assessment context
  ]
  OUTPUTS: [
    Approval (kind: security_exception, state: approved),
    policy_exception Object — linked to vulnerability,
    scheduled re-review Approval (via autoReviewAfter Worker)
  ]
  COST TIER: low (human-driven; security_impact_analysis for context only)
  AUTOMATION GATE: none (Approval flow is human-driven)
  STEPS:
    1. Security Lead sees vulnerability or security_finding in Studio.
       DECISION: Run impact analysis first?
       - YES: security_impact_analysis Analyzer (hybrid, on_demand) runs:
              Input: pull_request[], vulnerability[], security_finding[]
              Output: Recommendation with severity + affected component[]
       - NO: proceed with known context
    2. Security Lead initiates security_exception Approval:
         kind: security_exception
         payload: {
           expiresAt,
           acceptedRisk,
           mitigations: [],
           secondaryApprover? (required if severity: critical),
           autoReviewAfter: duration
         }
    3. DECISION: Secondary approver required?
       - YES (severity: critical): second Approval from CISO / VP Eng
       - NO: single Security Lead approval sufficient
    4. Approval approved → policy_exception created:
         linked to vulnerability; blocks security_scan_validator from
         failing on this vulnerability until expiresAt
    5. autoReviewAfter schedule creates a new Approval automatically
       when duration elapses — forces periodic re-evaluation.
  DECISION_POINTS:
    - ImpactAnalysisFirst: run security_impact_analysis / skip
    - SecondaryApproverRequired: yes (critical severity) / no
    - ExceptionDuration: set expiresAt (max enforced by Tenant policy)
  GUARDS: [
    security_exception Approval must have expiresAt set; no open-ended exceptions,
    Critical severity vulnerabilities require secondaryApprover,
    autoReviewAfter must be set; exceptions without review schedule are rejected,
    policy_exception scope limited to the specific vulnerability Object;
      wildcards not permitted
  ]
  NEXT: Journey 9 (security_scan_validator will now accept this exception)
```

---

### Journey 13: SBOM Security Scan

```text
ALGORITHM SBOMSecurityScan
  ACTOR: Security Engineer / DevOps
  GOAL: Scan a build artifact's SBOM for vulnerable dependencies and
        generate remediation Recommendations
  INPUTS: [
    build_artifact — produced by CI,
    sbom — attached to build_artifact (SPDX / CycloneDX),
    sbom_component[] — packages listed in SBOM,
    dependency_vulnerability[] [sync: snyk / dependabot / github advisory]
  ]
  OUTPUTS: [
    Recommendation[] — upgrade library_version for each vulnerable component,
    compliance_check_result[] — license policy check,
    task[] (remediation) — if Recommendation accepted
  ]
  COST TIER: medium (security_impact_analysis hybrid; license check script)
  AUTOMATION GATE: none
  STEPS:
    1. build_artifact created → onEvent trigger fires security_impact_analysis
       (Analyzer, hybrid, scheduled + onEvent).
    2. Analyzer reads sbom → sbom_component[] → library_version[]:
         - Matches against dependency_vulnerability[] [sync: snyk]
         - Identifies: critical/high CVEs, license policy violations
    3. For each vulnerable sbom_component:
         - Recommendation created: severity per CVE cvssScore,
           suggestedWorker: upgrade to fixedVersion library_version
    4. compliance_check runs (script):
         - Checks sbom_license[] against Tenant license policy
         - compliance_check_result: pass | fail
         - On fail: Recommendation for license review or policy_exception
    5. Security Engineer reviews Recommendations:
         DECISION: Per Recommendation action?
         - ACCEPT → Journey 5 (accept Recommendation); upgrade triggers
                    create_pr_worker [write-back: github]
         - EXCEPTION → Journey 12 (security_exception Approval)
         - DISMISS → Recommendation dismissed with reason
  DECISION_POINTS:
    - PerRecommendationAction: accept (upgrade) / exception / dismiss
    - LicensePolicyViolation: accept (policy_exception) / fix (update dep)
  GUARDS: [
    Read-only scan — never modifies sbom or build_artifact,
    confidence: partial if snyk/dependabot Connector unavailable
      (scan continues with available CVE data),
    Recommendations linked to specific sbom_component + library_version;
      not to build_artifact as a whole
  ]
  NEXT: Journey 12 (security_exception) or Journey 5 (accept upgrade Recommendation)
```

---

### Journey 14: External System Inbound Sync

```text
ALGORITHM ExternalSystemInboundSync
  ACTOR: (platform — no direct user interaction)
  GOAL: Keep Studio graph Objects current with external system state
        by processing inbound Connector events
  INPUTS: [
    Gears OAGW event — from external system (Jira, GitHub, PagerDuty, etc.),
    Connector (registry entity) — defines FieldMappings + syncProtocol,
    {vendor}_event_handler_worker (per-Kit) — custom mapping logic
  ]
  OUTPUTS: [
    Object (created | updated) — in Studio graph,
    externalRef populated: { connectorId, externalId, externalUrl, lastSyncedAt },
    WorkerRun — execution record of sync Worker
  ]
  COST TIER: low (script Workers)
  AUTOMATION GATE: none (platform Worker; not subject to automationLevel gate)
  STEPS:
    1. External system emits event (push) or Studio polls (pull) via Gears OAGW.
       Connector.syncProtocol determines push vs pull:
         - push: webhook received via OAGW webhookPath; secret verified
         - pull: scheduled interval poll; incremental if supported
    2. connector_inbound_sync_worker (script, realtime):
         - Receives raw OAGW event payload
         - Looks up Connector FieldMappings for this event type
         - Invokes per-Kit {vendor}_event_handler_worker for custom logic
    3. {vendor}_event_handler_worker (per-Kit):
         DECISION: Object exists in Studio graph?
         - YES (externalRef.externalId matches): UPDATE Object
             - Apply FieldMappings: direct | lookup | transform Worker
             - Update Object.updatedAt, externalRef.lastSyncedAt
             - Emit object_updated event → may trigger Analyzers
         - NO: CREATE Object
             - Assign GTS Type ID from Connector Kit type mapping
             - Populate Object fields via FieldMappings
             - Set externalRef
             - Emit object_created event
    4. WorkerRun recorded (write-ahead: externalEvents[] populated before
       any Object modification begins).
    5. DECISION: Conflict detected (Object modified in Studio since last sync)?
       - Connector.WriteBackPolicy.conflictStrategy applies:
         - overwrite: external wins
         - skip: Studio version kept; event logged
         - merge: field-level merge (if FieldMapping supports)
         - escalate (default): Approval (kind: custom) created for human resolution
  DECISION_POINTS:
    - SyncDirection: push (event-driven) / pull (scheduled interval)
    - ObjectExistence: create / update
    - ConflictResolution: overwrite / skip / merge / escalate
  GUARDS: [
    externalEvents[] write-ahead must complete before Object is modified,
    FieldMappings must not map external fields to Object.id or Object.tenantId,
    Connector scopeFilter (per Tenant) must be evaluated before Object creation
      — events outside scope silently dropped,
    rateLimit enforced by Gears OAGW upstream; sync Worker never called
      above the Kit-declared rate
  ]
  NEXT: Object now available in Studio graph for Analyzer Workers,
        Recommendations, and user-driven journeys
```

---

## Cross-Journey Patterns

### Object lifecycle as the common thread

All journeys operate on named Objects (bug, task, pull_request, incident, release, etc.)
that flow through Studio's graph. Workers move Objects from state to state.
Connectors bring external Objects in (inbound sync) and push Studio actions back
(outbound write-back). The graph is the source of truth; external systems are peers.

### Validator-first quality gate

Journeys 3, 4, 6, 9, and 10 all include mandatory Validator steps before an Object
can advance to its next state. Validators produce ValidationSessions and Evidence —
immutable proof that quality gates were cleared. Evidence is attached to the Object
(pull_request.conformsToDesign, release audit trail) and cannot be retracted without
explicit revocation.

### automationLevel as the permission dial

Journeys 1, 3, 4, 10, and 11 require `automationLevel >= approved_automation` for
action Workers (Workers that change state or write back to external systems). Read-only
Analyzers and Validators (Journeys 2, 6, 7, 9) run at any automationLevel. Journey 8
is the explicit gate for raising the level. Lowering it requires no approval.

### Connector-mediated Objects

Most journeys include Objects synced from external systems (`[sync: jira]`,
`[sync: github]`, `[sync: pagerduty]`). These Objects carry `externalRef` with
`connectorId`, `externalId`, `externalUrl`, and `lastSyncedAt`. Workers operate on
Studio Objects regardless of origin — the Connector handles the sync boundary.

### Write-back as a two-gate operation

Any action that modifies an external system (creating a Jira issue, opening a GitHub PR,
triggering a deploy) passes through two independent gates:

- **Gate 1 (Studio execution):** `automationLevel >= approved_automation AND
  category in approvedWorkerCategories` — controls whether the action Worker runs at all.
- **Gate 2 (Connector write-back):** `WriteBackPolicy.requiresApproval` — controls
  whether the output is sent to the external system; may require a separate Approval.

Both gates must pass; Gate 1 does not imply Gate 2 clearance.

### Evidence and audit trail

Every Validator-gated transition produces Evidence attached to the Object. Every
WorkerRun records `externalEvents[]` write-ahead before execution. Every Approval
records `decidedBy` and `decidedAt`. The combination forms a complete audit trail
from intent to production.
