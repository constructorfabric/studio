import { useState, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X, FileEdit, Play, ChevronDown, AlertTriangle, Link2, Activity, CheckCircle2, XCircle, Clock, AlertCircle, ArrowRight } from 'lucide-react'
import Editor from '@monaco-editor/react'
import { useAppStore, selectObject } from '../../store/app-store'
import { ObjectDetail } from '../objects/ObjectDetail'
import { MOCK_RECOMMENDATIONS } from '../../data/mock-data'
import { FILE_CONTENTS } from '../../data/file-mock-data'
import type { StudioObject, WorkerDef } from '../../types/domain'
import { getWorkersForObject } from '../../data/mock-data'

// ─── Object ID → file content mapping ────────────────────────────────────────

const OBJECT_TO_FILE: Record<string, string> = {
  'prd-001':    'file-prd',
  'design-001': 'file-design',
  'adr-001':    'file-adr-001',
  'adr-002':    'file-adr-002',
  'fspec-001':  'file-feat-stripe',
  'fspec-002':  'file-feat-invoice',
  'pr-001':     'file-webhook-handler',
}

const OBJECT_FILE_LANG: Record<string, string> = {
  'file-prd': 'markdown', 'file-design': 'markdown',
  'file-adr-001': 'markdown', 'file-adr-002': 'markdown',
  'file-feat-stripe': 'markdown', 'file-feat-invoice': 'markdown',
  'file-webhook-handler': 'typescript',
}

// ─── State machine transitions ────────────────────────────────────────────────

const STATE_TRANSITIONS: Record<string, string[]> = {
  draft:       ['in_progress', 'approved'],
  in_progress: ['review', 'done', 'failed'],
  review:      ['approved', 'in_progress', 'failed'],
  planned:     ['in_progress'],
  approved:    ['in_progress'],
  open:        ['in_progress', 'closed'],
  running:     ['done', 'failed'],
  failed:      ['in_progress'],
  done:        [],
  merged:      [],
  closed:      [],
  stale:       ['in_progress'],
}

const STATE_COLOR: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  approved:    { bg: '#052e16', border: '#166534', text: '#4ade80', dot: '#22c55e' },
  done:        { bg: '#052e16', border: '#166534', text: '#4ade80', dot: '#22c55e' },
  merged:      { bg: '#052e16', border: '#166534', text: '#4ade80', dot: '#22c55e' },
  in_progress: { bg: '#1c1700', border: '#713f12', text: '#fbbf24', dot: '#f59e0b' },
  running:     { bg: '#1c1700', border: '#713f12', text: '#fbbf24', dot: '#f59e0b' },
  review:      { bg: '#1c1700', border: '#713f12', text: '#fbbf24', dot: '#f59e0b' },
  failed:      { bg: '#1c0a0a', border: '#7f1d1d', text: '#f87171', dot: '#ef4444' },
  open:        { bg: '#1c0a0a', border: '#7f1d1d', text: '#f87171', dot: '#ef4444' },
  draft:       { bg: '#18181b', border: '#3f3f46', text: '#a1a1aa', dot: '#71717a' },
  planned:     { bg: '#0f172a', border: '#1e3a5f', text: '#60a5fa', dot: '#3b82f6' },
  stale:       { bg: '#1c1700', border: '#713f12', text: '#fbbf24', dot: '#f59e0b' },
}

// ─── Content viewer modal ─────────────────────────────────────────────────────

