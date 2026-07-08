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
  Plus,
  X,
  Zap,
} from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import { FLOW_DEFS } from '../../data/mock-data'
import type { LoopRun, IterationRun, WorkerRun, LoopTerminationReason } from '../../types/domain'

// Loop-capable flows = Flows from the catalog that have loopPolicy set
const LOOP_FLOWS = FLOW_DEFS.filter(f => f.loopPolicy != null)

// ─── New Loop Picker Modal ────────────────────────────────────────────────────

const TYPE_LABEL: Record<string, string> = {
  prd: 'PRD', design: 'DESIGN', adr: 'ADR', decomposition: 'DECOMP',
  feature_spec: 'FSPEC', task: 'TASK', pull_request: 'PR', build: 'BUILD',
  incident: 'INC', component: 'COMP',
}

const STATE_DOT: Record<string, string> = {
  approved: 'bg-emerald-500', done: 'bg-emerald-500',
  in_progress: 'bg-amber-500', review: 'bg-amber-500',
  failed: 'bg-red-500', open: 'bg-red-500',
  draft: 'bg-zinc-500', planned: 'bg-zinc-500',
}

function NewLoopPicker({ onStart, onClose }: {
  onStart: (flowId: string, objectId: string) => void
  onClose: () => void
}) {
  const objects = useAppStore(s => s.objects)
  const [selectedFlowId, setSelectedFlowId] = useState(LOOP_FLOWS[0]?.id ?? '')
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null)

  const loopFlow = LOOP_FLOWS.find(f => f.id === selectedFlowId) ?? LOOP_FLOWS[0]
  const loopPolicy = loopFlow?.loopPolicy
  const applicableTypeIds = loopFlow?.entryConstraints?.map(c => c.typeId) ?? []
  const compatibleObjects = objects.filter(o => applicableTypeIds.includes(o.typeId))

  const canStart = selectedObjectId !== null && compatibleObjects.some(o => o.id === selectedObjectId)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-[720px] max-h-[80vh] bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-indigo-400" />
            <h2 className="text-sm font-semibold text-zinc-100">New Agentic Loop</h2>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Loop type selector */}
          <div className="w-56 shrink-0 border-r border-zinc-800 overflow-y-auto p-3">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2 px-1">Flow (loop-capable)</p>
            {LOOP_FLOWS.map(f => (
              <button
                key={f.id}
                onClick={() => { setSelectedFlowId(f.id); setSelectedObjectId(null) }}
                className={`w-full text-left px-3 py-2.5 rounded-lg mb-1 transition-colors text-xs ${
                  selectedFlowId === f.id
                    ? 'bg-indigo-900/40 border border-indigo-700/50 text-indigo-200'
                    : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 border border-transparent'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Config panel */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            {/* Flow description */}
            <div>
              <h3 className="text-sm font-semibold text-zinc-100 mb-1">{loopFlow?.label}</h3>
              <p className="text-xs text-zinc-400 leading-relaxed">{loopFlow?.description}</p>
            </div>

            {/* Steps preview */}
            {loopFlow && (
              <div>
                <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2">Steps per iteration</p>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {loopFlow.steps.map((step, i) => (
                    <span key={i} className="flex items-center gap-1">
                      <span className="text-[10px] bg-zinc-800 border border-zinc-700 text-zinc-300 px-2 py-0.5 rounded">{step.workerLabel}</span>
                      {i < loopFlow.steps.length - 1 && <span className="text-zinc-600 text-[10px]">→</span>}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* LoopPolicy summary */}
            {loopPolicy && (
              <div className="flex items-center gap-4 p-3 bg-zinc-800/40 border border-zinc-700/50 rounded-lg">
                <div className="text-center">
                  <p className="text-xs font-bold text-zinc-200">{loopPolicy.maxIterations}</p>
                  <p className="text-[10px] text-zinc-500">max iter</p>
                </div>
                <div className="text-center">
                  <p className="text-xs font-bold text-zinc-200">${loopPolicy.budgetUsd.toFixed(2)}</p>
                  <p className="text-[10px] text-zinc-500">budget</p>
                </div>
                <div className="text-center">
                  <p className="text-xs font-bold text-zinc-200">{(loopPolicy.threshold * 100).toFixed(0)}%</p>
                  <p className="text-[10px] text-zinc-500">threshold</p>
                </div>
                <div className="text-center">
                  <p className="text-xs font-bold text-indigo-300">{loopPolicy.metric}</p>
                  <p className="text-[10px] text-zinc-500">metric</p>
                </div>
                <div className="text-center">
                  <p className="text-xs font-bold text-amber-300">{loopPolicy.onExhaustion}</p>
                  <p className="text-[10px] text-zinc-500">on budget</p>
                </div>
              </div>
            )}

            {/* Object selector */}
            <div>
              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2">
                Select Object ({applicableTypeIds.map(t => TYPE_LABEL[t] ?? t).join(', ')})
              </p>
              {compatibleObjects.length === 0 ? (
                <p className="text-xs text-zinc-600 italic">No compatible objects in workspace</p>
              ) : (
                <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                  {compatibleObjects.map(obj => (
                    <button
                      key={obj.id}
                      onClick={() => setSelectedObjectId(obj.id)}
                      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left transition-colors text-xs ${
                        selectedObjectId === obj.id
                          ? 'bg-indigo-900/40 border border-indigo-700/50 text-indigo-200'
                          : 'bg-zinc-800/50 border border-zinc-700/30 text-zinc-300 hover:bg-zinc-800 hover:border-zinc-600'
                      }`}
                    >
                      <div className={`w-2 h-2 rounded-full shrink-0 ${STATE_DOT[obj.state] ?? 'bg-blue-500'}`} />
                      <span className="font-medium truncate flex-1">{obj.title}</span>
                      <span className="text-[9px] font-bold uppercase text-zinc-500 shrink-0">{TYPE_LABEL[obj.typeId] ?? obj.typeId}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-zinc-800">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 transition-colors">
            Cancel
          </button>
          <button
            onClick={() => selectedObjectId && onStart(selectedFlowId, selectedObjectId)}
            disabled={!canStart}
            className={`flex items-center gap-1.5 px-5 py-2 rounded-lg text-xs font-semibold transition-colors ${
              canStart
                ? 'bg-indigo-600 hover:bg-indigo-500 text-white'
                : 'bg-zinc-800 text-zinc-600 cursor-not-allowed'
            }`}
          >
            <RefreshCw size={11} />
            Start Loop
          </button>
        </div>
      </div>
    </div>
  )
}

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

  const [showPicker, setShowPicker] = useState(false)

  // Sort loopRuns by startedAt desc; auto-select first on mount
  const sortedLoops = [...loopRuns].sort(
    (a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()
  )

  const resolvedActiveId = activeLoopId ?? sortedLoops[0]?.id ?? null
  const selectedLoop = resolvedActiveId ? loopRuns.find(lr => lr.id === resolvedActiveId) ?? null : null

  function handleStart(loopTypeId: string, objectId: string) {
    const id = startAgenticLoop(loopTypeId, objectId)
    setActiveLoopId(id)
    setShowPicker(false)
  }

  return (
    <>
      {showPicker && (
        <NewLoopPicker onStart={handleStart} onClose={() => setShowPicker(false)} />
      )}

      <div className="flex-1 flex overflow-hidden">
        {/* Left panel — Loop list */}
        <div className="w-72 shrink-0 border-r border-zinc-800 flex flex-col overflow-hidden bg-zinc-950">
          {/* Header */}
          <div className="px-4 py-3 border-b border-zinc-800 shrink-0 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-zinc-200">Loops</h2>
              <p className="text-[10px] text-zinc-600 mt-0.5">{sortedLoops.length} runs</p>
            </div>
            <button
              onClick={() => setShowPicker(true)}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
            >
              <Plus size={11} />
              New
            </button>
          </div>

          {/* List */}
          <div className="flex-1 overflow-y-auto">
            {sortedLoops.length === 0 ? (
              <div className="p-6 text-center">
                <RefreshCw size={20} className="text-zinc-700 mx-auto mb-2" />
                <p className="text-xs text-zinc-600">No loops yet — click New to start one</p>
              </div>
            ) : (
              sortedLoops.map(loop => (
                <LoopListItem
                  key={loop.id}
                  loop={loop}
                  selected={resolvedActiveId === loop.id}
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
            <EmptyDetail onStart={() => setShowPicker(true)} />
          )}
        </div>
      </div>
    </>
  )
}
