import type { StudioObject, WorkerDef, FlowDef, Recommendation } from '../types/domain'

// ─── Objects ──────────────────────────────────────────────────────────────────

export const MOCK_OBJECTS: StudioObject[] = [
  {
    id: 'prd-001',
    typeId: 'prd',
    tenantId: 'tenant-acme',
    title: 'Billing Service v2',
    state: 'approved',
    validationStatus: 'pass',
    stalenessScore: 0.05,
    description: 'Product requirements for multi-tenant billing service v2, including Stripe integration, invoice generation, and ledger management.',
    links: [
      // F-027: removed derived_from/drives links to adr-001, adr-002, design-001 — wrong direction;
      // ADRs inform prd-001 (adr→prd), design-001 derives from prd-001 (design→prd)
    ],
    createdAt: '2026-06-01T09:00:00Z',
    updatedAt: '2026-06-15T14:30:00Z',
    metadata: { version: '2.0', owner: 'product@acme.com', priority: 'P0' },
  },
  {
    id: 'adr-001',
    typeId: 'adr',
    tenantId: 'tenant-acme',
    title: 'Event-driven billing architecture',
    state: 'approved',
    validationStatus: 'pass',
    stalenessScore: 0.08,
    description: 'Decision to use event-driven architecture for billing processing to enable async invoice generation and webhook handling.',
    links: [
      { targetId: 'prd-001', kind: 'informs' },
      { targetId: 'design-001', kind: 'informs' },
    ],
    createdAt: '2026-06-02T10:00:00Z',
    updatedAt: '2026-06-10T11:00:00Z',
    metadata: { status: 'accepted', supersedes: null },
  },
  {
    id: 'adr-002',
    typeId: 'adr',
    tenantId: 'tenant-acme',
    title: 'PostgreSQL for billing ledger',
    state: 'approved',
    validationStatus: 'pass',
    stalenessScore: 0.03,
    description: 'Decision to use PostgreSQL with partitioning for the billing ledger to support high-volume transaction data.',
    links: [
      { targetId: 'prd-001', kind: 'informs' },
      { targetId: 'design-001', kind: 'informs' },
      { targetId: 'task-003', kind: 'informs' },
    ],
    createdAt: '2026-06-02T11:00:00Z',
    updatedAt: '2026-06-10T11:30:00Z',
    metadata: { status: 'accepted', alternatives: ['MySQL', 'CockroachDB'] },
  },
  {
    id: 'design-001',
    typeId: 'design',
    tenantId: 'tenant-acme',
    title: 'Billing Service Architecture',
    state: 'approved',
    validationStatus: 'pass',
    stalenessScore: 0.12,
    description: 'System design for billing service v2 covering webhook ingestion, event bus, invoice generation service, ledger schema and API contracts.',
    links: [
      { targetId: 'prd-001', kind: 'derived_from' },
      { targetId: 'adr-001', kind: 'references' },
      { targetId: 'adr-002', kind: 'references' },
      { targetId: 'decomp-001', kind: 'decomposes_into' },
    ],
    createdAt: '2026-06-05T09:00:00Z',
    updatedAt: '2026-06-18T16:00:00Z',
    metadata: { version: '1.2', reviewers: ['arch@acme.com'] },
  },
  {
    id: 'decomp-001',
    typeId: 'decomposition',
    tenantId: 'tenant-acme',
    title: 'Billing v2 Tasks',
    state: 'approved',
    validationStatus: 'pass',
    stalenessScore: 0.10,
    description: 'Task decomposition for billing service v2 implementation, ordered by dependency.',
    links: [
      { targetId: 'design-001', kind: 'derived_from' },
      { targetId: 'task-001', kind: 'decomposes_into' },
      { targetId: 'task-002', kind: 'decomposes_into' },
      { targetId: 'task-003', kind: 'decomposes_into' },
    ],
    createdAt: '2026-06-10T10:00:00Z',
    updatedAt: '2026-06-20T09:00:00Z',
  },
  {
    id: 'task-001',
    typeId: 'task',
    tenantId: 'tenant-acme',
    title: 'Implement Stripe Webhook Handler',
    state: 'in_progress',
    validationStatus: 'pending',
    stalenessScore: 0.0,
    description: 'Implement the Stripe webhook ingestion endpoint, signature verification, and event dispatch to internal billing event bus.',
    links: [
      { targetId: 'decomp-001', kind: 'derived_from' },
      { targetId: 'fspec-001', kind: 'implements' },
      // F-027: removed derived_from/produces link to pr-001 — pr-001 already has implements→task-001
    ],
    createdAt: '2026-06-20T10:00:00Z',
    updatedAt: '2026-07-05T11:00:00Z',
    metadata: { assignee: 'dev1@acme.com', sprint: 'Sprint 42', points: 5 },
  },
  {
    id: 'task-002',
    typeId: 'task',
    tenantId: 'tenant-acme',
    title: 'Implement Invoice Generation Worker',
    state: 'planned',
    validationStatus: 'none',
    stalenessScore: 0.0,
    description: 'Build the async invoice generation worker that processes billing events and produces PDF invoices stored in S3.',
    links: [
      { targetId: 'decomp-001', kind: 'derived_from' },
      { targetId: 'fspec-002', kind: 'implements' },
    ],
    createdAt: '2026-06-20T10:30:00Z',
    updatedAt: '2026-06-25T09:00:00Z',
    metadata: { assignee: null, sprint: 'Sprint 43', points: 8 },
  },
  {
    id: 'task-003',
    typeId: 'task',
    tenantId: 'tenant-acme',
    title: 'Billing Ledger Schema Migration',
    state: 'done',
    validationStatus: 'pass',
    stalenessScore: 0.45,
    description: 'PostgreSQL schema migration for billing ledger with partitioning by tenant and month.',
    links: [
      { targetId: 'decomp-001', kind: 'derived_from' },
      { targetId: 'adr-002', kind: 'implements' },
    ],
    createdAt: '2026-06-15T09:00:00Z',
    updatedAt: '2026-06-28T14:00:00Z',
    metadata: { assignee: 'dev2@acme.com', sprint: 'Sprint 41', points: 3 },
  },
  {
    id: 'fspec-001',
    typeId: 'feature_spec',
    tenantId: 'tenant-acme',
    title: 'Stripe Webhook Flow',
    state: 'approved',
    validationStatus: 'pass',
    stalenessScore: 0.05,
    description: 'Feature specification for the Stripe webhook handler including all event types, error handling, retry logic, and idempotency guarantees.',
    links: [
      { targetId: 'task-001', kind: 'derived_from' },
      { targetId: 'design-001', kind: 'derived_from' },
    ],
    createdAt: '2026-06-22T09:00:00Z',
    updatedAt: '2026-07-01T10:00:00Z',
    metadata: { testScenarios: 12, coverage: '95%' },
  },
  {
    id: 'fspec-002',
    typeId: 'feature_spec',
    tenantId: 'tenant-acme',
    title: 'Invoice Generation Flow',
    state: 'draft',
    validationStatus: 'pending',
    stalenessScore: 0.0,
    description: 'Feature specification for invoice generation worker. Currently missing test scenarios and error handling flows.',
    links: [
      { targetId: 'task-002', kind: 'derived_from' },
      { targetId: 'design-001', kind: 'derived_from' },
    ],
    createdAt: '2026-06-28T14:00:00Z',
    updatedAt: '2026-07-02T09:00:00Z',
    metadata: { testScenarios: 0, coverage: '0%' },
  },
  {
    id: 'pr-001',
    typeId: 'pull_request',
    tenantId: 'tenant-acme',
    title: 'feat/stripe-webhook-handler',
    state: 'review',
    validationStatus: 'pending',
    stalenessScore: 0.0,
    description: 'Pull request implementing the Stripe webhook handler per feature spec. Awaiting design validation and security review.',
    links: [
      { targetId: 'task-001', kind: 'implements' },
      { targetId: 'fspec-001', kind: 'validates' },
    ],
    createdAt: '2026-07-04T15:00:00Z',
    updatedAt: '2026-07-06T10:00:00Z',
    metadata: { prNumber: 247, branch: 'feat/stripe-webhook-handler', commits: 8, additions: 1240, deletions: 45 },
  },
  {
    id: 'build-001',
    typeId: 'build',
    tenantId: 'tenant-acme',
    title: 'ci-run-4521',
    state: 'running',
    validationStatus: 'pending',
    stalenessScore: 0.0,
    description: 'CI build for PR #247 feat/stripe-webhook-handler. Running unit tests, integration tests and coverage check.',
    links: [
      { targetId: 'pr-001', kind: 'validates' },
    ],
    createdAt: '2026-07-06T10:05:00Z',
    updatedAt: '2026-07-06T10:05:00Z',
    metadata: { pipeline: 'billing-service-ci', runner: 'github-actions', duration: '4m 32s' },
  },
  {
    id: 'inc-001',
    typeId: 'incident',
    tenantId: 'tenant-acme',
    title: 'Billing duplicate charge INC-441',
    state: 'open',
    validationStatus: 'none',
    stalenessScore: 0.0,
    description: 'Production incident: customers being charged twice for subscription renewals. Severity P1. Billing event deduplication logic suspect.',
    links: [
      { targetId: 'fspec-001', kind: 'references' },
      { targetId: 'design-001', kind: 'references' },
    ],
    createdAt: '2026-07-06T08:00:00Z',
    updatedAt: '2026-07-06T11:00:00Z',
    metadata: { severity: 'P1', affectedTenants: 12, status: 'investigating' },
  },
]

