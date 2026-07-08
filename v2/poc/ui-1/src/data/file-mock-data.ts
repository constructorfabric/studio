export interface FileNode {
  id: string
  name: string
  type: 'file' | 'folder'
  children?: FileNode[]
  language?: 'markdown' | 'typescript' | 'sql' | 'toml' | 'text'
  linkedObjectId?: string  // links to a Studio object id
  isDraft?: boolean
}

export const FILE_TREE: FileNode[] = [
  {
    id: 'folder-bootstrap',
    name: '.bootstrap',
    type: 'folder',
    children: [
      { id: 'file-studio-toml', name: 'studio.toml', type: 'file', language: 'toml' },
      {
        id: 'folder-kits',
        name: 'kits',
        type: 'folder',
        children: [
          { id: 'file-saas-kit', name: 'saas-kit.toml', type: 'file', language: 'toml' }
        ]
      }
    ]
  },
  {
    id: 'folder-docs',
    name: 'docs',
    type: 'folder',
    children: [
      { id: 'file-prd', name: 'PRD.md', type: 'file', language: 'markdown', linkedObjectId: 'obj-prd' },
      { id: 'file-design', name: 'DESIGN.md', type: 'file', language: 'markdown', linkedObjectId: 'obj-design' },
      { id: 'file-adr-001', name: 'ADR-001-event-driven.md', type: 'file', language: 'markdown', linkedObjectId: 'obj-adr-1' },
      { id: 'file-adr-002', name: 'ADR-002-postgresql.md', type: 'file', language: 'markdown', linkedObjectId: 'obj-adr-2' },
      {
        id: 'folder-features',
        name: 'features',
        type: 'folder',
        children: [
          { id: 'file-feat-stripe', name: 'FEAT-stripe-webhook.md', type: 'file', language: 'markdown', linkedObjectId: 'obj-fspec-stripe' },
          { id: 'file-feat-invoice', name: 'FEAT-invoice-gen.md', type: 'file', language: 'markdown', linkedObjectId: 'obj-fspec-invoice', isDraft: true }
        ]
      }
    ]
  },
  {
    id: 'folder-src',
    name: 'src',
    type: 'folder',
    children: [
      {
        id: 'folder-billing',
        name: 'billing',
        type: 'folder',
        children: [
          { id: 'file-webhook-handler', name: 'webhook-handler.ts', type: 'file', language: 'typescript' },
          { id: 'file-invoice-gen', name: 'invoice-generator.ts', type: 'file', language: 'typescript' },
          { id: 'file-ledger', name: 'ledger.ts', type: 'file', language: 'typescript' }
        ]
      },
      {
        id: 'folder-migrations',
        name: 'migrations',
        type: 'folder',
        children: [
          { id: 'file-migration-001', name: '001_billing_schema.sql', type: 'file', language: 'sql' }
        ]
      }
    ]
  },
  {
    id: 'folder-tests',
    name: 'tests',
    type: 'folder',
    children: [
      { id: 'file-webhook-spec', name: 'webhook-handler.spec.ts', type: 'file', language: 'typescript' }
    ]
  }
]

