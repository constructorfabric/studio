import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CheckSquare, MapPin, MessageSquare, Search, Tag, TestTube2, Wand2, Wrench, CheckCircle2, Loader2, X } from 'lucide-react'
import { useAppStore } from '../../store/app-store'

// ─── Action → Worker mapping ──────────────────────────────────────────────────

const ACTION_TO_WORKER: Record<string, string> = {
  improve:       'create_prd_worker',
  analyze:       'gap_analysis_validator',
  'create-task': 'decompose_feature_worker',
  fix:           'implement_code_worker',
  test:          'implement_code_worker',
  check:         'gap_analysis_validator',
  optimize:      'implement_code_worker',
}

const EXPLAIN_TEXTS: Record<string, string> = {
  improve:  'Running AI improvement on selected text — will generate a refined version with clearer language and better structure.',
  analyze:  'Analyzing selected section for gaps — checking requirement coverage, missing edge cases, and traceability links.',
  'create-task': 'Decomposing selected scope into implementation tasks — each task will get a unique ID and Definition of Done.',
  fix:      'Analyzing selected code for bugs, style issues, and design violations — will generate a corrected version.',
  marker:   'Inserting a @cpt- traceability marker referencing the nearest feature spec flow ID.',
  'add-req': 'Assigning a unique requirement ID (R-XXX) to selected text and registering it in the object graph.',
  test:     'Generating unit tests for selected code based on the linked feature spec test scenarios.',
  explain:  'Explaining selected code in plain language — purpose, side effects, dependencies, and potential issues.',
  check:    'Running migration safety analysis — checking for missing rollbacks, lock escalations, and performance risks.',
  optimize: 'Analyzing query for performance issues — missing indices, N+1 patterns, and lock contention.',
}

// ─── Actions per language ─────────────────────────────────────────────────────

const ACTIONS_BY_LANGUAGE = {
  markdown: [
    { id: 'improve',       icon: Wand2,       label: 'Improve',      color: '#a78bfa', isWorker: true },
    { id: 'analyze',       icon: Search,      label: 'Analyze',      color: '#60a5fa', isWorker: true },
    { id: 'add-req',       icon: Tag,         label: 'Add ID',       color: '#34d399', isWorker: false },
    { id: 'create-task',   icon: CheckSquare, label: 'Task',         color: '#fb923c', isWorker: true },
  ],
  typescript: [
    { id: 'fix',           icon: Wrench,      label: 'Fix',          color: '#f87171', isWorker: true },
    { id: 'marker',        icon: MapPin,      label: 'Marker',       color: '#60a5fa', isWorker: false },
    { id: 'test',          icon: TestTube2,   label: 'Gen Test',     color: '#34d399', isWorker: true },
    { id: 'explain',       icon: MessageSquare, label: 'Explain',    color: '#a78bfa', isWorker: false },
  ],
  sql: [
    { id: 'check',         icon: Search,      label: 'Check',        color: '#60a5fa', isWorker: true },
    { id: 'optimize',      icon: Wand2,       label: 'Optimize',     color: '#fb923c', isWorker: true },
  ],
}

type ActionState = 'idle' | 'running' | 'done'

// ─── Marker IDs for autocomplete ─────────────────────────────────────────────

const MARKER_IDS = [
  'obj-fspec-stripe-flow-001', 'obj-fspec-stripe-flow-002',
  'obj-fspec-invoice-flow-001', 'obj-prd-r-001', 'obj-prd-r-002',
]

// ─── Result overlay shown after explain/non-worker actions ───────────────────

function ResultOverlay({ text, onClose }: { text: string; onClose: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -6, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6 }}
      style={{
        position: 'fixed',
        top: 'auto',
        left: '50%',
        bottom: 80,
        transform: 'translateX(-50%)',
        zIndex: 110,
        background: '#18181b',
        border: '1px solid rgba(99,102,241,0.4)',
        borderRadius: 10,
        padding: '12px 14px',
        maxWidth: 420,
        boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
        backdropFilter: 'blur(8px)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <div style={{ flex: 1 }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: '#818cf8', marginBottom: 4 }}>AI Action</p>
          <p style={{ fontSize: 12, color: '#a1a1aa', lineHeight: 1.5 }}>{text}</p>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#52525b', padding: 2 }}>
          <X size={13} />
        </button>
      </div>
    </motion.div>
  )
}

// ─── Marker picker ────────────────────────────────────────────────────────────

