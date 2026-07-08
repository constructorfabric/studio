import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle, XCircle, Loader, AlertCircle, X, ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import { useAppStore, selectActiveWorkerRuns } from '../../store/app-store'
import type { WorkerRun } from '../../types/domain'

export function WorkerRunSimulator() {
  const activeRuns = useAppStore(selectActiveWorkerRuns)
  const recentDoneRuns = useAppStore(s => s.workerRuns.filter(r => r.state === 'done' || r.state === 'failed').slice(0, 3))
  const dismissRunToast = useAppStore(s => s.dismissRunToast)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const allVisible = [...activeRuns, ...recentDoneRuns].slice(0, 6)

  if (allVisible.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-40 flex flex-col gap-2 max-w-sm w-full">
      <AnimatePresence>
        {allVisible.map(run => (
          <RunToast
            key={run.id}
            run={run}
            expanded={expanded.has(run.id)}
            onToggle={() => toggleExpand(run.id)}
            onDismiss={() => dismissRunToast(run.id)}
          />
        ))}
      </AnimatePresence>
    </div>
  )
}

function RunToast({
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
    pending: {
      icon: <Loader size={14} className="text-zinc-400 animate-spin" />,
      border: 'border-zinc-700',
      label: 'Pending',
      labelColor: 'text-zinc-400',
    },
    running: {
      icon: <Loader size={14} className="text-blue-400 animate-spin" />,
      border: 'border-blue-700/50',
      label: 'Running',
      labelColor: 'text-blue-400',
    },
    awaiting_input: {
      icon: <AlertCircle size={14} className="text-amber-400" />,
      border: 'border-amber-600/60',
      label: 'Awaiting Input',
      labelColor: 'text-amber-400',
    },
    done: {
      icon: <CheckCircle size={14} className="text-emerald-400" />,
      border: 'border-emerald-700/50',
      label: 'Done',
      labelColor: 'text-emerald-400',
    },
    failed: {
      icon: <XCircle size={14} className="text-red-400" />,
      border: 'border-red-700/50',
      label: 'Failed',
      labelColor: 'text-red-400',
    },
    paused: {
      icon: <AlertCircle size={14} className="text-amber-400" />,
      border: 'border-amber-600/60',
      label: 'Paused',
      labelColor: 'text-amber-400',
    },
    aborted: {
      icon: <XCircle size={14} className="text-zinc-400" />,
      border: 'border-zinc-700',
      label: 'Aborted',
      labelColor: 'text-zinc-400',
    },
    escalated: {
      icon: <AlertCircle size={14} className="text-orange-400" />,
      border: 'border-orange-600/60',
      label: 'Escalated',
      labelColor: 'text-orange-400',
    },
  }[run.state] ?? {
    icon: <Loader size={14} className="animate-spin" />,
    border: 'border-zinc-700',
    label: run.state,
    labelColor: 'text-zinc-400',
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, scale: 0.97 }}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      className={`bg-zinc-900 border ${stateConfig.border} rounded-xl shadow-2xl overflow-hidden backdrop-blur`}
    >
      {/* Header row */}
      <div className="flex items-center gap-2 px-3 py-2.5">
        {stateConfig.icon}
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-zinc-200 truncate">{run.workerLabel}</p>
          <p className="text-[10px] text-zinc-500 truncate">{run.objectTitle}</p>
        </div>
        <span className={`text-[10px] font-medium shrink-0 ${stateConfig.labelColor}`}>{stateConfig.label}</span>
        <div className="flex items-center gap-1">
          <button onClick={onToggle} className="p-1 rounded text-zinc-500 hover:text-zinc-300 transition-colors">
            {expanded ? <ChevronDown size={12} /> : <ChevronUp size={12} />}
          </button>
          {(run.state === 'done' || run.state === 'failed') && (
            <button onClick={onDismiss} className="p-1 rounded text-zinc-500 hover:text-zinc-300 transition-colors">
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Progress bar */}
      {(run.state === 'running' || run.state === 'pending' || run.state === 'awaiting_input') && (
        <div className="px-3 pb-1">
          <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
            {run.state === 'running' ? (
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${run.progress}%`,
                  background: 'linear-gradient(90deg, #6366f1, #818cf8)',
                }}
              />
            ) : run.state === 'awaiting_input' ? (
              <div className="h-full w-full bg-amber-500/40 relative overflow-hidden">
                <div className="absolute inset-0 bg-amber-500 progress-indeterminate" style={{ width: '30%' }} />
              </div>
            ) : (
              <div className="h-full bg-zinc-700 w-8 progress-indeterminate rounded-full" />
            )}
          </div>
          {run.state === 'running' && (
            <p className="text-[10px] text-zinc-500 mt-0.5">{Math.round(run.progress)}% complete</p>
          )}
        </div>
      )}

      {/* Expanded details */}
      {expanded && run.output && (
        <div className="px-3 pb-3 pt-1">
          <p className="text-[11px] text-zinc-400 bg-zinc-800/60 rounded-lg p-2 leading-relaxed">{run.output}</p>
        </div>
      )}
    </motion.div>
  )
}