// ─── Graph Node Positions ─────────────────────────────────────────────────────

export const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  // ADRs flank the PRD vertically — enough gap for informs-arcs to curve cleanly
  'adr-001':    { x: 0,    y: 0   },
  'prd-001':    { x: 0,    y: 240 },
  'adr-002':    { x: 0,    y: 480 },
  // Main SDLC chain flows left→right on the centre lane
  'design-001': { x: 340,  y: 240 },
  'decomp-001': { x: 660,  y: 240 },
  // Tasks spread vertically around the centre
  'task-001':   { x: 980,  y: 100 },
  'task-002':   { x: 980,  y: 240 },
  'task-003':   { x: 980,  y: 380 },
  // Feature specs beside their tasks
  'fspec-001':  { x: 1300, y: 100 },
  'fspec-002':  { x: 1300, y: 240 },
  // PR and build continue the chain
  'pr-001':     { x: 1620, y: 100 },
  'build-001':  { x: 1940, y: 100 },
  // Incident sits below the PR lane
  'inc-001':    { x: 1620, y: 380 },
}

// ─── Worker Definitions ───────────────────────────────────────────────────────

export const WORKER_DEFS: WorkerDef[] = [
  // F-010: SDLC producer Workers — requiresAutomationGate: true, category: 'quality'
  {
    id: 'create_prd_worker',
    label: 'Create PRD',
    description: 'Generates a product requirements document from a high-level intent description.',
    requiresAutomationGate: true,
    category: 'quality',
    profile: 'on_demand',
    actionLabel: 'Create PRD',
    applicableTypes: ['prd'],
  },
  {
    id: 'create_design_worker',
    label: 'Create Design',
    description: 'Generates a system design document from an approved PRD.',
    requiresAutomationGate: true,
    category: 'quality',
    profile: 'on_demand',
    actionLabel: 'Create Design',
    applicableTypes: ['prd'],
    interaction: {
      kind: 'input_request',
      prompt: 'Specify any architectural constraints or technology preferences for this design:',
    },
  },
  {
    id: 'decompose_feature_worker',
    label: 'Decompose into Tasks',
    description: 'Decomposes a design document into ordered, implementable tasks.',
    requiresAutomationGate: true,
    category: 'quality',
    profile: 'on_demand',
    actionLabel: 'Decompose',
    applicableTypes: ['design'],
    interaction: {
      kind: 'menu',
      prompt: 'Choose decomposition strategy:',
      options: ['Dependency order', 'Risk-first', 'Value-first'],
    },
  },
  {
    id: 'create_feature_spec_worker',
    label: 'Create Feature Spec',
    description: 'Authors a detailed feature specification with test scenarios from a task definition.',
    requiresAutomationGate: true,
    category: 'quality',
    profile: 'on_demand',
    actionLabel: 'Create Feature Spec',
    applicableTypes: ['task'],
  },
  {
    id: 'implement_code_worker',
    label: 'Implement Code',
    description: 'Writes implementation code from a feature spec or task definition.',
    requiresAutomationGate: true,
    category: 'platform',
    profile: 'on_demand',
    actionLabel: 'Implement',
    applicableTypes: ['task', 'feature_spec'],
    interaction: {
      kind: 'input_request',
      prompt: 'Clarify the implementation scope (e.g. files to touch, patterns to follow, tests to write):',
    },
  },
  {
    id: 'create_pr_worker',
    label: 'Create Pull Request',
    description: 'Creates a GitHub pull request from completed implementation work.',
    requiresAutomationGate: true,
    category: 'platform',
    profile: 'on_demand',
    actionLabel: 'Create PR',
    applicableTypes: ['pull_request', 'task'],
  },
  {
    id: 'create_adr_worker',
    label: 'Create ADR',
    description: 'Authors an architecture decision record capturing context, options and decision.',
    requiresAutomationGate: true,
    category: 'quality',
    profile: 'on_demand',
    actionLabel: 'Create ADR',
    applicableTypes: ['adr'],
  },
  {
    id: 'gap_analysis_validator',
    label: 'Gap Analysis',
    description: 'Validates coverage and identifies missing requirements, test scenarios or traceability gaps.',
    requiresAutomationGate: false,
    category: 'quality',
    profile: 'scheduled',
    actionLabel: 'Run Gap Analysis',
    applicableTypes: ['prd', 'design', 'feature_spec', 'incident'],
  },
  {
    id: 'pr_design_validator',
    label: 'Validate PR vs Design',
    description: 'Validates that a pull request implements the design correctly. Raises findings for deviations.',
    requiresAutomationGate: false,
    category: 'quality',
    profile: 'realtime',
    actionLabel: 'Validate vs Design',
    applicableTypes: ['pull_request'],
    interaction: {
      kind: 'menu',
      prompt: 'Select action for finding: "Missing event deduplication guard"',
      options: ['Fix', 'Skip', 'Accept Risk'],
    },
  },
  {
    id: 'traceability_analysis',
    label: 'Traceability Analysis',
    description: 'Traces coverage from requirements through design, tasks, code and tests.',
    requiresAutomationGate: false,
    category: 'traceability',
    profile: 'scheduled',
    actionLabel: 'Analyze Traceability',
    applicableTypes: ['prd', 'design', 'decomposition'],
  },
  {
    id: 'stale_artifact_detection',
    label: 'Detect Stale Artifacts',
    description: 'Identifies artifacts that have drifted from source and need updating.',
    requiresAutomationGate: false,
    category: 'quality',
    profile: 'scheduled',
    actionLabel: 'Check Staleness',
    applicableTypes: ['task', 'feature_spec', 'design'],
  },
  {
    id: 'security_impact_analysis',
    label: 'Security Impact Analysis',
    description: 'Analyzes security implications of a pull request or design change.',
    requiresAutomationGate: false,
    category: 'security',
    profile: 'on_demand',
    actionLabel: 'Security Review',
    applicableTypes: ['pull_request', 'design'],
  },
  {
    id: 'object_graph_retriever',
    label: 'Retrieve Context',
    description: 'Retrieves relevant object context and related artifacts for analysis.',
    requiresAutomationGate: false,
    category: 'retrieval',
    profile: 'realtime',
    actionLabel: 'Retrieve Context',
    applicableTypes: ['prd', 'design', 'task', 'feature_spec'],
  },
  // F-028: replaced reverse_engineer_worker with doc-defined find_suspected_component
  {
    id: 'find_suspected_component',
    label: 'Find Suspected Component',
    description: 'Identifies the component most likely responsible for the bug',
    requiresAutomationGate: false,
    category: 'quality',
    profile: 'on_demand',
    actionLabel: 'Find Component',
    applicableTypes: ['incident', 'task'],
  },
  // F-016: validators required by bug_fix_flow per §22.2
  {
    id: 'bug_description_validator',
    label: 'Bug Description Validation',
    description: 'Validates that a bug report contains sufficient information for triage and reproduction.',
    requiresAutomationGate: false,
    category: 'quality',
    profile: 'on_demand',
    actionLabel: 'Validate Bug',
    applicableTypes: ['incident', 'task'],
  },
  {
    id: 'confirm_test_fails_validator',
    label: 'Confirm Test Fails',
    description: 'Confirms that the regression test for the bug fails before the fix is applied.',
    requiresAutomationGate: false,
    category: 'quality',
    profile: 'on_demand',
    actionLabel: 'Confirm Fails',
    applicableTypes: ['incident', 'task'],
  },
  {
    id: 'confirm_test_passes_validator',
    label: 'Confirm Test Passes',
    description: 'Confirms that the regression test passes after the fix is applied.',
    requiresAutomationGate: false,
    category: 'quality',
    profile: 'on_demand',
    actionLabel: 'Confirm Passes',
    applicableTypes: ['incident', 'task'],
  },
  // F-008: validators required by release_readiness_review per §22.2
  {
    id: 'test_coverage_validator',
    label: 'Test Coverage (>=80%)',
    description: 'Validates that test coverage meets or exceeds the 80% threshold.',
    requiresAutomationGate: false,
    category: 'quality',
    profile: 'scheduled',
    actionLabel: 'Check Coverage',
    applicableTypes: ['pull_request', 'task', 'feature_spec'],
  },
  {
    id: 'security_scan_validator',
    label: 'Security Scan',
    description: 'Runs automated security scanning against the release candidate.',
    requiresAutomationGate: false,
    category: 'security',
    profile: 'scheduled',
    actionLabel: 'Security Scan',
    applicableTypes: ['pull_request', 'design'],
  },
  {
    id: 'tech_lead_approval',
    label: 'Tech Lead Approval',
    description: 'Human approval gate requiring sign-off from a tech lead before release.',
    requiresAutomationGate: false,
    category: 'quality',
    profile: 'on_demand',
    actionLabel: 'Approve',
    applicableTypes: ['prd', 'design', 'pull_request'],
  },
]

