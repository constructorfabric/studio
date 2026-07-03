# Brainstorm Session — Studio v2 Domain Model

**Session ID:** studio-v2-domain-model-2026-07-03
**Date:** 2026-07-03
**Rounds:** 20
**Mode:** inline / normal
**SIMPLE_MODE:** normal
**BRAINSTORM_MAX_ROUNDS:** 10 (exceeded — continued by user choice)
**PANEL_MODE:** inline

---

## Panel

| ID | Persona | Focus |
|---|---|---|
| E1 | Domain Architect | Core graph, aggregate boundaries, invariants |
| E2 | Product Strategist | Killer workflows, user-persona coverage, ROI |
| E3 | Integration Engineer | Connectors, sync, events, external IDs |
| E4 | AI Systems Lead | Action engine, validators, cost routing |
| E5 | Enterprise Platform Lead | Workspace, RBAC/ABAC, policies, multi-tenancy |

---

## Original Intent

Разработать доменную модель для Studio v2 на основе вижена (STUDIO_VISION.md).

---

## Topics Covered

| Round | Topic |
|---|---|
| 1 | Aggregate boundaries — ShadowObject, ActionGraph, bounded contexts |
| 1C | Challenge round 1 — WorkerRun, Flow/FlowRun, GTS typeTag, versioning, Workspace |
| 2 | Connector model |
| 2C | Challenge round 2 — Connector as Worker, obj_ext, Kit permissions |
| 3 | Extensibility — vendor types, Kit, obj_ext |
| 3C | Challenge round 3 — obj_ext registry, Kit draft scope, smoke tests, WorkerImplementation |
| 4 | WorkerRun execution model |
| 4C | Challenge round 4 — sync/async, eta, checkpoint, dynamic dispatch, effectiveLimits |
| 5 | Object lifecycle & state transitions |
| 5C | Challenge round 5 — StatePolicy, x-gts-state-requires, external mapping, StateTransitionEvent |
| 6 | Role, Policy & Authorization |
| 6C | Challenge round 6 — PolicyOverride priority, condition cache, IdentityMapping, Worker→Worker, PolicyDelegation |
| 7 | AuditLog |
| 7C | Challenge round 7 — auditMode sync/async, SavedAuditQuery, write-ahead, retention, audit_exporter |
| 8 | Recommendation |
| 8C | Challenge round 8 — validationWorker, suggestedInput refresh, confidence, debounce, severityWorker |
| 9 | Events (→ Gears Events Broker) |
| 10 | Notifications |
| 10C | Challenge round 10 — NotificationRuleOverride, urgency, credentials in Settings, groupBy |
| 11 | Object type catalog (SDLC industry survey) |
| 11C | Challenge round 11 — dashboard→Insight, granularity, document base type, prompt→skill, secret_reference |
| 12 | Critical vision gaps — Action, Validator, Evidence, Connector, Object base attrs |
| 13 | Validator loop — ValidationSession, escalation, WorkerRun states |
| 14 | Flow Library — 12 Analyzers + 2 Flows |
| 15 | Killer Workflows traceability |
| 16 | Staleness model |
| 17 | Human control points — Approval model |
| 18 | Connector details — FieldMapping, WriteBackPolicy, sync protocol |
| 19 | Expansion path — automationLevel, deploymentMode |
| 20 | AI cost routing (partial — wrapped before completion) |

---

## Decisions (85)

### Core Domain Model

- **Object** = base type; all domain objects extend via GTS chaining
- **Object base attrs** = `id, typeId, tenantId, state, createdAt, updatedAt, ownerId, validationStatus, stalenessScore, externalRef`
- **Worker** = first-class Studio registry entity (NOT extends Gears serverless)
- **Validator extends Worker** = adds `maxRetries, escalateTo, abortOnLimit`; output always ValidationResult
- **Flow** = first-class Studio registry entity (constraint config)
- **Kit** = first-class Studio registry entity (extension unit)
- **Connector** = first-class Studio registry entity; uses Gears OAGW as networking infrastructure
- **WorkerRun extends Object** = execution record
- **FlowRun extends Object** = flow execution record
- **Action** = Worker with state-aware Contract (no separate type)
- **WorkerRun states** = `pending|running|done|failed|escalated|aborted`