export const FILE_CONTENTS: Record<string, string> = {
  'file-prd': `# Billing Service v2 — Product Requirements

## Overview

The Billing Service v2 is a cloud-native microservice responsible for processing payments,
generating invoices, and maintaining a tamper-proof financial ledger for the SaaS platform.

**Version:** 2.0  
**Status:** Draft  
**Authors:** Platform Team  
**Date:** 2026-01-15

---

## Actors

| Actor | Description |
|-------|-------------|
| Customer | End-user who initiates subscriptions and views invoices |
| Stripe | External payment processor providing webhook events |
| Billing Admin | Internal operator who manages billing rules and disputes |
| Audit System | Downstream consumer of ledger events for compliance |

---

## Functional Requirements

### R-001 — Webhook Ingestion
The system SHALL receive and validate Stripe webhook events via HMAC-SHA256 signature verification.

### R-002 — Event Routing
The system SHALL route validated events to appropriate domain handlers based on event type.

### R-003 — Invoice Generation
The system SHALL generate PDF invoices upon successful payment events within 30 seconds.

### R-004 — Ledger Recording
The system SHALL record every financial transaction in an append-only PostgreSQL ledger.

### R-005 — Idempotency
The system SHALL ensure idempotent processing of webhook events using Stripe event IDs.

### R-006 — Retry Handling
The system SHALL handle payment failures with configurable retry schedules (3 attempts, exponential backoff).

### R-007 — Audit Trail
The system SHALL emit structured events to the Audit System for every state transition.

### R-008 — Invoice Retrieval
The system SHALL expose a REST API for customers to retrieve their invoice history.

---

## Non-Functional Requirements

- **Availability:** 99.9% uptime SLA
- **Latency:** Webhook processing < 200ms p99
- **Throughput:** 500 events/second sustained
- **Data Retention:** 7 years for financial records
- **Security:** TLS 1.3, secrets via Vault, no PII in logs

---

## Success Criteria

- [ ] Zero missed Stripe events over 30-day period
- [ ] Invoice generation latency < 30s
- [ ] All ledger entries pass double-entry bookkeeping validation
- [ ] 100% audit trail coverage for financial events
`,

  'file-design': `# Billing Service v2 — System Design

## Architecture Overview

The Billing Service follows a hexagonal (ports-and-adapters) architecture with an
event-driven core. External systems communicate via webhooks and REST; internal
components communicate via domain events on an in-process event bus.

\`\`\`
┌─────────────────────────────────────────────────────────┐
│                    Billing Service                       │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │   Webhook    │───▶│   Domain     │───▶│  Ledger  │  │
│  │   Handler    │    │   Events     │    │ Service  │  │
│  └──────────────┘    └──────────────┘    └──────────┘  │
│                             │                           │
│                      ┌──────┴──────┐                   │
│                      │  Invoice    │                   │
│                      │ Generator  │                   │
│                      └─────────────┘                   │
└─────────────────────────────────────────────────────────┘
         │                                      │
    ┌────┴────┐                          ┌──────┴─────┐
    │ Stripe  │                          │ PostgreSQL  │
    └─────────┘                          └────────────┘
\`\`\`

---

## Components

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| WebhookHandler | Signature validation, event parsing | Node.js, crypto |
| InvoiceGenerator | PDF generation, S3 upload | PDFKit, AWS S3 |
| LedgerService | Double-entry bookkeeping | PostgreSQL, Knex |
| EventBus | Internal domain event routing | Node EventEmitter |
| RetryScheduler | Failed payment retry logic | Bull queue |

---

## Sequence Diagram — Payment Success Flow

\`\`\`mermaid
sequenceDiagram
    participant Stripe
    participant WebhookHandler
    participant EventBus
    participant InvoiceGenerator
    participant LedgerService

    Stripe->>WebhookHandler: POST /webhooks/stripe
    WebhookHandler->>WebhookHandler: validateSignature()
    WebhookHandler->>EventBus: emit(billing.payment_succeeded)
    EventBus->>InvoiceGenerator: onPaymentSucceeded()
    EventBus->>LedgerService: onPaymentSucceeded()
    InvoiceGenerator-->>Stripe: (async) PDF generated
    LedgerService-->>Stripe: (async) ledger entry created
\`\`\`

---

## Interface Definitions

### WebhookHandler
\`\`\`typescript
interface IWebhookHandler {
  handleWebhook(payload: Buffer, signature: string): Promise<void>
}
\`\`\`

### LedgerService
\`\`\`typescript
interface ILedgerService {
  record(entry: LedgerEntry): Promise<string>  // returns entry ID
  getHistory(customerId: string): Promise<LedgerEntry[]>
}
\`\`\`

### InvoiceGenerator
\`\`\`typescript
interface IInvoiceGenerator {
  generate(event: PaymentSucceededEvent): Promise<string>  // returns PDF URL
}
\`\`\`
`,

  'file-adr-001': `# ADR-001 — Event-Driven Billing Architecture

**Status:** Accepted  
**Date:** 2026-01-10  
**Authors:** Platform Team

---

## Context

The previous billing system used synchronous REST calls between components,
causing cascading failures when downstream services were slow or unavailable.
Payment processing latency was unacceptably high (p99 > 2s).

---

## Decision Drivers

- Decouple payment processing from invoice generation
- Improve resilience: partial failures should not block payment recording
- Enable independent scaling of invoice generation
- Support audit trail requirements without coupling to business logic

---

## Options Considered

### Option A: Synchronous REST (status quo)
- Pro: Simple, easy to debug
- Con: Tight coupling, cascading failures, high latency

### Option B: Message Queue (RabbitMQ/Kafka)
- Pro: Full decoupling, replay capability
- Con: Operational complexity, additional infrastructure

### Option C: In-process Event Emitter + PostgreSQL outbox
- Pro: Low latency, no external dependencies, transactional consistency
- Con: Not distributed (single process), limited replay

---

## Decision

We adopt **Option C** for the initial v2 release: an in-process EventEmitter for
domain event routing, with a PostgreSQL outbox table for durability and replay.

This gives us event-driven semantics without introducing Kafka operational overhead
at our current scale (< 500 events/second).

---

## Consequences

**Positive:**
- Invoice generation failures do not block payment recording
- Ledger writes are transactionally consistent with outbox entries
- Zero new infrastructure dependencies

**Negative:**
- Cannot scale invoice generator independently from webhook handler
- No cross-service event consumption (revisit when we need that)
- Outbox polling adds ~100ms latency to downstream consumers
`,

  'file-adr-002': `# ADR-002 — PostgreSQL for Ledger Storage

**Status:** Accepted  
**Date:** 2026-01-12  
**Authors:** Platform Team

---

## Context

The billing ledger requires ACID guarantees, complex querying for reconciliation,
and 7-year retention with audit trail integrity. We need to choose a storage backend.

---

## Decision Drivers

- ACID transactions for double-entry bookkeeping
- Complex SQL queries for reconciliation reports
- Familiarity: team has deep PostgreSQL expertise
- Row-level security for multi-tenant isolation

---

## Options Considered

### Option A: PostgreSQL
- Pro: ACID, familiar, row-level security, JSONB for flexible data
- Con: Vertical scaling limits, not optimized for time-series

### Option B: DynamoDB
- Pro: Horizontal scale, managed
- Con: No complex queries, eventual consistency risks for financial data

### Option C: CockroachDB
- Pro: Distributed ACID
- Con: Unfamiliar, licensing cost

---

## Decision

**PostgreSQL** with append-only ledger table, row-level security per tenant,
and read replicas for reporting queries.

---

## Consequences

- Single-region write endpoint (acceptable for current scale)
- Reconciliation queries can use standard SQL window functions
- Leverage existing PostgreSQL expertise and tooling
`,

  'file-feat-stripe': `# FEAT-stripe-webhook — Stripe Webhook Processing

**Status:** Implemented  
**Linked PRD Requirements:** R-001, R-002, R-005, R-007  
**Linked Design Components:** WebhookHandler, EventBus

---

## Overview

Receive, validate, and route Stripe webhook events to domain handlers.

---

## Flows

### Flow-001 — Webhook Ingestion
1. Stripe POSTs event to \`/webhooks/stripe\`
2. Extract \`stripe-signature\` header
3. Validate HMAC-SHA256 signature using webhook secret
4. Parse JSON payload
5. Check idempotency: if event ID already processed, return 200 immediately
6. Route to appropriate handler
7. Return 200 OK

### Flow-002 — Signature Validation
1. Reconstruct signed payload: \`{timestamp}.{body}\`
2. Compute HMAC-SHA256 using webhook secret
3. Compare with provided signature (constant-time comparison)
4. Reject with 400 if invalid, log warning

---

## Algorithms

### Idempotency Check
\`\`\`
function isAlreadyProcessed(eventId: string): Promise<boolean>
  SELECT 1 FROM processed_events WHERE stripe_event_id = eventId
  IF found: return true
  ELSE: INSERT INTO processed_events (stripe_event_id, processed_at) VALUES (...)
        return false
\`\`\`

---

## Test Scenarios

### GIVEN a valid Stripe webhook payload
**WHEN** the HMAC signature matches the expected digest  
**THEN** the event is accepted and routed to the domain handler

### GIVEN a webhook with invalid signature
**WHEN** the signature validation fails  
**THEN** HTTP 400 is returned and a security warning is logged

### GIVEN a duplicate event (same event ID)
**WHEN** the event has already been processed  
**THEN** HTTP 200 is returned immediately without re-processing

### GIVEN an unrecognized event type
**WHEN** no handler is registered for the event type  
**THEN** the event is logged as unhandled and HTTP 200 returned
`,

  'file-feat-invoice': `# FEAT-invoice-gen — Invoice Generation

**Status:** DRAFT  
**Linked PRD Requirements:** R-003, R-008  
**Linked Design Components:** InvoiceGenerator

---

## Overview

Generate PDF invoices upon successful payment and make them available via REST API.

---

## Flows

### Flow-001 — Invoice Generation on Payment Success
1. Receive \`billing.payment_succeeded\` domain event
2. Fetch customer details from Customer Service
3. Fetch line items from Subscription Service
4. Render PDF using template engine
5. Upload PDF to S3 with customer-scoped path
6. Store invoice record in database with S3 URL
7. Emit \`billing.invoice_generated\` event

### Flow-002 — Invoice Retrieval API
1. Customer requests \`GET /invoices\`
2. Validate JWT, extract customer ID
3. Query invoice records for customer
4. Return paginated list with pre-signed S3 URLs (TTL: 1 hour)

---

## Algorithms

### PDF Template Rendering
\`\`\`
function renderInvoice(data: InvoiceData): Buffer
  Load Handlebars template from /templates/invoice.hbs
  Apply data: { customer, lineItems, total, tax, invoiceNumber, date }
  Generate PDF via PDFKit
  Return Buffer
\`\`\`

---

<!-- TODO: Test scenarios not yet written — this is the gap identified by gap_analysis_validator -->
<!-- DRAFT: Awaiting review from billing team before implementation -->
`,

  'file-webhook-handler': `import { EventEmitter } from 'events'

// @cpt-obj-fspec-stripe
export class StripeWebhookHandler {
  private readonly secret: string
  private readonly emitter: EventEmitter

  constructor(secret: string, emitter: EventEmitter) {
    this.secret = secret
    this.emitter = emitter
  }

  // @cpt-obj-fspec-stripe-flow-001
  async handleWebhook(payload: Buffer, signature: string): Promise<void> {
    await this.validateSignature(payload, signature)
    const event = JSON.parse(payload.toString())
    await this.routeEvent(event)
  }

  // @cpt-obj-fspec-stripe-flow-002
  private async validateSignature(payload: Buffer, signature: string): Promise<void> {
    // Stripe signature validation using HMAC-SHA256
    const crypto = await import('crypto')
    const hmac = crypto.createHmac('sha256', this.secret)
    hmac.update(payload)
    const digest = hmac.digest('hex')
    if (digest !== signature.split('=')[1]) {
      throw new Error('Invalid webhook signature')
    }
  }

  private async routeEvent(event: Record<string, unknown>): Promise<void> {
    switch (event.type) {
      case 'invoice.payment_succeeded':
        await this.handlePaymentSuccess(event)
        break
      case 'invoice.payment_failed':
        await this.handlePaymentFailed(event)
        break
      default:
        console.warn(\`Unhandled event type: \${event.type}\`)
    }
  }

  private async handlePaymentSuccess(event: Record<string, unknown>): Promise<void> {
    // TODO: emit billing.payment_succeeded domain event
    const invoiceId = (event.data as Record<string, unknown>)?.object as string
    this.emitter.emit('billing.payment_succeeded', { invoiceId })
    console.log(\`Payment succeeded for invoice: \${invoiceId}\`)
  }

  private async handlePaymentFailed(event: Record<string, unknown>): Promise<void> {
    console.error(\`Payment failed:\`, event)
    this.emitter.emit('billing.payment_failed', event)
  }
}
`,

  'file-invoice-gen': `// Invoice Generator — no @cpt- markers yet (traceability gap)
import PDFDocument from 'pdfkit'

export interface InvoiceData {
  invoiceNumber: string
  date: string
  customer: {
    id: string
    name: string
    email: string
    address: string
  }
  lineItems: Array<{
    description: string
    quantity: number
    unitPrice: number
    total: number
  }>
  subtotal: number
  tax: number
  total: number
}

export class InvoiceGenerator {
  private readonly s3BucketName: string

  constructor(s3BucketName: string) {
    this.s3BucketName = s3BucketName
  }

  async generate(data: InvoiceData): Promise<string> {
    const pdfBuffer = await this.renderPdf(data)
    const s3Key = \`invoices/\${data.customer.id}/\${data.invoiceNumber}.pdf\`
    // Upload to S3 (mocked)
    await this.uploadToS3(s3Key, pdfBuffer)
    return \`https://\${this.s3BucketName}.s3.amazonaws.com/\${s3Key}\`
  }

  private async renderPdf(data: InvoiceData): Promise<Buffer> {
    return new Promise((resolve, reject) => {
      const doc = new PDFDocument({ margin: 50 })
      const chunks: Buffer[] = []

      doc.on('data', chunk => chunks.push(chunk))
      doc.on('end', () => resolve(Buffer.concat(chunks)))
      doc.on('error', reject)

      // Header
      doc.fontSize(24).text('INVOICE', { align: 'right' })
      doc.fontSize(12).text(\`Invoice #\${data.invoiceNumber}\`, { align: 'right' })
      doc.text(\`Date: \${data.date}\`, { align: 'right' })

      // Customer
      doc.moveDown().fontSize(14).text('Bill To:')
      doc.fontSize(12).text(data.customer.name)
      doc.text(data.customer.email)
      doc.text(data.customer.address)

      // Line items
      doc.moveDown().fontSize(14).text('Items:')
      data.lineItems.forEach(item => {
        doc.fontSize(12).text(
          \`\${item.description} x\${item.quantity} @ \$\${item.unitPrice} = \$\${item.total}\`
        )
      })

      // Totals
      doc.moveDown()
      doc.fontSize(12).text(\`Subtotal: \$\${data.subtotal}\`, { align: 'right' })
      doc.text(\`Tax: \$\${data.tax}\`, { align: 'right' })
      doc.fontSize(14).text(\`Total: \$\${data.total}\`, { align: 'right' })

      doc.end()
    })
  }

  private async uploadToS3(key: string, buffer: Buffer): Promise<void> {
    // Mock S3 upload
    console.log(\`Uploading \${key} (\${buffer.length} bytes) to S3\`)
  }
}
`,

  'file-ledger': `// @cpt-obj-design-ledger
export interface LedgerEntry {
  id?: string
  customerId: string
  type: 'credit' | 'debit'
  amount: number
  currency: string
  description: string
  stripeEventId?: string
  createdAt?: Date
}

export interface LedgerBalance {
  customerId: string
  totalCredits: number
  totalDebits: number
  balance: number
  currency: string
}

export class LedgerService {
  private db: Map<string, LedgerEntry[]>

  constructor() {
    // In production this would be a PostgreSQL connection
    this.db = new Map()
  }

  async record(entry: LedgerEntry): Promise<string> {
    const id = \`ledger_\${Date.now()}_\${Math.random().toString(36).slice(2)}\`
    const fullEntry: LedgerEntry = {
      ...entry,
      id,
      createdAt: new Date(),
    }
    const existing = this.db.get(entry.customerId) ?? []
    this.db.set(entry.customerId, [...existing, fullEntry])
    return id
  }

  async getHistory(customerId: string): Promise<LedgerEntry[]> {
    return this.db.get(customerId) ?? []
  }

  async getBalance(customerId: string): Promise<LedgerBalance> {
    const entries = await this.getHistory(customerId)
    const totalCredits = entries
      .filter(e => e.type === 'credit')
      .reduce((sum, e) => sum + e.amount, 0)
    const totalDebits = entries
      .filter(e => e.type === 'debit')
      .reduce((sum, e) => sum + e.amount, 0)
    return {
      customerId,
      totalCredits,
      totalDebits,
      balance: totalCredits - totalDebits,
      currency: entries[0]?.currency ?? 'USD',
    }
  }

  async reconcile(customerId: string): Promise<boolean> {
    const balance = await this.getBalance(customerId)
    // Double-entry bookkeeping: balance should never be negative
    return balance.balance >= 0
  }
}
`,

  'file-migration-001': `-- Migration: 001_billing_schema
-- Description: Initial billing ledger schema
-- Created: 2026-01-15

BEGIN;

-- Ledger entries table (append-only)
CREATE TABLE billing_ledger (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id   TEXT NOT NULL,
  type          TEXT NOT NULL CHECK (type IN ('credit', 'debit')),
  amount        NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
  currency      CHAR(3) NOT NULL DEFAULT 'USD',
  description   TEXT NOT NULL,
  stripe_event_id TEXT UNIQUE,
  metadata      JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Processed events table (idempotency)
CREATE TABLE processed_events (
  stripe_event_id TEXT PRIMARY KEY,
  event_type      TEXT NOT NULL,
  processed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Invoice records table
CREATE TABLE invoices (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_number TEXT NOT NULL UNIQUE,
  customer_id   TEXT NOT NULL,
  amount        NUMERIC(12, 2) NOT NULL,
  currency      CHAR(3) NOT NULL DEFAULT 'USD',
  status        TEXT NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'issued', 'paid', 'void')),
  pdf_url       TEXT,
  stripe_event_id TEXT REFERENCES processed_events(stripe_event_id),
  issued_at     TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices
CREATE INDEX idx_billing_ledger_customer ON billing_ledger (customer_id, created_at DESC);
CREATE INDEX idx_billing_ledger_stripe_event ON billing_ledger (stripe_event_id);
CREATE INDEX idx_invoices_customer ON invoices (customer_id, created_at DESC);
CREATE INDEX idx_invoices_status ON invoices (status);

-- Row-level security
ALTER TABLE billing_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;

-- Prevent updates and deletes on ledger (append-only)
CREATE RULE no_update_ledger AS ON UPDATE TO billing_ledger DO INSTEAD NOTHING;
CREATE RULE no_delete_ledger AS ON DELETE TO billing_ledger DO INSTEAD NOTHING;

COMMIT;
`,

  'file-webhook-spec': `import { EventEmitter } from 'events'
import { createHmac } from 'crypto'
import { StripeWebhookHandler } from '../src/billing/webhook-handler'

function makeSignature(secret: string, payload: Buffer): string {
  const hmac = createHmac('sha256', secret)
  hmac.update(payload)
  return \`v1=\${hmac.digest('hex')}\`
}

describe('StripeWebhookHandler', () => {
  const SECRET = 'test-webhook-secret'
  let emitter: EventEmitter
  let handler: StripeWebhookHandler

  beforeEach(() => {
    emitter = new EventEmitter()
    handler = new StripeWebhookHandler(SECRET, emitter)
  })

  describe('handleWebhook', () => {
    it('accepts a valid webhook with correct signature', async () => {
      const payload = Buffer.from(JSON.stringify({
        type: 'invoice.payment_succeeded',
        data: { object: 'inv_test_123' }
      }))
      const signature = makeSignature(SECRET, payload)

      await expect(handler.handleWebhook(payload, signature)).resolves.toBeUndefined()
    })

    it('rejects a webhook with invalid signature', async () => {
      const payload = Buffer.from(JSON.stringify({ type: 'invoice.payment_succeeded' }))
      const badSignature = 'v1=invalid'

      await expect(handler.handleWebhook(payload, badSignature))
        .rejects.toThrow('Invalid webhook signature')
    })

    it('emits billing.payment_succeeded for successful payment', async () => {
      const invoiceId = 'inv_test_456'
      const payload = Buffer.from(JSON.stringify({
        type: 'invoice.payment_succeeded',
        data: { object: invoiceId }
      }))
      const signature = makeSignature(SECRET, payload)

      const eventPromise = new Promise<Record<string, unknown>>(resolve => {
        emitter.on('billing.payment_succeeded', resolve)
      })

      await handler.handleWebhook(payload, signature)
      const event = await eventPromise
      expect(event).toEqual({ invoiceId })
    })

    it('emits billing.payment_failed for failed payment', async () => {
      const payload = Buffer.from(JSON.stringify({
        type: 'invoice.payment_failed',
        data: { object: 'inv_test_789' }
      }))
      const signature = makeSignature(SECRET, payload)

      const eventPromise = new Promise(resolve => {
        emitter.on('billing.payment_failed', resolve)
      })

      await handler.handleWebhook(payload, signature)
      await expect(eventPromise).resolves.toBeDefined()
    })

    it('handles unknown event types without throwing', async () => {
      const payload = Buffer.from(JSON.stringify({ type: 'customer.created' }))
      const signature = makeSignature(SECRET, payload)

      await expect(handler.handleWebhook(payload, signature)).resolves.toBeUndefined()
    })
  })
})
`,

  'file-studio-toml': `# Constructor Studio Configuration
# billing-service project

[project]
name = "billing-service"
version = "2.0.0"
description = "Cloud-native billing microservice"

[studio]
version = "2"
kit = "kits/saas-kit.toml"

[sdlc]
artifacts_dir = "docs"
features_dir = "docs/features"
src_dir = "src"
tests_dir = "tests"

[traceability]
marker_prefix = "@cpt-"
scan_extensions = [".ts", ".tsx", ".js"]

[workers]
enabled = ["gap_analysis_validator", "implement_code_worker", "create_prd_worker"]

[flows]
auto_trigger = true
on_file_save = ["gap_analysis_validator"]
`,

  'file-saas-kit': `# Constructor Studio Kit — SaaS Billing
# Kit version: 1.2.0

[kit]
id = "saas-billing-kit"
name = "SaaS Billing Kit"
version = "1.2.0"
description = "Constructor Studio kit for SaaS billing services"

[artifacts]
required = ["PRD", "DESIGN", "ADR"]
optional = ["DECOMPOSITION"]

[[artifact_templates]]
kind = "PRD"
template = "templates/prd.md"
sections = ["overview", "actors", "functional_requirements", "nfr", "success_criteria"]

[[artifact_templates]]
kind = "FEATURE"
template = "templates/feature.md"
sections = ["overview", "flows", "algorithms", "test_scenarios"]
required_sections = ["test_scenarios"]

[workers]
gap_analysis = { worker = "gap_analysis_validator", triggers = ["on_save", "on_pr"] }
implementation = { worker = "implement_code_worker", triggers = ["on_demand"] }

[traceability]
enforce_markers = true
marker_format = "@cpt-{object_id}"
coverage_threshold = 0.8
`
}