// ─── Workers by Object Type ───────────────────────────────────────────────────

export function getWorkersForObject(typeId: string): WorkerDef[] {
  return WORKER_DEFS.filter(w => w.applicableTypes.includes(typeId as never))
}

// ─── Flow Definitions ─────────────────────────────────────────────────────────

export const FLOW_DEFS: FlowDef[] = [
  {
    id: 'sdlc_pipeline_flow',
    label: 'SDLC Pipeline',
    description: 'Full SDLC pipeline from PRD through design, decomposition, feature spec, implementation to pull request.',
    steps: [
      { id: 'step-prd',    workerId: 'create_prd_worker',        workerLabel: 'Create PRD',          objectTypeTarget: 'prd',          status: 'pending' },
      { id: 'step-adr',    workerId: 'create_adr_worker',        workerLabel: 'Create ADR',          objectTypeTarget: 'adr',          status: 'pending' },
      { id: 'step-design', workerId: 'create_design_worker',     workerLabel: 'Create Design',       objectTypeTarget: 'design',       status: 'pending' },
      { id: 'step-decomp', workerId: 'decompose_feature_worker', workerLabel: 'Decompose Tasks',     objectTypeTarget: 'decomposition', status: 'pending' },
      { id: 'step-fspec',  workerId: 'create_feature_spec_worker', workerLabel: 'Create Feature Spec', objectTypeTarget: 'feature_spec', status: 'pending' },
      { id: 'step-impl',   workerId: 'implement_code_worker',    workerLabel: 'Implement',           objectTypeTarget: 'task',         status: 'pending' },
      { id: 'step-pr',     workerId: 'create_pr_worker',         workerLabel: 'Create PR',           objectTypeTarget: 'pull_request', status: 'pending' },
    ],
  },
  // F-008/STALE-001: steps fixed to match §22.2 — gap analysis, test coverage, security scan, tech lead approval
  {
    id: 'release_readiness_review',
    label: 'Release Readiness Review',
    description: 'Pre-release quality gate: gap analysis, test coverage, security scan, and tech lead approval.',
    steps: [
      { id: 'step-gap',      workerId: 'gap_analysis_validator',    workerLabel: 'Gap Analysis',         objectTypeTarget: 'feature_spec', status: 'pending' },
      { id: 'step-coverage', workerId: 'test_coverage_validator',   workerLabel: 'Test Coverage (>=80%)', objectTypeTarget: 'pull_request', status: 'pending' },
      { id: 'step-security', workerId: 'security_scan_validator',   workerLabel: 'Security Scan',        objectTypeTarget: 'pull_request', status: 'pending' },
      { id: 'step-approval', workerId: 'tech_lead_approval',        workerLabel: 'Tech Lead Approval',   objectTypeTarget: 'pull_request', status: 'pending' },
    ],
  },
  // F-016: steps fixed to match §22.2 bug_to_fix_pr_flow
  {
    id: 'bug_fix_flow',
    label: 'Bug Fix Flow',
    description: 'Structured bug fix: validate description, implement fix, confirm tests, create PR.',
    steps: [
      { id: 'step-validate',       workerId: 'bug_description_validator',    workerLabel: 'Bug Description Validation', objectTypeTarget: 'incident',     status: 'pending' },
      { id: 'step-fix',            workerId: 'implement_code_worker',         workerLabel: 'Implement Fix',              objectTypeTarget: 'task',         status: 'pending' },
      { id: 'step-confirm-fails',  workerId: 'confirm_test_fails_validator',  workerLabel: 'Confirm Test Fails',         objectTypeTarget: 'task',         status: 'pending' },
      { id: 'step-confirm-passes', workerId: 'confirm_test_passes_validator', workerLabel: 'Confirm Test Passes',        objectTypeTarget: 'task',         status: 'pending' },
      { id: 'step-pr',             workerId: 'create_pr_worker',              workerLabel: 'Create Fix PR',              objectTypeTarget: 'pull_request', status: 'pending' },
    ],
  },
]

// ─── Recommendations ──────────────────────────────────────────────────────────

