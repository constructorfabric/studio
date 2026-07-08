import { create } from 'zustand'
import type {
  StudioObject,
  WorkerRun,
  WorkerRunState,
  FlowRun,
  FlowStepStatus,
  FlowExecState,
  FlowGraphDef,
  FlowNodeExecState,
  FlowPendingInteraction,
  Recommendation,
  AppView,
  LogEntry,
} from '../types/domain'
import {
  MOCK_OBJECTS,
  MOCK_RECOMMENDATIONS,
  MOCK_WORKER_RUNS,
  FLOW_DEFS,
  FLOW_GRAPH_DEFS,
  WORKER_DEFS,
  getWorkersForObject,
} from '../data/mock-data'
import { FILE_CONTENTS, FILE_TREE } from '../data/file-mock-data'
import type { FileNode } from '../types/domain'
import type { LineAction } from '../types/domain'

interface AppState {
  // Data
  objects: StudioObject[]
  workerRuns: WorkerRun[]
  activeFlowRun: FlowRun | null
  completedFlowRuns: FlowRun[]
  flowExecState: FlowExecState | null
  recommendations: Recommendation[]

  // UI State
  selectedObjectId: string | null
  activeView: AppView
  activeTab: string
  pendingInteractionRunId: string | null
  isSimulating: boolean
  sidebarCollapsed: boolean
  chatOpen: boolean
  chatHeight: number
  dismissedRunIds: string[]
  // File view state
  openFileId: string | null
  fileContents: Record<string, string>
  modifiedFiles: Set<string>
  expandedFolders: Set<string>
  lineAction: LineAction

  // Actions
  selectObject: (id: string | null) => void
  setActiveView: (view: AppView) => void
  setActiveTab: (tab: string) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleChat: () => void
  setChatHeight: (h: number) => void
  // File view actions
  openFile: (fileId: string) => void
  closeFile: () => void
  updateFileContent: (fileId: string, content: string) => void
  saveFile: (fileId: string) => void
  toggleFolder: (folderId: string) => void
  setLineAction: (action: LineAction) => void

  // Worker actions
  runWorker: (workerId: string, objectId: string) => string
  runWorkerOnFile: (workerId: string, fileId: string) => string
  respondToInteraction: (runId: string, response: string) => void
  cancelWorkerRun: (runId: string, cascade?: boolean) => void
  dismissRunToast: (runId: string) => void
  clearAllRunToasts: () => void   // atomically dismiss all current terminal runs
  pauseWorkerRun: (runId: string) => void
  resumeWorkerRun: (runId: string) => void
  addRunLog: (runId: string, entry: LogEntry) => void

  // Flow actions
  runFlow: (flowId: string) => void
  stopFlow: () => void
  startFlowGraph: (flowId: string) => void
  stopFlowGraph: () => void
  respondToFlowInteraction: (optionId: string, textInput?: string) => void

  // Recommendation actions
  acceptRecommendation: (recId: string) => void
  dismissRecommendation: (recId: string) => void

  // Simulation
  simulateFullPipeline: () => void
}

let runIdCounter = 1000

function genId(): string {
  return `run-${Date.now()}-${runIdCounter++}`
}

function nowIso(): string {
  return new Date().toISOString()
}

// Tracks setInterval handles for active worker simulations
const runIntervals = new Map<string, ReturnType<typeof setTimeout>>()

function getSimLog(workerId: string, progress: number): string {
  const phase = Math.floor(progress / 20)
  const phases: Record<number, string[]> = {
    0: ['Initializing context...', 'Loading workspace configuration...', 'Fetching linked objects...'],
    1: ['Analyzing dependencies...', 'Building context graph...', 'Scanning related artifacts...'],
    2: ['Running primary analysis...', 'Applying worker logic...', 'Processing object data...'],
    3: ['Validating output...', 'Running compliance checks...', 'Cross-referencing schema...'],
    4: ['Finalizing...', 'Persisting results...', 'Emitting events...'],
  }
  const msgs = phases[Math.min(phase, 4)] ?? phases[4]
  // Vary by workerId so logs feel different per worker
  const idx = (workerId.length + progress) % msgs.length
  return msgs[idx]
}

// Flow interaction resume callback
let flowResumeCallback: ((optionId: string) => void) | null = null

