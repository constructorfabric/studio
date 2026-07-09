export interface CptIdentifier {
  id: string                    // e.g. 'cpt-billing-fr-webhook-ingestion'
  system: string                // 'billing'
  kind: string                  // 'fr', 'component', etc.
  slug: string                  // 'webhook-ingestion'
  name: string                  // human label: 'Webhook Ingestion'
  description: string           // one-line description
  definedIn: {
    fileId: string              // file-mock-data key
    documentTitle: string       // 'Billing Service v2 PRD'
    artifactType: string        // 'PRD', 'DESIGN', 'DECOMPOSITION', 'ADR'
  }
  references: {                 // other documents that reference this id
    fileId: string
    documentTitle: string
    artifactType: string
    context: string             // e.g. 'Architecture Drivers', 'Feature Entry'
  }[]
}

// Full registry for our billing demo
export const CPT_REGISTRY: Record<string, CptIdentifier> = {

  // ── PRD: Functional Requirements ─────────────────────────────────────────
  'cpt-billing-fr-webhook-ingestion': {
    id: 'cpt-billing-fr-webhook-ingestion', system: 'billing', kind: 'fr', slug: 'webhook-ingestion',
    name: 'Webhook Ingestion',
    description: 'The system shall accept, verify HMAC signatures, and dispatch Stripe webhook events to the internal billing event bus.',
    definedIn: { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD' },
    references: [
      { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN', context: 'Architecture Drivers — Functional Drivers' },
      { fileId: 'file-webhook-spec', documentTitle: 'Stripe Webhook Flow', artifactType: 'FEATURE', context: 'Feature Context — References' },
    ],
  },
  'cpt-billing-fr-invoice-generation': {
    id: 'cpt-billing-fr-invoice-generation', system: 'billing', kind: 'fr', slug: 'invoice-generation',
    name: 'Invoice Generation',
    description: 'The system shall asynchronously generate PDF invoices from billing events and store them in S3.',
    definedIn: { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD' },
    references: [
      { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN', context: 'Architecture Drivers — Functional Drivers' },
      { fileId: 'file-feat-invoice', documentTitle: 'Invoice Generation Flow', artifactType: 'FEATURE', context: 'Feature Context — References' },
    ],
  },
  'cpt-billing-fr-ledger-partitioning': {
    id: 'cpt-billing-fr-ledger-partitioning', system: 'billing', kind: 'fr', slug: 'ledger-partitioning',
    name: 'Ledger Partitioning',
    description: 'The billing ledger shall be partitioned by tenant_id and month to support high-volume transaction data.',
    definedIn: { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD' },
    references: [
      { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN', context: 'Database schemas — billing_ledger' },
      { fileId: 'file-adr-002', documentTitle: 'PostgreSQL for billing ledger', artifactType: 'ADR', context: 'Decision Outcome' },
    ],
  },
  'cpt-billing-nfr-throughput': {
    id: 'cpt-billing-nfr-throughput', system: 'billing', kind: 'nfr', slug: 'throughput',
    name: 'Webhook Throughput',
    description: 'The system shall process >= 1 000 webhook events/second sustained, >= 5 000 peak.',
    definedIn: { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD' },
    references: [
      { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN', context: 'NFR Allocation — throughput' },
    ],
  },
  'cpt-billing-nfr-latency': {
    id: 'cpt-billing-nfr-latency', system: 'billing', kind: 'nfr', slug: 'latency',
    name: 'Webhook Acknowledgement Latency',
    description: 'Webhook acknowledgement p99 <= 200 ms; invoice generation p99 <= 30 s.',
    definedIn: { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD' },
    references: [
      { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN', context: 'NFR Allocation — latency' },
    ],
  },
  'cpt-billing-actor-tenant': {
    id: 'cpt-billing-actor-tenant', system: 'billing', kind: 'actor', slug: 'tenant',
    name: 'Tenant (Customer)',
    description: 'A paying customer organisation whose billing events, invoices, and ledger entries are managed by the system.',
    definedIn: { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD' },
    references: [],
  },
  'cpt-billing-usecase-stripe-payment': {
    id: 'cpt-billing-usecase-stripe-payment', system: 'billing', kind: 'usecase', slug: 'stripe-payment',
    name: 'Process Stripe Payment Event',
    description: 'A payment_intent.succeeded event arrives -> verified -> invoice generated -> ledger updated -> tenant notified.',
    definedIn: { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD' },
    references: [
      { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN', context: 'Interactions & Sequences — webhook-to-invoice' },
      { fileId: 'file-webhook-spec', documentTitle: 'Stripe Webhook Flow', artifactType: 'FEATURE', context: 'Actor Flows' },
    ],
  },

  // ── DESIGN: Components ────────────────────────────────────────────────────
  'cpt-billing-component-webhook-handler': {
    id: 'cpt-billing-component-webhook-handler', system: 'billing', kind: 'component', slug: 'webhook-handler',
    name: 'Webhook Handler',
    description: 'Ingests raw Stripe events via HTTP, verifies HMAC signatures, deduplicates, and publishes to internal event bus.',
    definedIn: { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN' },
    references: [
      { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD', context: 'FR — webhook ingestion' },
      { fileId: 'file-webhook-handler', documentTitle: 'feat/stripe-webhook-handler', artifactType: 'CODE', context: 'Implementation' },
    ],
  },
  'cpt-billing-component-invoice-service': {
    id: 'cpt-billing-component-invoice-service', system: 'billing', kind: 'component', slug: 'invoice-service',
    name: 'Invoice Service',
    description: 'Subscribes to billing events, generates PDF invoices asynchronously, stores in S3, and notifies tenants.',
    definedIn: { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN' },
    references: [
      { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD', context: 'FR — invoice generation' },
      { fileId: 'file-feat-invoice', documentTitle: 'Invoice Generation Flow', artifactType: 'FEATURE', context: 'Feature Context' },
    ],
  },
  'cpt-billing-component-billing-ledger': {
    id: 'cpt-billing-component-billing-ledger', system: 'billing', kind: 'component', slug: 'billing-ledger',
    name: 'Billing Ledger',
    description: 'Append-only PostgreSQL ledger partitioned by tenant_id + month; the authoritative record of all billing transactions.',
    definedIn: { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN' },
    references: [
      { fileId: 'file-adr-002', documentTitle: 'PostgreSQL for billing ledger', artifactType: 'ADR', context: 'Decision Outcome' },
    ],
  },
  'cpt-billing-constraint-data-isolation': {
    id: 'cpt-billing-constraint-data-isolation', system: 'billing', kind: 'constraint', slug: 'data-isolation',
    name: 'Tenant Data Isolation',
    description: 'All ledger and invoice data must be strictly partitioned by tenant_id; no cross-tenant queries are permitted.',
    definedIn: { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN' },
    references: [
      { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD', context: 'NFR — security' },
    ],
  },
  'cpt-billing-principle-event-driven': {
    id: 'cpt-billing-principle-event-driven', system: 'billing', kind: 'principle', slug: 'event-driven',
    name: 'Event-Driven Processing',
    description: 'All billing processing is asynchronous and event-driven; the webhook handler never blocks on invoice generation.',
    definedIn: { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN' },
    references: [
      { fileId: 'file-adr-001', documentTitle: 'Event-driven billing architecture', artifactType: 'ADR', context: 'Decision Outcome' },
    ],
  },
  'cpt-billing-dbtable-billing-ledger': {
    id: 'cpt-billing-dbtable-billing-ledger', system: 'billing', kind: 'dbtable', slug: 'billing-ledger',
    name: 'billing_ledger (table)',
    description: 'PostgreSQL table: billing_ledger (tenant_id, invoice_id, amount_cents, currency, event_type, created_at). Partitioned by tenant_id, month.',
    definedIn: { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN' },
    references: [
      { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD', context: 'FR — ledger partitioning' },
    ],
  },
  'cpt-billing-seq-webhook-to-invoice': {
    id: 'cpt-billing-seq-webhook-to-invoice', system: 'billing', kind: 'seq', slug: 'webhook-to-invoice',
    name: 'Webhook -> Invoice Sequence',
    description: 'Stripe sends event -> Webhook Handler verifies + dispatches -> Invoice Service generates PDF -> S3 + notify.',
    definedIn: { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN' },
    references: [
      { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD', context: 'Use Cases — stripe-payment' },
    ],
  },

  // ── ADR identifiers ───────────────────────────────────────────────────────
  'cpt-billing-adr-event-driven-arch': {
    id: 'cpt-billing-adr-event-driven-arch', system: 'billing', kind: 'adr', slug: 'event-driven-arch',
    name: 'ADR-001: Event-Driven Architecture',
    description: 'Decision to use event-driven architecture for billing processing.',
    definedIn: { fileId: 'file-adr-001', documentTitle: 'Event-driven billing architecture', artifactType: 'ADR' },
    references: [
      { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN', context: 'Architecture Drivers' },
      { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD', context: 'NFR — reliability' },
    ],
  },
  'cpt-billing-adr-postgresql-ledger': {
    id: 'cpt-billing-adr-postgresql-ledger', system: 'billing', kind: 'adr', slug: 'postgresql-ledger',
    name: 'ADR-002: PostgreSQL Ledger',
    description: 'Decision to use PostgreSQL with partitioning for the billing ledger.',
    definedIn: { fileId: 'file-adr-002', documentTitle: 'PostgreSQL for billing ledger', artifactType: 'ADR' },
    references: [
      { fileId: 'file-design', documentTitle: 'Billing Service Architecture', artifactType: 'DESIGN', context: 'Database schemas' },
      { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD', context: 'FR — ledger partitioning' },
    ],
  },

  // ── FEATURE / FEATURE SPEC identifiers ───────────────────────────────────
  'cpt-billing-flow-stripe-webhook-happy': {
    id: 'cpt-billing-flow-stripe-webhook-happy', system: 'billing', kind: 'flow', slug: 'stripe-webhook-happy',
    name: 'Stripe Webhook — Happy Path',
    description: 'GIVEN valid Stripe event WHEN received THEN verify HMAC, dispatch to bus, return 200.',
    definedIn: { fileId: 'file-feat-stripe', documentTitle: 'Stripe Webhook Flow', artifactType: 'FEATURE' },
    references: [
      { fileId: 'file-prd', documentTitle: 'Billing Service v2 PRD', artifactType: 'PRD', context: 'Use Cases — stripe-payment' },
      { fileId: 'file-webhook-handler', documentTitle: 'feat/stripe-webhook-handler', artifactType: 'CODE', context: 'Implementation' },
    ],
  },
  'cpt-billing-dod-webhook-handler-impl': {
    id: 'cpt-billing-dod-webhook-handler-impl', system: 'billing', kind: 'dod', slug: 'webhook-handler-impl',
    name: 'DoD: Webhook Handler Implementation',
    description: 'StripeWebhookHandler class with HMAC verification, event routing, idempotency guards, and error handling implemented and tested.',
    definedIn: { fileId: 'file-feat-stripe', documentTitle: 'Stripe Webhook Flow', artifactType: 'FEATURE' },
    references: [
      { fileId: 'file-webhook-handler', documentTitle: 'feat/stripe-webhook-handler', artifactType: 'CODE', context: 'PR implements this DoD' },
    ],
  },
}

// Helper: find all identifiers referenced in a given file
export function getCptIdsForFile(fileId: string): CptIdentifier[] {
  return Object.values(CPT_REGISTRY).filter(
    id => id.definedIn.fileId === fileId || id.references.some(r => r.fileId === fileId)
  )
}

// Helper: get all ids that are defined in a file (definition site)
export function getCptDefinitionsInFile(fileId: string): CptIdentifier[] {
  return Object.values(CPT_REGISTRY).filter(id => id.definedIn.fileId === fileId)
}

// Helper: find the definition file for an id string
export function getCptById(id: string): CptIdentifier | undefined {
  return CPT_REGISTRY[id]
}