export const MOCK_RECOMMENDATIONS: Recommendation[] = [
  {
    id: 'rec-001',
    title: 'Invoice Generation Flow spec missing test scenarios',
    description: 'Feature spec "Invoice Generation Flow" has 0 test scenarios defined. This leaves the implementation unverifiable and risks regression.',
    severity: 'critical',
    state: 'pending',
    suggestedWorkerId: 'gap_analysis_validator',
    suggestedWorkerLabel: 'Gap Analysis',
    relatedObjectIds: ['fspec-002', 'task-002'],
    createdAt: '2026-07-06T07:00:00Z',
  },
  {
    id: 'rec-002',
    title: 'Billing Ledger Migration has no traceability markers in source code',
    description: 'Task "Billing Ledger Schema Migration" is marked done but no @cpt-* traceability markers were found in the merged code. Coverage gap detected.',
    severity: 'warning',
    state: 'pending',
    suggestedWorkerId: 'stale_artifact_detection',
    suggestedWorkerLabel: 'Detect Stale Artifacts',
    relatedObjectIds: ['task-003'],
    createdAt: '2026-07-05T16:00:00Z',
  },
  {
    id: 'rec-003',
    title: 'PR feat/stripe-webhook-handler has no security review',
    description: 'PR #247 has been in review for 2 days without a security impact analysis. Webhook handler touches payment data and should be reviewed.',
    severity: 'info',
    state: 'pending',
    suggestedWorkerId: 'security_impact_analysis',
    suggestedWorkerLabel: 'Security Impact Analysis',
    relatedObjectIds: ['pr-001'],
    createdAt: '2026-07-06T09:00:00Z',
  },
  {
    id: 'rec-004',
    title: 'Design references ADR-001 but no code implements event-driven pattern',
    description: 'Billing Service Architecture references event-driven pattern from ADR-001, but traceability analysis found no event bus implementation in merged code.',
    severity: 'warning',
    state: 'pending',
    suggestedWorkerId: 'traceability_analysis',
    suggestedWorkerLabel: 'Traceability Analysis',
    relatedObjectIds: ['design-001', 'adr-001'],
    createdAt: '2026-07-06T08:30:00Z',
  },
]

// ─── Flow Graph Definitions ───────────────────────────────────────────────────

import type { FlowGraphDef, KitDef, WorkspaceDef } from '../types/domain'

