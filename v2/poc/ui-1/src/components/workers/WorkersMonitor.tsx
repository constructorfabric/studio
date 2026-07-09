import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Play,
  Pause,
  Square,
  Terminal,
  Package,
  Clock,
  Loader,
  CheckCircle,
  XCircle,
  AlertCircle,
  List,
  ChevronRight,
  ChevronDown,
  GitBranch,
} from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import type { WorkerRun, FlowRun, LogEntry } from '../../types/domain'

// ─── State helpers ────────────────────────────────────────────────────────────

const ACTIVE_STATES = new Set(['running', 'pending', 'paused', 'awaiting_input'])

function isActive(run: WorkerRun): boolean {
  return ACTIVE_STATES.has(run.state)
}

function elapsed(startedAt: string, completedAt?: string): string {
  const end = completedAt ? new Date(completedAt) : new Date()
  const ms = end.getTime() - new Date(startedAt).getTime()
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

// ─── State icons / badges ─────────────────────────────────────────────────────

function WorkerStateIcon({ state }: { state: WorkerRun['state'] }) {
  switch (state) {
    case 'running':       return <Loader size={13} className="text-blue-400 animate-spin shrink-0" />
    case 'pending':       return <Clock size={13} className="text-zinc-400 shrink-0" />
    case 'paused':        return <Pause size={13} className="text-amber-400 shrink-0" />
    case 'awaiting_input':return <AlertCircle size={13} className="text-amber-400 shrink-0" />
    case 'done':          return <CheckCircle size={13} className="text-emerald-400 shrink-0" />
    case 'failed':        return <XCircle size={13} className="text-red-400 shrink-0" />
    case 'aborted':       return <XCircle size={13} className="text-zinc-500 shrink-0" />
    case 'escalated':     return <AlertCircle size={13} className="text-orange-400 shrink-0" />
    default:              return <Clock size={13} className="text-zinc-400 shrink-0" />
  }
}

function FlowStateIcon({ state }: { state: WorkerRun['state'] }) {
  switch (state) {
    case 'running':  return <Loader size={13} className="text-indigo-400 animate-spin shrink-0" />
    case 'done':     return <CheckCircle size={13} className="text-emerald-400 shrink-0" />
    case 'failed':   return <XCircle size={13} className="text-red-400 shrink-0" />
    case 'aborted':  return <XCircle size={13} className="text-zinc-500 shrink-0" />
    default:         return <GitBranch size={13} className="text-zinc-400 shrink-0" />
  }
}

function WorkerStateBadge({ state }: { state: WorkerRun['state'] }) {
  const config: Record<string, { label: string; className: string }> = {
    running:        { label: 'Running',         className: 'bg-blue-900/40 text-blue-300 border-blue-700/50' },
    pending:        { label: 'Pending',          className: 'bg-zinc-800 text-zinc-400 border-zinc-700' },
    paused:         { label: 'Paused',           className: 'bg-amber-900/30 text-amber-300 border-amber-700/50' },
    awaiting_input: { label: 'Awaiting Input',   className: 'bg-amber-900/30 text-amber-300 border-amber-700/50' },
    done:           { label: 'Done',             className: 'bg-emerald-900/30 text-emerald-300 border-emerald-700/50' },
    failed:         { label: 'Failed',           className: 'bg-red-900/30 text-red-300 border-red-700/50' },
    aborted:        { label: 'Aborted',          className: 'bg-zinc-800 text-zinc-500 border-zinc-700' },
    escalated:      { label: 'Escalated',        className: 'bg-orange-900/30 text-orange-300 border-orange-700/50' },
  }
  const c = config[state] ?? { label: state, className: 'bg-zinc-800 text-zinc-400 border-zinc-700' }
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${c.className}`}>
      {c.label}
    </span>
  )
}

// ─── Log tab ─────────────────────────────────────────────────────────────────

function LogLevelBadge({ level }: { level: LogEntry['level'] }) {
  const cfg: Record<string, string> = {
    debug: 'text-zinc-500',
    info:  'text-blue-400',
    warn:  'text-amber-400',
    error: 'text-red-400',
  }
  return (
    <span className={`text-[10px] font-mono font-bold uppercase w-10 shrink-0 ${cfg[level] ?? 'text-zinc-400'}`}>
      {level}
    </span>
  )
}

function LogTab({ run }: { run: WorkerRun }) {
  const logEndRef = useRef<HTMLDivElement>(null)
  const logs = run.logs ?? []

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  if (logs.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <p className="text-xs text-zinc-600 italic">No log entries yet</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-3 font-mono">
      <div className="space-y-0.5">
        {logs.map((entry, idx) => (
          <div key={idx} className="flex items-start gap-2 py-0.5 hover:bg-zinc-800/30 rounded px-1">
            <span className="text-[10px] text-zinc-600 shrink-0 tabular-nums">
              {new Date(entry.ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
            <LogLevelBadge level={entry.level} />
            <span className="text-[11px] text-zinc-300 leading-relaxed">{entry.msg}</span>
          </div>
        ))}
        <div ref={logEndRef} />
      </div>
    </div>
  )
}

// ─── Artifacts tab ────────────────────────────────────────────────────────────

const TYPE_LABEL: Record<string, string> = {
  prd: 'PRD', design: 'DESIGN', adr: 'ADR', decomposition: 'DECOMP',
  feature_spec: 'FSPEC', task: 'TASK', pull_request: 'PR', build: 'BUILD',
  incident: 'INC', component: 'COMPONENT', person: 'PERSON', team: 'TEAM',
  release: 'RELEASE', deployment: 'DEPLOY', environment: 'ENV',
}

const TYPE_COLOR: Record<string, string> = {
  prd: 'text-purple-400 bg-purple-900/30 border-purple-700/40',
  design: 'text-blue-400 bg-blue-900/30 border-blue-700/40',
  adr: 'text-violet-400 bg-violet-900/30 border-violet-700/40',
  decomposition: 'text-indigo-400 bg-indigo-900/30 border-indigo-700/40',
  feature_spec: 'text-teal-400 bg-teal-900/30 border-teal-700/40',
  task: 'text-cyan-400 bg-cyan-900/30 border-cyan-700/40',
  pull_request: 'text-orange-400 bg-orange-900/30 border-orange-700/40',
  build: 'text-lime-400 bg-lime-900/30 border-lime-700/40',
  incident: 'text-red-400 bg-red-900/30 border-red-700/40',
  component: 'text-cyan-300 bg-cyan-900/20 border-cyan-700/30',
  person: 'text-purple-300 bg-purple-900/20 border-purple-700/30',
  team: 'text-indigo-300 bg-indigo-900/20 border-indigo-700/30',
  release: 'text-emerald-400 bg-emerald-900/30 border-emerald-700/40',
  deployment: 'text-orange-300 bg-orange-900/20 border-orange-700/30',
  environment: 'text-slate-400 bg-slate-900/20 border-slate-700/30',
}

function ArtifactsTab({ run }: { run: WorkerRun }) {
  const objects = useAppStore(s => s.objects)
  const setActiveView = useAppStore(s => s.setActiveView)
  const selectObject = useAppStore(s => s.selectObject)
  const ids = run.createdObjectIds ?? []

  if (ids.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center">
          <Package size={24} className="text-zinc-700 mx-auto mb-2" />
          <p className="text-xs text-zinc-600 italic">No artifacts created</p>
        </div>
      </div>
    )
  }

  const artifacts = ids.map(id => objects.find(o => o.id === id)).filter(Boolean)

  return (
    <div className="flex-1 overflow-y-auto p-3">
      <div className="space-y-2">
        {artifacts.map(obj => {
          if (!obj) return null
          const typeLabel = TYPE_LABEL[obj.typeId] ?? obj.typeId.toUpperCase()
          const typeColor = TYPE_COLOR[obj.typeId] ?? 'text-zinc-400 bg-zinc-800 border-zinc-700'
          return (
            <div
              key={obj.id}
              className="flex items-center gap-3 p-2.5 rounded-lg bg-zinc-800/50 border border-zinc-700/50 hover:border-zinc-600 transition-colors"
            >
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0 ${typeColor}`}>
                {typeLabel}
              </span>
              <span className="text-xs text-zinc-200 flex-1 truncate">{obj.title}</span>
              <button
                onClick={() => {
                  selectObject(obj.id)
                  setActiveView('graph')
                }}
                className="text-[10px] text-indigo-400 hover:text-indigo-300 transition-colors shrink-0 px-2 py-1 rounded hover:bg-indigo-900/30"
              >
                View on Graph
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Worker Run Detail Panel ──────────────────────────────────────────────────

type DetailTab = 'log' | 'artifacts'

function WorkerRunDetailPanel({ run }: { run: WorkerRun }) {
  const [tab, setTab] = useState<DetailTab>('log')
  const pauseWorkerRun = useAppStore(s => s.pauseWorkerRun)
  const resumeWorkerRun = useAppStore(s => s.resumeWorkerRun)
  const cancelWorkerRun = useAppStore(s => s.cancelWorkerRun)

  const active = isActive(run)
  const canPause = run.state === 'running'
  const canResume = run.state === 'paused'
  const canStop = active

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-zinc-900/50">
      {/* Header */}
      <div className="px-5 py-4 border-b border-zinc-800 shrink-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <WorkerStateIcon state={run.state} />
              <h2 className="text-sm font-semibold text-zinc-100 truncate">{run.workerLabel}</h2>
              <WorkerStateBadge state={run.state} />
            </div>
            <p className="text-xs text-zinc-500 truncate">on: {run.objectTitle}</p>
            <p className="text-[10px] text-zinc-600 mt-0.5">
              Started {new Date(run.startedAt).toLocaleTimeString()} · {elapsed(run.startedAt, run.completedAt)} elapsed
            </p>
          </div>
          {/* Controls */}
          <div className="flex items-center gap-1.5 shrink-0">
            {canPause && (
              <button
                onClick={() => pauseWorkerRun(run.id)}
                title="Pause"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-900/30 text-amber-300 border border-amber-700/50 hover:bg-amber-900/50 transition-colors"
              >
                <Pause size={12} />
                Pause
              </button>
            )}
            {canResume && (
              <button
                onClick={() => resumeWorkerRun(run.id)}
                title="Resume"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-900/30 text-blue-300 border border-blue-700/50 hover:bg-blue-900/50 transition-colors"
              >
                <Play size={12} />
                Resume
              </button>
            )}
            {canStop && (
              <button
                onClick={() => cancelWorkerRun(run.id)}
                title="Stop"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-900/30 text-red-300 border border-red-700/50 hover:bg-red-900/50 transition-colors"
              >
                <Square size={12} />
                Stop
              </button>
            )}
          </div>
        </div>

        {/* Progress bar */}
        {(run.state === 'running' || run.state === 'paused' || run.state === 'pending') && (
          <div className="mt-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-zinc-500">{Math.round(run.progress)}% complete</span>
              {run.state === 'paused' && (
                <span className="text-[10px] text-amber-400">Paused</span>
              )}
            </div>
            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  run.state === 'paused'
                    ? 'bg-amber-500/60'
                    : 'bg-gradient-to-r from-indigo-500 to-blue-400'
                }`}
                style={{ width: `${run.progress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-zinc-800 shrink-0">
        <button
          onClick={() => setTab('log')}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors border-b-2 ${
            tab === 'log'
              ? 'border-indigo-500 text-indigo-300'
              : 'border-transparent text-zinc-500 hover:text-zinc-300'
          }`}
        >
          <Terminal size={12} />
          Log
          {(run.logs?.length ?? 0) > 0 && (
            <span className="text-[10px] bg-zinc-700 text-zinc-400 rounded-full px-1.5 py-0.5">
              {run.logs?.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setTab('artifacts')}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors border-b-2 ${
            tab === 'artifacts'
              ? 'border-indigo-500 text-indigo-300'
              : 'border-transparent text-zinc-500 hover:text-zinc-300'
          }`}
        >
          <Package size={12} />
          Artifacts
          {(run.createdObjectIds?.length ?? 0) > 0 && (
            <span className="text-[10px] bg-emerald-800/60 text-emerald-400 rounded-full px-1.5 py-0.5">
              {run.createdObjectIds?.length}
            </span>
          )}
        </button>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {tab === 'log' && <LogTab run={run} />}
        {tab === 'artifacts' && <ArtifactsTab run={run} />}
      </div>

      {/* Cost & Performance */}
      {(run.costUsd != null || run.model) && (
        <div className="px-4 py-3 border-t border-zinc-800 shrink-0">
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2">Cost & Performance</p>
          <div className="flex items-center gap-4 text-xs">
            {run.costUsd != null && (
              <div>
                <span className="text-indigo-300 font-bold">${run.costUsd.toFixed(2)}</span>
                <span className="text-zinc-600 ml-1">cost</span>
              </div>
            )}
            {run.tokensIn != null && (
              <div>
                <span className="text-zinc-300">{Math.round(((run.tokensIn ?? 0) + (run.tokensOut ?? 0))/1000)}k</span>
                <span className="text-zinc-600 ml-1">tokens</span>
              </div>
            )}
            {run.model && (
              <div className="text-zinc-500 text-[10px]">{run.model}</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Flow Run Detail Panel ────────────────────────────────────────────────────

function FlowRunDetailPanel({ flowRun }: { flowRun: FlowRun }) {
  const stopFlow = useAppStore(s => s.stopFlow)
  const activeFlowRun = useAppStore(s => s.activeFlowRun)

  const isActive = flowRun.state === 'running'
  const isLive = activeFlowRun?.id === flowRun.id

  const stepStatusConfig: Record<string, { label: string; className: string }> = {
    pending:  { label: 'Pending',  className: 'bg-zinc-800 text-zinc-400 border-zinc-700' },
    running:  { label: 'Running',  className: 'bg-blue-900/40 text-blue-300 border-blue-700/50' },
    done:     { label: 'Done',     className: 'bg-emerald-900/30 text-emerald-300 border-emerald-700/50' },
    failed:   { label: 'Failed',   className: 'bg-red-900/30 text-red-300 border-red-700/50' },
    skipped:  { label: 'Skipped',  className: 'bg-zinc-800 text-zinc-500 border-zinc-700' },
    escalated:{ label: 'Escalated',className: 'bg-orange-900/30 text-orange-300 border-orange-700/50' },
    aborted:  { label: 'Aborted',  className: 'bg-zinc-800 text-zinc-500 border-zinc-700' },
  }

  const allStepIds = Object.keys(flowRun.stepStatus)

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-zinc-900/50">
      {/* Header */}
      <div className="px-5 py-4 border-b border-zinc-800 shrink-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <FlowStateIcon state={flowRun.state} />
              <h2 className="text-sm font-semibold text-zinc-100 truncate">{flowRun.flowLabel}</h2>
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${
                flowRun.state === 'running'
                  ? 'bg-indigo-900/40 text-indigo-300 border-indigo-700/50'
                  : flowRun.state === 'done'
                  ? 'bg-emerald-900/30 text-emerald-300 border-emerald-700/50'
                  : flowRun.state === 'failed'
                  ? 'bg-red-900/30 text-red-300 border-red-700/50'
                  : 'bg-zinc-800 text-zinc-500 border-zinc-700'
              }`}>
                {flowRun.state.charAt(0).toUpperCase() + flowRun.state.slice(1)}
              </span>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-indigo-900/20 text-indigo-400 border border-indigo-700/30">
                FLOW
              </span>
            </div>
            <p className="text-[10px] text-zinc-600 mt-0.5">
              Started {new Date(flowRun.startedAt).toLocaleTimeString()} · {elapsed(flowRun.startedAt, flowRun.completedAt)} elapsed
            </p>
          </div>
          {isLive && isActive && (
            <button
              onClick={() => stopFlow()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-900/30 text-red-300 border border-red-700/50 hover:bg-red-900/50 transition-colors shrink-0"
            >
              <Square size={12} />
              Stop Flow
            </button>
          )}
        </div>

        {/* Progress: completed steps */}
        <div className="mt-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] text-zinc-500">
              {flowRun.completedSteps.length} / {allStepIds.length} steps
            </span>
          </div>
          <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500 bg-gradient-to-r from-indigo-500 to-violet-400"
              style={{ width: allStepIds.length > 0 ? `${(flowRun.completedSteps.length / allStepIds.length) * 100}%` : '0%' }}
            />
          </div>
        </div>
      </div>

      {/* Steps tab header */}
      <div className="flex border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium text-indigo-300 border-b-2 border-indigo-500">
          <List size={12} />
          Steps
        </div>
      </div>

      {/* Steps list */}
      <div className="flex-1 overflow-y-auto p-3">
        {allStepIds.length === 0 ? (
          <p className="text-xs text-zinc-600 italic text-center mt-4">No step data available</p>
        ) : (
          <div className="space-y-1.5">
            {allStepIds.map((stepId, idx) => {
              const status = flowRun.stepStatus[stepId] ?? 'pending'
              const cfg = stepStatusConfig[status] ?? { label: status, className: 'bg-zinc-800 text-zinc-400 border-zinc-700' }
              const isRunningStep = status === 'running'
              return (
                <div
                  key={stepId}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-colors ${
                    isRunningStep ? 'border-blue-700/50 bg-blue-900/10' : 'border-zinc-800 bg-zinc-900/30'
                  }`}
                >
                  <span className="text-[10px] text-zinc-600 tabular-nums w-4 shrink-0">{idx + 1}</span>
                  {isRunningStep ? (
                    <Loader size={12} className="text-blue-400 animate-spin shrink-0" />
                  ) : status === 'done' ? (
                    <CheckCircle size={12} className="text-emerald-400 shrink-0" />
                  ) : status === 'failed' ? (
                    <XCircle size={12} className="text-red-400 shrink-0" />
                  ) : (
                    <Clock size={12} className="text-zinc-600 shrink-0" />
                  )}
                  <span className="text-xs text-zinc-300 flex-1 truncate">{stepId}</span>
                  <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${cfg.className}`}>
                    {cfg.label}
                  </span>
                </div>
              )
            })}
          </div>
        )}
        <p className="text-[10px] text-zinc-600 italic text-center mt-4">
          Step logs are available in each child Worker Run below
        </p>
      </div>
    </div>
  )
}

// ─── Tree node types ──────────────────────────────────────────────────────────

type TreeNodeKind = 'flow' | 'worker'

interface TreeNode {
  kind: TreeNodeKind
  id: string
  // For flow nodes
  flowRun?: FlowRun
  // For worker nodes
  workerRun?: WorkerRun
  children: TreeNode[]
  depth: number
}

// ─── Build tree ───────────────────────────────────────────────────────────────

function buildTree(
  workerRuns: WorkerRun[],
  activeFlowRun: FlowRun | null,
  completedFlowRuns: FlowRun[]
): TreeNode[] {
  const allFlowRuns = [
    ...(activeFlowRun ? [activeFlowRun] : []),
    ...completedFlowRuns,
  ].sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())

  const flowRunIds = new Set(allFlowRuns.map(f => f.id))

  // Worker runs that are children of a FlowRun
  const childOfFlow = new Set(
    workerRuns.filter(r => r.parentRunId && flowRunIds.has(r.parentRunId)).map(r => r.id)
  )

  // Worker runs that are children of another WorkerRun
  const workerRunIds = new Set(workerRuns.map(r => r.id))
  const childOfWorker = new Set(
    workerRuns.filter(r => r.parentRunId && workerRunIds.has(r.parentRunId) && !flowRunIds.has(r.parentRunId)).map(r => r.id)
  )

  const roots: TreeNode[] = []

  // Flow root nodes
  for (const flowRun of allFlowRuns) {
    const children = workerRuns
      .filter(r => r.parentRunId === flowRun.id)
      .sort((a, b) => new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime())
      .map(r => {
        // Children of this workerRun
        const grandchildren = workerRuns
          .filter(gr => gr.parentRunId === r.id)
          .sort((a, b) => new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime())
          .map(gr => ({ kind: 'worker' as const, id: gr.id, workerRun: gr, children: [], depth: 2 }))
        return { kind: 'worker' as const, id: r.id, workerRun: r, children: grandchildren, depth: 1 }
      })
    roots.push({ kind: 'flow', id: flowRun.id, flowRun, children, depth: 0 })
  }

  // Standalone worker runs (not child of flow or another worker)
  const standaloneWorkers = workerRuns
    .filter(r => !childOfFlow.has(r.id) && !childOfWorker.has(r.id) && (!r.parentRunId || !flowRunIds.has(r.parentRunId)))
    .sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())

  for (const run of standaloneWorkers) {
    const children = workerRuns
      .filter(r => r.parentRunId === run.id)
      .sort((a, b) => new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime())
      .map(r => ({ kind: 'worker' as const, id: r.id, workerRun: r, children: [], depth: 1 }))
    roots.push({ kind: 'worker', id: run.id, workerRun: run, children, depth: 0 })
  }

  return roots
}

// ─── Tree List Item ───────────────────────────────────────────────────────────

function FlowTreeItem({
  node,
  selected,
  expanded,
  onSelect,
  onToggle,
}: {
  node: TreeNode
  selected: boolean
  expanded: boolean
  onSelect: () => void
  onToggle: () => void
}) {
  const flowRun = node.flowRun!
  const hasChildren = node.children.length > 0
  const isActive = flowRun.state === 'running'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -6 }}
    >
      <button
        onClick={onSelect}
        className={`w-full text-left px-2 py-2 border-b border-zinc-800/60 transition-colors flex items-start gap-1.5 ${
          selected
            ? 'bg-indigo-900/20 border-l-2 border-l-indigo-500'
            : 'hover:bg-zinc-800/40 border-l-2 border-l-transparent'
        }`}
      >
        {/* Expand toggle */}
        <button
          onClick={e => { e.stopPropagation(); onToggle() }}
          className="mt-0.5 shrink-0 text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          {hasChildren
            ? expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />
            : <span className="w-3 block" />
          }
        </button>
        <div className="flex items-start gap-2 flex-1 min-w-0">
          <FlowStateIcon state={flowRun.state} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-bold px-1 py-0.5 rounded bg-indigo-900/30 text-indigo-400 border border-indigo-700/30 shrink-0">FLOW</span>
              <p className="text-xs font-medium text-zinc-200 truncate">{flowRun.flowLabel}</p>
              {isActive && (
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse shrink-0" />
              )}
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[10px] text-zinc-600">
                {flowRun.completedSteps.length}/{Object.keys(flowRun.stepStatus).length} steps
              </span>
            </div>
          </div>
        </div>
      </button>
    </motion.div>
  )
}

function WorkerTreeItem({
  node,
  selected,
  expanded,
  onSelect,
  onToggle,
}: {
  node: TreeNode
  selected: boolean
  expanded: boolean
  onSelect: () => void
  onToggle: () => void
}) {
  const run = node.workerRun!
  const hasChildren = node.children.length > 0
  const active = isActive(run)
  const indent = node.depth * 16

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -6 }}
    >
      <button
        onClick={onSelect}
        className={`w-full text-left px-2 py-2 border-b border-zinc-800/60 transition-colors flex items-start gap-1.5 ${
          selected
            ? 'bg-indigo-900/20 border-l-2 border-l-indigo-500'
            : 'hover:bg-zinc-800/40 border-l-2 border-l-transparent'
        }`}
        style={{ paddingLeft: `${8 + indent}px` }}
      >
        {/* Expand toggle */}
        <button
          onClick={e => { e.stopPropagation(); onToggle() }}
          className="mt-0.5 shrink-0 text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          {hasChildren
            ? expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />
            : <span className="w-3 block" />
          }
        </button>
        <div className="relative mt-0.5 shrink-0">
          <WorkerStateIcon state={run.state} />
          {active && run.state === 'running' && (
            <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-blue-500 animate-ping opacity-75" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-zinc-200 truncate leading-tight">{run.workerLabel}</p>
          <p className="text-[10px] text-zinc-500 truncate mt-0.5">{run.objectTitle}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <WorkerStateBadge state={run.state} />
            <span className="text-[10px] text-zinc-600">{elapsed(run.startedAt, run.completedAt)}</span>
            {run.costUsd != null && run.costUsd > 0 && (
              <span className="text-[9px] text-zinc-600 tabular-nums">${run.costUsd.toFixed(2)}</span>
            )}
          </div>
        </div>
      </button>
    </motion.div>
  )
}

// ─── Tree renderer ────────────────────────────────────────────────────────────

function TreeRenderer({
  nodes,
  selectedId,
  selectedKind,
  expandedIds,
  onSelectWorker,
  onSelectFlow,
  onToggle,
}: {
  nodes: TreeNode[]
  selectedId: string | null
  selectedKind: TreeNodeKind | null
  expandedIds: Set<string>
  onSelectWorker: (id: string) => void
  onSelectFlow: (id: string) => void
  onToggle: (id: string) => void
}) {
  const renderNode = (node: TreeNode): React.ReactNode => {
    const expanded = expandedIds.has(node.id)
    const isSelected = selectedId === node.id && (
      (node.kind === 'flow' && selectedKind === 'flow') ||
      (node.kind === 'worker' && selectedKind === 'worker')
    )
    return (
      <div key={node.id}>
        {node.kind === 'flow' ? (
          <FlowTreeItem
            node={node}
            selected={isSelected}
            expanded={expanded}
            onSelect={() => onSelectFlow(node.id)}
            onToggle={() => onToggle(node.id)}
          />
        ) : (
          <WorkerTreeItem
            node={node}
            selected={isSelected}
            expanded={expanded}
            onSelect={() => onSelectWorker(node.id)}
            onToggle={() => onToggle(node.id)}
          />
        )}
        {expanded && node.children.length > 0 && (
          <AnimatePresence initial={false}>
            {node.children.map(child => renderNode(child))}
          </AnimatePresence>
        )}
      </div>
    )
  }

  return <>{nodes.map(renderNode)}</>
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <div className="w-14 h-14 rounded-2xl bg-zinc-800/60 border border-zinc-700/50 flex items-center justify-center mx-auto mb-4">
          <List size={22} className="text-zinc-600" />
        </div>
        <p className="text-sm font-medium text-zinc-400">No run selected</p>
        <p className="text-xs text-zinc-600 mt-1">Click a run from the list to inspect it</p>
      </div>
    </div>
  )
}

// ─── Main WorkersMonitor ──────────────────────────────────────────────────────

export function WorkersMonitor() {
  const workerRuns = useAppStore(s => s.workerRuns)
  const activeFlowRun = useAppStore(s => s.activeFlowRun)
  const completedFlowRuns = useAppStore(s => s.completedFlowRuns)
  const selectedMonitorRunId = useAppStore(s => s.selectedMonitorRunId)
  const setSelectedMonitorRun = useAppStore(s => s.setSelectedMonitorRun)

  // Track whether selected is a flow or worker
  const [selectedKind, setSelectedKind] = useState<TreeNodeKind | null>(null)

  // Expanded nodes
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  const tree = buildTree(workerRuns, activeFlowRun, completedFlowRuns)

  const allFlowRuns = [
    ...(activeFlowRun ? [activeFlowRun] : []),
    ...completedFlowRuns,
  ]

  const activeCount = workerRuns.filter(r => isActive(r)).length

  // Auto-expand active flow runs and active worker runs
  useEffect(() => {
    setExpandedIds(prev => {
      const next = new Set(prev)
      // Auto-expand active flow runs
      if (activeFlowRun) next.add(activeFlowRun.id)
      // Auto-expand worker run parents that are active
      workerRuns.filter(r => isActive(r) && r.parentRunId).forEach(r => {
        if (r.parentRunId) next.add(r.parentRunId)
      })
      return next
    })
  }, [activeFlowRun?.id, workerRuns.filter(r => isActive(r)).length]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-select logic: if nothing selected, pick first node
  useEffect(() => {
    if (!selectedMonitorRunId) {
      // Try to find active flow run, then active worker run, then first of either
      if (activeFlowRun) {
        setSelectedMonitorRun(activeFlowRun.id)
        setSelectedKind('flow')
      } else if (workerRuns.length > 0) {
        const sorted = [...workerRuns].sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())
        setSelectedMonitorRun(sorted[0].id)
        setSelectedKind('worker')
      }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSelectWorker = (id: string) => {
    setSelectedMonitorRun(id)
    setSelectedKind('worker')
  }

  const handleSelectFlow = (id: string) => {
    setSelectedMonitorRun(id)
    setSelectedKind('flow')
  }

  const handleToggle = (id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  // Resolve the detail panel content
  const selectedWorkerRun = selectedKind === 'worker'
    ? workerRuns.find(r => r.id === selectedMonitorRunId) ?? null
    : null
  const selectedFlowRun = selectedKind === 'flow'
    ? allFlowRuns.find(f => f.id === selectedMonitorRunId) ?? null
    : null

  const totalCount = workerRuns.length + allFlowRuns.length

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left panel — tree list */}
      <div className="w-[300px] shrink-0 border-r border-zinc-800 flex flex-col overflow-hidden bg-zinc-950">
        {/* Panel header */}
        <div className="px-4 py-3 border-b border-zinc-800 shrink-0">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-200">Monitor</h2>
            <div className="flex items-center gap-2">
              {activeCount > 0 && (
                <span className="text-[10px] font-medium bg-blue-900/40 text-blue-300 border border-blue-700/50 rounded-full px-2 py-0.5 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                  {activeCount} active
                </span>
              )}
              <span className="text-[10px] text-zinc-600">{totalCount} total</span>
            </div>
          </div>
        </div>

        {/* Tree list */}
        <div className="flex-1 overflow-y-auto">
          {tree.length === 0 ? (
            <div className="p-4 text-center">
              <p className="text-xs text-zinc-600 italic">No runs yet</p>
            </div>
          ) : (
            <AnimatePresence initial={false}>
              <TreeRenderer
                nodes={tree}
                selectedId={selectedMonitorRunId}
                selectedKind={selectedKind}
                expandedIds={expandedIds}
                onSelectWorker={handleSelectWorker}
                onSelectFlow={handleSelectFlow}
                onToggle={handleToggle}
              />
            </AnimatePresence>
          )}
        </div>
      </div>

      {/* Right panel — detail */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {selectedWorkerRun ? (
          <WorkerRunDetailPanel run={selectedWorkerRun} />
        ) : selectedFlowRun ? (
          <FlowRunDetailPanel flowRun={selectedFlowRun} />
        ) : (
          <EmptyState />
        )}
      </div>
    </div>
  )
}
