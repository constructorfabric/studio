import { useState, useMemo } from 'react'
import {
  ScrollText, CheckCircle, XCircle, Loader, GitBranch, Link2,
  RefreshCw, User, Zap, AlertTriangle, Filter, ChevronDown,
  ArrowRight, Clock, Search,
} from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import type { WorkerRun, LoopRun, StudioObject } from '../../types/domain'

// ─── Audit Event Types ────────────────────────────────────────────────────────

type AuditEventKind =
  | 'worker_run.started'
  | 'worker_run.completed'
  | 'worker_run.failed'
  | 'worker_run.aborted'
  | 'flow_run.started'
  | 'flow_run.completed'
  | 'loop_run.started'
  | 'loop_run.completed'
  | 'object.state_changed'
  | 'object.created'
  | 'object.link_added'
  | 'recommendation.accepted'
  | 'recommendation.dismissed'
  | 'evidence.attached'
  | 'approval.granted'

interface AuditEvent {
  id: string
  ts: string
  kind: AuditEventKind
  actor: string            // User ID or Worker ID
  actorKind: 'user' | 'worker' | 'system'
  objectId?: string
  objectTitle?: string
  objectTypeId?: string
  description: string
  meta?: Record<string, string>  // e.g. { from: 'draft', to: 'approved' }
  severity: 'info' | 'warning' | 'critical'
}

// ─── Event kind config ────────────────────────────────────────────────────────

const KIND_CFG: Record<AuditEventKind, { label: string; color: string; icon: React.ReactNode }> = {
  'worker_run.started':      { label: 'Worker started',      color: '#6366f1', icon: <Loader size={12} className="animate-spin" /> },
  'worker_run.completed':    { label: 'Worker completed',    color: '#10b981', icon: <CheckCircle size={12} /> },
  'worker_run.failed':       { label: 'Worker failed',       color: '#ef4444', icon: <XCircle size={12} /> },
  'worker_run.aborted':      { label: 'Worker aborted',      color: '#71717a', icon: <XCircle size={12} /> },
  'flow_run.started':        { label: 'Flow started',        color: '#6366f1', icon: <GitBranch size={12} /> },
  'flow_run.completed':      { label: 'Flow completed',      color: '#10b981', icon: <GitBranch size={12} /> },
  'loop_run.started':        { label: 'Loop started',        color: '#8b5cf6', icon: <RefreshCw size={12} /> },
  'loop_run.completed':      { label: 'Loop completed',      color: '#10b981', icon: <RefreshCw size={12} /> },
  'object.state_changed':    { label: 'State changed',       color: '#f59e0b', icon: <ArrowRight size={12} /> },
  'object.created':          { label: 'Object created',      color: '#06b6d4', icon: <Zap size={12} /> },
  'object.link_added':       { label: 'Link added',          color: '#a78bfa', icon: <Link2 size={12} /> },
  'recommendation.accepted': { label: 'Recommendation accepted', color: '#10b981', icon: <CheckCircle size={12} /> },
  'recommendation.dismissed':{ label: 'Recommendation dismissed', color: '#71717a', icon: <XCircle size={12} /> },
  'evidence.attached':       { label: 'Evidence attached',   color: '#14b8a6', icon: <CheckCircle size={12} /> },
  'approval.granted':        { label: 'Approval granted',    color: '#10b981', icon: <User size={12} /> },
}

const TYPE_LABEL: Record<string, string> = {
  prd: 'PRD', design: 'DESIGN', adr: 'ADR', decomposition: 'DECOMP',
  feature_spec: 'FSPEC', task: 'TASK', pull_request: 'PR', build: 'BUILD',
  incident: 'INC', component: 'COMP', release: 'RELEASE',
  deployment: 'DEPLOY', environment: 'ENV', person: 'PERSON', team: 'TEAM',
}

// ─── Synthesise audit events from store state ─────────────────────────────────