### GTS Conventions

- vendor = `cf` (same as Gears)
- Studio base Object: `gts.cf.studio.core.object.v1~`
- Studio base Worker: `gts.cf.studio.core.worker.v1~`
- Studio base Validator: `gts.cf.studio.core.worker.v1~cf.studio.core.validator.v1~`
- Events extend Gears: `gts.cf.core.events.type.v1~cf.studio.core.<event>.v1~`
- Tenant extends Gears RG: `gts.cf.core.rg.type.v1~cf.core._.tenant.v1~cf.studio.core.tenant.v1~`
- User extends Gears AM: `gts.cf.core.am.user.v1~cf.studio.core.user.v1~`
- Permission extends Gears: `gts.cf.toolkit.authz.permission.v1~cf.studio.core.permission.v1~`

### Validation Loop

- **ValidationSession** = aggregates retry loop; `state: running|pass|fail|escalated|aborted`
- **ValidationResult** = per-attempt result; `state: pass|fail|superseded|revoked`
- **Evidence** = structured proof; `state: valid|superseded|revoked`; produced by Worker output Contract
- Escalation creates `Approval` Object linked to `ValidationSession`
- Validator retry policy: Kit → Tenant → call (three levels, narrowing only)

### Connector

- Uses Gears OAGW upstream as networking infrastructure
- **FieldMapping.kind** = `direct|lookup|transform` (transform via Worker)
- **WriteBackPolicy** = `{ allowedActions, requiresApproval, conflictStrategy: escalate (default) }`
- **syncProtocol** = `{ push?, pull?, preferred: push }` — both optional
- **rateLimit** → passed to OAGW upstream at Kit install
- **scopeFilter** per Tenant; schema from Connector Kit

### State & Lifecycle

- **StatePolicy** = separate registry entity (process vs data structure)
- Transitions per-property in StatePolicy (not in GTS type schema)
- `x-gts-state-requires: { state, strict: false (default) }` in Worker Contract
- `x-gts-state-sets` in Worker output Contract
- **StateTransitionEvent** = computed projection over WorkerRun tree
- External state mapping = per Tenant config at Kit install (not in type schema)

### Staleness

- `stalenessScore = max(timeStaleness, dependencyStaleness, syncStaleness)`
- `stalenessPolicy: { timeTTL, dependencyTypes, recommendationThreshold }` in `x-gts-traits`
- `stale_artifact_detection` Analyzer updates asynchronously (15min cron + onEvent debounce 5m)
- Recommendation created when `stalenessScore >= threshold`

### Authorization

- Role = Object in graph (lifecycle, audit, Tenant-scoped)
- Policy = registry entity (Kit); PolicyOverride = Object (Tenant runtime)
- Priority: PolicyOverride > Policy (Override cannot expand beyond Policy)
- ABAC conditions = ref → Worker (returns `{ allowed, reason }`); cached with TTL (default 60s)
- IdentityMapping.externalPattern = `{ provider: GTS Type ID, pattern: string }`
- Worker→Worker authz = implicit via dependencies (both Kits approved → call authorized)
- PolicyDelegation = explicit downward grant with optional `expiresAt`

### AuditLog

- Materialized view over WorkerRun (CQRS + Event Sourcing)
- `auditMode: sync|async` per Worker (Tenant can override)
- Write-ahead: `externalEvents` recorded before Worker begins
- Kit Views + `SavedAuditQuery extends Object`
- `retentionAction: archive|delete` (default: archive)
- Core `audit_exporter` pre-installed; vendor formats via Kits

### Recommendation

- `Recommendation extends Object`; `state: pending|accepted|executing|done|dismissed|invalidated`
- `validationWorker` for auto/manual Re-check (also refreshes `suggestedInput`)
- `confidence: full|partial|low` (partial = external systems unavailable)
- `severity` static + optional `severityWorker` for dynamic recompute
- Trigger modes: `schedule`, `onEvent (+ debounce)`, `onDemand`

