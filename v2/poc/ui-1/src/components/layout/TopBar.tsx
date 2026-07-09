import { Bell, GitBranch, Layers, Activity, Lightbulb, Network, ChevronRight, Cpu, FolderOpen, Package, Library, Globe, RefreshCw, ScrollText, Zap } from 'lucide-react'
import { useAppStore, selectPendingRecommendations } from '../../store/app-store'
import type { AppView } from '../../types/domain'

const MONTHLY_BUDGET = 50  // USD — mock tenant budget

const VIEWS: { id: AppView; label: string; icon: React.ReactNode }[] = [
  { id: 'graph',           label: 'Graph',       icon: <Network size={13} /> },
  { id: 'files',           label: 'Files',       icon: <FolderOpen size={13} /> },
  { id: 'catalog',         label: 'Actions',     icon: <Library size={13} /> },
  { id: 'flows',           label: 'Flows',       icon: <GitBranch size={13} /> },
  { id: 'workers',         label: 'Monitor',     icon: <Activity size={13} /> },
  { id: 'audit',           label: 'Audit',       icon: <ScrollText size={13} /> },
  { id: 'recommendations', label: 'Recs',        icon: <Lightbulb size={13} /> },
  { id: 'kits',            label: 'Kits',        icon: <Package size={13} /> },
  { id: 'workspaces',      label: 'Workspaces',  icon: <Globe size={13} /> },
]

export function TopBar() {
  const activeView  = useAppStore(s => s.activeView)
  const setActiveView = useAppStore(s => s.setActiveView)
  const recommendations = useAppStore(selectPendingRecommendations)
  const criticalCount = recommendations.filter(r => r.severity === 'critical').length

  // Aggregate total AI spend from all worker runs that have cost
  const totalSpent = useAppStore(s =>
    s.workerRuns.reduce((sum, r) => sum + (r.costUsd ?? 0), 0)
  )
  const spentPct   = Math.min(totalSpent / MONTHLY_BUDGET, 1)
  const nearLimit  = spentPct >= 0.8
  const overBudget = spentPct >= 1

  return (
    <header className="h-12 flex items-center justify-between px-4 border-b border-zinc-800 bg-zinc-950 shrink-0 z-50">
      {/* Left: Logo + Breadcrumb */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center">
            <Cpu size={14} className="text-white" />
          </div>
          <span className="text-sm font-semibold text-zinc-100 whitespace-nowrap">Constructor Studio</span>
          <span className="text-zinc-600 text-xs font-medium px-1.5 py-0.5 bg-zinc-800 rounded">v2</span>
        </div>
        <ChevronRight size={14} className="text-zinc-600 shrink-0" />
        <div className="flex items-center gap-1.5 min-w-0">
          <Layers size={13} className="text-zinc-500 shrink-0" />
          <span className="text-sm text-zinc-400 truncate">acme-corp</span>
        </div>
        <ChevronRight size={14} className="text-zinc-600 shrink-0" />
        <span className="text-sm text-zinc-300 font-medium truncate">Multi-tenant Billing Service</span>
      </div>

      {/* Center: View Switcher */}
      <nav className="flex items-center gap-1 bg-zinc-900 rounded-lg p-1 border border-zinc-800">
        {VIEWS.map(v => (
          <button
            key={v.id}
            onClick={() => setActiveView(v.id)}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all
              ${activeView === v.id
                ? 'bg-zinc-700 text-zinc-100 shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
              }
            `}
          >
            {v.icon}
            {v.label}
            {v.id === 'recommendations' && recommendations.length > 0 && (
              <span className={`
                ml-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none
                ${criticalCount > 0 ? 'bg-red-500 text-white' : 'bg-amber-500 text-zinc-900'}
              `}>
                {recommendations.length}
              </span>
            )}
          </button>
        ))}
      </nav>

      {/* Right: Actions */}
      <div className="flex items-center gap-2 shrink-0">
        {/* AI Budget meter */}
        <button
          onClick={() => setActiveView('audit')}
          title={`AI spend: $${totalSpent.toFixed(2)} / $${MONTHLY_BUDGET} budget`}
          className="flex items-center gap-2 px-2.5 py-1.5 bg-zinc-900 border border-zinc-800 rounded-lg hover:border-zinc-700 transition-colors"
        >
          <Zap size={11} className={overBudget ? 'text-red-400' : nearLimit ? 'text-amber-400' : 'text-indigo-400'} />
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-1.5">
              <span className={`text-[11px] font-semibold tabular-nums ${overBudget ? 'text-red-300' : nearLimit ? 'text-amber-300' : 'text-zinc-200'}`}>
                ${totalSpent.toFixed(2)}
              </span>
              <span className="text-[10px] text-zinc-600">/ ${MONTHLY_BUDGET}</span>
            </div>
            {/* Progress bar */}
            <div className="w-20 h-1 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  overBudget ? 'bg-red-500' : nearLimit ? 'bg-amber-500' : 'bg-indigo-500'
                }`}
                style={{ width: `${spentPct * 100}%` }}
              />
            </div>
          </div>
          {nearLimit && !overBudget && (
            <span className="text-[9px] font-bold text-amber-400 uppercase tracking-wider">80%</span>
          )}
          {overBudget && (
            <span className="text-[9px] font-bold text-red-400 uppercase tracking-wider">LIMIT</span>
          )}
        </button>

        {/* Tenant info */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-zinc-900 border border-zinc-800 rounded-lg">
          <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
          <span className="text-xs text-zinc-400">tenant: <span className="text-zinc-200 font-medium">acme-corp</span></span>
        </div>

        {/* Notifications */}
        <button className="relative p-2 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors">
          <Bell size={16} />
          {criticalCount > 0 && (
            <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full"></span>
          )}
        </button>

      </div>
    </header>
  )
}