function ContentModal({ object, onClose }: { object: StudioObject; onClose: () => void }) {
  const fileId = OBJECT_TO_FILE[object.id]
  const lang = (fileId && OBJECT_FILE_LANG[fileId]) ?? 'markdown'
  const storeContent = useAppStore(s => fileId ? s.fileContents[fileId] : undefined)
  const fileContent = storeContent ?? (fileId ? FILE_CONTENTS[fileId] : undefined)
  const updateFileContent = useAppStore(s => s.updateFileContent)
  const openFile = useAppStore(s => s.openFile)
  const setActiveView = useAppStore(s => s.setActiveView)

  const [localContent, setLocalContent] = useState(fileContent ?? generatePlaceholder(object))
  const [modified, setModified] = useState(false)

  const handleChange = (val: string | undefined) => {
    const v = val ?? ''
    setLocalContent(v)
    setModified(true)
  }

  const handleSave = () => {
    if (fileId) updateFileContent(fileId, localContent)
    setModified(false)
  }

  const handleOpenInFiles = () => {
    if (fileId) {
      openFile(fileId)
      setActiveView('files')
    }
    onClose()
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(6px)',
        zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 12 }}
        transition={{ duration: 0.18 }}
        style={{
          width: '80vw', maxWidth: 1100, height: '80vh',
          background: '#0c0c0e', border: '1px solid rgba(63,63,70,0.6)',
          borderRadius: 14, overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
          boxShadow: '0 32px 80px rgba(0,0,0,0.7)',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '10px 14px', borderBottom: '1px solid rgba(63,63,70,0.5)',
          display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
          background: '#0a0a0c',
        }}>
          <FileEdit size={14} color="#818cf8" />
          <span style={{ fontSize: 13, fontWeight: 600, color: '#e4e4e7', flex: 1 }}>{object.title}</span>
          <span style={{ fontSize: 11, color: '#52525b', fontFamily: 'monospace' }}>{lang}</span>
          {modified && (
            <span style={{ fontSize: 10, color: '#f59e0b', fontWeight: 600 }}>● modified</span>
          )}
          {fileId && (
            <button onClick={handleOpenInFiles} style={{
              fontSize: 11, padding: '3px 10px', borderRadius: 6,
              border: '1px solid rgba(63,63,70,0.6)', background: 'transparent',
              color: '#a1a1aa', cursor: 'pointer',
            }}>Open in Files</button>
          )}
          {modified && (
            <button onClick={handleSave} style={{
              fontSize: 11, padding: '3px 10px', borderRadius: 6, border: 'none',
              background: '#4f46e5', color: '#fff', cursor: 'pointer', fontWeight: 600,
            }}>Save</button>
          )}
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#71717a', padding: 4 }}>
            <X size={15} />
          </button>
        </div>

        {/* Editor */}
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <Editor
            height="100%"
            language={lang}
            value={localContent}
            theme="vs-dark"
            onChange={handleChange}
            options={{
              fontSize: 13,
              lineHeight: 20,
              fontFamily: '"JetBrains Mono", "Fira Code", monospace',
              minimap: { enabled: true },
              scrollBeyondLastLine: false,
              wordWrap: 'on',
              padding: { top: 12, bottom: 12 },
              renderLineHighlight: 'line',
              cursorBlinking: 'smooth',
              smoothScrolling: true,
            }}
          />
        </div>
      </motion.div>
    </motion.div>
  )
}

function generatePlaceholder(object: StudioObject): string {
  const header = `# ${object.title}\n\n`
  const meta = `**Type:** ${object.typeId}  \n**State:** ${object.state}  \n**ID:** ${object.id}\n\n`
  const desc = object.description ? `## Description\n\n${object.description}\n\n` : ''
  return header + meta + desc + `## Content\n\n_This artifact has no linked file. Start editing here._\n`
}

// ─── State chip with transition picker ───────────────────────────────────────

