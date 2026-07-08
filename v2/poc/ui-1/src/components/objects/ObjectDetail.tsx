import { useState } from 'react'
import { Play, ExternalLink, Clock, CheckCircle, XCircle, AlertCircle, Loader, Lock, AlertTriangle, ShieldCheck, TrendingUp, TrendingDown, Minus, FileCheck, GitMerge } from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import { getWorkersForObject, MOCK_OBJECTS, MOCK_RECOMMENDATIONS } from '../../data/mock-data'
import type { StudioObject, WorkerRun, ObjectTypeId } from '../../types/domain'
import { StateBadge, ValidationBadge } from '../layout/RightPanel'

interface Props {
  object: StudioObject
  activeTab: string
}

export function ObjectDetail({ object, activeTab }: Props) {
  switch (activeTab) {
    case 'overview': return <OverviewTab object={object} />
    case 'actions':  return <ActionsTab object={object} />
    case 'history':  return <HistoryTab object={object} />
    case 'links':    return <LinksTab object={object} />
    case 'score':    return <ScoreTab object={object} />
    default:         return <OverviewTab object={object} />
  }
}

// ─── Mock per-object score data ───────────────────────────────────────────────

interface ObjectScore {
  qualityScore: number          // 0-100
  traceability: number          // 0-100 % coverage
  reqsCovered: number
  reqsTotal: number
  validationHistory: ('pass' | 'fail' | 'skip')[]
  staleness: number             // 0-100
  findings: Array<{ severity: 'critical' | 'warning' | 'info'; label: string }>
  aiCostUsd: number
  lastRunMs: number
}

function getObjectScore(obj: StudioObject): ObjectScore {
  const base: Record<string, ObjectScore> = {
    'prd-001':     { qualityScore: 82, traceability: 87, reqsCovered: 7, reqsTotal: 8, validationHistory: ['pass','pass','fail','pass','pass'], staleness: 5,  findings: [{ severity: 'info', label: 'R-005 has no linked test case' }, { severity: 'warning', label: '1 use-case missing acceptance criteria' }], aiCostUsd: 0.12, lastRunMs: 3200 },
    'design-001':  { qualityScore: 78, traceability: 92, reqsCovered: 8, reqsTotal: 8, validationHistory: ['pass','fail','pass','pass'], staleness: 15, findings: [{ severity: 'warning', label: 'Event bus pattern not implemented in code' }, { severity: 'info', label: '2 interfaces lack error schemas' }], aiCostUsd: 0.34, lastRunMs: 5100 },
    'adr-001':     { qualityScore: 91, traceability: 100, reqsCovered: 3, reqsTotal: 3, validationHistory: ['pass','pass','pass'], staleness: 8,  findings: [], aiCostUsd: 0.08, lastRunMs: 1800 },
    'adr-002':     { qualityScore: 88, traceability: 100, reqsCovered: 2, reqsTotal: 2, validationHistory: ['pass','pass'], staleness: 12, findings: [{ severity: 'info', label: 'No migration plan documented' }], aiCostUsd: 0.07, lastRunMs: 1600 },
    'decomp-001':  { qualityScore: 74, traceability: 78, reqsCovered: 6, reqsTotal: 8, validationHistory: ['fail','pass','pass'], staleness: 10, findings: [{ severity: 'warning', label: '2 tasks have no Definition of Done' }, { severity: 'critical', label: 'Tasks missing prd fr[] coverage' }], aiCostUsd: 0.29, lastRunMs: 4800 },
    'task-001':    { qualityScore: 70, traceability: 65, reqsCovered: 1, reqsTotal: 1, validationHistory: ['pass','fail','pass'], staleness: 5,  findings: [{ severity: 'warning', label: 'No traceability markers in source code' }], aiCostUsd: 0.18, lastRunMs: 2900 },
    'task-002':    { qualityScore: 60, traceability: 0,  reqsCovered: 0, reqsTotal: 1, validationHistory: ['fail'], staleness: 20, findings: [{ severity: 'critical', label: 'Feature spec not approved yet' }, { severity: 'warning', label: 'No implementation started' }], aiCostUsd: 0, lastRunMs: 0 },
    'task-003':    { qualityScore: 95, traceability: 100, reqsCovered: 1, reqsTotal: 1, validationHistory: ['pass','pass','pass'], staleness: 0,  findings: [], aiCostUsd: 0.22, lastRunMs: 3400 },
    'fspec-001':   { qualityScore: 88, traceability: 94, reqsCovered: 3, reqsTotal: 3, validationHistory: ['pass','pass'], staleness: 5,  findings: [{ severity: 'info', label: '1 error scenario missing repro steps' }], aiCostUsd: 0.41, lastRunMs: 6200 },
    'fspec-002':   { qualityScore: 45, traceability: 30, reqsCovered: 0, reqsTotal: 2, validationHistory: ['fail'], staleness: 25, findings: [{ severity: 'critical', label: 'No test scenarios defined' }, { severity: 'critical', label: 'Missing algo blocks for invoice calc' }, { severity: 'warning', label: 'Definition of Done incomplete' }], aiCostUsd: 0, lastRunMs: 0 },
    'pr-001':      { qualityScore: 72, traceability: 80, reqsCovered: 2, reqsTotal: 3, validationHistory: ['fail','pass'], staleness: 5,  findings: [{ severity: 'warning', label: 'No security review completed' }, { severity: 'info', label: 'CI run pending' }], aiCostUsd: 0.15, lastRunMs: 2100 },
    'build-001':   { qualityScore: 100, traceability: 100, reqsCovered: 0, reqsTotal: 0, validationHistory: ['pass'], staleness: 0, findings: [], aiCostUsd: 0.02, lastRunMs: 800 },
    'incident-001':{ qualityScore: 40, traceability: 20, reqsCovered: 0, reqsTotal: 0, validationHistory: ['fail'], staleness: 30, findings: [{ severity: 'critical', label: 'No postmortem created' }, { severity: 'critical', label: 'Root cause not identified' }], aiCostUsd: 0, lastRunMs: 0 },
  }
  return base[obj.id] ?? { qualityScore: 60, traceability: 50, reqsCovered: 0, reqsTotal: 0, validationHistory: ['pass'], staleness: obj.stalenessScore, findings: [], aiCostUsd: 0.05, lastRunMs: 1000 }
}