export const FLOW_GRAPH_DEFS: FlowGraphDef[] = [
  // ─── Flow 1: SDLC Pipeline (with branching + interactions) ─────────────────
  {
    id: 'flow-sdlc-pipeline',
    name: 'SDLC Pipeline',
    description: 'PRD → Design → Decompose → Implement → PR — with validation gates, branching decisions, and human interactions',
    category: 'sdlc',
    nodes: [
      { id: 'n-start',       nodeType: 'start',    label: 'Start',                                        position: { x: 280, y: 20 } },

      // Decision: how to create PRD?
      { id: 'n-prd-source',  nodeType: 'decision', label: 'PRD Source?',
        interaction: {
          kind: 'menu', prompt: 'How do you want to create the PRD?',
          options: [
            { id: 'author',   label: 'Author with AI', description: 'Use create_prd_worker to draft from intent', color: '#818cf8', nextNodeHint: 'n-prd' },
            { id: 'import',   label: 'Import from Confluence', description: 'Sync existing PRD via Connector',     color: '#22d3ee', nextNodeHint: 'n-import' },
          ]
        },
        position: { x: 260, y: 110 } },

      { id: 'n-import',      nodeType: 'worker',   label: 'Import PRD',        sublabel: 'script · connector', position: { x: 60,  y: 220 } },
      { id: 'n-prd',         nodeType: 'worker',   label: 'Create PRD',        sublabel: 'LLM · quality',      position: { x: 460, y: 220 } },

      // Gate: PRD valid?
      { id: 'n-gate-prd',    nodeType: 'gate',     label: 'PRD Valid?', maxRetries: 2,
        interaction: {
          kind: 'menu', prompt: 'Validation failed — how to proceed?',
          options: [
            { id: 'fix',     label: 'Fix gaps and retry', description: 'Re-run PRD worker with corrections', color: '#818cf8' },
            { id: 'risk',    label: 'Accept risk',        description: 'Create risk_acceptance Approval and continue', color: '#f59e0b' },
            { id: 'escalate',label: 'Escalate',           description: 'Block and notify tech lead', color: '#f87171' },
          ]
        },
        position: { x: 262, y: 340 } },

      { id: 'n-escalate-prd',nodeType: 'escalation',label: 'Escalate',                                   position: { x: 480, y: 340 } },
      { id: 'n-design',      nodeType: 'worker',   label: 'Create Design',     sublabel: 'LLM · quality',      position: { x: 260, y: 460 } },

      // Gate: Design valid?
      { id: 'n-gate-design', nodeType: 'gate',     label: 'Design Valid?', maxRetries: 2,
        interaction: {
          kind: 'menu', prompt: 'Design validation failed — what now?',
          options: [
            { id: 'fix',     label: 'Fix and retry',  description: 'Regenerate with gap feedback', color: '#818cf8' },
            { id: 'risk',    label: 'Accept risk',    description: 'Continue with known gaps',     color: '#f59e0b' },
          ]
        },
        position: { x: 262, y: 580 } },

      // Worker with mid-run interaction
      { id: 'n-decomp',      nodeType: 'worker',   label: 'Decompose Tasks',   sublabel: 'LLM · quality',
        interaction: {
          kind: 'menu', prompt: 'Choose task ordering strategy:',
          options: [
            { id: 'dependency', label: 'Dependency order', description: 'Critical path first — ensures unblocked execution', color: '#10b981' },
            { id: 'risk',       label: 'Risk-first',       description: 'Tackle high-risk tasks early for fast feedback',     color: '#f87171' },
            { id: 'value',      label: 'Value-first',      description: 'Deliver customer value as early as possible',        color: '#f59e0b' },
          ]
        },
        position: { x: 260, y: 700 } },

      { id: 'n-gate-decomp', nodeType: 'gate',     label: 'Tasks Valid?', maxRetries: 1, position: { x: 262, y: 820 } },
      { id: 'n-impl',        nodeType: 'worker',   label: 'Implement',         sublabel: 'LLM · coding',       position: { x: 260, y: 940 } },
      { id: 'n-gate-pr',     nodeType: 'gate',     label: 'PR Valid?', maxRetries: 3,
        interaction: {
          kind: 'menu', prompt: 'PR validation found issues — per-finding action:',
          options: [
            { id: 'fix',     label: 'Fix all findings',   description: 'Auto-fix with implement_code_worker', color: '#10b981' },
            { id: 'skip',    label: 'Skip minor issues',  description: 'Dismiss info-level findings',         color: '#f59e0b' },
            { id: 'risk',    label: 'Accept all risks',   description: 'Create risk_acceptance Approval',     color: '#f87171' },
          ]
        },
        position: { x: 262, y: 1060 } },
      { id: 'n-end',         nodeType: 'end',      label: 'Done',                                         position: { x: 278, y: 1180 } },
    ],
    edges: [
      { id: 'e1',  source: 'n-start',       target: 'n-prd-source',  edgeKind: 'default' },
      // Decision branches
      { id: 'e2a', source: 'n-prd-source',  target: 'n-prd',         edgeKind: 'branch', label: 'Author',  branchOptionId: 'author' },
      { id: 'e2b', source: 'n-prd-source',  target: 'n-import',      edgeKind: 'branch', label: 'Import',  branchOptionId: 'import' },
      // Merge both branches into gate
      { id: 'e3a', source: 'n-prd',         target: 'n-gate-prd',    edgeKind: 'default' },
      { id: 'e3b', source: 'n-import',      target: 'n-gate-prd',    edgeKind: 'default' },
      // Gate outcomes
      { id: 'e4',  source: 'n-gate-prd',    target: 'n-design',      edgeKind: 'pass',  label: 'PASS' },
      { id: 'e5',  source: 'n-gate-prd',    target: 'n-escalate-prd',edgeKind: 'fail',  label: 'Escalate', branchOptionId: 'escalate' },
      { id: 'e6',  source: 'n-gate-prd',    target: 'n-design',      edgeKind: 'pass',  label: 'Accept risk', branchOptionId: 'risk' },
      { id: 'e7',  source: 'n-gate-prd',    target: 'n-prd',         edgeKind: 'retry', label: 'retry',    branchOptionId: 'fix' },
      // Design
      { id: 'e8',  source: 'n-design',      target: 'n-gate-design', edgeKind: 'default' },
      { id: 'e9',  source: 'n-gate-design', target: 'n-decomp',      edgeKind: 'pass',  label: 'PASS' },
      { id: 'e10', source: 'n-gate-design', target: 'n-design',      edgeKind: 'retry', label: 'retry' },
      // Decompose + gate
      { id: 'e11', source: 'n-decomp',      target: 'n-gate-decomp', edgeKind: 'default' },
      { id: 'e12', source: 'n-gate-decomp', target: 'n-impl',        edgeKind: 'pass',  label: 'PASS' },
      { id: 'e13', source: 'n-gate-decomp', target: 'n-decomp',      edgeKind: 'retry', label: 'retry' },
      // Implement + PR gate
      { id: 'e14', source: 'n-impl',        target: 'n-gate-pr',     edgeKind: 'default' },
      { id: 'e15', source: 'n-gate-pr',     target: 'n-end',         edgeKind: 'pass',  label: 'PASS' },
      { id: 'e16', source: 'n-gate-pr',     target: 'n-impl',        edgeKind: 'retry', label: 'retry' },
    ],
  },

  // ─── Flow 2: Bug Fix (with branching + interactions) ───────────────────────
  {
    id: 'flow-bug-fix',
    name: 'Bug Fix',
    description: 'Bug report → environment choice → reproduce → test → fix → CI → PR',
    category: 'ops',
    nodes: [
      { id: 'b-start',    nodeType: 'start',    label: 'Bug Report',                                      position: { x: 200, y: 20 } },

      // Decision: environment
      { id: 'b-env',      nodeType: 'decision', label: 'Environment?',
        interaction: {
          kind: 'menu', prompt: 'Where to reproduce the bug?',
          options: [
            { id: 'staging', label: 'Staging',           description: 'Use shared staging environment (fast)', color: '#10b981' },
            { id: 'local',   label: 'Local dev env',     description: 'Reproduce on developer machine',        color: '#60a5fa' },
            { id: 'deploy',  label: 'Deploy test env',   description: 'Deploy isolated environment (slower)',  color: '#f59e0b' },
          ]
        },
        position: { x: 180, y: 110 } },

      { id: 'b-validate', nodeType: 'gate',     label: 'Bug Valid?', maxRetries: 1,
        interaction: {
          kind: 'menu', prompt: 'Bug validation failed — what to do?',
          options: [
            { id: 'info',   label: 'Request more info', description: 'Ask reporter for steps to reproduce', color: '#60a5fa' },
            { id: 'assume', label: 'Proceed with assumptions', description: 'Continue based on description', color: '#f59e0b' },
            { id: 'close',  label: 'Close as invalid',  description: 'Mark bug as not reproducible',        color: '#f87171' },
          ]
        },
        position: { x: 182, y: 220 } },

      { id: 'b-closed',   nodeType: 'escalation',label: 'Closed (invalid)',                               position: { x: 400, y: 220 } },
      { id: 'b-find',     nodeType: 'worker',   label: 'Find Component',    sublabel: 'script · ops',     position: { x: 180, y: 340 } },
      { id: 'b-reproduce',nodeType: 'worker',   label: 'Reproduce Bug',     sublabel: 'hybrid · ops',     position: { x: 180, y: 460 } },

      // Decision: TDD or not?
      { id: 'b-approach', nodeType: 'decision', label: 'Test approach?',
        interaction: {
          kind: 'menu', prompt: 'How do you want to approach the fix?',
          options: [
            { id: 'tdd',  label: 'Test-first (TDD)',           description: 'Write failing test, then fix', color: '#10b981' },
            { id: 'impl', label: 'Implement first',            description: 'Fix then add regression test', color: '#818cf8' },
          ]
        },
        position: { x: 180, y: 570 } },

      { id: 'b-test',     nodeType: 'worker',   label: 'Create Failing Test', sublabel: 'LLM · quality',  position: { x: 30,  y: 680 } },
      { id: 'b-fix',      nodeType: 'worker',   label: 'Implement Fix',       sublabel: 'LLM · coding',   position: { x: 180, y: 790 } },
      { id: 'b-gate-ci',  nodeType: 'gate',     label: 'CI Passes?', maxRetries: 3,
        interaction: {
          kind: 'menu', prompt: 'CI is failing — how to handle?',
          options: [
            { id: 'retry', label: 'Fix and retry',   description: 'Amend the implementation',   color: '#818cf8' },
            { id: 'issue', label: 'Open follow-up',  description: 'Merge with tech debt ticket', color: '#f59e0b' },
          ]
        },
        position: { x: 182, y: 910 } },
      { id: 'b-pr',       nodeType: 'worker',   label: 'Create PR',           sublabel: 'hybrid · platform', position: { x: 180, y: 1030 } },

      // Human approval
      { id: 'b-review',   nodeType: 'human',    label: 'Tech Lead Review',
        interaction: {
          kind: 'approval', prompt: 'Review the fix and approve or reject the PR.',
          options: [
            { id: 'approve', label: 'Approve & merge', color: '#10b981' },
            { id: 'changes', label: 'Request changes',  color: '#f59e0b' },
          ]
        },
        position: { x: 180, y: 1140 } },
      { id: 'b-end',      nodeType: 'end',      label: 'Fixed',                                           position: { x: 196, y: 1260 } },
    ],
    edges: [
      { id: 'f1',  source: 'b-start',    target: 'b-env',      edgeKind: 'default' },
      { id: 'f2',  source: 'b-env',      target: 'b-validate', edgeKind: 'branch', label: 'any env' },
      { id: 'f3',  source: 'b-validate', target: 'b-find',     edgeKind: 'pass',  label: 'Valid' },
      { id: 'f4',  source: 'b-validate', target: 'b-closed',   edgeKind: 'fail',  label: 'Close', branchOptionId: 'close' },
      { id: 'f4b', source: 'b-validate', target: 'b-find',     edgeKind: 'pass',  label: 'Assume', branchOptionId: 'assume' },
      { id: 'f5',  source: 'b-find',     target: 'b-reproduce',edgeKind: 'default' },
      { id: 'f6',  source: 'b-reproduce',target: 'b-approach', edgeKind: 'default' },
      // TDD branch
      { id: 'f7a', source: 'b-approach', target: 'b-test',     edgeKind: 'branch', label: 'TDD',  branchOptionId: 'tdd' },
      { id: 'f7b', source: 'b-test',     target: 'b-fix',      edgeKind: 'default' },
      // Impl-first branch
      { id: 'f8',  source: 'b-approach', target: 'b-fix',      edgeKind: 'branch', label: 'Impl', branchOptionId: 'impl' },
      { id: 'f9',  source: 'b-fix',      target: 'b-gate-ci',  edgeKind: 'default' },
      { id: 'f10', source: 'b-gate-ci',  target: 'b-pr',       edgeKind: 'pass',  label: 'PASS' },
      { id: 'f11', source: 'b-gate-ci',  target: 'b-fix',      edgeKind: 'retry', label: 'retry' },
      { id: 'f12', source: 'b-pr',       target: 'b-review',   edgeKind: 'default' },
      { id: 'f13', source: 'b-review',   target: 'b-end',      edgeKind: 'pass',  label: 'Approved', branchOptionId: 'approve' },
      { id: 'f14', source: 'b-review',   target: 'b-fix',      edgeKind: 'retry', label: 'Changes',  branchOptionId: 'changes' },
    ],
  },

  // ─── Flow 3: Release Readiness ──────────────────────────────────────────────
  {
    id: 'flow-release-readiness',
    name: 'Release Readiness',
    description: 'Traceability → Security → Approval — with interactive gap resolution',
    category: 'ops',
    nodes: [
      { id: 'r-start',      nodeType: 'start',      label: 'Release Candidate',                             position: { x: 220, y: 20 } },
      { id: 'r-trace',      nodeType: 'worker',      label: 'Traceability Analysis', sublabel: 'hybrid · traceability', position: { x: 160, y: 110 } },
      { id: 'r-gate-trace', nodeType: 'gate',        label: 'Coverage OK?', maxRetries: 2,
        interaction: {
          kind: 'menu', prompt: 'Traceability coverage is below threshold. How to proceed?',
          options: [
            { id: 'fix',   label: 'Fix coverage gaps', description: 'Run traceability_analysis with auto-fixes', color: '#818cf8' },
            { id: 'lower', label: 'Lower threshold',   description: 'Adjust min-coverage for this release',      color: '#f59e0b' },
            { id: 'block', label: 'Block release',     description: 'Fail the release until gaps are resolved',  color: '#f87171' },
          ]
        },
        position: { x: 182, y: 230 } },
      { id: 'r-version',    nodeType: 'decision',    label: 'Version bump?',
        interaction: {
          kind: 'menu', prompt: 'What kind of version bump does this release require?',
          options: [
            { id: 'patch', label: 'Patch (bug fixes)',      description: 'x.x.N — no API changes',     color: '#10b981' },
            { id: 'minor', label: 'Minor (new features)',   description: 'x.N.0 — backwards compatible',color: '#60a5fa' },
            { id: 'major', label: 'Major (breaking)',       description: 'N.0.0 — breaking API change', color: '#f87171' },
          ]
        },
        position: { x: 182, y: 350 } },
      { id: 'r-sec',        nodeType: 'worker',      label: 'Security Analysis',  sublabel: 'hybrid · security', position: { x: 160, y: 480 } },
      { id: 'r-gate-sec',   nodeType: 'gate',        label: 'Security OK?', maxRetries: 1,
        interaction: {
          kind: 'menu', prompt: 'Security issues found — how to handle?',
          options: [
            { id: 'fix',     label: 'Fix before release',  description: 'Block until security issues resolved', color: '#f87171' },
            { id: 'accept',  label: 'Accept with mitigations', description: 'Document and ship with workaround', color: '#f59e0b' },
          ]
        },
        position: { x: 182, y: 600 } },
      { id: 'r-escalate',   nodeType: 'escalation',  label: 'Security Blocked',                              position: { x: 400, y: 600 } },
      { id: 'r-approval',   nodeType: 'human',       label: 'Tech Lead Approval',
        interaction: {
          kind: 'approval', prompt: 'Review the release readiness report and approve or reject.',
          options: [
            { id: 'approve',  label: 'Approve release',  color: '#10b981' },
            { id: 'changes',  label: 'Request changes',   color: '#f59e0b' },
            { id: 'reject',   label: 'Reject release',    color: '#f87171' },
          ]
        },
        position: { x: 160, y: 720 } },
      { id: 'r-end',        nodeType: 'end',         label: 'Released',                                      position: { x: 196, y: 840 } },
      { id: 'r-blocked',    nodeType: 'escalation',  label: 'Release Blocked',                               position: { x: 400, y: 840 } },
    ],
    edges: [
      { id: 'r1', source: 'r-start',      target: 'r-trace',     edgeKind: 'default' },
      { id: 'r2', source: 'r-trace',      target: 'r-gate-trace',edgeKind: 'default' },
      { id: 'r3', source: 'r-gate-trace', target: 'r-version',   edgeKind: 'pass',  label: 'PASS' },
      { id: 'r4', source: 'r-gate-trace', target: 'r-trace',     edgeKind: 'retry', label: 'Fix & retry', branchOptionId: 'fix' },
      { id: 'r5', source: 'r-gate-trace', target: 'r-version',   edgeKind: 'pass',  label: 'Lower',       branchOptionId: 'lower' },
      { id: 'r6', source: 'r-version',    target: 'r-sec',       edgeKind: 'branch', label: 'any' },
      { id: 'r7', source: 'r-sec',        target: 'r-gate-sec',  edgeKind: 'default' },
      { id: 'r8', source: 'r-gate-sec',   target: 'r-approval',  edgeKind: 'pass',  label: 'PASS' },
      { id: 'r9', source: 'r-gate-sec',   target: 'r-escalate',  edgeKind: 'fail',  label: 'Block', branchOptionId: 'fix' },
      { id: 'r10',source: 'r-gate-sec',   target: 'r-approval',  edgeKind: 'pass',  label: 'Accept', branchOptionId: 'accept' },
      { id: 'r11',source: 'r-approval',   target: 'r-end',       edgeKind: 'pass',  label: 'Approved', branchOptionId: 'approve' },
      { id: 'r12',source: 'r-approval',   target: 'r-trace',     edgeKind: 'retry', label: 'Changes', branchOptionId: 'changes' },
      { id: 'r13',source: 'r-approval',   target: 'r-blocked',   edgeKind: 'fail',  label: 'Rejected', branchOptionId: 'reject' },
    ],
  },
]

