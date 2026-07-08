import { AlertTriangle, Info, CheckCircle, Loader, XCircle, Play, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/app-store'
import { MOCK_OBJECTS } from '../../data/mock-data'
import type { Recommendation, RecommendationSeverity } from '../../types/domain'

function SeverityIcon({ severity }: { severity: RecommendationSeverity }) {
  switch (severity) {
    case 'critical': return <AlertTriangle size={15} className="text-red-400" />
    case 'warning':  return <AlertTriangle size={15} className="text-amber-400" />
    case 'info':     return <Info size={15} className="text-blue-400" />
  }
}

function getSeverityStyle(severity: RecommendationSeverity): string {
  switch (severity) {
    case 'critical': return 'border-red-800/50 bg-red-950/20'
    case 'warning':  return 'border-amber-800/40 bg-amber-950/10'
    case 'info':     return 'border-blue-800/30 bg-blue-950/10'
  }
}

function getSeverityBadge(severity: RecommendationSeverity): string {
  switch (severity) {
    case 'critical': return 'bg-red-900/60 text-red-300 border-red-700/60'
    case 'warning':  return 'bg-amber-900/50 text-amber-300 border-amber-700/50'
    case 'info':     return 'bg-blue-900/40 text-blue-300 border-blue-700/40'
  }
}

function StateIcon({ state }: { state: string }) {
  switch (state) {
    case 'executing': return <Loader size={13} className="text-indigo-400 animate-spin" />
    case 'done':      return <CheckCircle size={13} className="text-emerald-400" />
    case 'dismissed': return <XCircle size={13} className="text-zinc-600" />
    default:          return null
  }
}

function RecCard({ rec }: { rec: Recommendation }) {
  const acceptRecommendation = useAppStore(s => s.acceptRecommendation)
  const dismissRecommendation = useAppStore(s => s.dismissRecommendation)
  const selectObject = useAppStore(s => s.selectObject)
  const setActiveView = useAppStore(s => s.setActiveView)

  const relatedObjects = rec.relatedObjectIds
    .map(id => MOCK_OBJECTS.find(o => o.id === id))
    .filter(Boolean)

  const isPending = rec.state === 'pending'
  const isDone = rec.state === 'done'
  const isDismissed = rec.state === 'dismissed'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: isDismissed ? 0.4 : 1, y: 0 }}
      exit={{ opacity: 0, height: 0, marginBottom: 0 }}
      className={`
        border rounded-xl overflow-hidden transition-all
        ${getSeverityStyle(rec.severity)}
        ${rec.severity === 'critical' && isPending ? 'pulse-critical' : ''}
      `}
    >
      {/* Header */}
      <div className="p-4">
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex items-start gap-2.5 min-w-0 flex-1">
            <div className="mt-0.5 shrink-0">
              <SeverityIcon severity={rec.severity} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${getSeverityBadge(rec.severity)}`}>
                  {rec.severity}
                </span>
                {rec.state !== 'pending' && (
                  <div className="flex items-center gap-1">
                    <StateIcon state={rec.state} />
                    <span className="text-[10px] text-zinc-500 capitalize">{rec.state}</span>
                  </div>
                )}
              </div>
              <p className={`text-sm font-semibold leading-tight ${isDismissed ? 'text-zinc-500' : 'text-zinc-100'}`}>
                {rec.title}
              </p>
            </div>
          </div>
        </div>

        <p className={`text-xs leading-relaxed mb-3 ${isDismissed ? 'text-zinc-600' : 'text-zinc-400'}`}>
          {rec.description}
        </p>

        {/* Related objects */}
        {relatedObjects.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {relatedObjects.map(obj => obj && (
              <button
                key={obj.id}
                onClick={() => {
                  selectObject(obj.id)
                  setActiveView('graph')
                }}
                className="text-[11px] px-2 py-0.5 rounded-md bg-zinc-800 border border-zinc-700 text-zinc-300 hover:text-zinc-100 hover:border-zinc-500 transition-colors"
              >
                {obj.title}
              </button>
            ))}
          </div>
        )}

        {/* Suggested worker */}
        <div className="flex items-center gap-1.5 text-[11px] text-zinc-500 mb-3">
          <span>Suggested fix:</span>
          <span className="text-zinc-300 font-medium">{rec.suggestedWorkerLabel}</span>
        </div>

        {/* Actions */}
        {!isDone && !isDismissed && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => acceptRecommendation(rec.id)}
              disabled={rec.state === 'executing'}
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all
                ${rec.state === 'executing'
                  ? 'bg-indigo-900/40 text-indigo-400 cursor-not-allowed'
                  : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm'
                }
              `}
            >
              {rec.state === 'executing' ? (
                <><Loader size={12} className="animate-spin" /> Executing…</>
              ) : (
                <><Play size={12} /> Accept & Run</>
              )}
            </button>
            <button
              onClick={() => dismissRecommendation(rec.id)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
            >
              <X size={12} />
              Dismiss
            </button>
          </div>
        )}
        {isDone && (
          <div className="flex items-center gap-1.5 text-xs text-emerald-400">
            <CheckCircle size={13} />
            Completed successfully
          </div>
        )}
        {isDismissed && (
          <div className="flex items-center gap-1.5 text-xs text-zinc-600">
            <XCircle size={13} />
            Dismissed
          </div>
        )}
      </div>
    </motion.div>
  )
}