// ─── SVG Charts ───────────────────────────────────────────────────────────────

function DonutChart({ value, total, color, size = 80, label }: {
  value: number; total: number; color: string; size?: number; label?: string
}) {
  const pct = total === 0 ? 0 : Math.round((value / total) * 100)
  const r = size / 2 - 8
  const circ = 2 * Math.PI * r
  const dash = (pct / 100) * circ
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(63,63,70,0.4)" strokeWidth={7} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={7}
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 0.6s ease' }}
        />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: size < 70 ? 13 : 16, fontWeight: 800, color: '#e4e4e7', lineHeight: 1 }}>{pct}%</span>
        {label && <span style={{ fontSize: 9, color: '#71717a', marginTop: 1 }}>{label}</span>}
      </div>
    </div>
  )
}

function RadialGauge({ value, color, size = 80, label }: { value: number; color: string; size?: number; label?: string }) {
  const r = size / 2 - 8
  const circ = Math.PI * r  // half circle
  const dash = (value / 100) * circ
  return (
    <div style={{ position: 'relative', width: size, height: size / 2 + 16, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ overflow: 'visible' }}>
        <path d={`M 8,${size/2} A ${r},${r} 0 0 1 ${size-8},${size/2}`} fill="none" stroke="rgba(63,63,70,0.4)" strokeWidth={7} strokeLinecap="round" />
        <path d={`M 8,${size/2} A ${r},${r} 0 0 1 ${size-8},${size/2}`} fill="none" stroke={color} strokeWidth={7} strokeLinecap="round"
          strokeDasharray={`${dash} ${circ}`} style={{ transition: 'stroke-dasharray 0.6s ease' }} />
      </svg>
      <div style={{ position: 'absolute', bottom: 4, left: 0, right: 0, textAlign: 'center' }}>
        <span style={{ fontSize: 17, fontWeight: 800, color: '#e4e4e7' }}>{value}</span>
        {label && <div style={{ fontSize: 9, color: '#71717a', marginTop: 1 }}>{label}</div>}
      </div>
    </div>
  )
}