function synthesiseEvents(
  workerRuns: WorkerRun[],
  loopRuns: LoopRun[],
  objects: StudioObject[],
): AuditEvent[] {
  const events: AuditEvent[] = []

  // WorkerRun events
  for (const run of workerRuns) {
    const base = {
      objectId: run.objectId,
      objectTitle: run.objectTitle,
      actor: run.workerId,
      actorKind: 'worker' as const,
    }
    events.push({
      id: `wr-start-${run.id}`,
      ts: run.startedAt,
      kind: 'worker_run.started',
      description: `${run.workerLabel} started on "${run.objectTitle}"`,
      severity: 'info',
      meta: { workerId: run.workerId, runId: run.id },
      ...base,
    })
    if (run.completedAt) {
      const kind: AuditEventKind =
        run.state === 'done' ? 'worker_run.completed' :
        run.state === 'aborted' ? 'worker_run.aborted' :
        'worker_run.failed'
      events.push({
        id: `wr-end-${run.id}`,
        ts: run.completedAt,
        kind,
        description: `${run.workerLabel} ${run.state === 'done' ? 'completed' : run.state} on "${run.objectTitle}"${run.output ? ` — ${run.output.slice(0, 80)}` : ''}`,
        severity: run.state === 'done' ? 'info' : run.state === 'aborted' ? 'info' : 'warning',
        meta: run.costUsd ? { cost: `$${run.costUsd.toFixed(2)}`, tokens: String(run.tokensIn ?? 0) } : undefined,
        ...base,
      })
    }
  }

  // LoopRun events
  for (const lr of loopRuns) {
    events.push({
      id: `lr-start-${lr.id}`,
      ts: lr.startedAt,
      kind: 'loop_run.started',
      actor: 'system',
      actorKind: 'system',
      objectId: lr.objectId,
      objectTitle: lr.objectTitle,
      description: `Loop "${lr.flowLabel}" started on "${lr.objectTitle}"`,
      severity: 'info',
      meta: { flowId: lr.flowId },
    })
    if (lr.completedAt) {
      events.push({
        id: `lr-end-${lr.id}`,
        ts: lr.completedAt,
        kind: 'loop_run.completed',
        actor: 'system',
        actorKind: 'system',
        objectId: lr.objectId,
        objectTitle: lr.objectTitle,
        description: `Loop "${lr.flowLabel}" ${lr.terminationReason ?? 'completed'} — score ${lr.bestScore.toFixed(2)}, ${lr.iterations.length} iterations, $${lr.totalCostUsd.toFixed(2)}`,
        severity: 'info',
        meta: { terminationReason: lr.terminationReason ?? 'done', cost: `$${lr.totalCostUsd.toFixed(2)}` },
      })
    }
  }

  // Object creation events (synthesised from createdAt)
  for (const obj of objects) {
    events.push({
      id: `obj-created-${obj.id}`,
      ts: obj.createdAt,
      kind: 'object.created',
      actor: 'system',
      actorKind: 'system',
      objectId: obj.id,
      objectTitle: obj.title,
      objectTypeId: obj.typeId,
      description: `${TYPE_LABEL[obj.typeId] ?? obj.typeId} "${obj.title}" created`,
      severity: 'info',
    })

    // State-change event if not draft/planned (implies at least one transition happened)
    if (!['draft', 'planned', 'open'].includes(obj.state)) {
      events.push({
        id: `obj-state-${obj.id}`,
        ts: obj.updatedAt,
        kind: 'object.state_changed',
        actor: 'user',
        actorKind: 'user',
        objectId: obj.id,
        objectTitle: obj.title,
        objectTypeId: obj.typeId,
        description: `"${obj.title}" transitioned to ${obj.state.replace('_', ' ')}`,
        severity: obj.state === 'failed' ? 'warning' : 'info',
        meta: { to: obj.state },
      })
    }

    // Link events
    for (const link of obj.links) {
      const target = objects.find(o => o.id === link.targetId)
      if (target) {
        events.push({
          id: `link-${obj.id}-${link.targetId}-${link.kind}`,
          ts: obj.updatedAt,
          kind: 'object.link_added',
          actor: 'system',
          actorKind: 'system',
          objectId: obj.id,
          objectTitle: obj.title,
          objectTypeId: obj.typeId,
          description: `"${obj.title}" → ${link.kind.replace(/_/g, ' ')} → "${target.title}"`,
          severity: 'info',
          meta: { kind: link.kind, targetId: target.id },
        })
      }
    }
  }

  // Sort newest first
  return events.sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())
}

