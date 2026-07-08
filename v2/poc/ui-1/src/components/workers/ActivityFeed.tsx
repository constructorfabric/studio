import { CheckCircle, XCircle, Loader, AlertCircle, Clock, ChevronDown, ChevronUp, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useAppStore } from '../../store/app-store'
import type { WorkerRun } from '../../types/domain'

export function ActivityFeed() {
  const workerRuns = useAppStore(s => s.workerRuns)
  const dismissRunToast = useAppStore(s => s.dismissRunToast)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  if (workerRuns.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center mx-auto mb-3">
            <Clock size={20} className="text-zinc-600" />
          </div>
          <p className="text-sm text-zinc-400 font-medium">No Activity Yet</p>
          <p className="text-xs text-zinc-600 mt-1">Worker runs will appear here</p>
        </div>
      </div>
    )
  }

  const grouped = {
    active: workerRuns.filter(r => r.state === 'running' || r.state === 'pending' || r.state === 'awaiting_input'),
    done: workerRuns.filter(r => r.state === 'done'),
    failed: workerRuns.filter(r => r.state === 'failed'),
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-6">
      {grouped.active.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
            Active ({grouped.active.length})
          </h3>
          <div className="space-y-2">
            {grouped.active.map(run => (
              <RunCard
                key={run.id}
                run={run}
                expanded={expanded.has(run.id)}
                onToggle={() => toggleExpand(run.id)}
                onDismiss={() => dismissRunToast(run.id)}
              />
            ))}
          </div>
        </section>
      )}

      {grouped.failed.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold text-red-400/80 uppercase tracking-wider mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            Failed ({grouped.failed.length})
          </h3>
          <div className="space-y-2">
            {grouped.failed.map(run => (
              <RunCard
                key={run.id}
                run={run}
                expanded={expanded.has(run.id)}
                onToggle={() => toggleExpand(run.id)}
                onDismiss={() => dismissRunToast(run.id)}
              />
            ))}
          </div>
        </section>
      )}

      {grouped.done.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            Completed ({grouped.done.length})
          </h3>
          <div className="space-y-2">
            {grouped.done.map(run => (
              <RunCard
                key={run.id}
                run={run}
                expanded={expanded.has(run.id)}
                onToggle={() => toggleExpand(run.id)}
                onDismiss={() => dismissRunToast(run.id)}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function RunCard({
  run,
  expanded,
  onToggle,
  onDismiss,
}: {
  run: WorkerRun
  expanded: boolean
  onToggle: () => void
  onDismiss: () => void
}) {
  const stateConfig = {
    pending:        { icon: <Clock size={14} className="text-zinc-400" />,                         border: 'border-zinc-700',       headerBg: 'bg-zinc-900' },
    running:        { icon: <Loader size={14} className="text-blue-400 animate-spin" />,           border: 'border-blue-800/40',    headerBg: 'bg-zinc-900' },
    awaiting_input: { icon: <AlertCircle size={14} className="text-amber-400" />,                  border: 'border-amber-700/50',   headerBg: 'bg-amber-950/20' },
    done:           { icon: <CheckCircle size={14} className="text-emerald-400" />,                border: 'border-emerald-800/30', headerBg: 'bg-zinc-900' },
    failed:         { icon: <XCircle size={14} className="text-red-400" />,                        border: 'border-red-800/40',     headerBg: 'bg-red-950/20' },
    paused:         { icon: <AlertCircle size={14} className="text-amber-400" />,                  border: 'border-amber-700/50',   headerBg: 'bg-zinc-900' },
    aborted:        { icon: <XCircle size={14} className="text-zinc-400" />,                       border: 'border-zinc-700',       headerBg: 'bg-zinc-900' },
    escalated:      { icon: <AlertCircle size={14} className="text-orange-400" />,                 border: 'border-orange-700/50',  headerBg: 'bg-orange-950/20' },
  }[run.state] ?? { icon: <Clock size={14} className="text-zinc-400" />, border: 'border-zinc-700', headerBg: 'bg-zinc-900' }

  const duration = run.completedAt
    ? Math.round((new Date(run.completedAt).getTime() - new Date(run.startedAt).getTime()) / 1000)
    : null

  return (
    <div className={`border ${stateConfig.border} rounded-xl overflow-hidden fade-in`}>
      <div className={`${stateConfig.headerBg} px-3 py-2.5 flex items-center gap-2`}>
        {stateConfig.icon}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-zinc-200 truncate">{run.workerLabel}</p>
            <div className="flex items-center gap-1 shrink-0 ml-2">
              {duration !== null && (
                <span className="text-[10px] text-zinc-500">{duration}s</span>
              )}
              <button onClick={onToggle} className="p-1 text-zinc-500 hover:text-zinc-300 transition-colors">
                {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              </button>
              <button onClick={onDismiss} className="p-1 text-zinc-600 hover:text-red-400 transition-colors">
                <Trash2 size={12} />
              </button>
            </div>
          </div>
          <p className="text-[11px] text-zinc-500 truncate">on: {run.objectTitle}</p>
        </div>
      </div>

      {/* Progress bar for active runs */}
      {(run.state === 'running' || run.state === 'pending') && (
        <div className="px-3 py-1.5 bg-zinc-950/50">
          <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${run.progress}%`,
                background: 'linear-gradient(90deg, #4f46e5, #6366f1, #818cf8)',
              }}
            />
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-[10px] text-zinc-600">{Math.round(run.progress)}% complete</span>
            <span className="text-[10px] text-zinc-600">
              {new Date(run.startedAt).toLocaleTimeString()}
            </span>
          </div>
        </div>
      )}

      {/* Awaiting input state */}
      {run.state === 'awaiting_input' && (
        <div className="px-3 py-2 bg-amber-950/20 border-t border-amber-800/30">
          <p className="text-[11px] text-amber-300">Waiting for your input to continue…</p>
        </div>
      )}

      {/* Expanded details */}
      {expanded && (
        <div className="px-3 pb-3 pt-1 space-y-2 border-t border-zinc-800">
          <div className="flex gap-4 text-[11px] text-zinc-500">
            <span>Started: {new Date(run.startedAt).toLocaleTimeString()}</span>
            {run.completedAt && <span>Ended: {new Date(run.completedAt).toLocaleTimeString()}</span>}
          </div>
          {run.interactionResponse && (
            <div>
              <p className="text-[10px] font-semibold text-zinc-400 mb-1">User Response</p>
              <p className="text-[11px] text-zinc-300 bg-zinc-800/50 rounded p-2">{run.interactionResponse}</p>
            </div>
          )}
          {run.output && (
            <div>
              <p className="text-[10px] font-semibold text-zinc-400 mb-1">Output</p>
              <p className="text-[11px] text-zinc-300 bg-zinc-800/50 rounded p-2 leading-relaxed">{run.output}</p>
            </div>
          )}
          {run.error && (
            <div>
              <p className="text-[10px] font-semibold text-red-400 mb-1">Error</p>
              <p className="text-[11px] text-red-300 bg-red-950/30 rounded p-2">{run.error}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