const FILE_TO_OBJECT: Record<string, string> = {
  'file-prd':           'prd-001',
  'file-design':        'design-001',
  'file-adr-001':       'adr-001',
  'file-adr-002':       'adr-002',
  'file-feat-stripe':   'fspec-001',
  'file-feat-invoice':  'fspec-002',
  'file-webhook-handler': 'pr-001',
  'file-webhook-spec':  'pr-001',
}

function findFileInTree(nodes: FileNode[], id: string): FileNode | null {
  for (const n of nodes) {
    if (n.id === id) return n
    if (n.children) { const f = findFileInTree(n.children, id); if (f) return f }
  }
  return null
}

export const useAppStore = create<AppState>((set, get) => ({
  // ─── Initial State ──────────────────────────────────────────────────────────
  objects: MOCK_OBJECTS,
  workerRuns: MOCK_WORKER_RUNS,
  activeFlowRun: null,
  completedFlowRuns: [],
  flowExecState: null,
  recommendations: MOCK_RECOMMENDATIONS,
  selectedObjectId: null,
  activeView: 'graph',
  activeTab: 'overview',
  pendingInteractionRunId: null,
  isSimulating: false,
  sidebarCollapsed: false,
  chatOpen: false,
  chatHeight: 320,
  dismissedRunIds: [],
  openFileId: null,
  fileContents: {},
  modifiedFiles: new Set(),
  expandedFolders: new Set(['folder-docs', 'folder-src', 'folder-billing']),
  lineAction: { visible: false },

  // ─── UI Actions ─────────────────────────────────────────────────────────────
  selectObject: (id) => set({ selectedObjectId: id, activeTab: 'overview' }),
  setActiveView: (view) => set({ activeView: view }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  toggleChat: () => set(s => ({ chatOpen: !s.chatOpen })),
  setChatHeight: (h) => set({ chatHeight: h }),

  // ─── File View Actions ───────────────────────────────────────────────────────
  openFile: (fileId) => {
    const file = findFileInTree(FILE_TREE, fileId)
    const linkedObjectId = FILE_TO_OBJECT[fileId] ?? null
    set(state => ({
      openFileId: fileId,
      fileContents: fileId in state.fileContents
        ? state.fileContents
        : { ...state.fileContents, [fileId]: FILE_CONTENTS[fileId] ?? '' },
      selectedObjectId: linkedObjectId ?? state.selectedObjectId,
      activeTab: linkedObjectId ? 'overview' : state.activeTab,
    }))
  },
  closeFile: () => set({ openFileId: null }),
  updateFileContent: (fileId, content) => set(state => ({
    fileContents: { ...state.fileContents, [fileId]: content },
    modifiedFiles: new Set([...state.modifiedFiles, fileId])
  })),
  saveFile: (fileId) => set(state => {
    const next = new Set(state.modifiedFiles)
    next.delete(fileId)
    return { modifiedFiles: next }
  }),
  toggleFolder: (folderId) => set(state => {
    const next = new Set(state.expandedFolders)
    if (next.has(folderId)) next.delete(folderId)
    else next.add(folderId)
    return { expandedFolders: next }
  }),
  setLineAction: (action) => set({ lineAction: action }),

  // ─── Worker Run ─────────────────────────────────────────────────────────────
  runWorker: (workerId, objectId) => {
    const workerDef = WORKER_DEFS.find(w => w.id === workerId)
    const obj = get().objects.find(o => o.id === objectId)
    if (!workerDef || !obj) return ''

    const runId = genId()
    const run: WorkerRun = {
      id: runId,
      workerId,
      workerLabel: workerDef.label,
      objectId,
      objectTitle: obj.title,
      state: 'pending',
      progress: 0,
      startedAt: nowIso(),
      logs: [],
      createdObjectIds: [],
    }

    set(state => ({ workerRuns: [run, ...state.workerRuns] }))

    // Emit start log
    get().addRunLog(runId, { ts: nowIso(), level: 'info', msg: 'Worker started' })

    // Simulate pending → running
    setTimeout(() => {
      set(state => ({
        workerRuns: state.workerRuns.map(r =>
          r.id === runId ? { ...r, state: 'running' as WorkerRunState, progress: 10 } : r
        ),
      }))
      get().addRunLog(runId, { ts: nowIso(), level: 'info', msg: getSimLog(workerId, 10) })

      // Progress updates
      const progressInterval = setInterval(() => {
        const current = get().workerRuns.find(r => r.id === runId)
        if (!current || current.state !== 'running') {
          clearInterval(progressInterval)
          return
        }
        const nextProgress = Math.min(current.progress + Math.random() * 15 + 5, workerDef.interaction ? 70 : 95)
        set(state => ({
          workerRuns: state.workerRuns.map(r =>
            r.id === runId ? { ...r, progress: nextProgress } : r
          ),
        }))
        get().addRunLog(runId, { ts: nowIso(), level: 'info', msg: getSimLog(workerId, nextProgress) })
        if (nextProgress >= (workerDef.interaction ? 70 : 95)) {
          clearInterval(progressInterval)
        }
      }, 400)

      if (workerDef.interaction) {
        // Pause for interaction after ~2s
        const interactionHandle = setTimeout(() => {
          clearInterval(progressInterval)
          set(state => ({
            workerRuns: state.workerRuns.map(r =>
              r.id === runId
                ? { ...r, state: 'awaiting_input' as WorkerRunState, progress: 70, interaction: workerDef.interaction }
                : r
            ),
            pendingInteractionRunId: runId,
          }))
        }, 2200)
        runIntervals.set(runId, interactionHandle)
      } else {
        // Complete after ~3s
        const completionHandle = setTimeout(() => {
          clearInterval(progressInterval)
          finishRun(runId, objectId, get, set)
        }, 3000)
        runIntervals.set(runId, completionHandle)
      }
    }, 600)

    return runId
  },

  runWorkerOnFile: (workerId, fileId) => {
    const objectId = FILE_TO_OBJECT[fileId]
    if (!objectId) {
      // No linked object — still run but with first available matching object
      const workerDef = WORKER_DEFS.find(w => w.id === workerId)
      if (!workerDef) return ''
      const obj = get().objects[0]
      if (!obj) return ''
      return get().runWorker(workerId, obj.id)
    }
    return get().runWorker(workerId, objectId)
  },

  respondToInteraction: (runId, response) => {
    // F-023: guard — only valid from awaiting_input state
    const run = get().workerRuns.find(r => r.id === runId)
    if (!run || run.state !== 'awaiting_input') return

    set(state => ({
      workerRuns: state.workerRuns.map(r =>
        r.id === runId
          ? { ...r, state: 'running' as WorkerRunState, progress: 75, interactionResponse: response }
          : r
      ),
      pendingInteractionRunId: null,
    }))

    // Continue to completion
    const progressInterval2 = setInterval(() => {
      const current = get().workerRuns.find(r => r.id === runId)
      if (!current || current.state !== 'running') {
        clearInterval(progressInterval2)
        return
      }
      const nextProgress = Math.min(current.progress + Math.random() * 10 + 5, 95)
      set(state => ({
        workerRuns: state.workerRuns.map(r =>
          r.id === runId ? { ...r, progress: nextProgress } : r
        ),
      }))
      if (nextProgress >= 95) clearInterval(progressInterval2)
    }, 300)

    setTimeout(() => {
      clearInterval(progressInterval2)
      const current = get().workerRuns.find(r => r.id === runId)
      if (current) finishRun(runId, current.objectId, get, set)
    }, 2000)
  },

  // F-003: cancelWorkerRun — sets run to aborted state, preserves it in the list
  cancelWorkerRun: (runId, cascade) => {
    const h = runIntervals.get(runId)
    if (h) { clearTimeout(h); runIntervals.delete(runId) }
    set(state => ({
      workerRuns: state.workerRuns.map(r => {
        if (r.id === runId) {
          // cancelledBy is not in the WorkerRun type; would need schema extension for production
          return { ...r, state: 'aborted' as WorkerRunState, completedAt: nowIso() }
        }
        // If cascade=true, abort child runs (runs where parentRunId === runId, if tracked)
        // WorkerRun does not currently have a parentRunId field; cascade is a no-op for children
        return r
      }),
      pendingInteractionRunId: state.pendingInteractionRunId === runId ? null : state.pendingInteractionRunId,
    }))
  },

  // F-003: dismissRunToast — UI-only action to track which run toasts have been dismissed
  dismissRunToast: (runId) => {
    set(state => ({
      dismissedRunIds: state.dismissedRunIds.includes(runId)
        ? state.dismissedRunIds
        : [...state.dismissedRunIds, runId],
    }))
  },

  // Atomic clear-all: dismiss every currently visible terminal run in one set() call
  // so Zustand can't batch/race individual forEach dismissals.
  clearAllRunToasts: () => {
    set(state => {
      const TERMINAL = new Set(['done', 'failed', 'aborted', 'escalated'])
      const terminalIds = state.workerRuns
        .filter(r => TERMINAL.has(r.state) && !state.dismissedRunIds.includes(r.id))
        .map(r => r.id)
      if (terminalIds.length === 0) return {}
      return { dismissedRunIds: [...state.dismissedRunIds, ...terminalIds] }
    })
  },

  pauseWorkerRun: (runId) => {
    // Clear any pending simulation interval
    const h = runIntervals.get(runId)
    if (h) { clearTimeout(h); runIntervals.delete(runId) }
    set(state => ({
      workerRuns: state.workerRuns.map(r =>
        r.id === runId && r.state === 'running'
          ? { ...r, state: 'paused' as const }
          : r
      ),
    }))
  },

  resumeWorkerRun: (runId) => {
    const run = get().workerRuns.find(r => r.id === runId)
    if (!run || run.state !== 'paused') return
    // Transition back to running
    set(state => ({
      workerRuns: state.workerRuns.map(r =>
        r.id === runId ? { ...r, state: 'running' as const } : r
      ),
    }))
    // Resume simulation from current progress
    const resumeProgress = (progress: number) => {
      const current = get().workerRuns.find(r => r.id === runId)
      if (!current || current.state !== 'running') return
      if (progress >= 100) {
        finishRun(runId, current.objectId, get, set)
        return
      }
      const next = Math.min(progress + 12, 100)
      set(state => ({
        workerRuns: state.workerRuns.map(r =>
          r.id === runId ? { ...r, progress: next } : r
        ),
      }))
      get().addRunLog(runId, { ts: nowIso(), level: 'info', msg: getSimLog(current.workerId, next) })
      const h = setTimeout(() => resumeProgress(next), 800)
      runIntervals.set(runId, h)
    }
    resumeProgress(run.progress)
  },

  addRunLog: (runId, entry) => {
    set(state => ({
      workerRuns: state.workerRuns.map(r =>
        r.id === runId ? { ...r, logs: [...(r.logs ?? []), entry] } : r
      ),
    }))
  },

  // ─── Flow Actions ────────────────────────────────────────────────────────────
  runFlow: (flowId) => {
    const flowDef = FLOW_DEFS.find(f => f.id === flowId)
    if (!flowDef) return

    // F-021: entryConstraints enforcement
    if (flowDef.entryConstraints && flowDef.entryConstraints.length > 0) {
      const targetObj = get().objects.find(o => o.id === get().selectedObjectId)
      const constraintViolation = flowDef.entryConstraints.find(c => {
        if (c.typeId && targetObj?.typeId !== c.typeId) return true
        if (c.requiredStates && targetObj && !c.requiredStates.includes(targetObj.state)) return true
        return false
      })
      if (constraintViolation) {
        console.warn(`Flow ${flowId} entryConstraints not met`)
        return // Do not start the flow
      }
    }

    const flowRunId = genId()
    const initialStepStatus: Record<string, FlowStepStatus> = {}
    flowDef.steps.forEach(s => { initialStepStatus[s.id] = 'pending' })

    const flowRun: FlowRun = {
      id: flowRunId,
      flowId,
      flowLabel: flowDef.label,
      state: 'running',
      completedSteps: [],
      skippedSteps: [],
      activeStepId: flowDef.steps[0]?.id,
      stepStatus: initialStepStatus,
      startedAt: nowIso(),
    }

    set({ activeFlowRun: flowRun, activeView: 'flows' })

    // Simulate steps
    let stepIndex = 0
    const runNextStep = () => {
      const currentFlow = get().activeFlowRun
      if (!currentFlow || currentFlow.state !== 'running') return
      if (stepIndex >= flowDef.steps.length) {
        set(state => ({
          activeFlowRun: state.activeFlowRun
            ? { ...state.activeFlowRun, state: 'done', completedAt: nowIso(), activeStepId: undefined }
            : null,
        }))
        return
      }

      const step = flowDef.steps[stepIndex]
      // Set current step running
      set(state => ({
        activeFlowRun: state.activeFlowRun
          ? {
              ...state.activeFlowRun,
              activeStepId: step.id,
              stepStatus: { ...state.activeFlowRun.stepStatus, [step.id]: 'running' },
            }
          : null,
      }))

      setTimeout(() => {
        // Complete step
        set(state => ({
          activeFlowRun: state.activeFlowRun
            ? {
                ...state.activeFlowRun,
                completedSteps: [...state.activeFlowRun.completedSteps, step.id],
                stepStatus: { ...state.activeFlowRun.stepStatus, [step.id]: 'done' },
              }
            : null,
        }))
        stepIndex++
        setTimeout(runNextStep, 400)
      }, 1800)
    }

    setTimeout(runNextStep, 300)
  },

  // F-006: stopFlow — transition FlowRun to aborted instead of nulling it
  stopFlow: () => {
    const current = get().activeFlowRun
    if (current) {
      const abortedRun: FlowRun = { ...current, state: 'aborted' as const, completedAt: nowIso() }
      set(state => ({
        activeFlowRun: null,
        completedFlowRuns: [...state.completedFlowRuns, abortedRun],
      }))
    }
  },

  stopFlowGraph: () => {
    set({ flowExecState: null })
  },

  respondToFlowInteraction: (optionId: string, textInput?: string) => {
    set(state => {
      if (!state.flowExecState?.pendingInteraction) return state
      const nodeId = state.flowExecState.pendingInteraction.nodeId
      return {
        flowExecState: {
          ...state.flowExecState,
          status: 'running',
          pendingInteraction: undefined,
          takenBranches: { ...state.flowExecState.takenBranches, [nodeId]: optionId },
          inputResponses: textInput ? { ...state.flowExecState.inputResponses, [nodeId]: textInput } : state.flowExecState.inputResponses,
          nodeStates: { ...state.flowExecState.nodeStates, [nodeId]: optionId === 'approve' || optionId === 'fix' || optionId === 'author' || optionId === 'import' || optionId === 'staging' || optionId === 'local' || optionId === 'deploy' || optionId === 'dependency' || optionId === 'risk' || optionId === 'value' || optionId === 'tdd' || optionId === 'impl' || optionId === 'patch' || optionId === 'minor' || optionId === 'major' || optionId === 'accept' || optionId === 'lower' ? 'done' : optionId === 'escalate' || optionId === 'close' || optionId === 'block' || optionId === 'reject' ? 'failed' : 'done' },
        }
      }
    })
    if (flowResumeCallback) { flowResumeCallback(optionId); flowResumeCallback = null }
  },

  startFlowGraph: (flowId: string) => {
    const flowMaybe = FLOW_GRAPH_DEFS.find((f: FlowGraphDef) => f.id === flowId)
    if (!flowMaybe) return
    const flow: FlowGraphDef = flowMaybe

    const nodeStates: Record<string, FlowNodeExecState> = {}
    flow.nodes.forEach(n => { nodeStates[n.id] = 'idle' })

    set({
      flowExecState: {
        flowId,
        status: 'running',
        nodeStates,
        retryCounters: {},
        currentNodeId: null,
        producedArtifacts: [],
        startedAt: Date.now(),
        takenBranches: {},
        inputResponses: {},
      },
      activeView: 'flows',
    })

    // Async step-by-step execution with pauses for user interactions
    const runStep = async (nodeId: string, takenBranches: Record<string, string>): Promise<void> => {
      const node = flow.nodes.find(n => n.id === nodeId)
      if (!node) return

      const setNode = (state: FlowNodeExecState) => set(s => ({
        flowExecState: s.flowExecState ? { ...s.flowExecState, nodeStates: { ...s.flowExecState.nodeStates, [nodeId]: state }, currentNodeId: nodeId } : null
      }))

      const addArtifact = (label: string, nodeType: string) => set(s => ({
        flowExecState: s.flowExecState ? { ...s.flowExecState, producedArtifacts: [...s.flowExecState.producedArtifacts, { label, nodeType, nodeId }] } : null
      }))

      const waitForInteraction = (pending: FlowPendingInteraction): Promise<string> => {
        set(s => ({ flowExecState: s.flowExecState ? { ...s.flowExecState, status: 'waiting_input', pendingInteraction: pending } : null }))
        return new Promise(resolve => { flowResumeCallback = resolve })
      }

      const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

      if (node.nodeType === 'start') {
        setNode('done')
        await sleep(300)
        const next = flow.edges.find(e => e.source === nodeId)?.target
        if (next) await runStep(next, takenBranches)
        return
      }

      if (node.nodeType === 'end') {
        setNode('done')
        await sleep(400)
        set(s => ({ flowExecState: s.flowExecState ? { ...s.flowExecState, status: 'done', currentNodeId: null } : null }))
        return
      }

      if (node.nodeType === 'escalation') {
        setNode('done')
        await sleep(500)
        set(s => ({ flowExecState: s.flowExecState ? { ...s.flowExecState, status: 'done', currentNodeId: null } : null }))
        return
      }

      if (node.nodeType === 'decision') {
        setNode('running')
        await sleep(400)
        // Always requires interaction
        const chosen = await waitForInteraction({ nodeId, interaction: node.interaction! })
        const updatedBranches = { ...takenBranches, [nodeId]: chosen }
        set(s => ({ flowExecState: s.flowExecState ? { ...s.flowExecState, status: 'running', takenBranches: updatedBranches, nodeStates: { ...s.flowExecState.nodeStates, [nodeId]: 'done' } } : null }))
        // Follow branch edge
        const branchEdge = flow.edges.find(e => e.source === nodeId && (e.branchOptionId === chosen || (!e.branchOptionId && (e.edgeKind === 'branch' || e.edgeKind === 'default'))))
        if (branchEdge) await runStep(branchEdge.target, updatedBranches)
        return
      }

      if (node.nodeType === 'worker' || node.nodeType === 'human') {
        setNode('running')
        const dur = node.nodeType === 'human' ? 800 : (1200 + Math.random() * 800)
        await sleep(dur)
        // Mid-run interaction?
        let chosen: string | undefined
        if (node.interaction) {
          chosen = await waitForInteraction({ nodeId, interaction: node.interaction })
          set(s => ({ flowExecState: s.flowExecState ? { ...s.flowExecState, status: 'running', takenBranches: { ...s.flowExecState.takenBranches, [nodeId]: chosen! } } : null }))
          await sleep(600)
        }
        setNode('done')
        addArtifact(node.label, node.nodeType)
        await sleep(300)
        const next = flow.edges.find(e => e.source === nodeId && e.edgeKind === 'default')?.target
        if (next) await runStep(next, { ...takenBranches, ...(chosen ? { [nodeId]: chosen } : {}) })
        return
      }

      if (node.nodeType === 'gate') {
        const maxRetries = node.maxRetries ?? 2
        const retryCount = (get().flowExecState?.retryCounters[nodeId] ?? 0)
        setNode('running')
        await sleep(900)

        const willFail = Math.random() < 0.45 && retryCount < maxRetries
        if (willFail) {
          // Ask user how to handle failure via interaction
          if (node.interaction) {
            const chosen = await waitForInteraction({ nodeId, interaction: node.interaction })
            set(s => ({
              flowExecState: s.flowExecState ? {
                ...s.flowExecState, status: 'running',
                nodeStates: { ...s.flowExecState.nodeStates, [nodeId]: 'retrying' },
                retryCounters: { ...s.flowExecState.retryCounters, [nodeId]: retryCount + 1 },
                takenBranches: { ...s.flowExecState.takenBranches, [nodeId]: chosen },
              } : null
            }))
            // Route based on choice
            if (chosen === 'escalate' || chosen === 'close' || chosen === 'block' || chosen === 'reject') {
              const failEdge = flow.edges.find(e => e.source === nodeId && e.edgeKind === 'fail')
              if (failEdge) await runStep(failEdge.target, { ...takenBranches, [nodeId]: chosen })
              return
            }
            if (chosen === 'risk' || chosen === 'accept' || chosen === 'lower') {
              // Accept risk — continue to pass path
              set(s => ({ flowExecState: s.flowExecState ? { ...s.flowExecState, nodeStates: { ...s.flowExecState.nodeStates, [nodeId]: 'passed' } } : null }))
              await sleep(400)
              const passEdge = flow.edges.find(e => e.source === nodeId && e.edgeKind === 'pass' && !e.branchOptionId)
              if (passEdge) await runStep(passEdge.target, takenBranches)
              return
            }
            // 'fix' or default: retry
            const retryEdge = flow.edges.find(e => e.source === nodeId && e.edgeKind === 'retry')
            if (retryEdge) {
              await runStep(retryEdge.target, takenBranches)
              await sleep(400)
              // Re-run this gate (simplified: just pass)
            }
          } else {
            set(s => ({ flowExecState: s.flowExecState ? { ...s.flowExecState, nodeStates: { ...s.flowExecState.nodeStates, [nodeId]: 'retrying' }, retryCounters: { ...s.flowExecState.retryCounters, [nodeId]: retryCount + 1 } } : null }))
            const retryEdge = flow.edges.find(e => e.source === nodeId && e.edgeKind === 'retry')
            if (retryEdge) { await runStep(retryEdge.target, takenBranches); await sleep(400) }
          }
        }

        // F-020: when retries are exhausted, follow the 'fail' edge instead of always passing
        if (retryCount >= maxRetries) {
          const failTarget = flow.edges.find(e => e.source === nodeId && e.edgeKind === 'fail')?.target
          if (failTarget) {
            set(s => ({ flowExecState: s.flowExecState ? { ...s.flowExecState, nodeStates: { ...s.flowExecState.nodeStates, [nodeId]: 'failed' } } : null }))
            await sleep(800)
            await runStep(failTarget, takenBranches)
            return
          }
          // Only if no fail edge exists, fall through to pass
        }

        set(s => ({ flowExecState: s.flowExecState ? { ...s.flowExecState, nodeStates: { ...s.flowExecState.nodeStates, [nodeId]: 'passed' } } : null }))
        await sleep(300)
        const passEdge = flow.edges.find(e => e.source === nodeId && e.edgeKind === 'pass' && !e.branchOptionId)
        if (passEdge) await runStep(passEdge.target, takenBranches)
      }
    }

    const startNode = flow.nodes.find(n => n.nodeType === 'start')
    if (startNode) runStep(startNode.id, {}).catch(() => {})
  },

  // ─── Recommendation Actions ──────────────────────────────────────────────────
  acceptRecommendation: (recId) => {
    const rec = get().recommendations.find(r => r.id === recId)
    if (!rec) return

    // F-005: guard — do not proceed if workerDef or targetObjectId is missing
    const workerDef = WORKER_DEFS.find(w => w.id === rec.suggestedWorkerId)
    const targetObjectId = rec.relatedObjectIds[0]
    if (!workerDef || !targetObjectId) {
      console.error(`acceptRecommendation: workerDef or targetObjectId missing for rec ${recId}`)
      set(state => ({
        recommendations: state.recommendations.map(r =>
          r.id === recId ? { ...r, state: 'pending' } : r
        ),
      }))
      return
    }

    // F-005: first set state to 'accepted' (not 'executing')
    set(state => ({
      recommendations: state.recommendations.map(r =>
        r.id === recId ? { ...r, state: 'accepted' } : r
      ),
    }))

    // F-005: PoC: simulates Re-check delay; production should run validationWorker first
    setTimeout(() => {
      set(state => ({
        recommendations: state.recommendations.map(r =>
          r.id === recId ? { ...r, state: 'executing' } : r
        ),
      }))

      const runId = get().runWorker(rec.suggestedWorkerId, targetObjectId)
      // Mark done when run completes
      const checkDone = setInterval(() => {
        const run = get().workerRuns.find(r => r.id === runId)
        if (run?.state === 'done' || run?.state === 'failed') {
          clearInterval(checkDone)
          set(state => ({
            recommendations: state.recommendations.map(r =>
              r.id === recId ? { ...r, state: 'done' } : r
            ),
          }))
        }
      }, 500)
    }, 500)
  },

  dismissRecommendation: (recId) => {
    set(state => ({
      recommendations: state.recommendations.map(r =>
        r.id === recId ? { ...r, state: 'dismissed' } : r
      ),
    }))
  },

  // ─── Simulate Full Pipeline ──────────────────────────────────────────────────
  simulateFullPipeline: () => {
    const { isSimulating } = get()
    if (isSimulating) return

    set({ isSimulating: true, activeView: 'flows' })
    get().runFlow('sdlc_pipeline_flow')

    // Reset after flow completes
    setTimeout(() => {
      set({ isSimulating: false })
    }, FLOW_DEFS[0].steps.length * 2500 + 2000)
  },
}))

// ─── Worker → artifact type map ───────────────────────────────────────────────
const WORKER_ARTIFACT_TYPE: Record<string, string> = {
  create_prd_worker:       'prd',
  create_design_worker:    'design',
  create_adr_worker:       'adr',
  decompose_feature_worker:'decomposition',
  implement_code_worker:   'pull_request',
  create_release_worker:   'release',
  deploy_to_staging_worker:'deployment',
  deploy_to_prod_worker:   'deployment',
}

// ─── Helper: finish a worker run ──────────────────────────────────────────────
function finishRun(
  runId: string,
  objectId: string,
  get: () => AppState,
  set: (fn: (state: AppState) => Partial<AppState>) => void
) {
  const run = get().workerRuns.find(r => r.id === runId)
  if (!run) return

  const workerDef = WORKER_DEFS.find(w => w.id === run.workerId)
  const outputMessages: Record<string, string> = {
    create_design_worker: 'Design document created: Billing Service Architecture v1.3. 5 components identified, 12 API contracts defined.',
    decompose_feature_worker: 'Decomposed into 8 tasks across 3 sprints. Critical path identified: Schema → Webhook → Invoice → PR.',
    gap_analysis_validator: 'Gap analysis complete. Found 2 missing test scenarios, 1 uncovered requirement (FR-07). Coverage: 87%.',
    pr_design_validator: 'PR validated against design. 3 findings: 1 critical (missing dedup guard), 2 warnings. Action required.',
    traceability_analysis: 'Traceability: PRD→Design 100%, Design→Tasks 94%, Tasks→Code 78%. 3 gaps identified.',
    stale_artifact_detection: 'Staleness scan complete. 2 artifacts marked stale. task-003 missing @cpt markers in source.',
    security_impact_analysis: 'Security review complete. 1 HIGH finding: Webhook signature not validated before event dispatch. Fix required.',
    implement_code_worker: 'Implementation complete. 847 lines across 6 files. Unit tests: 34 passing. Coverage: 92%.',
    create_pr_worker: 'PR #248 created: feat/invoice-generation-worker. 12 commits, +1,240/-45 lines.',
    reverse_engineer_worker: 'Reverse engineering complete. Reconstructed 4 SDLC artifacts. 2 gaps in original design identified.',
  }

  const output = outputMessages[run.workerId] || `${workerDef?.label ?? 'Worker'} completed successfully.`

  // Emit completion log
  get().addRunLog(runId, { ts: nowIso(), level: 'info', msg: 'Worker completed successfully' })

  set(state => ({
    workerRuns: state.workerRuns.map(r =>
      r.id === runId
        ? { ...r, state: 'done' as WorkerRunState, progress: 100, completedAt: nowIso(), output }
        : r
    ),
  }))

  // Artifact creation
  const artifactTypeId = WORKER_ARTIFACT_TYPE[run.workerId]
  if (artifactTypeId) {
    const now = nowIso()
    const newObjId = `${artifactTypeId}-${Date.now()}`
    const newObj: StudioObject = {
      id: newObjId,
      typeId: artifactTypeId as import('../types/domain').ObjectTypeId,
      tenantId: 'tenant-acme',
      state: 'draft',
      title: `${run.objectTitle} — ${workerDef?.label ?? artifactTypeId}`,
      validationStatus: 'none',
      stalenessScore: 0,
      links: [],
      createdAt: now,
      updatedAt: now,
    }
    set(state => ({
      objects: [...state.objects, newObj],
      workerRuns: state.workerRuns.map(r =>
        r.id === runId
          ? { ...r, createdObjectIds: [...(r.createdObjectIds ?? []), newObjId] }
          : r
      ),
    }))
  }

  // Update object state based on worker
  const objectUpdates: Partial<StudioObject> = {}
  if (run.workerId === 'gap_analysis_validator') {
    objectUpdates.validationStatus = 'pass'
    // F-001: stalenessScore is 0.0–1.0 float; subtract 0.10 instead of integer 10
    objectUpdates.stalenessScore = Math.max(0, (get().objects.find(o => o.id === objectId)?.stalenessScore ?? 0) - 0.10)
  } else if (run.workerId === 'traceability_analysis') {
    objectUpdates.validationStatus = 'pass'
  } else if (run.workerId === 'stale_artifact_detection') {
    objectUpdates.stalenessScore = 0
  }

  if (Object.keys(objectUpdates).length > 0) {
    set(state => ({
      objects: state.objects.map(o =>
        o.id === objectId ? { ...o, ...objectUpdates } : o
      ),
    }))
  }

  // Clean up interval handle if still tracked
  runIntervals.delete(runId)
}

// ─── Selectors ────────────────────────────────────────────────────────────────
export const selectObject = (state: AppState) =>
  state.selectedObjectId ? state.objects.find(o => o.id === state.selectedObjectId) ?? null : null

export const selectActiveWorkerRuns = (state: AppState) =>
  state.workerRuns.filter(r => r.state === 'running' || r.state === 'awaiting_input' || r.state === 'pending')

export const selectPendingRecommendations = (state: AppState) =>
  state.recommendations.filter(r => r.state === 'pending' || r.state === 'accepted' || r.state === 'executing')

export const selectWorkersForObject = (typeId: string) => () =>
  getWorkersForObject(typeId)