// ─── Filter types ─────────────────────────────────────────────────────────────

const FILTER_KINDS: { value: string; label: string }[] = [
  { value: 'all', label: 'All events' },
  { value: 'worker', label: 'Worker runs' },
  { value: 'flow', label: 'Flow & Loop runs' },
  { value: 'object', label: 'Object changes' },
  { value: 'governance', label: 'Governance' },
]

// ─── AuditLog component ───────────────────────────────────────────────────────

export function AuditLog() {
  const workerRuns = useAppStore(s => s.workerRuns)
  const loopRuns   = useAppStore(s => s.loopRuns)
  const objects    = useAppStore(s => s.objects)
  const selectObject = useAppStore(s => s.selectObject)
  const setActiveView = useAppStore(s => s.setActiveView)

  const [search, setSearch]     = useState('')
  const [kindFilter, setKindFilter] = useState('all')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const allEvents = useMemo(
    () => synthesiseEvents(workerRuns, loopRuns, objects),
    [workerRuns, loopRuns, objects]
  )

  const filtered = useMemo(() => {
    return allEvents.filter(ev => {
      const matchSearch = !search ||
        ev.description.toLowerCase().includes(search.toLowerCase()) ||
        (ev.objectTitle ?? '').toLowerCase().includes(search.toLowerCase())

      const matchKind =
        kindFilter === 'all' ? true :
        kindFilter === 'worker' ? ev.kind.startsWith('worker_run') :
        kindFilter === 'flow' ? (ev.kind.startsWith('flow_run') || ev.kind.startsWith('loop_run')) :
        kindFilter === 'object' ? ev.kind.startsWith('object') :
        kindFilter === 'governance' ? ['recommendation.accepted','recommendation.dismissed','approval.granted','evidence.attached'].includes(ev.kind) :
        true

      return matchSearch && matchKind
    })
  }, [allEvents, search, kindFilter])

  const toggleExpand = (id: string) => setExpanded(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  function fmtTime(ts: string): string {
    try {
      const d = new Date(ts)
      return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch { return ts }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-zinc-950">
      {/* Header */}
      <div className="px-5 py-3 border-b border-zinc-800 shrink-0">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <ScrollText size={16} className="text-zinc-400" />
            <h1 className="text-sm font-semibold text-zinc-100">Audit Log</h1>
            <span className="text-xs text-zinc-500">{filtered.length} events</span>
          </div>

          {/* Filter bar */}
          <div className="flex items-center gap-3 flex-1 max-w-2xl">
            {/* Search */}
            <div className="relative flex-1">
              <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input
                type="text"
                placeholder="Search events, objects…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full pl-7 pr-3 py-1.5 bg-zinc-900 border border-zinc-700 rounded-lg text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors"
              />
            </div>

            {/* Kind filter */}
            <div className="relative">
              <select
                value={kindFilter}
                onChange={e => setKindFilter(e.target.value)}
                className="appearance-none bg-zinc-900 border border-zinc-700 text-xs text-zinc-300 px-3 py-1.5 pr-7 rounded-lg focus:outline-none focus:border-indigo-500 cursor-pointer"
              >
                {FILTER_KINDS.map(f => (
                  <option key={f.value} value={f.value}>{f.label}</option>
                ))}
              </select>
              <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
            </div>
          </div>
        </div>
      </div>

      {/* Event stream */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 gap-3">
            <ScrollText size={28} className="text-zinc-700" />
            <p className="text-sm text-zinc-500">No matching events</p>
          </div>
        ) : (
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute left-[29px] top-0 bottom-0 w-px bg-zinc-800" />

            {filtered.map((ev, idx) => {
              const cfg = KIND_CFG[ev.kind]
              const isExpanded = expanded.has(ev.id)
              const hasMeta = ev.meta && Object.keys(ev.meta).length > 0
              const isFirst = idx === 0
              const prevDate = idx > 0 ? new Date(filtered[idx-1].ts).toDateString() : null
              const thisDate = new Date(ev.ts).toDateString()
              const showDateSep = isFirst || thisDate !== prevDate

              return (
                <div key={ev.id}>
                  {/* Date separator */}
                  {showDateSep && (
                    <div className="flex items-center gap-3 px-4 py-2 sticky top-0 bg-zinc-950/95 backdrop-blur z-10">
                      <div className="flex-1 h-px bg-zinc-800" />
                      <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider whitespace-nowrap">
                        {new Date(ev.ts).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
                      </span>
                      <div className="flex-1 h-px bg-zinc-800" />
                    </div>
                  )}

                  {/* Event row */}
                  <div
                    className="flex items-start gap-3 px-4 py-2.5 hover:bg-zinc-900/40 transition-colors cursor-pointer group"
                    onClick={() => {
                      toggleExpand(ev.id)
                      if (ev.objectId) selectObject(ev.objectId)
                    }}
                  >
                    {/* Timeline dot */}
                    <div className="relative shrink-0 mt-0.5 z-10">
                      <div
                        className="w-5 h-5 rounded-full flex items-center justify-center"
                        style={{ background: `${cfg.color}20`, border: `1px solid ${cfg.color}50` }}
                      >
                        <span style={{ color: cfg.color }}>{cfg.icon}</span>
                      </div>
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          {/* Event label + object type badge */}
                          <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                            <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: cfg.color }}>
                              {cfg.label}
                            </span>
                            {ev.objectTypeId && (
                              <span className="text-[9px] font-bold uppercase px-1 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-500">
                                {TYPE_LABEL[ev.objectTypeId] ?? ev.objectTypeId}
                              </span>
                            )}
                            {ev.severity === 'warning' && (
                              <AlertTriangle size={10} className="text-amber-500 shrink-0" />
                            )}
                            {ev.severity === 'critical' && (
                              <AlertTriangle size={10} className="text-red-500 shrink-0" />
                            )}
                          </div>

                          {/* Description */}
                          <p className="text-xs text-zinc-300 leading-relaxed">{ev.description}</p>

                          {/* Meta (expanded) */}
                          {isExpanded && hasMeta && (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {Object.entries(ev.meta!).map(([k, v]) => (
                                <span key={k} className="text-[10px] px-2 py-0.5 rounded bg-zinc-800/70 border border-zinc-700/50 text-zinc-400">
                                  <span className="text-zinc-600">{k}: </span>{v}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* Timestamp + actor */}
                        <div className="text-right shrink-0">
                          <p className="text-[10px] text-zinc-500 tabular-nums whitespace-nowrap">
                            {fmtTime(ev.ts)}
                          </p>
                          <div className="flex items-center gap-1 justify-end mt-0.5">
                            {ev.actorKind === 'user' && <User size={9} className="text-zinc-600" />}
                            {ev.actorKind === 'worker' && <Zap size={9} className="text-zinc-600" />}
                            {ev.actorKind === 'system' && <Clock size={9} className="text-zinc-600" />}
                            <span className="text-[9px] text-zinc-600 max-w-[80px] truncate">{ev.actor}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Footer stats */}
      <div className="px-5 py-2 border-t border-zinc-800 shrink-0 flex items-center gap-6">
        {[
          { label: 'Worker runs', count: allEvents.filter(e => e.kind.startsWith('worker_run')).length, color: 'text-indigo-400' },
          { label: 'State changes', count: allEvents.filter(e => e.kind === 'object.state_changed').length, color: 'text-amber-400' },
          { label: 'Loop runs', count: allEvents.filter(e => e.kind.startsWith('loop_run')).length, color: 'text-violet-400' },
          { label: 'Objects', count: allEvents.filter(e => e.kind === 'object.created').length, color: 'text-cyan-400' },
        ].map(s => (
          <div key={s.label} className="flex items-center gap-1.5">
            <span className={`text-xs font-bold tabular-nums ${s.color}`}>{s.count}</span>
            <span className="text-[10px] text-zinc-600">{s.label}</span>
          </div>
        ))}
        <span className="ml-auto text-[10px] text-zinc-600">Tenant: acme-corp</span>
      </div>
    </div>
  )
}