function StateChip({ object }: { object: StudioObject }) {
  const [open, setOpen] = useState(false)
  const sc = STATE_COLOR[object.state] ?? STATE_COLOR.draft
  const transitions = STATE_TRANSITIONS[object.state] ?? []

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => transitions.length > 0 && setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 5,
          padding: '3px 8px', borderRadius: 20,
          background: sc.bg, border: `1px solid ${sc.border}`,
          color: sc.text, fontSize: 11, fontWeight: 600, cursor: transitions.length > 0 ? 'pointer' : 'default',
          transition: 'all 0.15s',
        }}
        title={transitions.length > 0 ? 'Click to transition state' : undefined}
      >
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: sc.dot, display: 'inline-block', flexShrink: 0 }} />
        {object.state.replace('_', ' ')}
        {transitions.length > 0 && <ChevronDown size={10} />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            transition={{ duration: 0.1 }}
            style={{
              position: 'absolute', top: '110%', left: 0, zIndex: 50,
              background: '#18181b', border: '1px solid rgba(63,63,70,0.6)',
              borderRadius: 8, padding: '4px', minWidth: 140,
              boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            }}
          >
            <p style={{ fontSize: 9, color: '#52525b', padding: '3px 6px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Transition to
            </p>
            {transitions.map(t => {
              const tc = STATE_COLOR[t] ?? STATE_COLOR.draft
              return (
                <button
                  key={t}
                  onClick={() => setOpen(false)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6, width: '100%',
                    padding: '5px 8px', borderRadius: 5, border: 'none',
                    background: 'transparent', cursor: 'pointer', textAlign: 'left',
                    color: tc.text, fontSize: 11, fontWeight: 500,
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(63,63,70,0.3)' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                >
                  <ArrowRight size={10} />
                  {t.replace('_', ' ')}
                </button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Validation chip ──────────────────────────────────────────────────────────

function ValidationChip({ status, onClick }: { status: string; onClick: () => void }) {
  if (status === 'none') return null
  const configs: Record<string, { icon: React.ReactNode; color: string; bg: string; border: string }> = {
    pass:    { icon: <CheckCircle2 size={10} />, color: '#4ade80', bg: '#052e16', border: '#166534' },
    fail:    { icon: <XCircle size={10} />,      color: '#f87171', bg: '#1c0a0a', border: '#7f1d1d' },
    pending: { icon: <Clock size={10} />,         color: '#a1a1aa', bg: '#18181b', border: '#3f3f46' },
    skipped: { icon: <AlertCircle size={10} />,   color: '#71717a', bg: '#18181b', border: '#3f3f46' },
  }
  const c = configs[status] ?? configs.pending
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 4,
        padding: '3px 8px', borderRadius: 20,
        background: c.bg, border: `1px solid ${c.border}`,
        color: c.color, fontSize: 11, fontWeight: 500, cursor: 'pointer',
      }}
      title="Click to view validation history"
    >
      {c.icon} {status}
    </button>
  )
}

// ─── Recommendations chip ─────────────────────────────────────────────────────

function RecsChip({ objectId, onClick }: { objectId: string; onClick: () => void }) {
  const recs = MOCK_RECOMMENDATIONS.filter(r =>
    r.relatedObjectIds.includes(objectId) && r.state === 'pending'
  )
  if (recs.length === 0) return null
  const hasCritical = recs.some(r => r.severity === 'critical')
  const hasWarning = recs.some(r => r.severity === 'warning')
  const color = hasCritical ? '#f87171' : hasWarning ? '#fbbf24' : '#60a5fa'
  const bg = hasCritical ? '#1c0a0a' : hasWarning ? '#1c1700' : '#0f172a'
  const border = hasCritical ? '#7f1d1d' : hasWarning ? '#713f12' : '#1e3a5f'

  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 4,
        padding: '3px 8px', borderRadius: 20,
        background: bg, border: `1px solid ${border}`,
        color, fontSize: 11, fontWeight: 600, cursor: 'pointer',
        animation: hasCritical ? 'pulse 2s ease-in-out infinite' : 'none',
      }}
      title="Click to view recommendations"
    >
      <AlertTriangle size={10} /> {recs.length} rec{recs.length !== 1 ? 's' : ''}
    </button>
  )
}

// ─── Inline Recommendations panel ────────────────────────────────────────────

function InlineRecs({ objectId }: { objectId: string }) {
  const recs = MOCK_RECOMMENDATIONS.filter(r =>
    r.relatedObjectIds.includes(objectId) && r.state === 'pending'
  )
  const severityColors: Record<string, string> = {
    critical: '#f87171', warning: '#fbbf24', info: '#60a5fa',
  }
  return (
    <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(63,63,70,0.4)' }}>
      <p style={{ fontSize: 10, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
        Recommendations
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {recs.map(rec => (
          <div key={rec.id} style={{
            padding: '6px 8px', borderRadius: 6,
            background: 'rgba(24,24,27,0.7)',
            border: `1px solid ${severityColors[rec.severity] ?? '#3f3f46'}30`,
            borderLeft: `3px solid ${severityColors[rec.severity] ?? '#3f3f46'}`,
          }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
              <AlertTriangle size={10} color={severityColors[rec.severity]} style={{ marginTop: 1, flexShrink: 0 }} />
              <div>
                <p style={{ fontSize: 11, fontWeight: 600, color: '#d4d4d8', lineHeight: 1.3, marginBottom: 2 }}>{rec.title}</p>
                <p style={{ fontSize: 10, color: '#71717a', lineHeight: 1.4 }}>{rec.description}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Links chip ───────────────────────────────────────────────────────────────

function LinksChip({ count, onClick }: { count: number; onClick: () => void }) {
  if (count === 0) return null
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 4,
        padding: '3px 8px', borderRadius: 20,
        background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.3)',
        color: '#818cf8', fontSize: 11, fontWeight: 500, cursor: 'pointer',
      }}
      title="Click to view links"
    >
      <Link2 size={10} /> {count} link{count !== 1 ? 's' : ''}
    </button>
  )
}

// ─── Runs chip ────────────────────────────────────────────────────────────────

function RunsChip({ count, onClick }: { count: number; onClick: () => void }) {
  if (count === 0) return null
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 4,
        padding: '3px 8px', borderRadius: 20,
        background: 'rgba(24,24,27,0.8)', border: '1px solid rgba(63,63,70,0.5)',
        color: '#a1a1aa', fontSize: 11, fontWeight: 500, cursor: 'pointer',
      }}
      title="Click to view run history"
    >
      <Activity size={10} /> {count} run{count !== 1 ? 's' : ''}
    </button>
  )
}

// ─── Quick actions bar ────────────────────────────────────────────────────────

function QuickActions({ object }: { object: StudioObject }) {
  const runWorker = useAppStore(s => s.runWorker)
  const workerRuns = useAppStore(s => s.workerRuns)
  const [open, setOpen] = useState(false)
  const workers = getWorkersForObject(object.typeId)
  const topWorkers = workers.slice(0, 3)
  const moreWorkers = workers.slice(3)

  const isRunning = (workerId: string) =>
    workerRuns.some(r => r.objectId === object.id && r.workerId === workerId &&
      ['running', 'pending', 'awaiting_input'].includes(r.state))

  if (workers.length === 0) return null

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
      {topWorkers.map(w => {
        const running = isRunning(w.id)
        return (
          <button
            key={w.id}
            onClick={() => !running && runWorker(w.id, object.id)}
            disabled={running}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '3px 9px', borderRadius: 6, border: 'none',
              background: running ? 'rgba(99,102,241,0.3)' : 'rgba(99,102,241,0.15)',
              color: running ? '#818cf8' : '#a5b4fc',
              fontSize: 11, fontWeight: 500, cursor: running ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s',
            } as React.CSSProperties}
            onMouseEnter={e => { if (!running) (e.currentTarget as HTMLElement).style.background = 'rgba(99,102,241,0.25)' }}
            onMouseLeave={e => { if (!running) (e.currentTarget as HTMLElement).style.background = 'rgba(99,102,241,0.15)' }}
          >
            <Play size={9} />
            {w.actionLabel}
          </button>
        )
      })}
      {moreWorkers.length > 0 && (
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setOpen(o => !o)}
            style={{
              display: 'flex', alignItems: 'center', gap: 3,
              padding: '3px 8px', borderRadius: 6,
              background: 'rgba(63,63,70,0.3)', border: '1px solid rgba(63,63,70,0.5)',
              color: '#71717a', fontSize: 11, cursor: 'pointer',
            }}
          >
            +{moreWorkers.length} <ChevronDown size={9} />
          </button>
          <AnimatePresence>
            {open && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                style={{
                  position: 'absolute', bottom: '110%', right: 0, zIndex: 50,
                  background: '#18181b', border: '1px solid rgba(63,63,70,0.6)',
                  borderRadius: 8, padding: '4px', minWidth: 160,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                }}
              >
                {moreWorkers.map(w => (
                  <button
                    key={w.id}
                    onClick={() => { runWorker(w.id, object.id); setOpen(false) }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 6, width: '100%',
                      padding: '5px 8px', borderRadius: 5, border: 'none',
                      background: 'transparent', cursor: 'pointer',
                      color: '#a1a1aa', fontSize: 11, textAlign: 'left',
                    }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(63,63,70,0.3)' }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                  >
                    <Play size={9} /> {w.actionLabel}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}

// ─── Type badge ───────────────────────────────────────────────────────────────

function TypeBadge({ typeId }: { typeId: string }) {
  const configs: Record<string, { label: string; className: string }> = {
    prd:           { label: 'PRD',           className: 'bg-purple-900/50 text-purple-300 border-purple-700/50' },
    adr:           { label: 'ADR',           className: 'bg-violet-900/50 text-violet-300 border-violet-700/50' },
    design:        { label: 'DESIGN',        className: 'bg-blue-900/50 text-blue-300 border-blue-700/50' },
    decomposition: { label: 'DECOMP',        className: 'bg-indigo-900/50 text-indigo-300 border-indigo-700/50' },
    feature_spec:  { label: 'FEATURE SPEC',  className: 'bg-teal-900/50 text-teal-300 border-teal-700/50' },
    task:          { label: 'TASK',          className: 'bg-cyan-900/50 text-cyan-300 border-cyan-700/50' },
    pull_request:  { label: 'PULL REQUEST',  className: 'bg-orange-900/50 text-orange-300 border-orange-700/50' },
    build:         { label: 'BUILD',         className: 'bg-lime-900/50 text-lime-300 border-lime-700/50' },
    incident:      { label: 'INCIDENT',      className: 'bg-red-900/50 text-red-300 border-red-700/50' },
  }
  const config = configs[typeId] ?? { label: typeId.toUpperCase(), className: 'bg-zinc-800 text-zinc-300 border-zinc-700' }
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border tracking-wider ${config.className}`}>
      {config.label}
    </span>
  )
}

export function StateBadge({ state }: { state: string }) {
  const sc = STATE_COLOR[state] ?? STATE_COLOR.draft
  return (
    <span style={{
      fontSize: 10, fontWeight: 500, padding: '2px 8px', borderRadius: 20,
      background: sc.bg, border: `1px solid ${sc.border}`, color: sc.text,
    }}>
      {state.replace('_', ' ')}
    </span>
  )
}

export function ValidationBadge({ status }: { status: string }) {
  if (status === 'none') return null
  const configs: Record<string, string> = {
    pass:    'bg-emerald-900/30 text-emerald-400 border-emerald-700/40',
    fail:    'bg-red-900/30 text-red-400 border-red-700/40',
    pending: 'bg-zinc-800 text-zinc-400 border-zinc-700',
    skipped: 'bg-zinc-800 text-zinc-500 border-zinc-700',
  }
  const icons: Record<string, string> = { pass: '✓', fail: '✗', pending: '○', skipped: '–' }
  return (
    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${configs[status] ?? 'bg-zinc-800 text-zinc-400 border-zinc-700'}`}>
      {icons[status]} {status}
    </span>
  )
}

// ─── Main RightPanel ──────────────────────────────────────────────────────────

const TABS = ['Overview', 'Actions', 'History', 'Links', 'Score']

export function RightPanel() {
  const selectedObject = useAppStore(selectObject)
  const selectObjectFn = useAppStore(s => s.selectObject)
  const activeTab = useAppStore(s => s.activeTab)
  const setActiveTab = useAppStore(s => s.setActiveTab)
  const workerRuns = useAppStore(s => s.workerRuns)

  const [showContent, setShowContent] = useState(false)
  const [showRecs, setShowRecs] = useState(false)

  if (!selectedObject) return null

  const objectRuns = workerRuns.filter(r => r.objectId === selectedObject.id)
  const hasLinkedFile = !!OBJECT_TO_FILE[selectedObject.id]

  return (
    <>
      <AnimatePresence>
        {selectedObject && (
          <motion.aside
            key="right-panel"
            initial={{ x: 380, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 380, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="w-96 border-l border-zinc-800 bg-zinc-950 flex flex-col shrink-0 overflow-hidden"
            style={{ minWidth: '24rem', maxWidth: '24rem' }}
          >
            {/* ── Header ── */}
            <div style={{ padding: '12px 14px', borderBottom: '1px solid rgba(63,63,70,0.5)', flexShrink: 0 }}>
              {/* Title row */}
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <TypeBadge typeId={selectedObject.typeId} />
                  </div>
                  <h2 style={{ fontSize: 13, fontWeight: 700, color: '#e4e4e7', lineHeight: 1.3, marginBottom: 2 }}>
                    {selectedObject.title}
                  </h2>
                  <p style={{ fontSize: 10, color: '#52525b', fontFamily: 'monospace' }}>{selectedObject.id}</p>
                </div>
                <button
                  onClick={() => selectObjectFn(null)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#71717a', padding: 4, flexShrink: 0 }}
                >
                  <X size={14} />
                </button>
              </div>

              {/* ── Signal chips row ── */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap', marginBottom: 10 }}>
                <StateChip object={selectedObject} />
                <ValidationChip
                  status={selectedObject.validationStatus}
                  onClick={() => setActiveTab('history')}
                />
                {selectedObject.stalenessScore > 20 && (
                  <span style={{
                    fontSize: 11, padding: '3px 8px', borderRadius: 20,
                    background: '#1c1700', border: '1px solid #713f12', color: '#fbbf24', fontWeight: 500,
                  }}>
                    {selectedObject.stalenessScore}% stale
                  </span>
                )}
                <RecsChip
                  objectId={selectedObject.id}
                  onClick={() => setShowRecs(r => !r)}
                />
                <LinksChip
                  count={selectedObject.links.length}
                  onClick={() => setActiveTab('links')}
                />
                <RunsChip
                  count={objectRuns.length}
                  onClick={() => setActiveTab('history')}
                />
              </div>

              {/* ── View/Edit + description row ── */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                <button
                  onClick={() => setShowContent(true)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 5,
                    padding: '4px 11px', borderRadius: 7, border: '1px solid rgba(63,63,70,0.6)',
                    background: 'rgba(24,24,27,0.8)', color: hasLinkedFile ? '#a5b4fc' : '#a1a1aa',
                    fontSize: 11, fontWeight: 600, cursor: 'pointer',
                    borderColor: hasLinkedFile ? 'rgba(99,102,241,0.4)' : 'rgba(63,63,70,0.6)',
                  }}
                >
                  <FileEdit size={12} /> View / Edit
                </button>
              </div>
            </div>

            {/* ── Inline recs ── */}
            <AnimatePresence>
              {showRecs && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  style={{ overflow: 'hidden', flexShrink: 0 }}
                >
                  <InlineRecs objectId={selectedObject.id} />
                </motion.div>
              )}
            </AnimatePresence>

            {/* ── Tabs ── */}
            <div style={{ display: 'flex', borderBottom: '1px solid rgba(63,63,70,0.5)', background: '#09090b', flexShrink: 0 }}>
              {TABS.map(tab => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab.toLowerCase())}
                  style={{
                    flex: 1, padding: '8px 0', fontSize: 11, fontWeight: 500,
                    border: 'none', background: 'transparent', cursor: 'pointer',
                    color: activeTab === tab.toLowerCase() ? '#818cf8' : '#71717a',
                    borderBottom: activeTab === tab.toLowerCase() ? '2px solid #6366f1' : '2px solid transparent',
                    transition: 'all 0.15s',
                    position: 'relative',
                  }}
                >
                  {tab}
                  {tab === 'Actions' && getWorkersForObject(selectedObject.typeId).length > 0 && (
                    <span style={{
                      fontSize: 9, fontWeight: 700, marginLeft: 3,
                      color: activeTab === 'actions' ? '#818cf8' : '#52525b',
                    }}>
                      {getWorkersForObject(selectedObject.typeId).length}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* ── Tab content ── */}
            <div style={{ flex: 1, overflowY: 'auto' }}>
              <ObjectDetail object={selectedObject} activeTab={activeTab} />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Content modal */}
      <AnimatePresence>
        {showContent && selectedObject && (
          <ContentModal object={selectedObject} onClose={() => setShowContent(false)} />
        )}
      </AnimatePresence>
    </>
  )
}