// ─── Kit Definitions ─────────────────────────────────────────────────────────

export const KIT_DEFS: KitDef[] = [
  {
    id: 'kit-sdlc',
    name: 'SDLC Kit',
    description: 'Full software delivery lifecycle — PRD, Design, Decomposition, Feature Spec, Implementation, PR validation',
    version: '2.1.0',
    status: 'active',
    category: 'sdlc',
    workerCount: 14,
    connectorCount: 0,
    author: 'Constructor Fabric',
    tags: ['sdlc', 'quality', 'traceability'],
    installedAt: '2026-05-01T10:00:00Z',
    workers: [
      { id: 'create_prd_worker',          label: 'Create PRD',           category: 'quality' },
      { id: 'create_design_worker',       label: 'Create Design',        category: 'quality' },
      { id: 'decompose_feature_worker',   label: 'Decompose Feature',    category: 'quality' },
      { id: 'create_feature_spec_worker', label: 'Create Feature Spec',  category: 'quality' },
      { id: 'implement_code_worker',      label: 'Implement Code',       category: 'quality' },
      { id: 'create_adr_worker',          label: 'Create ADR',           category: 'quality' },
      { id: 'gap_analysis_validator',     label: 'Gap Analysis',         category: 'quality' },
      { id: 'pr_design_validator',        label: 'PR Design Validator',  category: 'quality' },
      { id: 'traceability_analysis',      label: 'Traceability Analysis',category: 'traceability' },
      { id: 'stale_artifact_detection',   label: 'Stale Detection',      category: 'quality' },
      { id: 'create_pr_worker',           label: 'Create Pull Request',  category: 'platform' },
      // F-028: replaced reverse_engineer_worker with find_suspected_component (doc-defined)
      { id: 'find_suspected_component',   label: 'Find Suspected Component', category: 'quality' },
      { id: 'object_graph_retriever',     label: 'Object Graph Retriever',category: 'retrieval' },
      // F-035: release_readiness_review is a Flow, not a plain Worker — listed for Kit inventory only
      { id: 'release_readiness_review',   label: 'Release Readiness',    category: 'ops' },
    ],
  },
  {
    id: 'kit-github',
    name: 'GitHub Connector',
    description: 'Sync repositories, pull requests, branches, commits, and CI runs from GitHub',
    version: '1.3.0',
    status: 'active',
    category: 'connector',
    workerCount: 4,
    connectorCount: 1,
    author: 'Constructor Fabric',
    tags: ['github', 'connector', 'ci'],
    installedAt: '2026-05-01T10:30:00Z',
    workers: [
      { id: 'github_sync_worker',  label: 'GitHub Sync',     category: 'platform' },
      { id: 'create_pr_worker',    label: 'Create PR',        category: 'platform' },
      { id: 'run_ci_worker',       label: 'Run CI',           category: 'ops' },
      { id: 'pr_status_worker',    label: 'PR Status',        category: 'ops' },
    ],
  },
  {
    id: 'kit-jira',
    name: 'Jira Connector',
    description: 'Sync tasks, epics, and bugs from Jira; write back on task state transitions',
    version: '1.1.0',
    status: 'active',
    category: 'connector',
    workerCount: 3,
    connectorCount: 1,
    author: 'Constructor Fabric',
    tags: ['jira', 'connector', 'tasks'],
    installedAt: '2026-05-02T09:00:00Z',
    workers: [
      { id: 'jira_sync_worker',    label: 'Jira Sync',        category: 'platform' },
      { id: 'jira_create_task',    label: 'Create Jira Task', category: 'platform' },
      { id: 'jira_update_status',  label: 'Update Status',    category: 'platform' },
    ],
  },
  {
    id: 'kit-saas',
    name: 'SaaS Multitenant Kit',
    description: 'Architecture patterns, validators, and workers for multi-tenant SaaS platforms',
    version: '1.0.0',
    latestVersion: '1.1.0',
    status: 'update_available',
    category: 'architecture',
    workerCount: 8,
    connectorCount: 0,
    author: 'Constructor Fabric',
    tags: ['saas', 'multitenant', 'rbac', 'security'],
    installedAt: '2026-05-10T14:00:00Z',
    workers: [
      { id: 'tenant_isolation_validator', label: 'Tenant Isolation Check', category: 'security' },
      { id: 'rbac_validator',            label: 'RBAC Validator',          category: 'security' },
      { id: 'multi_tenancy_analyzer',    label: 'Multi-tenancy Analyzer',  category: 'security' },
      { id: 'saas_perf_analyzer',        label: 'SaaS Perf Analyzer',      category: 'ops' },
      { id: 'billing_flow_validator',    label: 'Billing Flow Validator',  category: 'quality' },
      { id: 'api_gateway_validator',     label: 'API Gateway Validator',   category: 'quality' },
      { id: 'data_isolation_validator',  label: 'Data Isolation Check',    category: 'security' },
      { id: 'provisioning_worker',       label: 'Provisioning Worker',     category: 'ops' },
    ],
  },
  {
    id: 'kit-security',
    name: 'Security Analysis Kit',
    description: 'Security impact analysis, vulnerability scanning, dependency checks',
    version: '0.9.0',
    status: 'active',
    category: 'security',
    workerCount: 6,
    connectorCount: 0,
    author: 'Constructor Fabric',
    tags: ['security', 'vulnerability', 'compliance'],
    installedAt: '2026-05-15T11:00:00Z',
    workers: [
      { id: 'security_impact_analysis', label: 'Security Impact Analysis', category: 'security' },
      { id: 'dependency_scan_worker',   label: 'Dependency Scanner',       category: 'security' },
      { id: 'sast_worker',              label: 'SAST Analysis',            category: 'security' },
      { id: 'secret_scan_worker',       label: 'Secret Scanner',           category: 'security' },
      { id: 'compliance_validator',     label: 'Compliance Validator',     category: 'security' },
      { id: 'pentest_advisor_worker',   label: 'Pentest Advisor',          category: 'security' },
    ],
  },
]