### Notifications

- `NotificationRule` = registry (Kit); `NotificationRuleOverride extends Object` (runtime on/off + expiresAt)
- `NotificationSubscription.urgency: immediate|digest|muted`
- Kit declares `requiredSettings` (secret: true); Tenant fills via Gears Settings
- Template: primary Object only + Studio deep link
- `digest.groupBy: objectId|eventType|none`
- Vendor channels via Kits; credentials in Gears Settings

### Flow Library

- 12 Analyzer Workers: gap_analysis, traceability_analysis, contradiction_detection, bloat_detection,
  stale_artifact_detection, ownership_gap_analysis, duplicate_work_detection,
  architecture_drift_detection, security_impact_analysis, test_gap_detection,
  operations_metrics_analysis, ai_cost_efficiency_analysis
- 2 Flows: `bug_to_fix_pr_flow` (3 mandatory Validators), `release_readiness_review`
- Runtime: `ownership_gap_analysis` → script; `contradiction_detection`, `duplicate_work_detection` → llm; rest → hybrid
- Profile: `realtime|scheduled|on_demand`
- Worker metadata: `displayName, description, category, icon, profile`

### Killer Workflows

- `pull_request`: `closesIssues`, `implementsRequirements`, `conformsToDesign`, `verifiedBy`
- `test_case.verifiesRequirements: requirement[]` + `verifiesFeature?: feature_spec`
- `pr_design_validator extends Validator` (SDLC Kit, hybrid, onEvent PR → review)
- `FlowRun` sufficient for Killer Workflow 1 (no separate type needed)

### Approval & Human Control

- Generic `Approval` with `kind` discriminator + typed `payload` per kind
- `customerImpact?: { scope, affectedUsers, rollbackPlan }` optional
- `security_exception` payload: `expiresAt, acceptedRisk, mitigations, secondaryApprover?, autoReviewAfter?`
- `indexes` in `x-gts-traits` → persistence layer reads at schema init

### Expansion Path

- `Tenant.automationLevel: readonly|recommendations|approved_automation|enterprise`
- `Tenant.approvedWorkerCategories: string[]` (granular per category)
- `Tenant.deploymentMode: cloud|private|on_prem` (independent of automationLevel)
- Raising automationLevel = `Approval (kind: architecture_decision)`; lowering = no approval
- Runtime check: `automationLevel >= approved_automation AND category in approvedWorkerCategories`

### Tech Stack & SBOM

- Tech stack: `library`, `library_version`, `framework`, `runtime`, `database`, `database_instance`, `third_party_service`, `cloud_service`, `tech_dependency`
- SBOM: `sbom`, `sbom_component`, `sbom_relationship`, `sbom_license`, `sbom_checksum`
- Relationship kinds: `CONTAINS|DEPENDS_ON|DESCRIBES|GENERATED_FROM|VARIANT_OF`

### Component & Release

- `component_version`, `component_dependency (kind: uses|implements|extends|calls)`
- `release_component` join: which `component_version` in which `release`

---

## Open Questions

1. **AI cost routing** — `ModelRouter` registry entity; `PromptExperiment` A/B testing; `WorkerRun.cost` field; `performance_benchmark` for AI Workers; custom enterprise models via Gears Models Registry
2. **Insight layer** — how Vision Insight layer (Connectors + Data + Analytics + Benchmarking) maps to Gears Analytics vs Studio domain
3. **Kit reference architecture** — `deploymentPattern` and `referenceArchitecture` attributes in Kit manifest
4. **`indexes` in x-gts-traits** — full spec for persistence layer (which fields, compound indexes)
5. **`automationLevel` runtime check** — exact hook point in Worker execution engine
6. **`component` kind values** — need exhaustive taxonomy (service, library, module, subsystem, frontend, backend, data-pipeline, etc.)
7. **`PromptExperiment`** — statistical significance model, traffic split mechanics

---

## Output Artifact

Domain model written to: `v2/docs/domain-model.md`
Last commit: `73e057b`
