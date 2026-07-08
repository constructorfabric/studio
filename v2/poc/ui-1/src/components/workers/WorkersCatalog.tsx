import { useState } from 'react'
import { Search, Lock, Play, Cpu } from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import { WORKER_DEFS } from '../../data/mock-data'
import type { WorkerCategory, WorkerDef } from '../../types/domain'

// ─── Category config ──────────────────────────────────────────────────────────

const CATEGORIES: { id: WorkerCategory | 'all'; label: string }[] = [
  { id: 'all',          label: 'All' },
  { id: 'quality',      label: 'Quality' },
  { id: 'security',     label: 'Security' },
  { id: 'ops',          label: 'Ops' },
  { id: 'ai-cost',      label: 'AI Cost' },
  { id: 'traceability', label: 'Traceability' },
  { id: 'retrieval',    label: 'Retrieval' },
  { id: 'platform',     label: 'Platform' },
]

const CATEGORY_BADGE: Record<WorkerCategory, string> = {
  quality:      'text-blue-300 bg-blue-900/30 border-blue-700/40',
  security:     'text-red-300 bg-red-900/30 border-red-700/40',
  ops:          'text-orange-300 bg-orange-900/30 border-orange-700/40',
  'ai-cost':    'text-purple-300 bg-purple-900/30 border-purple-700/40',
  traceability: 'text-cyan-300 bg-cyan-900/30 border-cyan-700/40',
  retrieval:    'text-teal-300 bg-teal-900/30 border-teal-700/40',
  platform:     'text-zinc-300 bg-zinc-800 border-zinc-700',
}

const PROFILE_BADGE: Record<string, string> = {
  on_demand: 'text-indigo-300 bg-indigo-900/20 border-indigo-700/30',
  analyzer:  'text-violet-300 bg-violet-900/20 border-violet-700/30',
  validator: 'text-emerald-300 bg-emerald-900/20 border-emerald-700/30',
  realtime:  'text-amber-300 bg-amber-900/20 border-amber-700/30',
  scheduled: 'text-slate-300 bg-slate-900/20 border-slate-700/30',
}

const TYPE_LABEL: Record<string, string> = {
  prd: 'PRD', design: 'DESIGN', adr: 'ADR', decomposition: 'DECOMP',
  feature_spec: 'FSPEC', task: 'TASK', pull_request: 'PR', build: 'BUILD',
  incident: 'INC', component: 'COMP', person: 'PERSON', team: 'TEAM',
  release: 'RELEASE', deployment: 'DEPLOY', environment: 'ENV',
  worker_run: 'RUN', flow_run: 'FLOW', recommendation: 'REC',
  approval: 'APPROVAL', validation_session: 'VSESS', evidence: 'EVID',
  worker_interaction: 'WINT',
}

// ─── Worker Card ──────────────────────────────────────────────────────────────