// ─── Workspace Definitions ────────────────────────────────────────────────────

export const WORKSPACE_DEFS: WorkspaceDef[] = [
  {
    id: 'ws-billing',
    name: 'Billing Service',
    description: 'Multi-tenant billing service with Stripe integration',
    status: 'active',
    sources: [
      { id: 'src-1', url: 'github.com/acme/billing-service', role: 'main', branch: 'main', lastSyncedAt: '2026-07-08T09:15:00Z' },
      { id: 'src-2', url: 'github.com/acme/billing-docs', role: 'docs', branch: 'main', lastSyncedAt: '2026-07-08T09:10:00Z' },
    ],
    installedKitIds: ['kit-sdlc', 'kit-github', 'kit-jira', 'kit-saas', 'kit-security'],
    automationLevel: 'approved_automation',
    lastSyncedAt: '2026-07-08T09:15:00Z',
    objectCount: 47,
  },
  {
    id: 'ws-auth',
    name: 'Auth Platform',
    description: 'Identity and access management platform',
    status: 'offline',
    sources: [
      { id: 'src-3', url: 'github.com/acme/auth-platform', role: 'main', branch: 'main', lastSyncedAt: '2026-07-01T14:00:00Z' },
    ],
    installedKitIds: ['kit-sdlc', 'kit-github', 'kit-security'],
    automationLevel: 'recommendations',
    lastSyncedAt: '2026-07-01T14:00:00Z',
    objectCount: 31,
  },
  {
    id: 'ws-gateway',
    name: 'API Gateway',
    description: 'Central API gateway and routing layer',
    status: 'syncing',
    sources: [
      { id: 'src-4', url: 'github.com/acme/api-gateway', role: 'main', branch: 'main', lastSyncedAt: '2026-07-08T08:00:00Z' },
      { id: 'src-5', url: 'github.com/acme/gateway-config', role: 'platform', branch: 'main', lastSyncedAt: '2026-07-08T08:00:00Z' },
    ],
    installedKitIds: ['kit-sdlc', 'kit-github'],
    automationLevel: 'recommendations',
    lastSyncedAt: '2026-07-08T08:00:00Z',
    objectCount: 18,
  },
]

// ─── Mock Worker Run History ──────────────────────────────────────────────────

import type { WorkerRun } from '../types/domain'

function h(id: string, workerId: string, workerLabel: string, objectId: string, objectTitle: string,
           state: 'done'|'failed', startedAt: string, durationMs: number,
           costUsd: number, tokensIn: number, tokensOut: number, model: string,
           output?: string, error?: string): WorkerRun {
  const endDate = new Date(new Date(startedAt).getTime() + durationMs)
  return {
    id, workerId, workerLabel, objectId, objectTitle,
    state, progress: state === 'done' ? 100 : 0,
    startedAt, completedAt: endDate.toISOString(),
    costUsd, tokensIn, tokensOut, model, durationMs,
    output, error,
  }
}