export function RecommendationsPanel() {
  const recommendations = useAppStore(s => s.recommendations)

  const critical = recommendations.filter(r => r.severity === 'critical' && r.state !== 'dismissed')
  const warning  = recommendations.filter(r => r.severity === 'warning'  && r.state !== 'dismissed')
  const info     = recommendations.filter(r => r.severity === 'info'     && r.state !== 'dismissed')
  const dismissed = recommendations.filter(r => r.state === 'dismissed')
  const done      = recommendations.filter(r => r.state === 'done')

  const activeCount = critical.length + warning.length + info.length

  return (
    <div className="flex-1 overflow-y-auto p-6">
      {/* Summary header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">Recommendations</h2>
          <p className="text-sm text-zinc-400 mt-0.5">AI-detected gaps and suggested remediation</p>
        </div>
        <div className="flex items-center gap-2">
          {critical.length > 0 && (
            <span className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-red-900/40 border border-red-700/60 text-xs font-bold text-red-300">
              <AlertTriangle size={12} />
              {critical.length} critical
            </span>
          )}
          {warning.length > 0 && (
            <span className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-900/30 border border-amber-700/50 text-xs font-bold text-amber-300">
              <AlertTriangle size={12} />
              {warning.length} warning
            </span>
          )}
          {info.length > 0 && (
            <span className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-900/30 border border-blue-700/40 text-xs font-bold text-blue-300">
              <Info size={12} />
              {info.length} info
            </span>
          )}
        </div>
      </div>

      {activeCount === 0 && done.length === 0 && dismissed.length === 0 && (
        <div className="text-center py-20">
          <div className="w-14 h-14 rounded-2xl bg-emerald-900/30 border border-emerald-800/40 flex items-center justify-center mx-auto mb-4">
            <CheckCircle size={24} className="text-emerald-400" />
          </div>
          <p className="text-base font-medium text-zinc-300">All Clear</p>
          <p className="text-sm text-zinc-500 mt-1">No recommendations at this time</p>
        </div>
      )}

      <div className="space-y-6">
        {/* Critical */}
        {critical.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <AlertTriangle size={12} />
              Critical
            </h3>
            <div className="space-y-3">
              <AnimatePresence>
                {critical.map(rec => <RecCard key={rec.id} rec={rec} />)}
              </AnimatePresence>
            </div>
          </section>
        )}

        {/* Warnings */}
        {warning.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <AlertTriangle size={12} />
              Warning
            </h3>
            <div className="space-y-3">
              <AnimatePresence>
                {warning.map(rec => <RecCard key={rec.id} rec={rec} />)}
              </AnimatePresence>
            </div>
          </section>
        )}

        {/* Info */}
        {info.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-blue-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Info size={12} />
              Info
            </h3>
            <div className="space-y-3">
              <AnimatePresence>
                {info.map(rec => <RecCard key={rec.id} rec={rec} />)}
              </AnimatePresence>
            </div>
          </section>
        )}

        {/* Done */}
        {done.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3 flex items-center gap-2">
              <CheckCircle size={12} />
              Resolved ({done.length})
            </h3>
            <div className="space-y-3">
              {done.map(rec => <RecCard key={rec.id} rec={rec} />)}
            </div>
          </section>
        )}

        {/* Dismissed */}
        {dismissed.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-zinc-600 uppercase tracking-wider mb-3 flex items-center gap-2">
              <XCircle size={12} />
              Dismissed ({dismissed.length})
            </h3>
            <div className="space-y-3">
              {dismissed.map(rec => <RecCard key={rec.id} rec={rec} />)}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
