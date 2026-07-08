import { useState } from 'react'
import {
  RefreshCw,
  CheckCircle,
  XCircle,
  Loader,
  Star,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  Clock,
} from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import type { LoopRun, IterationRun, WorkerRun, LoopTerminationReason } from '../../types/domain'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtCost(usd: number): string {
  return `$${usd.toFixed(2)}`
}

function fmtTokens(n: number): string {
  if (n >= 1000) return `${Math.round(n / 1000)}k`
  return `${n}`
}

function fmtMs(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${ms}ms`
}

function fmtScore(s: number): string {
  return s.toFixed(2)
}

// ─── State Icon ───────────────────────────────────────────────────────────────

function LoopStateIcon({ state }: { state: LoopRun['state'] }) {
  switch (state) {
    case 'running': return <Loader size={13} className="text-indigo-400 animate-spin shrink-0" />
    case 'done':    return <CheckCircle size={13} className="text-emerald-400 shrink-0" />
    case 'failed':  return <XCircle size={13} className="text-red-400 shrink-0" />
    case 'aborted': return <XCircle size={13} className="text-zinc-500 shrink-0" />
    default:        return <RefreshCw size={13} className="text-zinc-400 shrink-0" />
  }
}

function WorkerRunStateIcon({ state }: { state: WorkerRun['state'] }) {
  switch (state) {
    case 'running': return <Loader size={12} className="text-blue-400 animate-spin shrink-0" />
    case 'done':    return <CheckCircle size={12} className="text-emerald-400 shrink-0" />
    case 'failed':  return <XCircle size={12} className="text-red-400 shrink-0" />
    default:        return <Clock size={12} className="text-zinc-500 shrink-0" />
  }
}

// ─── Termination Reason Badge ─────────────────────────────────────────────────

function TerminationBadge({ reason }: { reason?: LoopTerminationReason }) {
  if (!reason) return null
  const cfg: Record<LoopTerminationReason, { label: string; className: string }> = {
    converged:      { label: 'Converged',       className: 'bg-emerald-900/30 text-emerald-300 border-emerald-700/50' },
    maxIterations:  { label: 'Max Iterations',  className: 'bg-amber-900/30 text-amber-300 border-amber-700/50' },
    budgetExhausted:{ label: 'Budget Exhausted',className: 'bg-amber-900/30 text-amber-300 border-amber-700/50' },
    failed:         { label: 'Failed',          className: 'bg-red-900/30 text-red-300 border-red-700/50' },
    escalated:      { label: 'Escalated',       className: 'bg-orange-900/30 text-orange-300 border-orange-700/50' },
    aborted:        { label: 'Aborted',         className: 'bg-zinc-800 text-zinc-500 border-zinc-700' },
  }
  const c = cfg[reason] ?? { label: reason, className: 'bg-zinc-800 text-zinc-400 border-zinc-700' }
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${c.className}`}>
      {c.label}
    </span>
  )
}

// ─── Loop List Item ───────────────────────────────────────────────────────────

function LoopListItem({
  loop,
  selected,
  onClick,
}: {
  loop: LoopRun
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-3 border-b border-zinc-800/60 transition-colors ${
        selected
          ? 'bg-indigo-900/20 border-l-2 border-l-indigo-500'
          : 'hover:bg-zinc-800/40 border-l-2 border-l-transparent'
      }`}
    >
      <div className="flex items-start gap-2">
        <div className="mt-0.5">
          <LoopStateIcon state={loop.state} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-zinc-200 truncate leading-tight">{loop.flowLabel}</p>
          <p className="text-[10px] text-zinc-500 truncate mt-0.5">{loop.objectTitle}</p>
          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
            <span className="text-[10px] bg-zinc-800 text-zinc-400 border border-zinc-700 rounded px-1.5 py-0.5">
              {loop.iterations.length} iter
            </span>
            <span className="text-[10px] bg-zinc-800 text-zinc-400 border border-zinc-700 rounded px-1.5 py-0.5">
              {fmtCost(loop.totalCostUsd)}
            </span>
            {loop.terminationReason && (
              <TerminationBadge reason={loop.terminationReason} />
            )}
          </div>
        </div>
      </div>
    </button>
  )
}

// ─── Budget Bar ───────────────────────────────────────────────────────────────

function BudgetBar({ pct }: { pct: number }) {
  const color =
    pct > 0.8 ? 'bg-red-500' :
    pct > 0.5 ? 'bg-amber-500' :
    'bg-emerald-500'
  return (
    <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${Math.min(pct * 100, 100)}%` }}
      />
    </div>
  )
}

