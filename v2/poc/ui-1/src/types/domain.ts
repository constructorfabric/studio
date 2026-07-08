// ─── Core Object Types ────────────────────────────────────────────────────────

export type ObjectTypeId =
  | 'prd'
  | 'design'
  | 'task'
  | 'pull_request'
  | 'incident'
  | 'adr'
  | 'feature_spec'
  | 'decomposition'
  | 'build'
  | 'worker_run'
  | 'flow_run'
  | 'recommendation'
  | 'approval'
  | 'validation_session'
  | 'evidence'
  | 'worker_interaction'
  | 'component'
  | 'person'
  | 'team'
  | 'release'
  | 'deployment'
  | 'environment'

export type ObjectState =
  | 'draft'
  | 'approved'
  | 'in_progress'
  | 'planned'
  | 'done'
  | 'failed'
  | 'stale'
  | 'open'
  | 'review'
  | 'running'
  | 'merged'
  | 'closed'
  | 'superseded'

// Core GTS link kinds per §1.1. Kit-extensible custom kinds (triggers, blocks, related_to) are not pre-registered core kinds.
export type LinkKind =
  | 'derived_from'
  | 'decomposes_into'
  | 'implements'
  | 'references'
  | 'incorporates'
  | 'validates'
  | 'supersedes'
  | 'informs'

export type ValidationStatus = 'pass' | 'fail' | 'pending' | 'none'

export interface ObjectLink {
  targetId: string
  kind: LinkKind
  // Exactly one of createdBy (User ref) or sourceRunId (WorkerRun ref) should be set per §1.1
  createdBy?: string
  sourceRunId?: string
}

export interface StudioObject {
  id: string
  typeId: ObjectTypeId
  tenantId: string
  title: string
  state: ObjectState
  validationStatus: ValidationStatus
  stalenessScore: number // 0.0–1.0 float per §20.1; 0.0=fresh, 1.0=stale
  links: ObjectLink[]
  createdAt: string
  updatedAt: string
  description?: string
  metadata?: Record<string, unknown>
}

export interface LogEntry {
  ts: string        // ISO timestamp string
  level: 'debug' | 'info' | 'warn' | 'error'
  msg: string
}

export type LoopTerminationReason =
  | 'converged' | 'maxIterations' | 'budgetExhausted' | 'failed' | 'escalated' | 'aborted'

export interface IterationRun {
  iteration: number          // 1-based
  score: number              // quality metric (0.0–1.0)
  improvement: number        // score delta vs previous (positive = better)
  valid: boolean             // passed validation
  costUsd: number
  tokens: number
  durationMs: number
  workerRunIds: string[]     // all child WorkerRun IDs for this iteration
  isBest: boolean
}

export interface LoopRun {
  id: string
  flowId: string
  flowLabel: string
  objectId: string
  objectTitle: string
  state: WorkerRunState
  startedAt: string
  completedAt?: string
  // Iteration tracking
  iterations: IterationRun[]
  currentIteration: number
  bestScore: number
  bestIterationIdx: number   // 0-based index into iterations[]
  // Convergence
  converged: boolean
  terminationReason?: LoopTerminationReason
  // Budget
  totalCostUsd: number
  totalTokens: number
  budgetConsumedPct: number  // 0.0–1.0
  maxCostUsd: number
  maxTokens: number
}

// ─── Worker Types ─────────────────────────────────────────────────────────────

export type WorkerCategory = 'quality' | 'security' | 'ops' | 'ai-cost' | 'traceability' | 'retrieval' | 'platform'
export type WorkerProfile = 'realtime' | 'scheduled' | 'on_demand' | 'analyzer'
export type WorkerRunState = 'pending' | 'running' | 'awaiting_input' | 'paused' | 'done' | 'failed' | 'escalated' | 'aborted'
export type InteractionKind = 'menu' | 'input_request' | 'free_form_intent'

export interface WorkerInteractionDef {
  kind: InteractionKind
  prompt: string
  options?: string[]
  requiredRole?: string  // role pattern restricting who may answer; null = any authorized user
}

export interface WorkerDef {
  id: string
  label: string
  description: string
  requiresAutomationGate: boolean
  category: WorkerCategory
  profile: WorkerProfile
  actionLabel: string
  applicableTypes: ObjectTypeId[]
  interaction?: WorkerInteractionDef
}

// ─── Worker Run ───────────────────────────────────────────────────────────────

export interface WorkerRun {
  id: string
  workerId: string
  workerLabel: string
  objectId: string
  objectTitle: string
  state: WorkerRunState
  progress: number // 0-100
  startedAt: string
  completedAt?: string
  output?: string
  error?: string
  interaction?: WorkerInteractionDef
  interactionResponse?: string
  // Cost & performance
  costUsd?: number
  tokensIn?: number
  tokensOut?: number
  model?: string
  durationMs?: number
  logs?: LogEntry[]
  createdObjectIds?: string[]
  parentRunId?: string   // ID of the FlowRun or WorkerRun that spawned this run
}

// ─── Flow Types ───────────────────────────────────────────────────────────────

export type FlowStepStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped' | 'escalated' | 'aborted'

export interface FlowStep {
  id: string
  workerId: string
  workerLabel: string
  objectTypeTarget: ObjectTypeId
  status: FlowStepStatus
  workerRunId?: string
}

export interface FlowDef {
  id: string
  label: string
  description: string
  steps: FlowStep[]
  entryConstraints?: { typeId: ObjectTypeId; requiredStates?: ObjectState[] }[]
}