function MarkerPicker({ onPick, onClose }: { onPick: (id: string) => void; onClose: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -4, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0 }}
      style={{
        position: 'fixed',
        bottom: 80,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 110,
        background: '#18181b',
        border: '1px solid rgba(99,102,241,0.4)',
        borderRadius: 10,
        padding: 8,
        minWidth: 300,
        boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6, padding: '0 4px' }}>
        <p style={{ fontSize: 11, fontWeight: 600, color: '#818cf8' }}>Insert traceability marker</p>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#52525b' }}>
          <X size={12} />
        </button>
      </div>
      {MARKER_IDS.map(id => (
        <button
          key={id}
          onClick={() => onPick(id)}
          style={{
            display: 'block', width: '100%', textAlign: 'left',
            padding: '5px 8px', borderRadius: 5, border: 'none',
            background: 'transparent', cursor: 'pointer',
            fontSize: 11, fontFamily: 'monospace', color: '#60a5fa',
            transition: 'background 0.1s',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(99,102,241,0.15)' }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
        >
          // @cpt-{id}
        </button>
      ))}
    </motion.div>
  )
}

// ─── ReqID picker ─────────────────────────────────────────────────────────────

const REQ_IDS = ['R-001', 'R-002', 'R-003', 'R-004', 'R-005', 'R-006', 'R-007', 'R-008']

function ReqIdPicker({ onPick, onClose }: { onPick: (id: string) => void; onClose: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      style={{
        position: 'fixed',
        bottom: 80,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 110,
        background: '#18181b',
        border: '1px solid rgba(52,211,153,0.4)',
        borderRadius: 10,
        padding: 8,
        minWidth: 220,
        boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6, padding: '0 4px' }}>
        <p style={{ fontSize: 11, fontWeight: 600, color: '#34d399' }}>Add requirement ID</p>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#52525b' }}>
          <X size={12} />
        </button>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, padding: '0 4px' }}>
        {REQ_IDS.map(id => (
          <button
            key={id}
            onClick={() => onPick(id)}
            style={{
              padding: '3px 10px', borderRadius: 20,
              border: '1px solid rgba(52,211,153,0.3)',
              background: 'rgba(52,211,153,0.08)',
              color: '#34d399', fontSize: 11, fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {id}
          </button>
        ))}
      </div>
    </motion.div>
  )
}

// ─── Main LineActionBar ───────────────────────────────────────────────────────