// ─── Score Bar Chart ──────────────────────────────────────────────────────────

function ScoreChart({ iterations }: { iterations: IterationRun[] }) {
  return (
    <div className="space-y-2">
      {iterations.map(iter => {
        const widthPct = iter.score * 100
        const isPositive = iter.improvement >= 0
        return (
          <div key={iter.iteration} className="flex items-center gap-2">
            <span className="text-[10px] text-zinc-500 w-12 shrink-0 tabular-nums">
              Iter {iter.iteration}
            </span>
            <div className="flex-1 h-4 bg-zinc-800 rounded overflow-hidden relative">
              <div
                className={`h-full rounded transition-all duration-500 ${
                  iter.isBest ? 'bg-indigo-500' : 'bg-zinc-600'
                }`}
                style={{ width: `${widthPct}%` }}
              />
            </div>
            <span className="text-[10px] text-zinc-300 tabular-nums w-8 shrink-0">
              {fmtScore(iter.score)}
            </span>
            {iter.iteration > 1 && (
              <span className={`text-[10px] tabular-nums w-10 shrink-0 ${
                isPositive ? 'text-emerald-400' : 'text-red-400'
              }`}>
                {isPositive ? '+' : ''}{iter.improvement.toFixed(2)}
              </span>
            )}
            {iter.isBest && (
              <Star size={11} className="text-amber-400 shrink-0" />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Iteration Section ────────────────────────────────────────────────────────

function IterationSection({
  iter,
  allWorkerRuns,
}: {
  iter: IterationRun
  allWorkerRuns: WorkerRun[]
}) {
  const [expanded, setExpanded] = useState(iter.isBest)

  const childRuns = allWorkerRuns.filter(r => iter.workerRunIds.includes(r.id))

  return (
    <div className="border border-zinc-800 rounded-lg overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-2 px-3 py-2.5 bg-zinc-900/50 hover:bg-zinc-800/50 transition-colors text-left"
      >
        {expanded ? <ChevronDown size={12} className="text-zinc-500 shrink-0" /> : <ChevronRight size={12} className="text-zinc-500 shrink-0" />}
        <span className="text-xs font-semibold text-zinc-200">Iteration {iter.iteration}</span>
        {iter.isBest && <Star size={11} className="text-amber-400 shrink-0" />}
        <span className="text-xs text-zinc-400 ml-1">{fmtScore(iter.score)}</span>
        {iter.iteration > 1 && (
          <span className={`text-[10px] ${iter.improvement >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {iter.improvement >= 0 ? '+' : ''}{iter.improvement.toFixed(2)}
          </span>
        )}
        <div className="flex-1" />
        <span className="text-[10px] text-zinc-600 tabular-nums">{fmtCost(iter.costUsd)}</span>
        <span className="text-[10px] text-zinc-600 tabular-nums ml-2">{fmtTokens(iter.tokens)} tok</span>
        <span className="text-[10px] text-zinc-600 tabular-nums ml-2">{fmtMs(iter.durationMs)}</span>
      </button>

      {/* Child runs */}
      {expanded && (
        <div className="divide-y divide-zinc-800/60">
          {childRuns.length === 0 ? (
            <p className="text-[10px] text-zinc-600 italic px-3 py-2">No child runs recorded</p>
          ) : (
            childRuns.map(run => (
              <div key={run.id} className="flex items-center gap-2 px-4 py-2 bg-zinc-950/40">
                <WorkerRunStateIcon state={run.state} />
                <span className="text-[11px] text-zinc-300 flex-1 truncate">{run.workerLabel}</span>
                {run.durationMs != null && (
                  <span className="text-[10px] text-zinc-600 tabular-nums">{fmtMs(run.durationMs)}</span>
                )}
                {run.costUsd != null && (
                  <span className="text-[10px] text-zinc-600 tabular-nums ml-2">{fmtCost(run.costUsd)}</span>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ─── Convergence Summary ──────────────────────────────────────────────────────

function ConvergenceSummary({ loop }: { loop: LoopRun }) {
  if (!loop.terminationReason) return null

  let msg: string
  if (loop.terminationReason === 'converged') {
    const lastIter = loop.iterations[loop.iterations.length - 1]
    const improvement = lastIter?.improvement ?? 0
    msg = `Converged after ${loop.iterations.length} iteration${loop.iterations.length !== 1 ? 's' : ''} — improvement ${improvement.toFixed(2)} < threshold 0.05`
  } else if (loop.terminationReason === 'budgetExhausted') {
    msg = `Budget exhausted — best result from iteration ${loop.bestIterationIdx + 1} accepted`
  } else if (loop.terminationReason === 'maxIterations') {
    msg = `Maximum iterations reached — best result from iteration ${loop.bestIterationIdx + 1} accepted`
  } else {
    msg = `Loop terminated: ${loop.terminationReason}`
  }

  return (
    <div className="px-4 py-3 bg-zinc-900/40 border border-zinc-800 rounded-lg">
      <div className="flex items-start gap-2">
        <AlertCircle size={13} className="text-zinc-500 shrink-0 mt-0.5" />
        <p className="text-xs text-zinc-400">{msg}</p>
      </div>
    </div>
  )
}

// ─── Detail Panel ─────────────────────────────────────────────────────────────

function LoopDetailPanel({ loop }: { loop: LoopRun }) {
  const workerRuns = useAppStore(s => s.workerRuns)
  const bestIter = loop.iterations[loop.bestIterationIdx]

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-zinc-900/50">
      {/* Header */}
      <div className="px-5 py-4 border-b border-zinc-800 shrink-0">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <LoopStateIcon state={loop.state} />
              <h2 className="text-sm font-semibold text-zinc-100 truncate">{loop.flowLabel}</h2>
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${
                loop.state === 'running'
                  ? 'bg-indigo-900/40 text-indigo-300 border-indigo-700/50'
                  : loop.state === 'done'
                  ? 'bg-emerald-900/30 text-emerald-300 border-emerald-700/50'
                  : 'bg-zinc-800 text-zinc-500 border-zinc-700'
              }`}>
                {loop.state.charAt(0).toUpperCase() + loop.state.slice(1)}
              </span>
              {loop.terminationReason && <TerminationBadge reason={loop.terminationReason} />}
            </div>
            <p className="text-xs text-zinc-500 truncate">on: {loop.objectTitle}</p>
          </div>
          {bestIter && (
            <div className="text-right shrink-0">
              <p className="text-xs text-zinc-400">Best score</p>
              <p className="text-lg font-bold text-indigo-300 tabular-nums">{fmtScore(loop.bestScore)}</p>
              <p className="text-[10px] text-zinc-600">(iter {loop.bestIterationIdx + 1})</p>
            </div>
          )}
        </div>

        {/* Budget */}
        <div className="space-y-1.5">
          <BudgetBar pct={loop.budgetConsumedPct} />
          <div className="flex items-center justify-between">
            <p className="text-[10px] text-zinc-500">
              Budget: {fmtCost(loop.totalCostUsd)} / {fmtCost(loop.maxCostUsd)}
              {' · '}
              {fmtTokens(loop.totalTokens)} / {fmtTokens(loop.maxTokens)} tokens
            </p>
            <p className="text-[10px] text-zinc-600 tabular-nums">
              {(loop.budgetConsumedPct * 100).toFixed(1)}% consumed
            </p>
          </div>
        </div>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* Score chart */}
        {loop.iterations.length > 0 && (
          <section>
            <h3 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-3">Score Progress</h3>
            <ScoreChart iterations={loop.iterations} />
          </section>
        )}

        {/* Iteration tree */}
        {loop.iterations.length > 0 && (
          <section>
            <h3 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-3">Iterations</h3>
            <div className="space-y-2">
              {loop.iterations.map(iter => (
                <IterationSection
                  key={iter.iteration}
                  iter={iter}
                  allWorkerRuns={workerRuns}
                />
              ))}
            </div>
          </section>
        )}

        {/* Convergence summary */}
        {loop.terminationReason && (
          <section>
            <h3 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-3">Outcome</h3>
            <ConvergenceSummary loop={loop} />
          </section>
        )}
      </div>
    </div>
  )
}

// ─── Empty Detail State ───────────────────────────────────────────────────────

function EmptyDetail({ onStart }: { onStart: () => void }) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="text-center max-w-sm">
        <div className="w-14 h-14 rounded-2xl bg-zinc-800/60 border border-zinc-700/50 flex items-center justify-center mx-auto mb-4">
          <RefreshCw size={22} className="text-zinc-600" />
        </div>
        <p className="text-sm font-medium text-zinc-300 mb-2">Agentic Loops</p>
        <p className="text-xs text-zinc-500 leading-relaxed mb-4">
          Agentic loops iteratively improve artifacts through propose &rarr; validate &rarr; evaluate &rarr; feedback cycles.
          Each iteration refines the result using structured feedback from the previous attempt.
          The loop terminates when improvement falls below the convergence threshold or the token budget is exhausted.
        </p>
        <button
          onClick={onStart}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors mx-auto"
        >
          <RefreshCw size={12} />
          Start Loop
        </button>
      </div>
    </div>
  )
}

// ─── Main AgenticLoopView ─────────────────────────────────────────────────────

export function AgenticLoopView() {
  const loopRuns = useAppStore(s => s.loopRuns)
  const activeLoopId = useAppStore(s => s.activeLoopId)
  const setActiveLoopId = useAppStore(s => s.setActiveLoopId)
  const startAgenticLoop = useAppStore(s => s.startAgenticLoop)
  const selectedObjectId = useAppStore(s => s.selectedObjectId)

  // Sort loopRuns by startedAt desc
  const sortedLoops = [...loopRuns].sort(
    (a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()
  )

  const selectedLoop = activeLoopId
    ? loopRuns.find(lr => lr.id === activeLoopId) ?? null
    : null

  function handleStartLoop() {
    const objectId = selectedObjectId ?? 'pr-001'
    const id = startAgenticLoop('agentic_code_optimization_loop', objectId)
    setActiveLoopId(id)
  }

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left panel — Loop list */}
      <div className="w-[360px] shrink-0 border-r border-zinc-800 flex flex-col overflow-hidden bg-zinc-950">
        {/* Header */}
        <div className="px-4 py-3 border-b border-zinc-800 shrink-0">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-200">Agentic Loops</h2>
            <button
              onClick={handleStartLoop}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
            >
              <RefreshCw size={11} />
              Start Loop
            </button>
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {sortedLoops.length === 0 ? (
            <div className="p-4 text-center">
              <p className="text-xs text-zinc-600 italic">No loops yet — start one above</p>
            </div>
          ) : (
            sortedLoops.map(loop => (
              <LoopListItem
                key={loop.id}
                loop={loop}
                selected={activeLoopId === loop.id}
                onClick={() => setActiveLoopId(loop.id)}
              />
            ))
          )}
        </div>
      </div>

      {/* Right panel — detail */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {selectedLoop ? (
          <LoopDetailPanel loop={selectedLoop} />
        ) : (
          <EmptyDetail onStart={handleStartLoop} />
        )}
      </div>
    </div>
  )
}
