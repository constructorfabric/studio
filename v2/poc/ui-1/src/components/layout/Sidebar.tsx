import { useState } from 'react'
import { Search, FileText, Layout, CheckSquare, GitPullRequest, AlertTriangle, BookOpen, Layers, Package, Zap, ChevronRight, Clock, FolderOpen, GitBranch, Activity } from 'lucide-react'
import { useAppStore, selectPendingRecommendations } from '../../store/app-store'
import type { ObjectTypeId } from '../../types/domain'

const TYPE_CONFIGS: { typeId: ObjectTypeId; label: string; icon: React.ReactNode; color: string }[] = [
  { typeId: 'prd',          label: 'PRDs',          icon: <FileText size={13} />,      color: 'text-purple-400' },
  { typeId: 'adr',          label: 'ADRs',          icon: <BookOpen size={13} />,      color: 'text-violet-400' },
  { typeId: 'design',       label: 'Designs',       icon: <Layout size={13} />,        color: 'text-blue-400' },
  { typeId: 'decomposition',label: 'Decompositions',icon: <Layers size={13} />,        color: 'text-indigo-400' },
  { typeId: 'feature_spec', label: 'Feature Specs', icon: <Zap size={13} />,           color: 'text-teal-400' },
  { typeId: 'task',         label: 'Tasks',         icon: <CheckSquare size={13} />,   color: 'text-cyan-400' },
  { typeId: 'pull_request', label: 'Pull Requests', icon: <GitPullRequest size={13} />,color: 'text-orange-400' },
  { typeId: 'build',        label: 'Builds',        icon: <Package size={13} />,       color: 'text-lime-400' },
  { typeId: 'incident',     label: 'Incidents',     icon: <AlertTriangle size={13} />, color: 'text-red-400' },
]

function getStateColor(state: string): string {
  switch (state) {
    case 'approved': case 'done': case 'merged': return 'bg-emerald-500'
    case 'in_progress': case 'running': case 'review': return 'bg-amber-500'
    case 'failed': case 'open': return 'bg-red-500'
    case 'draft': case 'planned': return 'bg-zinc-500'
    default: return 'bg-blue-500'
  }
}

