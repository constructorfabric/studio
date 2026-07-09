import { useState } from 'react'
import {
  Search, FileText, Layout, CheckSquare, GitPullRequest, AlertTriangle,
  BookOpen, Layers, Package, Zap, ChevronRight, ChevronDown, Clock,
  Cpu, Users, User, Tag, Rocket, Shield, Server, Map, Calendar,
  GitBranch, FolderOpen,
} from 'lucide-react'
import { useAppStore, selectPendingRecommendations } from '../../store/app-store'
import type { ObjectTypeId } from '../../types/domain'

// ─── Category → type mapping ──────────────────────────────────────────────────

interface TypeConfig {
  typeId: ObjectTypeId
  label: string
  icon: React.ReactNode
  color: string
}

interface Category {
  id: string
  label: string
  icon: React.ReactNode
  color: string
  types: TypeConfig[]
}

const CATEGORIES: Category[] = [
  {
    id: 'workspace',
    label: 'Workspace',
    icon: <FolderOpen size={13} />,
    color: 'text-indigo-400',
    types: [
      { typeId: 'prd',           label: 'PRDs',           icon: <FileText size={12} />,    color: 'text-purple-400' },
      { typeId: 'adr',           label: 'ADRs',           icon: <BookOpen size={12} />,    color: 'text-violet-400' },
      { typeId: 'design',        label: 'Designs',        icon: <Layout size={12} />,      color: 'text-blue-400' },
      { typeId: 'decomposition', label: 'Decompositions', icon: <Layers size={12} />,      color: 'text-indigo-400' },
      { typeId: 'feature_spec',  label: 'Feature Specs',  icon: <Zap size={12} />,         color: 'text-teal-400' },
    ],
  },
  {
    id: 'tasks',
    label: 'Tasks',
    icon: <CheckSquare size={13} />,
    color: 'text-cyan-400',
    types: [
      { typeId: 'task', label: 'Tasks', icon: <CheckSquare size={12} />, color: 'text-cyan-400' },
    ],
  },
  {
    id: 'version_control',
    label: 'Version Control',
    icon: <GitBranch size={13} />,
    color: 'text-orange-400',
    types: [
      { typeId: 'pull_request', label: 'Pull Requests', icon: <GitPullRequest size={12} />, color: 'text-orange-400' },
      { typeId: 'build',        label: 'Builds',        icon: <Package size={12} />,         color: 'text-lime-400' },
    ],
  },
  {
    id: 'components',
    label: 'Components',
    icon: <Cpu size={13} />,
    color: 'text-cyan-300',
    types: [
      { typeId: 'component', label: 'Components', icon: <Cpu size={12} />, color: 'text-cyan-300' },
    ],
  },
  {
    id: 'organization',
    label: 'Organization',
    icon: <Users size={13} />,
    color: 'text-violet-300',
    types: [
      { typeId: 'person', label: 'People', icon: <User size={12} />,  color: 'text-violet-300' },
      { typeId: 'team',   label: 'Teams',  icon: <Users size={12} />, color: 'text-purple-300' },
    ],
  },
  {
    id: 'release',
    label: 'Release Management',
    icon: <Rocket size={13} />,
    color: 'text-emerald-400',
    types: [
      { typeId: 'release',    label: 'Releases',    icon: <Tag size={12} />,    color: 'text-emerald-400' },
      { typeId: 'deployment', label: 'Deployments', icon: <Rocket size={12} />, color: 'text-green-400' },
    ],
  },
  {
    id: 'roadmap',
    label: 'Roadmap',
    icon: <Map size={13} />,
    color: 'text-amber-400',
    types: [
      { typeId: 'prd', label: 'PRDs (Roadmap)', icon: <Map size={12} />, color: 'text-amber-400' },
    ],
  },
  {
    id: 'planning',
    label: 'Planning',
    icon: <Calendar size={13} />,
    color: 'text-blue-300',
    types: [
      { typeId: 'decomposition', label: 'Decompositions', icon: <Layers size={12} />,      color: 'text-indigo-400' },
      { typeId: 'task',          label: 'Tasks',          icon: <CheckSquare size={12} />, color: 'text-cyan-400' },
    ],
  },
  {
    id: 'security',
    label: 'Security',
    icon: <Shield size={13} />,
    color: 'text-red-400',
    types: [
      { typeId: 'incident', label: 'Incidents', icon: <AlertTriangle size={12} />, color: 'text-red-400' },
    ],
  },
  {
    id: 'infrastructure',
    label: 'Infrastructure',
    icon: <Server size={13} />,
    color: 'text-slate-300',
    types: [
      { typeId: 'environment', label: 'Environments', icon: <Server size={12} />, color: 'text-slate-300' },
    ],
  },
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
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set())

  const objects = useAppStore(s => s.objects)
  const workerRuns = useAppStore(s => s.workerRuns)
  const selectObject = useAppStore(s => s.selectObject)
  const selectedObjectId = useAppStore(s => s.selectedObjectId)
  const recommendations = useAppStore(selectPendingRecommendations)
  const setActiveView = useAppStore(s => s.setActiveView)

  const criticalCount = recommendations.filter(r => r.severity === 'critical').length
  const recentRuns = workerRuns.filter(r => !['done','failed','aborted','escalated'].includes(r.state)).slice(0, 3)

  const countByType = (typeId: ObjectTypeId) => objects.filter(o => o.typeId === typeId).length
  const countByCategory = (cat: Category) => {
    const typeIds = new Set(cat.types.map(t => t.typeId))
    return objects.filter(o => typeIds.has(o.typeId)).length
  }

  const filteredObjects = objects.filter(o => {
    const matchSearch = !search || o.title.toLowerCase().includes(search.toLowerCase())
    const matchType = !filterType || o.typeId === filterType
    return matchSearch && matchType
  })

  const toggleCat = (id: string) => setExpandedCats(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  return (
    <aside className="w-56 border-r border-zinc-800 bg-zinc-950 flex flex-col shrink-0 overflow-hidden">
      {/* Search */}
      <div className="p-3 border-b border-zinc-800 shrink-0">
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

      {/* Categories */}
      <div className="flex-1 overflow-y-auto">
        {/* All objects shortcut */}
        <div className="px-3 pt-2 pb-1">
          <button
            onClick={() => setFilterType(null)}
            className={`w-full flex items-center justify-between px-2 py-1 rounded-md text-xs transition-colors ${
              filterType === null && !search
                ? 'bg-zinc-800 text-zinc-100'
                : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900'
            }`}
          >
            <span>All objects</span>
            <span className="text-[10px] tabular-nums">{objects.length}</span>
          </button>
        </div>

        {/* Search results */}
        {search && (
          <div className="px-3 pb-2">
            <p className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1.5">
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

        {/* Category sections */}
        {!search && CATEGORIES.map(cat => {
          const isOpen = expandedCats.has(cat.id)
          const total = countByCategory(cat)

          return (
            <div key={cat.id} className="border-b border-zinc-800/60 last:border-0">
              {/* Category header */}
              <button
                onClick={() => toggleCat(cat.id)}
                className="w-full flex items-center gap-2 px-3 py-2 hover:bg-zinc-900/50 transition-colors"
              >
                {isOpen
                  ? <ChevronDown size={10} className="text-zinc-600 shrink-0" />
                  : <ChevronRight size={10} className="text-zinc-600 shrink-0" />
                }
                <span className={`shrink-0 ${cat.color}`}>{cat.icon}</span>
                <span className="text-[11px] font-medium text-zinc-300 flex-1 text-left truncate">
                  {cat.label}
                </span>
                {total > 0 && (
                  <span className="text-[10px] text-zinc-600 tabular-nums shrink-0">{total}</span>
                )}
              </button>

              {/* Type rows */}
              {isOpen && (
                <div className="px-2 pb-1.5 space-y-0.5">
                  {cat.types.map(({ typeId, label, icon, color }) => {
                    const count = countByType(typeId)
                    const isActive = filterType === typeId
                    const typeObjects = objects.filter(o => o.typeId === typeId)
                    return (
                      <div key={`${cat.id}-${typeId}`}>
                        <button
                          onClick={() => setFilterType(isActive ? null : typeId)}
                          className={`w-full flex items-center justify-between px-2 py-1 rounded-md text-xs transition-colors ${
                            isActive
                              ? 'bg-zinc-800 text-zinc-100'
                              : 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900/70'
                          }`}
                        >
                          <span className={`flex items-center gap-1.5 ${color}`}>
                            {icon}
                            <span className="text-zinc-300 text-[11px]">{label}</span>
                          </span>
                          <span className="text-[10px] text-zinc-600 tabular-nums">{count}</span>
                        </button>

                        {/* Objects directly under this type when active */}
                        {isActive && (
                          <div className="mt-0.5 mb-1 space-y-0.5 pl-3 border-l border-zinc-800 ml-2">
                            {typeObjects.map(obj => (
                              <button
                                key={obj.id}
                                onClick={() => selectObject(obj.id)}
                                className={`w-full text-left px-2 py-1 rounded-md transition-colors text-[11px] ${
                            selectedObjectId === obj.id
                              ? 'bg-indigo-900/40 text-zinc-100'
                              : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'
                          }`}
                        >
                          <div className="flex items-center gap-1.5">
                            <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${getStateColor(obj.state)}`} />
                            <span className="truncate">{obj.title}</span>
                          </div>
                        </button>
                      ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Active runs indicator */}
      {recentRuns.length > 0 && (
        <div className="px-3 py-2 border-t border-zinc-800 shrink-0">
          <p className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1.5">Active</p>
          <div className="space-y-1">
            {recentRuns.map(run => (
              <div key={run.id} className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full shrink-0 bg-indigo-500 animate-pulse" />
                <p className="text-[10px] text-zinc-400 truncate flex-1">{run.workerLabel}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      <div className="p-3 border-t border-zinc-800 shrink-0">
        <button
          onClick={() => setActiveView('recommendations')}
          className="w-full flex items-center justify-between p-2 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition-colors group"
        >
          <div className="flex items-center gap-2">
            {criticalCount > 0 ? (
              <div className="w-5 h-5 rounded bg-red-900/50 flex items-center justify-center">
                <AlertTriangle size={10} className="text-red-400" />
              </div>
            ) : (
              <div className="w-5 h-5 rounded bg-amber-900/30 flex items-center justify-center">
                <AlertTriangle size={10} className="text-amber-400" />
              </div>
            )}
            <div className="text-left">
              <p className="text-[10px] font-medium text-zinc-300">{recommendations.length} Recs</p>
              {criticalCount > 0 && <p className="text-[9px] text-red-400">{criticalCount} critical</p>}
            </div>
          </div>
          <ChevronRight size={11} className="text-zinc-600 group-hover:text-zinc-400 transition-colors" />
        </button>
        <div className="mt-2 flex items-center gap-1.5 px-1">
          <Clock size={10} className="text-zinc-700" />
          <span className="text-[9px] text-zinc-700">Last sync: just now</span>
        </div>
      </div>
    </aside>
  )
}