function Sparkline({ values, color, width = 120, height = 32 }: { values: number[]; color: string; width?: number; height?: number }) {
  if (values.length < 2) return null
  const max = Math.max(...values, 1)
  const min = Math.min(...values)
  const range = max - min || 1
  const step = width / (values.length - 1)
  const points = values.map((v, i) => `${i * step},${height - ((v - min) / range) * (height - 4) - 2}`).join(' ')
  return (
    <svg width={width} height={height} style={{ overflow: 'visible' }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {values.map((v, i) => (
        <circle key={i} cx={i * step} cy={height - ((v - min) / range) * (height - 4) - 2} r={i === values.length - 1 ? 3 : 2} fill={color} />
      ))}
    </svg>
  )
}

function ValidationDots({ history }: { history: ('pass' | 'fail' | 'skip')[] }) {
  const colors = { pass: '#10b981', fail: '#ef4444', skip: '#71717a' }
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
      {history.map((h, i) => (
        <div key={i} style={{
          width: 10, height: 10, borderRadius: '50%',
          background: colors[h],
          boxShadow: `0 0 0 2px ${colors[h]}22`,
        }} title={h} />
      ))}
      <span style={{ fontSize: 10, color: '#71717a', marginLeft: 2 }}>
        {history.filter(h => h === 'pass').length}/{history.length} passed
      </span>
    </div>
  )
}

function FindingItem({ severity, label }: { severity: 'critical' | 'warning' | 'info'; label: string }) {
  const colors = { critical: '#f87171', warning: '#fbbf24', info: '#60a5fa' }
  const bg = { critical: 'rgba(239,68,68,0.08)', warning: 'rgba(245,158,11,0.08)', info: 'rgba(59,130,246,0.08)' }
  const border = { critical: 'rgba(239,68,68,0.25)', warning: 'rgba(245,158,11,0.25)', info: 'rgba(59,130,246,0.2)' }
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 7,
      padding: '6px 8px', borderRadius: 7,
      background: bg[severity], border: `1px solid ${border[severity]}`,
      borderLeft: `3px solid ${colors[severity]}`,
    }}>
      <AlertTriangle size={10} color={colors[severity]} style={{ marginTop: 2, flexShrink: 0 }} />
      <span style={{ fontSize: 11, color: '#d4d4d8', lineHeight: 1.4 }}>{label}</span>
    </div>
  )
}

// ─── Score Tab ────────────────────────────────────────────────────────────────