export function Sidebar() {
  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState<ObjectTypeId | null>(null)
  const objects = useAppStore(s => s.objects)
  const workerRuns = useAppStore(s => s.workerRuns)
  const selectObject = useAppStore(s => s.selectObject)
  const selectedObjectId = useAppStore(s => s.selectedObjectId)
  const recommendations = useAppStore(selectPendingRecommendations)
  const setActiveView = useAppStore(s => s.setActiveView)

  const criticalCount = recommendations.filter(r => r.severity === 'critical').length
  const recentRuns = workerRuns.slice(0, 5)

  const filteredObjects = objects.filter(o => {
    const matchSearch = !search || o.title.toLowerCase().includes(search.toLowerCase())
    const matchType = !filterType || o.typeId === filterType
    return matchSearch && matchType
  })

  const countByType = (typeId: ObjectTypeId) => objects.filter(o => o.typeId === typeId).length

  return (
    <aside className="w-56 border-r border-zinc-800 bg-zinc-950 flex flex-col shrink-0 overflow-hidden">
      {/* Search */}
      <div className="p-3 border-b border-zinc-800">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="Search objects…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-zinc-900 border border-zinc-700 rounded-lg text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </div>
      </div>

      {/* Object Types Filter */}
      <div className="p-3 border-b border-zinc-800 overflow-y-auto">
        <p className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">Object Types</p>
        <div className="space-y-0.5">
          <button
            onClick={() => setFilterType(null)}
            className={`w-full flex items-center justify-between px-2 py-1 rounded-md text-xs transition-colors ${
              filterType === null ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <span className="text-zinc-400">All</span>
            </span>
            <span className="text-zinc-500 text-[10px]">{objects.length}</span>
          </button>
          {TYPE_CONFIGS.map(({ typeId, label, icon, color }) => (
            <button
              key={typeId}
              onClick={() => setFilterType(filterType === typeId ? null : typeId)}
              className={`w-full flex items-center justify-between px-2 py-1 rounded-md text-xs transition-colors ${
                filterType === typeId ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
              }`}
            >
              <span className={`flex items-center gap-1.5 ${color}`}>
                {icon}
                <span className="text-zinc-300">{label}</span>
              </span>
              <span className="text-zinc-500 text-[10px]">{countByType(typeId)}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Object List */}
      {(search || filterType) && (
        <div className="flex-1 overflow-y-auto p-2 border-b border-zinc-800">
          <p className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2 px-1">
            Results ({filteredObjects.length})
          </p>
          <div className="space-y-0.5">
            {filteredObjects.map(obj => (
              <button
                key={obj.id}
                onClick={() => selectObject(obj.id)}
                className={`w-full text-left px-2 py-1.5 rounded-md transition-colors ${
                  selectedObjectId === obj.id
                    ? 'bg-indigo-900/50 border border-indigo-700/50 text-zinc-100'
                    : 'text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100'
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${getStateColor(obj.state)}`} />
                  <span className="text-xs truncate">{obj.title}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Recent Runs Mini Feed */}
      <div className="p-3 border-b border-zinc-800">
        <p className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">Recent Activity</p>
        {recentRuns.length === 0 ? (
          <p className="text-xs text-zinc-600 italic">No runs yet</p>
        ) : (
          <div className="space-y-1.5">
            {recentRuns.map(run => (
              <div key={run.id} className="flex items-start gap-2">
                <div className={`mt-0.5 w-1.5 h-1.5 rounded-full shrink-0 ${
                  run.state === 'done' ? 'bg-emerald-500' :
                  run.state === 'failed' ? 'bg-red-500' :
                  run.state === 'awaiting_input' ? 'bg-amber-500' :
                  'bg-blue-500 animate-pulse'
                }`} />
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] text-zinc-300 truncate">{run.workerLabel}</p>
                  <p className="text-[10px] text-zinc-500 truncate">{run.objectTitle}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick nav */}
      <div className="p-3 border-b border-zinc-800 space-y-0.5">
        <button
          onClick={() => setActiveView('files')}
          className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 transition-colors"
        >
          <FolderOpen size={13} className="text-indigo-400" />
          <span>Files</span>
        </button>
        <button
          onClick={() => setActiveView('kits')}
          className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 transition-colors"
        >
          <Package size={13} className="text-violet-400" />
          <span>Kits</span>
        </button>
        <button
          onClick={() => setActiveView('workspaces')}
          className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 transition-colors"
        >
          <GitBranch size={13} className="text-cyan-400" />
          <span>Workspaces</span>
        </button>
        <button
          onClick={() => setActiveView('workers')}
          className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 transition-colors"
        >
          <Activity size={13} className="text-blue-400" />
          <span>Monitor</span>
        </button>
      </div>

      {/* Recommendations Summary */}
      <div className="p-3 mt-auto">
        <button
          onClick={() => setActiveView('recommendations')}
          className="w-full flex items-center justify-between p-2 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition-colors group"
        >
          <div className="flex items-center gap-2">
            {criticalCount > 0 ? (
              <div className="w-6 h-6 rounded-md bg-red-900/50 flex items-center justify-center pulse-critical">
                <AlertTriangle size={12} className="text-red-400" />
              </div>
            ) : (
              <div className="w-6 h-6 rounded-md bg-amber-900/30 flex items-center justify-center">
                <AlertTriangle size={12} className="text-amber-400" />
              </div>
            )}
            <div className="text-left">
              <p className="text-[11px] font-medium text-zinc-200">{recommendations.length} Recommendations</p>
              {criticalCount > 0 && <p className="text-[10px] text-red-400">{criticalCount} critical</p>}
            </div>
          </div>
          <ChevronRight size={12} className="text-zinc-500 group-hover:text-zinc-300 transition-colors" />
        </button>

        {/* Clock / last sync */}
        <div className="mt-2 flex items-center gap-1.5 px-1">
          <Clock size={11} className="text-zinc-600" />
          <span className="text-[10px] text-zinc-600">Last sync: just now</span>
        </div>
      </div>
    </aside>
  )
}