export interface FlowRun {
  id: string
  flowId: string
  flowLabel: string
  state: WorkerRunState
  completedSteps: string[]
  skippedSteps: string[]
  activeStepId?: string
  stepStatus: Record<string, FlowStepStatus>
  startedAt: string
  completedAt?: string
}

// ─── Recommendation Types ─────────────────────────────────────────────────────

export type RecommendationSeverity = 'info' | 'warning' | 'critical'
export type RecommendationState = 'pending' | 'accepted' | 'executing' | 'done' | 'dismissed' | 'invalidated'
export type RecommendationConfidence = 'full' | 'partial' | 'low'

export interface Recommendation {
  id: string
  title: string
  description: string
  severity: RecommendationSeverity
  state: RecommendationState
  confidence?: RecommendationConfidence
  suggestedWorkerId: string  // PoC denormalization of doc's suggestedWorker ref
  suggestedWorkerLabel: string
  relatedObjectIds: string[]
  createdAt: string
  sourceRunId?: string      // ref → WorkerRun that produced this recommendation
  reason?: string           // machine-readable gap description (distinct from description)
  validationWorkerId?: string
  severityWorkerId?: string
}

// ─── App View Types ───────────────────────────────────────────────────────────

export type AppView = 'graph' | 'flows' | 'activity' | 'recommendations' | 'files' | 'kits' | 'workspaces' | 'chat' | 'workers' | 'catalog' | 'loop'

export interface GraphNodeData {
  object: StudioObject
  selected?: boolean
}

export interface FileNode {
  id: string
  name: string
  type: 'file' | 'folder'
  children?: FileNode[]
  language?: 'markdown' | 'typescript' | 'sql' | 'toml' | 'text'
  linkedObjectId?: string
  isDraft?: boolean
}

// ─── Flow Graph Types ─────────────────────────────────────────────────────────

export type FlowNodeType = 'start' | 'end' | 'worker' | 'gate' | 'human' | 'escalation' | 'decision'
export type FlowEdgeKind = 'default' | 'pass' | 'fail' | 'retry' | 'branch'
export type FlowNodeExecState = 'idle' | 'running' | 'passed' | 'failed' | 'retrying' | 'skipped' | 'done' | 'waiting'

export interface FlowInteractionOption {
  id: string
  label: string
  description?: string
  color?: string          // optional accent color for the button
  nextNodeHint?: string   // which path this takes (informational)
}

export interface FlowNodeInteraction {
  kind: 'menu' | 'input' | 'approval'
  prompt: string
  options?: FlowInteractionOption[]   // for kind: menu | approval
  inputPlaceholder?: string           // for kind: input
  pauseAfterMs?: number               // delay before pausing (default: after worker runs)
}

export interface FlowGraphNode {
  id: string
  nodeType: FlowNodeType
  label: string
  sublabel?: string
  maxRetries?: number
  interaction?: FlowNodeInteraction   // pauses flow for user input
  position: { x: number; y: number }
}

export interface FlowGraphEdge {
  id: string
  source: string
  target: string
  edgeKind: FlowEdgeKind
  label?: string
  branchOptionId?: string   // only active when this option was chosen at source decision/gate
}

export interface FlowGraphDef {
  id: string
  name: string
  description: string
  category: string
  nodes: FlowGraphNode[]
  edges: FlowGraphEdge[]
}

export interface FlowArtifact {
  label: string
  nodeType: string
  nodeId: string
}

export interface FlowPendingInteraction {
  nodeId: string
  interaction: FlowNodeInteraction
  resumeAfterOptionId?: string   // set after user picks, used to route branches
}

export interface FlowExecState {
  flowId: string
  status: 'running' | 'done' | 'failed' | 'waiting_input'
  nodeStates: Record<string, FlowNodeExecState>
  retryCounters: Record<string, number>
  currentNodeId: string | null
  producedArtifacts: FlowArtifact[]
  startedAt: number
  pendingInteraction?: FlowPendingInteraction
  takenBranches: Record<string, string>   // nodeId → chosen option id
  inputResponses: Record<string, string>  // nodeId → text input
}

// ─── Kit Types ────────────────────────────────────────────────────────────────

export type KitStatus = 'active' | 'update_available' | 'rolling_back' | 'failed'

export interface KitDef {
  id: string
  name: string
  description: string
  version: string
  latestVersion?: string
  status: KitStatus
  category: string
  workerCount: number
  connectorCount: number
  author: string
  tags: string[]
  installedAt: string
  workers: Array<{ id: string; label: string; category: string }>
}

// ─── Workspace Types ──────────────────────────────────────────────────────────

export type WorkspaceStatus = 'active' | 'syncing' | 'error' | 'offline'

export interface WorkspaceSource {
  id: string
  url: string
  role: 'main' | 'docs' | 'platform' | 'shared' | 'test' | 'config'
  branch: string
  lastSyncedAt: string
}

export interface WorkspaceDef {
  id: string
  name: string
  description?: string
  status: WorkspaceStatus
  sources: WorkspaceSource[]
  installedKitIds: string[]
  automationLevel: 'recommendations' | 'approved_automation' | 'enterprise'
  lastSyncedAt: string
  objectCount: number
}

export interface LineAction {
  visible: boolean
  top?: number
  left?: number
  startLine?: number
  endLine?: number
  selectedText?: string
  fileId?: string
  language?: string
}