function WorkerCard({ worker }: { worker: WorkerDef }) {
  const [message, setMessage] = useState<string | null>(null)
  const selectedObjectId = useAppStore(s => s.selectedObjectId)
  const objects = useAppStore(s => s.objects)
  const runWorker = useAppStore(s => s.runWorker)
  const navigateToMonitor = useAppStore(s => s.navigateToMonitor)

  const selectedObject = selectedObjectId ? objects.find(o => o.id === selectedObjectId) : null
  const canRun = selectedObject && worker.applicableTypes.includes(selectedObject.typeId)

  const handleRun = () => {
    if (!selectedObjectId || !canRun) {
      setMessage('Select a compatible object first')
      setTimeout(() => setMessage(null), 2500)
      return
    }
    const runId = runWorker(worker.id, selectedObjectId)
    navigateToMonitor(runId)
  }

  const categoryClass = CATEGORY_BADGE[worker.category] ?? 'text-zinc-300 bg-zinc-800 border-zinc-700'
  const profileClass = PROFILE_BADGE[worker.profile] ?? 'text-zinc-300 bg-zinc-800 border-zinc-700'

  return (
    <div className="flex flex-col gap-3 p-4 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition-colors">
      {/* Top row: category + profile badges */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded border ${categoryClass}`}>
          {worker.category}
        </span>
        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${profileClass}`}>
          {worker.profile}
        </span>
        {worker.requiresAutomationGate && (
          <span className="flex items-center gap-1 text-[10px] text-amber-300 bg-amber-900/20 border border-amber-700/30 px-1.5 py-0.5 rounded">
            <Lock size={9} />
            Automation Gate Required
          </span>
        )}
      </div>

      {/* Worker label */}
      <div>
        <p className="text-sm font-semibold text-zinc-100 leading-tight">{worker.label}</p>
        <p className="text-xs text-zinc-400 mt-1 line-clamp-2 leading-relaxed">{worker.description}</p>
      </div>

      {/* Applicable types */}
      {worker.applicableTypes.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] text-zinc-600">Applies to:</span>
          {worker.applicableTypes.map(t => (
            <span
              key={t}
              className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-400"
            >
              {TYPE_LABEL[t] ?? t}
            </span>
          ))}
        </div>
      )}

      {/* Run button + message */}
      <div className="mt-auto pt-1 flex items-center gap-2">
        <button
          onClick={handleRun}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            canRun
              ? 'bg-indigo-600 hover:bg-indigo-500 text-white border border-indigo-500'
              : selectedObjectId
              ? 'bg-zinc-800 text-zinc-500 border border-zinc-700 cursor-not-allowed'
              : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-400 border border-zinc-700'
          }`}
        >
          <Play size={11} />
          Run
        </button>
        {message && (
          <span className="text-[11px] text-amber-400 animate-pulse">{message}</span>
        )}
        {!message && !selectedObjectId && (
          <span className="text-[11px] text-zinc-600">Select an object first</span>
        )}
        {!message && selectedObjectId && !canRun && (
          <span className="text-[11px] text-zinc-600">Object type not compatible</span>
        )}
      </div>
    </div>
  )
}

// ─── Main WorkersCatalog ──────────────────────────────────────────────────────

export function WorkersCatalog() {
  const [search, setSearch] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<WorkerCategory | 'all'>('all')

  const filtered = WORKER_DEFS.filter(w => {
    const matchSearch = !search ||
      w.label.toLowerCase().includes(search.toLowerCase()) ||
      w.description.toLowerCase().includes(search.toLowerCase())
    const matchCategory = selectedCategory === 'all' || w.category === selectedCategory
    return matchSearch && matchCategory
  })

  const countByCategory = (cat: WorkerCategory | 'all') =>
    cat === 'all'
      ? WORKER_DEFS.length
      : WORKER_DEFS.filter(w => w.category === cat).length

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left: category sidebar */}
      <div className="w-52 shrink-0 border-r border-zinc-800 bg-zinc-950 flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-2">
            <Cpu size={14} className="text-indigo-400" />
            <h2 className="text-sm font-semibold text-zinc-200">Categories</h2>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          <div className="space-y-0.5">
            {CATEGORIES.map(cat => (
              <button
                key={cat.id}
                onClick={() => setSelectedCategory(cat.id)}
                className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs transition-colors ${
                  selectedCategory === cat.id
                    ? 'bg-indigo-900/30 text-indigo-300 border border-indigo-700/40'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 border border-transparent'
                }`}
              >
                <span>{cat.label}</span>
                <span className={`text-[10px] tabular-nums ${selectedCategory === cat.id ? 'text-indigo-400' : 'text-zinc-600'}`}>
                  {countByCategory(cat.id)}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Right: catalog main area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-3 border-b border-zinc-800 shrink-0 flex items-center gap-4">
          <div>
            <h1 className="text-sm font-semibold text-zinc-100">Worker Catalog</h1>
            <p className="text-xs text-zinc-500 mt-0.5">Browse and run available workers</p>
          </div>
          {/* Search */}
          <div className="relative ml-auto w-64">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              placeholder="Search workers…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 bg-zinc-900 border border-zinc-700 rounded-lg text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>
          <span className="text-xs text-zinc-600 shrink-0">{filtered.length} workers</span>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Cpu size={28} className="text-zinc-700" />
              <p className="text-sm text-zinc-500">No workers match your filter</p>
              <button
                onClick={() => { setSearch(''); setSelectedCategory('all') }}
                className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
              >
                Clear filters
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {filtered.map(worker => (
                <WorkerCard key={worker.id} worker={worker} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