export function LineActionBar() {
  const lineAction = useAppStore(s => s.lineAction)
  const setLineAction = useAppStore(s => s.setLineAction)
  const runWorkerOnFile = useAppStore(s => s.runWorkerOnFile)
  const openFileId = useAppStore(s => s.openFileId)
  const updateFileContent = useAppStore(s => s.updateFileContent)
  const fileContents = useAppStore(s => s.fileContents)

  const [actionStates, setActionStates] = useState<Record<string, ActionState>>({})
  const [overlay, setOverlay] = useState<{ kind: 'result' | 'marker' | 'reqid'; text?: string } | null>(null)

  if (!lineAction.visible) return null

  const lang = lineAction.language as keyof typeof ACTIONS_BY_LANGUAGE
  const actions = ACTIONS_BY_LANGUAGE[lang] ?? ACTIONS_BY_LANGUAGE.typescript

  const handleAction = (action: (typeof actions)[0]) => {
    if (action.isWorker) {
      // Run worker action
      const workerId = ACTION_TO_WORKER[action.id]
      if (workerId && openFileId) {
        setActionStates(s => ({ ...s, [action.id]: 'running' }))
        runWorkerOnFile(workerId, openFileId)
        setTimeout(() => {
          setActionStates(s => ({ ...s, [action.id]: 'done' }))
          setTimeout(() => {
            setActionStates(s => ({ ...s, [action.id]: 'idle' }))
            setLineAction({ visible: false })
          }, 800)
        }, 1200)
      }
    } else {
      // Editor / explain actions
      if (action.id === 'marker') {
        setOverlay({ kind: 'marker' })
      } else if (action.id === 'add-req') {
        setOverlay({ kind: 'reqid' })
      } else if (action.id === 'explain') {
        const text = EXPLAIN_TEXTS[action.id] ?? 'Explanation generated by AI.'
        setOverlay({ kind: 'result', text })
      }
    }
  }

  const insertIntoFile = (text: string, mode: 'prepend-line' | 'inline') => {
    if (!openFileId) return
    const content = fileContents[openFileId] ?? ''
    const lines = content.split('\n')
    const startLine = (lineAction.startLine ?? 1) - 1

    let newContent: string
    if (mode === 'prepend-line') {
      lines.splice(startLine, 0, text)
      newContent = lines.join('\n')
    } else {
      // Replace selection with text wrapping selected text
      const selectedText = lineAction.selectedText ?? ''
      newContent = content.replace(selectedText, text + selectedText)
    }
    updateFileContent(openFileId, newContent)
    setLineAction({ visible: false })
    setOverlay(null)
  }

  const dismiss = () => {
    setLineAction({ visible: false })
    setOverlay(null)
  }

  return (
    <>
      {/* Main action bar */}
      <AnimatePresence>
        {lineAction.visible && (
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.92, y: 4 }}
            transition={{ duration: 0.1 }}
            style={{
              position: 'fixed',
              top: lineAction.top,
              left: lineAction.left,
              zIndex: 100,
            }}
          >
            <div style={{
              display: 'flex', alignItems: 'center', gap: 2,
              background: 'rgba(18,18,20,0.97)',
              border: '1px solid rgba(99,102,241,0.45)',
              borderRadius: 9, padding: '3px 4px',
              boxShadow: '0 4px 24px rgba(0,0,0,0.6), 0 0 0 1px rgba(99,102,241,0.1)',
              backdropFilter: 'blur(16px)',
            }}>
              {/* Line indicator */}
              <span style={{
                fontSize: 10, color: '#52525b', padding: '2px 7px',
                borderRight: '1px solid #27272a', marginRight: 2, whiteSpace: 'nowrap',
                fontFamily: 'monospace',
              }}>
                L{lineAction.startLine}{lineAction.endLine !== lineAction.startLine ? `–${lineAction.endLine}` : ''}
              </span>

              {actions.map(action => {
                const state = actionStates[action.id] ?? 'idle'
                return (
                  <button
                    key={action.id}
                    onClick={() => state === 'idle' && handleAction(action)}
                    disabled={state === 'running'}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      padding: '3px 9px', borderRadius: 6,
                      border: state === 'done' ? `1px solid ${action.color}40` : 'none',
                      background: state === 'done' ? `${action.color}15` :
                                  state === 'running' ? `${action.color}10` : 'transparent',
                      color: state !== 'idle' ? action.color : '#a1a1aa',
                      cursor: state === 'idle' ? 'pointer' : 'not-allowed',
                      fontSize: 11, fontWeight: 500, transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => {
                      if (state !== 'idle') return
                      const el = e.currentTarget as HTMLButtonElement
                      el.style.background = `${action.color}18`
                      el.style.color = action.color
                    }}
                    onMouseLeave={e => {
                      if (state !== 'idle') return
                      const el = e.currentTarget as HTMLButtonElement
                      el.style.background = 'transparent'
                      el.style.color = '#a1a1aa'
                    }}
                  >
                    {state === 'running' ? (
                      <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} />
                    ) : state === 'done' ? (
                      <CheckCircle2 size={11} />
                    ) : (
                      <action.icon size={11} />
                    )}
                    {state === 'running' ? '…' : state === 'done' ? 'Done' : action.label}
                  </button>
                )
              })}

              {/* Dismiss */}
              <button
                onClick={dismiss}
                style={{
                  padding: '3px 5px', borderRadius: 5, border: 'none',
                  background: 'transparent', color: '#52525b', cursor: 'pointer',
                  marginLeft: 2, borderLeft: '1px solid #27272a',
                }}
              >
                <X size={10} />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Overlay panels */}
      <AnimatePresence>
        {overlay?.kind === 'result' && (
          <ResultOverlay
            text={overlay.text ?? ''}
            onClose={() => setOverlay(null)}
          />
        )}
        {overlay?.kind === 'marker' && (
          <MarkerPicker
            onPick={id => insertIntoFile(`// @cpt-${id}`, 'prepend-line')}
            onClose={() => setOverlay(null)}
          />
        )}
        {overlay?.kind === 'reqid' && (
          <ReqIdPicker
            onPick={id => {
              const selected = lineAction.selectedText ?? ''
              if (openFileId && selected) {
                const content = fileContents[openFileId] ?? ''
                updateFileContent(openFileId, content.replace(selected, `**[${id}]** ${selected}`))
              }
              setLineAction({ visible: false })
              setOverlay(null)
            }}
            onClose={() => setOverlay(null)}
          />
        )}
      </AnimatePresence>
    </>
  )
}