function ScoreTab({ object }: { object: StudioObject }) {
  const score = getObjectScore(object)
  const qColor = score.qualityScore >= 80 ? '#10b981' : score.qualityScore >= 60 ? '#f59e0b' : '#ef4444'
  const tColor = score.traceability >= 80 ? '#10b981' : score.traceability >= 50 ? '#f59e0b' : '#ef4444'
  const sColor = score.staleness <= 20 ? '#10b981' : score.staleness <= 50 ? '#f59e0b' : '#ef4444'

  // Sparkline mock data (7-day trend)
  const qualityTrend = [65, 70, 68, 74, 78, score.qualityScore - 3, score.qualityScore]
  const stalenessTrend = [10, 12, 15, 18, score.staleness + 5, score.staleness + 2, score.staleness]

  return (
    <div style={{ padding: '14px 14px', display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Top gauges row */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8,
      }}>
        {/* Quality score */}
        <div style={{ background: 'rgba(24,24,27,0.6)', border: '1px solid rgba(63,63,70,0.4)', borderRadius: 10, padding: '10px 8px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <RadialGauge value={score.qualityScore} color={qColor} size={72} />
          <span style={{ fontSize: 10, fontWeight: 600, color: '#a1a1aa', textAlign: 'center', marginTop: 2 }}>Quality</span>
        </div>

        {/* Traceability donut */}
        <div style={{ background: 'rgba(24,24,27,0.6)', border: '1px solid rgba(63,63,70,0.4)', borderRadius: 10, padding: '10px 8px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <DonutChart value={score.traceability} total={100} color={tColor} size={72} />
          <span style={{ fontSize: 10, fontWeight: 600, color: '#a1a1aa', textAlign: 'center' }}>Traceability</span>
        </div>

        {/* Staleness */}
        <div style={{ background: 'rgba(24,24,27,0.6)', border: '1px solid rgba(63,63,70,0.4)', borderRadius: 10, padding: '10px 8px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <DonutChart value={100 - score.staleness} total={100} color={sColor} size={72} label="fresh" />
          <span style={{ fontSize: 10, fontWeight: 600, color: '#a1a1aa', textAlign: 'center' }}>Freshness</span>
        </div>
      </div>

      {/* Requirement coverage bar */}
      {score.reqsTotal > 0 && (
        <div style={{ background: 'rgba(24,24,27,0.6)', border: '1px solid rgba(63,63,70,0.4)', borderRadius: 10, padding: '10px 12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: '#a1a1aa', display: 'flex', alignItems: 'center', gap: 5 }}>
              <FileCheck size={12} color="#818cf8" /> Requirement Coverage
            </span>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#818cf8' }}>
              {score.reqsCovered}/{score.reqsTotal}
            </span>
          </div>
          <div style={{ height: 6, background: 'rgba(63,63,70,0.5)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 3,
              width: `${(score.reqsCovered / score.reqsTotal) * 100}%`,
              background: score.reqsCovered === score.reqsTotal ? '#10b981' : '#6366f1',
              transition: 'width 0.5s ease',
            }} />
          </div>
          <div style={{ display: 'flex', gap: 3, marginTop: 5, flexWrap: 'wrap' }}>
            {Array.from({ length: score.reqsTotal }).map((_, i) => (
              <div key={i} style={{
                width: 8, height: 8, borderRadius: 2,
                background: i < score.reqsCovered ? '#10b981' : 'rgba(63,63,70,0.5)',
              }} />
            ))}
          </div>
        </div>
      )}

      {/* Trends */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div style={{ background: 'rgba(24,24,27,0.6)', border: '1px solid rgba(63,63,70,0.4)', borderRadius: 10, padding: '10px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 8 }}>
            <TrendingUp size={11} color="#10b981" />
            <span style={{ fontSize: 10, fontWeight: 600, color: '#71717a' }}>Quality Trend</span>
          </div>
          <Sparkline values={qualityTrend} color={qColor} width={108} height={30} />
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
            <span style={{ fontSize: 9, color: '#52525b' }}>7d ago</span>
            <span style={{ fontSize: 9, color: '#52525b' }}>now</span>
          </div>
        </div>
        <div style={{ background: 'rgba(24,24,27,0.6)', border: '1px solid rgba(63,63,70,0.4)', borderRadius: 10, padding: '10px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 8 }}>
            <TrendingDown size={11} color={sColor} />
            <span style={{ fontSize: 10, fontWeight: 600, color: '#71717a' }}>Staleness Trend</span>
          </div>
          <Sparkline values={stalenessTrend} color={score.staleness > 30 ? '#ef4444' : '#f59e0b'} width={108} height={30} />
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
            <span style={{ fontSize: 9, color: '#52525b' }}>7d ago</span>
            <span style={{ fontSize: 9, color: '#52525b' }}>now</span>
          </div>
        </div>
      </div>

      {/* Validation history */}
      <div style={{ background: 'rgba(24,24,27,0.6)', border: '1px solid rgba(63,63,70,0.4)', borderRadius: 10, padding: '10px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 8 }}>
          <ShieldCheck size={11} color="#818cf8" />
          <span style={{ fontSize: 11, fontWeight: 600, color: '#a1a1aa' }}>Validation History</span>
        </div>
        <ValidationDots history={score.validationHistory} />
      </div>

      {/* AI Cost */}
      {score.aiCostUsd > 0 && (
        <div style={{ background: 'rgba(24,24,27,0.6)', border: '1px solid rgba(63,63,70,0.4)', borderRadius: 10, padding: '10px 12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: '#a1a1aa' }}>AI Attribution</span>
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            <div>
              <p style={{ fontSize: 18, fontWeight: 800, color: '#e4e4e7' }}>${score.aiCostUsd.toFixed(2)}</p>
              <p style={{ fontSize: 9, color: '#71717a' }}>total cost</p>
            </div>
            <div>
              <p style={{ fontSize: 18, fontWeight: 800, color: '#a78bfa' }}>{(score.lastRunMs / 1000).toFixed(1)}s</p>
              <p style={{ fontSize: 9, color: '#71717a' }}>last run</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Overview Tab (findings + status focused) ─────────────────────────────────

function OverviewTab({ object }: { object: StudioObject }) {
  const score = getObjectScore(object)
  const allObjects = MOCK_OBJECTS
  const recs = MOCK_RECOMMENDATIONS.filter(r => r.relatedObjectIds.includes(object.id) && r.state === 'pending')
  const incomingCount = allObjects.filter(o => o.links.some(l => l.targetId === object.id)).length

  return (
    <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Description */}
      {object.description && (
        <div>
          <p style={{ fontSize: 12, color: '#a1a1aa', lineHeight: 1.6 }}>{object.description}</p>
        </div>
      )}

      {/* Findings */}
      {score.findings.length > 0 && (
        <div>
          <h3 style={{ fontSize: 10, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 5 }}>
            <AlertTriangle size={10} /> Findings ({score.findings.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {score.findings.map((f, i) => <FindingItem key={i} severity={f.severity} label={f.label} />)}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {recs.length > 0 && (
        <div>
          <h3 style={{ fontSize: 10, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 5 }}>
            <AlertCircle size={10} /> Recommendations ({recs.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {recs.map(rec => {
              const sc = rec.severity === 'critical' ? { color: '#f87171', bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.2)', left: '#ef4444' }
                       : rec.severity === 'warning'  ? { color: '#fbbf24', bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.2)', left: '#f59e0b' }
                       : { color: '#60a5fa', bg: 'rgba(59,130,246,0.08)', border: 'rgba(59,130,246,0.2)', left: '#3b82f6' }
              return (
                <div key={rec.id} style={{
                  padding: '6px 8px', borderRadius: 7, background: sc.bg,
                  border: `1px solid ${sc.border}`, borderLeft: `3px solid ${sc.left}`,
                }}>
                  <p style={{ fontSize: 11, fontWeight: 600, color: '#d4d4d8', marginBottom: 2 }}>{rec.title}</p>
                  <p style={{ fontSize: 10, color: '#71717a', lineHeight: 1.4 }}>{rec.description}</p>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Status properties */}
      <div>
        <h3 style={{ fontSize: 10, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>Properties</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {[
            { label: 'State', value: <StateBadge state={object.state} /> },
            { label: 'Validation', value: <ValidationBadge status={object.validationStatus} /> },
            { label: 'Staleness', value: <span style={{ fontSize: 11, color: object.stalenessScore > 50 ? '#f87171' : object.stalenessScore > 20 ? '#fbbf24' : '#10b981' }}>{object.stalenessScore}%</span> },
            { label: 'ID', value: <span style={{ fontSize: 10, fontFamily: 'monospace', color: '#71717a' }}>{object.id}</span> },
            { label: 'Updated', value: <span style={{ fontSize: 11, color: '#a1a1aa' }}>{new Date(object.updatedAt).toLocaleDateString()}</span> },
            { label: 'Linked by', value: <span style={{ fontSize: 11, color: '#818cf8' }}>{incomingCount} object{incomingCount !== 1 ? 's' : ''}</span> },
          ].map(({ label, value }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid rgba(63,63,70,0.3)' }}>
              <span style={{ fontSize: 11, color: '#71717a' }}>{label}</span>
              <div>{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Metadata */}
      {object.metadata && Object.keys(object.metadata).length > 0 && (
        <div>
          <h3 style={{ fontSize: 10, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>Metadata</h3>
          <div style={{ background: 'rgba(24,24,27,0.6)', border: '1px solid rgba(63,63,70,0.4)', borderRadius: 8, padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 4 }}>
            {Object.entries(object.metadata).map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ fontSize: 10, color: '#71717a' }}>{k}</span>
                <span style={{ fontSize: 10, color: '#d4d4d8', fontFamily: 'monospace' }}>{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* No findings success */}
      {score.findings.length === 0 && recs.length === 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 10px', borderRadius: 8, background: 'rgba(16,185,129,0.07)', border: '1px solid rgba(16,185,129,0.2)' }}>
          <ShieldCheck size={13} color="#10b981" />
          <span style={{ fontSize: 11, color: '#6ee7b7' }}>No findings — object is healthy</span>
        </div>
      )}
    </div>
  )
}

// ─── Actions Tab ──────────────────────────────────────────────────────────────

function ActionsTab({ object }: { object: StudioObject }) {
  const runWorker = useAppStore(s => s.runWorker)
  const workerRuns = useAppStore(s => s.workerRuns)
  const workers = getWorkersForObject(object.typeId)

  const isRunning = (workerId: string) =>
    workerRuns.some(r => r.objectId === object.id && r.workerId === workerId &&
      (r.state === 'running' || r.state === 'pending' || r.state === 'awaiting_input'))

  const categoryColors: Record<string, string> = {
    quality: 'text-emerald-400', security: 'text-red-400', ops: 'text-amber-400',
    traceability: 'text-blue-400', retrieval: 'text-purple-400', platform: 'text-indigo-400',
  }
  const categoryBg: Record<string, string> = {
    quality: 'bg-emerald-900/20 border-emerald-800/30', security: 'bg-red-900/20 border-red-800/30',
    ops: 'bg-amber-900/20 border-amber-800/30', traceability: 'bg-blue-900/20 border-blue-800/30',
    retrieval: 'bg-purple-900/20 border-purple-800/30', platform: 'bg-indigo-900/20 border-indigo-800/30',
  }

  if (workers.length === 0) {
    return <div className="p-4 text-center text-zinc-500 text-sm py-12">No workers available for this object type.</div>
  }

  return (
    <div className="p-4 space-y-3">
      <p className="text-xs text-zinc-500">Available workers for <span className="text-zinc-300">{object.typeId}</span>:</p>
      {workers.map(worker => {
        const running = isRunning(worker.id)
        return (
          <div key={worker.id} className={`border rounded-lg p-3 ${categoryBg[worker.category] ?? 'bg-zinc-900 border-zinc-800'}`}>
            <div className="flex items-start justify-between gap-2 mb-1">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className={`text-[10px] font-semibold uppercase tracking-wider ${categoryColors[worker.category] ?? 'text-zinc-400'}`}>{worker.category}</span>
                  {worker.requiresAutomationGate && <span className="flex items-center gap-0.5 text-[10px] text-amber-500"><Lock size={9} />gated</span>}
                  <span className="text-[10px] text-zinc-600">• {worker.profile}</span>
                </div>
                <p className="text-xs font-semibold text-zinc-200">{worker.label}</p>
                <p className="text-[11px] text-zinc-500 mt-0.5 leading-relaxed">{worker.description}</p>
              </div>
              <button
                onClick={() => !running && runWorker(worker.id, object.id)}
                disabled={running}
                className={`shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all ${running ? 'bg-zinc-700 text-zinc-400 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm'}`}
              >
                {running ? <><Loader size={11} className="animate-spin" /> Running</> : <><Play size={11} /> {worker.actionLabel}</>}
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── History Tab ──────────────────────────────────────────────────────────────

function fmtDur(ms?: number): string {
  if (!ms) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function fmtTokens(n?: number): string {
  if (!n) return '—'
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

function HistoryTab({ object }: { object: StudioObject }) {
  const workerRuns = useAppStore(s => s.workerRuns)
  const objectRuns = [...workerRuns.filter(r => r.objectId === object.id)]
    .sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())

  if (objectRuns.length === 0) {
    return (
      <div className="p-4 text-center py-12">
        <p className="text-zinc-500 text-sm">No worker runs yet.</p>
        <p className="text-zinc-600 text-xs mt-1">Go to Actions tab to run a worker.</p>
      </div>
    )
  }

  const totalCost = objectRuns.reduce((s, r) => s + (r.costUsd ?? 0), 0)
  const totalTokensIn = objectRuns.reduce((s, r) => s + (r.tokensIn ?? 0), 0)
  const totalTokensOut = objectRuns.reduce((s, r) => s + (r.tokensOut ?? 0), 0)
  const passCount = objectRuns.filter(r => r.state === 'done').length
  const failCount = objectRuns.filter(r => r.state === 'failed').length

  // Cost per worker (aggregated)
  const costByWorker: Record<string, { label: string; cost: number; runs: number }> = {}
  objectRuns.forEach(r => {
    if (!costByWorker[r.workerId]) costByWorker[r.workerId] = { label: r.workerLabel, cost: 0, runs: 0 }
    costByWorker[r.workerId].cost += r.costUsd ?? 0
    costByWorker[r.workerId].runs++
  })
  const workerBreakdown = Object.values(costByWorker).sort((a, b) => b.cost - a.cost)
  const maxCost = workerBreakdown[0]?.cost ?? 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* ── Cost Summary ── */}
      <div style={{ padding: '12px 14px', borderBottom: '1px solid rgba(63,63,70,0.4)', background: 'rgba(9,9,11,0.4)' }}>
        <p style={{ fontSize: 10, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
          Total AI Spend
        </p>

        {/* Big number */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 10 }}>
          <span style={{ fontSize: 26, fontWeight: 800, color: '#e4e4e7', letterSpacing: '-0.02em' }}>
            ${totalCost.toFixed(2)}
          </span>
          <span style={{ fontSize: 11, color: '#71717a' }}>{objectRuns.length} runs</span>
        </div>

        {/* Stats row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 6, marginBottom: 12 }}>
          {[
            { label: 'In tokens', value: fmtTokens(totalTokensIn), color: '#818cf8' },
            { label: 'Out tokens', value: fmtTokens(totalTokensOut), color: '#a78bfa' },
            { label: 'Passed', value: String(passCount), color: '#10b981' },
            { label: 'Failed', value: String(failCount), color: failCount > 0 ? '#f87171' : '#71717a' },
          ].map(s => (
            <div key={s.label} style={{ background: 'rgba(24,24,27,0.6)', border: '1px solid rgba(63,63,70,0.4)', borderRadius: 7, padding: '6px 8px', textAlign: 'center' }}>
              <p style={{ fontSize: 14, fontWeight: 700, color: s.color }}>{s.value}</p>
              <p style={{ fontSize: 9, color: '#52525b', marginTop: 1 }}>{s.label}</p>
            </div>
          ))}
        </div>

        {/* Cost by worker breakdown */}
        {workerBreakdown.length > 0 && (
          <div>
            <p style={{ fontSize: 10, fontWeight: 600, color: '#52525b', marginBottom: 6 }}>By worker</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {workerBreakdown.map(w => (
                <div key={w.label} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 11, color: '#a1a1aa', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{w.label}</span>
                    <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                      <span style={{ fontSize: 10, color: '#71717a' }}>{w.runs}×</span>
                      <span style={{ fontSize: 11, fontWeight: 700, color: '#e4e4e7', minWidth: 36, textAlign: 'right' }}>${w.cost.toFixed(2)}</span>
                    </div>
                  </div>
                  <div style={{ height: 4, background: 'rgba(63,63,70,0.4)', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${(w.cost / maxCost) * 100}%`, background: 'linear-gradient(90deg, #4f46e5, #818cf8)', borderRadius: 2, transition: 'width 0.4s ease' }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Run list ── */}
      <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <p style={{ fontSize: 10, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Run History ({objectRuns.length})
        </p>
        {objectRuns.map(run => <RunCard key={run.id} run={run} />)}
      </div>
    </div>
  )
}

function RunCard({ run }: { run: WorkerRun }) {
  const [expanded, setExpanded] = useState(false)
  const isLive = run.state === 'running' || run.state === 'pending' || run.state === 'awaiting_input'

  const stateConfig = {
    done:           { icon: <CheckCircle size={13} />, color: '#10b981', label: 'Passed' },
    failed:         { icon: <XCircle size={13} />, color: '#f87171', label: 'Failed' },
    running:        { icon: <Loader size={13} style={{ animation: 'spin 1s linear infinite' }} />, color: '#6366f1', label: 'Running' },
    pending:        { icon: <Clock size={13} />, color: '#71717a', label: 'Pending' },
    awaiting_input: { icon: <AlertCircle size={13} />, color: '#f59e0b', label: 'Waiting' },
    paused:         { icon: <AlertCircle size={13} />, color: '#f59e0b', label: 'Paused' },
    aborted:        { icon: <XCircle size={13} />, color: '#71717a', label: 'Aborted' },
    escalated:      { icon: <AlertCircle size={13} />, color: '#f97316', label: 'Escalated' },
  }[run.state] ?? { icon: <Clock size={13} />, color: '#71717a', label: run.state }

  const ts = new Date(run.startedAt)
  const dateStr = ts.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const timeStr = ts.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })

  return (
    <div style={{
      background: 'rgba(24,24,27,0.5)', border: `1px solid ${run.state === 'failed' ? 'rgba(239,68,68,0.2)' : run.state === 'done' ? 'rgba(16,185,129,0.12)' : 'rgba(63,63,70,0.4)'}`,
      borderLeft: `3px solid ${stateConfig.color}`, borderRadius: 8, overflow: 'hidden',
    }}>
      {/* Header row */}
      <button
        onClick={() => setExpanded(e => !e)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}
      >
        <span style={{ color: stateConfig.color, flexShrink: 0 }}>{stateConfig.icon}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: '#d4d4d8', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {run.workerLabel}
        </span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
          {run.costUsd !== undefined && run.costUsd > 0 && (
            <span style={{ fontSize: 11, fontWeight: 700, color: '#a1a1aa' }}>${run.costUsd.toFixed(2)}</span>
          )}
          <span style={{ fontSize: 10, color: '#52525b' }}>{dateStr} {timeStr}</span>
        </div>
      </button>

      {/* Live progress */}
      {isLive && (
        <div style={{ padding: '0 10px 8px' }}>
          <div style={{ height: 3, background: 'rgba(63,63,70,0.5)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${run.progress}%`, background: '#6366f1', borderRadius: 2, transition: 'width 0.3s ease' }} />
          </div>
          <span style={{ fontSize: 10, color: '#71717a', marginTop: 2, display: 'block' }}>{Math.round(run.progress)}% — {run.workerLabel}</span>
        </div>
      )}

      {/* Expanded details */}
      {expanded && !isLive && (
        <div style={{ padding: '0 10px 10px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {/* Metrics */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {[
              { label: 'Duration', value: fmtDur(run.durationMs) },
              { label: 'In', value: fmtTokens(run.tokensIn) },
              { label: 'Out', value: fmtTokens(run.tokensOut) },
              { label: 'Model', value: run.model ?? '—' },
            ].map(m => (
              <span key={m.label} style={{ fontSize: 10, padding: '2px 7px', borderRadius: 20, background: 'rgba(63,63,70,0.3)', border: '1px solid rgba(63,63,70,0.4)', color: '#a1a1aa' }}>
                <span style={{ color: '#71717a' }}>{m.label}: </span>{m.value}
              </span>
            ))}
          </div>
          {/* Output / Error */}
          {run.output && (
            <p style={{ fontSize: 11, color: '#a1a1aa', background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.15)', borderRadius: 6, padding: '7px 9px', lineHeight: 1.5, margin: 0 }}>
              {run.output}
            </p>
          )}
          {run.error && (
            <p style={{ fontSize: 11, color: '#fca5a5', background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 6, padding: '7px 9px', lineHeight: 1.5, margin: 0 }}>
              ✗ {run.error}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Links Tab ────────────────────────────────────────────────────────────────

function LinksTab({ object }: { object: StudioObject }) {
  const allObjects = MOCK_OBJECTS
  const selectObject = useAppStore(s => s.selectObject)
  const linkKindColors: Record<string, string> = {
    derived_from: 'text-indigo-400 border-indigo-800/50 bg-indigo-900/20',
    decomposes_into: 'text-cyan-400 border-cyan-800/50 bg-cyan-900/20',
    implements: 'text-emerald-400 border-emerald-800/50 bg-emerald-900/20',
    validates: 'text-amber-400 border-amber-800/50 bg-amber-900/20',
    references: 'text-purple-400 border-purple-800/50 bg-purple-900/20',
    triggers: 'text-pink-400 border-pink-800/50 bg-pink-900/20',
    blocks: 'text-red-400 border-red-800/50 bg-red-900/20',
    related_to: 'text-zinc-400 border-zinc-700 bg-zinc-900',
  }
  const outgoing = object.links.map(link => ({ ...link, target: allObjects.find(o => o.id === link.targetId), direction: 'out' as const }))
  const incoming = allObjects.flatMap(obj => obj.links.filter(l => l.targetId === object.id).map(l => ({ ...l, targetId: obj.id, target: obj, direction: 'in' as const })))
  return (
    <div className="p-4 space-y-4">
      {outgoing.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Outgoing ({outgoing.length})</h3>
          <div className="space-y-1.5">
            {outgoing.map((link, i) => (
              <button key={i} onClick={() => link.target && selectObject(link.target.id)} className="w-full flex items-center justify-between p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-600 transition-colors group text-left">
                <div className="min-w-0 flex-1"><p className="text-xs text-zinc-200 truncate">{link.target?.title ?? link.targetId}</p><p className="text-[10px] text-zinc-500">{link.target?.typeId ?? '?'}</p></div>
                <div className="flex items-center gap-2 shrink-0 ml-2">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border ${linkKindColors[link.kind] ?? 'text-zinc-400 border-zinc-700 bg-zinc-900'}`}>{link.kind.replace(/_/g, ' ')}</span>
                  <ExternalLink size={11} className="text-zinc-600 group-hover:text-zinc-400" />
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
      {incoming.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Incoming ({incoming.length})</h3>
          <div className="space-y-1.5">
            {incoming.map((link, i) => (
              <button key={i} onClick={() => selectObject(link.target.id)} className="w-full flex items-center justify-between p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-600 transition-colors group text-left">
                <div className="min-w-0 flex-1"><p className="text-xs text-zinc-200 truncate">{link.target.title}</p><p className="text-[10px] text-zinc-500">{link.target.typeId}</p></div>
                <div className="flex items-center gap-2 shrink-0 ml-2">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border ${linkKindColors[link.kind] ?? 'text-zinc-400 border-zinc-700 bg-zinc-900'}`}>{link.kind.replace(/_/g, ' ')}</span>
                  <ExternalLink size={11} className="text-zinc-600 group-hover:text-zinc-400" />
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
      {outgoing.length === 0 && incoming.length === 0 && <div className="text-center py-12"><p className="text-zinc-500 text-sm">No links defined.</p></div>}
    </div>
  )
}

function PropertyRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-zinc-800/50">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className={`text-xs text-zinc-300 ${mono ? 'font-mono text-[11px]' : ''}`}>{value}</span>
    </div>
  )
}
