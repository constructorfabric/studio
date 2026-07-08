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
} from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import type { WorkerRun, LogEntry } from '../../types/domain'

// ─── State helpers ────────────────────────────────────────────────────────────

const ACTIVE_STATES = new Set(['running', 'pending', 'paused', 'awaiting_input'])

function isActive(run: WorkerRun): boolean {
  return ACTIVE_STATES.has(run.state)
}

function elapsed(run: WorkerRun): string {
  const end = run.completedAt ? new Date(run.completedAt) : new Date()
  const ms = end.getTime() - new Date(run.startedAt).getTime()
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

function StateIcon({ state }: { state: WorkerRun['state'] }) {
  switch (state) {
    case 'running':
      return <Loader size={14} className="text-blue-400 animate-spin shrink-0" />
    case 'pending':
      return <Clock size={14} className="text-zinc-400 shrink-0" />
    case 'paused':
      return <Pause size={14} className="text-amber-400 shrink-0" />
    case 'awaiting_input':
      return <AlertCircle size={14} className="text-amber-400 shrink-0" />
    case 'done':
      return <CheckCircle size={14} className="text-emerald-400 shrink-0" />
    case 'failed':
      return <XCircle size={14} className="text-red-400 shrink-0" />
    case 'aborted':
      return <XCircle size={14} className="text-zinc-500 shrink-0" />
    case 'escalated':
      return <AlertCircle size={14} className="text-orange-400 shrink-0" />
    default:
      return <Clock size={14} className="text-zinc-400 shrink-0" />
  }
}

function StateBadge({ state }: { state: WorkerRun['state'] }) {
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

// ─── Detail panel ─────────────────────────────────────────────────────────────

type DetailTab = 'log' | 'artifacts'

function DetailPanel({ run }: { run: WorkerRun }) {
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
              <StateIcon state={run.state} />
              <h2 className="text-sm font-semibold text-zinc-100 truncate">{run.workerLabel}</h2>
              <StateBadge state={run.state} />
            </div>
            <p className="text-xs text-zinc-500 truncate">on: {run.objectTitle}</p>
            <p className="text-[10px] text-zinc-600 mt-0.5">
              Started {new Date(run.startedAt).toLocaleTimeString()} · {elapsed(run)} elapsed
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
    </div>
  )
}

// ─── List item ────────────────────────────────────────────────────────────────

function RunListItem({
  run,
  selected,
  onClick,
}: {
  run: WorkerRun
  selected: boolean
  onClick: () => void
}) {
  const active = isActive(run)

  return (
    <motion.button
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -8 }}
      onClick={onClick}
      className={`w-full text-left px-3 py-2.5 border-b border-zinc-800/60 transition-colors ${
        selected
          ? 'bg-indigo-900/20 border-l-2 border-l-indigo-500'
          : 'hover:bg-zinc-800/40 border-l-2 border-l-transparent'
      }`}
    >
      <div className="flex items-start gap-2">
        <div className="relative mt-0.5">
          <StateIcon state={run.state} />
          {active && run.state === 'running' && (
            <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-blue-500 animate-ping opacity-75" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-zinc-200 truncate leading-tight">{run.workerLabel}</p>
          <p className="text-[10px] text-zinc-500 truncate mt-0.5">{run.objectTitle}</p>
          <div className="flex items-center gap-2 mt-1">
            <StateBadge state={run.state} />
            <span className="text-[10px] text-zinc-600">{elapsed(run)}</span>
          </div>
        </div>
      </div>
    </motion.button>
  )
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

// ─── Main component ───────────────────────────────────────────────────────────

export function WorkersMonitor() {
  const allRuns = useAppStore(s => s.workerRuns)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)

  // Sort: most recent first
  const sorted = [...allRuns].sort(
    (a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()
  )

  const selectedRun = sorted.find(r => r.id === selectedRunId) ?? null

  // Auto-select first active run if nothing selected
  useEffect(() => {
    if (!selectedRunId && sorted.length > 0) {
      setSelectedRunId(sorted[0].id)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Keep selectedRunId valid when runs list changes
  useEffect(() => {
    if (selectedRunId && !sorted.find(r => r.id === selectedRunId)) {
      setSelectedRunId(sorted[0]?.id ?? null)
    }
  }, [sorted.length, selectedRunId]) // eslint-disable-line react-hooks/exhaustive-deps

  const activeCount = sorted.filter(r => isActive(r)).length

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left panel — run list */}
      <div className="w-[280px] shrink-0 border-r border-zinc-800 flex flex-col overflow-hidden bg-zinc-950">
        {/* Panel header */}
        <div className="px-4 py-3 border-b border-zinc-800 shrink-0">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-200">Worker Runs</h2>
            <div className="flex items-center gap-2">
              {activeCount > 0 && (
                <span className="text-[10px] font-medium bg-blue-900/40 text-blue-300 border border-blue-700/50 rounded-full px-2 py-0.5 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                  {activeCount} active
                </span>
              )}
              <span className="text-[10px] text-zinc-600">{sorted.length} total</span>
            </div>
          </div>
        </div>

        {/* Run list */}
        <div className="flex-1 overflow-y-auto">
          {sorted.length === 0 ? (
            <div className="p-4 text-center">
              <p className="text-xs text-zinc-600 italic">No runs yet</p>
            </div>
          ) : (
            <AnimatePresence initial={false}>
              {sorted.map(run => (
                <RunListItem
                  key={run.id}
                  run={run}
                  selected={run.id === selectedRunId}
                  onClick={() => setSelectedRunId(run.id)}
                />
              ))}
            </AnimatePresence>
          )}
        </div>
      </div>

      {/* Right panel — detail */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {selectedRun ? <DetailPanel run={selectedRun} /> : <EmptyState />}
      </div>
    </div>
  )
}