export const MOCK_WORKER_RUNS: WorkerRun[] = [
  // PRD-001 — Billing Service v2
  h('hr-001','create_prd_worker','Create PRD','prd-001','Billing Service v2','done','2026-06-01T09:12:00Z',5200,0.38,12400,3100,'claude-sonnet-4-6','PRD created: 8 functional requirements, 4 non-functional, 6 use cases, 8 success criteria. Coverage: 100% actors defined.'),
  h('hr-002','gap_analysis_validator','Gap Analysis','prd-001','Billing Service v2','done','2026-06-01T09:18:00Z',2800,0.09,3200,820,'claude-haiku-4-5','Validation passed. All fr[] have success_criteria. R-005 has no linked test case — recommendation created.'),
  h('hr-003','gap_analysis_validator','Gap Analysis','prd-001','Billing Service v2','failed','2026-06-10T14:30:00Z',1900,0.07,2900,410,'claude-haiku-4-5',undefined,'Validation failed: 1 use-case references fr[] ID that does not exist. Retried manually.'),
  h('hr-004','traceability_analysis','Traceability Analysis','prd-001','Billing Service v2','done','2026-06-15T10:05:00Z',3400,0.12,4100,980,'claude-sonnet-4-6','Traceability: PRD → Design coverage 87%. R-003 fully traced to design + 2 tasks. R-005 not covered in any task.'),

  // Design-001 — Billing Service Architecture
  h('hr-010','object_graph_retriever','Object Graph Retriever','design-001','Billing Service Architecture','done','2026-06-02T10:00:00Z',1200,0.04,1800,240,'claude-haiku-4-5','Retrieved: 8 relevant Objects — PRD, 2 ADRs, 4 existing components, workspace config.'),
  h('hr-011','create_design_worker','Create Design','design-001','Billing Service Architecture','done','2026-06-02T10:02:00Z',8400,0.61,18200,5200,'claude-sonnet-4-6','Design created: 6 components, 12 API interfaces, 3 sequence diagrams. Architecture drivers linked to ADR-001, ADR-002.'),
  h('hr-012','gap_analysis_validator','Gap Analysis','design-001','Billing Service Architecture','failed','2026-06-02T10:16:00Z',2100,0.08,2800,380,'claude-haiku-4-5',undefined,'Validation failed: component[invoice_generator] missing input/output schema. Fixed and re-run.'),
  h('hr-013','gap_analysis_validator','Gap Analysis','design-001','Billing Service Architecture','done','2026-06-02T10:20:00Z',2400,0.09,3100,720,'claude-haiku-4-5','Validation passed. All 8 prd fr[] referenced in component[]. Event-driven pattern flagged as not yet implemented in code.'),
  h('hr-014','traceability_analysis','Traceability Analysis','design-001','Billing Service Architecture','done','2026-06-14T09:00:00Z',3100,0.11,3900,850,'claude-sonnet-4-6','Design → Code traceability: 92%. 5/6 components have merged PRs. billing_events bus — no implementation found.'),

  // ADR-001
  h('hr-020','object_graph_retriever','Object Graph Retriever','adr-001','Event-driven billing architecture','done','2026-05-30T14:00:00Z',900,0.03,1200,180,'claude-haiku-4-5','Retrieved: 3 related ADRs, existing event bus docs, competitor analysis.'),
  h('hr-021','create_adr_worker','Create ADR','adr-001','Event-driven billing architecture','done','2026-05-30T14:02:00Z',3800,0.24,7400,2100,'claude-sonnet-4-6','ADR created: 3 options analyzed, event-driven architecture selected. Positive consequences: scalability, loose coupling. Negative: complexity.'),
  h('hr-022','gap_analysis_validator','Gap Analysis','adr-001','Event-driven billing architecture','done','2026-05-30T14:08:00Z',1600,0.05,1900,420,'claude-haiku-4-5','Validation passed. >= 2 options present, decision outcome non-empty, consequences complete.'),

  // ADR-002
  h('hr-030','create_adr_worker','Create ADR','adr-002','PostgreSQL for billing ledger','done','2026-05-31T09:00:00Z',3200,0.21,6800,1900,'claude-sonnet-4-6','ADR created: PostgreSQL vs CockroachDB vs Cassandra. PostgreSQL selected for ACID compliance and operational familiarity.'),
  h('hr-031','gap_analysis_validator','Gap Analysis','adr-002','PostgreSQL for billing ledger','done','2026-05-31T09:07:00Z',1500,0.05,1800,380,'claude-haiku-4-5','Validation passed. No migration plan documented — info recommendation created.'),

  // Task-001 — Stripe Webhook Handler
  h('hr-040','create_feature_spec_worker','Create Feature Spec','task-001','Implement Stripe Webhook Handler','done','2026-06-05T11:00:00Z',6100,0.44,14200,4100,'claude-sonnet-4-6','Feature spec created: 3 GIVEN/WHEN/THEN flows, 2 algo blocks, 4 test scenarios (2 happy path, 2 error cases).'),
  h('hr-041','implement_code_worker','Implement Code','task-001','Implement Stripe Webhook Handler','done','2026-06-06T09:00:00Z',9200,0.71,22100,6800,'claude-sonnet-4-6','Implementation: StripeWebhookHandler class, signature validation, event routing. 847 lines. @cpt- markers for all 3 flow IDs.'),
  h('hr-042','pr_design_validator','PR Design Validator','task-001','Implement Stripe Webhook Handler','failed','2026-06-06T10:30:00Z',3400,0.14,4200,920,'claude-haiku-4-5',undefined,'Validation failed: handlePaymentFailed missing domain event emission. Fix required.'),
  h('hr-043','implement_code_worker','Implement Code','task-001','Implement Stripe Webhook Handler','done','2026-06-06T11:00:00Z',4100,0.32,9800,2900,'claude-sonnet-4-6','Fix applied: added billing.payment_failed event emission. Updated tests.'),
  h('hr-044','pr_design_validator','PR Design Validator','task-001','Implement Stripe Webhook Handler','done','2026-06-06T11:45:00Z',2900,0.10,3600,780,'claude-haiku-4-5','Validation passed. Evidence attached. PR ready for review.'),

  // Task-002 — Invoice Generation (draft, less history)
  h('hr-050','gap_analysis_validator','Gap Analysis','task-002','Implement Invoice Generation Worker','failed','2026-06-08T14:00:00Z',1800,0.06,2200,290,'claude-haiku-4-5',undefined,'Validation failed: feature_spec not approved. No test scenarios defined. 2 critical gaps found.'),

  // Task-003 — Schema Migration
  h('hr-060','implement_code_worker','Implement Code','task-003','Billing Ledger Schema Migration','done','2026-06-03T09:00:00Z',5800,0.42,13200,3900,'claude-sonnet-4-6','Migration created: CREATE TABLE billing_ledger, 3 indices, UNIQUE constraint on (tenant_id, invoice_id). Rollback script included.'),
  h('hr-061','gap_analysis_validator','Gap Analysis','task-003','Billing Ledger Schema Migration','done','2026-06-03T10:00:00Z',1400,0.04,1600,340,'claude-haiku-4-5','Validation passed. Migration is idempotent. All constraints verified.'),
  h('hr-062','traceability_analysis','Traceability Analysis','task-003','Billing Ledger Schema Migration','done','2026-06-03T10:10:00Z',2200,0.08,2800,560,'claude-haiku-4-5','Traceability: task-003 → design component[billing_ledger]. Coverage: 100%.'),

  // fspec-001 — Stripe Webhook
  h('hr-070','create_feature_spec_worker','Create Feature Spec','fspec-001','Stripe Webhook Flow','done','2026-06-04T13:00:00Z',5900,0.43,13800,4000,'claude-sonnet-4-6','Feature spec: 3 flows, 4 algo blocks, 6 test scenarios. All flows have >=1 happy + >=1 error case.'),
  h('hr-071','gap_analysis_validator','Gap Analysis','fspec-001','Stripe Webhook Flow','done','2026-06-04T14:02:00Z',2100,0.07,2400,580,'claude-haiku-4-5','Validation passed. 1 error scenario missing repro steps — info recommendation. Evidence attached.'),

  // fspec-002 — Invoice Generation (draft, problems)
  h('hr-080','create_feature_spec_worker','Create Feature Spec','fspec-002','Invoice Generation Flow','failed','2026-06-09T10:00:00Z',4200,0.31,9800,1200,'claude-sonnet-4-6',undefined,'Generation failed: insufficient context. No approved design components referenced. Re-run after design approval.'),
  h('hr-081','gap_analysis_validator','Gap Analysis','fspec-002','Invoice Generation Flow','failed','2026-06-09T11:00:00Z',1600,0.05,1900,280,'claude-haiku-4-5',undefined,'Validation failed: no test scenarios, missing algo blocks for invoice calculation logic.'),

  // PR-001 — feat/stripe-webhook-handler
  h('hr-090','pr_design_validator','PR Design Validator','pr-001','feat/stripe-webhook-handler','failed','2026-06-06T10:30:00Z',3400,0.14,4200,920,'claude-haiku-4-5',undefined,'PR validation failed: handlePaymentFailed missing domain event emission.'),
  h('hr-091','pr_design_validator','PR Design Validator','pr-001','feat/stripe-webhook-handler','done','2026-06-06T11:45:00Z',2900,0.10,3600,780,'claude-haiku-4-5','PR validation passed. Conformance to design confirmed. Evidence attached.'),
  h('hr-092','security_impact_analysis','Security Impact Analysis','pr-001','feat/stripe-webhook-handler','done','2026-06-07T09:00:00Z',3800,0.14,4600,1100,'claude-haiku-4-5','Security review: HMAC validation present. Webhook secret properly managed. No PII logged. Recommendation: add rate limiting.'),

  // Incident-001
  h('hr-100','gap_analysis_validator','Gap Analysis','incident-001','Billing duplicate charge INC-441','failed','2026-07-06T08:00:00Z',1200,0.04,1400,180,'claude-haiku-4-5',undefined,'Analysis failed: root cause not documented. No postmortem linked. 2 critical gaps.'),
]
