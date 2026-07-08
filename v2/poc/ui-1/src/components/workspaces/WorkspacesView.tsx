import { useState } from 'react'
import { Layers, Plus, RefreshCw, CheckCircle2, AlertTriangle, Wifi, WifiOff, GitBranch, Package, Clock, Settings, ChevronRight, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { WORKSPACE_DEFS, KIT_DEFS } from '../../data/mock-data'
import type { WorkspaceDef, WorkspaceStatus } from '../../types/domain'

// ─── Status indicator ─────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: WorkspaceStatus }) {
  const config = {
    active:   { color: '#10b981', bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.3)', label: 'Active',   icon: <CheckCircle2 size={10} /> },
    syncing:  { color: '#6366f1', bg: 'rgba(99,102,241,0.12)', border: 'rgba(99,102,241,0.3)', label: 'Syncing',  icon: <RefreshCw size={10} style={{ animation: 'spin 1s linear infinite' }} /> },
    error:    { color: '#ef4444', bg: 'rgba(239,68,68,0.12)',  border: 'rgba(239,68,68,0.3)',  label: 'Error',    icon: <AlertTriangle size={10} /> },
    offline:  { color: '#71717a', bg: 'rgba(63,63,70,0.20)',   border: 'rgba(63,63,70,0.4)',   label: 'Offline',  icon: <WifiOff size={10} /> },
  }
  const c = config[status]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      fontSize: 10, padding: '2px 7px', borderRadius: 20,
      background: c.bg, border: `1px solid ${c.border}`, color: c.color, fontWeight: 600,
    }}>
      {c.icon} {c.label}
    </span>
  )
}

function AutoLevelBadge({ level }: { level: string }) {
  const map: Record<string, { color: string; bg: string; border: string }> = {
    recommendations:     { color: '#60a5fa', bg: 'rgba(59,130,246,0.10)', border: 'rgba(59,130,246,0.3)' },
    approved_automation: { color: '#10b981', bg: 'rgba(16,185,129,0.10)', border: 'rgba(16,185,129,0.3)' },
    enterprise:          { color: '#f59e0b', bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.3)' },
  }
  const c = map[level] ?? map['recommendations']
  return (
    <span style={{
      fontSize: 10, padding: '2px 7px', borderRadius: 20,
      background: c.bg, border: `1px solid ${c.border}`, color: c.color, fontWeight: 500,
    }}>
      {level.replace('_', ' ')}
    </span>
  )
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// ─── Workspace Card ───────────────────────────────────────────────────────────

function WorkspaceCard({ ws, active, onSelect, current }: {
  ws: WorkspaceDef
  active: boolean
  onSelect: () => void
  current: boolean
}) {
  const kitNames = ws.installedKitIds.slice(0, 3).map(id => KIT_DEFS.find(k => k.id === id)?.name ?? id)

  return (
    <motion.div
      layout
      onClick={onSelect}
      style={{
        padding: '12px 14px', borderRadius: 10, cursor: 'pointer',
        border: active ? '1.5px solid rgba(99,102,241,0.5)' : current ? '1px solid rgba(16,185,129,0.3)' : '1px solid rgba(63,63,70,0.5)',
        background: active ? 'rgba(99,102,241,0.07)' : current ? 'rgba(16,185,129,0.05)' : 'rgba(24,24,27,0.5)',
        marginBottom: 6,
        transition: 'all 0.15s ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            {current && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981', display: 'inline-block' }} />}
            <span style={{ fontSize: 13, fontWeight: 600, color: active || current ? '#e4e4e7' : '#a1a1aa' }}>{ws.name}</span>
            <StatusBadge status={ws.status} />
          </div>
          {ws.description && (
            <p style={{ fontSize: 11, color: '#71717a', marginBottom: 6, lineHeight: 1.4 }}>{ws.description}</p>
          )}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, fontSize: 11, color: '#52525b' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <GitBranch size={10} /> {ws.sources.length} repo{ws.sources.length !== 1 ? 's' : ''}
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <Package size={10} /> {ws.installedKitIds.length} kits
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <Layers size={10} /> {ws.objectCount} objects
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <Clock size={10} /> {timeAgo(ws.lastSyncedAt)}
            </span>
          </div>
        </div>
        <ChevronRight size={14} color={active ? '#818cf8' : '#3f3f46'} />
      </div>
    </motion.div>
  )
}

// ─── Workspace Detail ─────────────────────────────────────────────────────────

function WorkspaceDetail({ ws, onSwitch, isCurrent }: {
  ws: WorkspaceDef
  onSwitch: () => void
  isCurrent: boolean
}) {
  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '16px 20px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, color: '#e4e4e7' }}>{ws.name}</h2>
            <StatusBadge status={ws.status} />
            {isCurrent && (
              <span style={{ fontSize: 10, color: '#10b981', fontWeight: 600 }}>● current</span>
            )}
          </div>
          {ws.description && <p style={{ fontSize: 12, color: '#71717a' }}>{ws.description}</p>}
        </div>
        {!isCurrent && (
          <button
            onClick={onSwitch}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '6px 14px', borderRadius: 8, border: 'none',
              background: '#4f46e5', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}
          >
            Switch to this
          </button>
        )}
      </div>

      {/* Automation level */}
      <div style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 11, color: '#71717a' }}>Automation level:</span>
        <AutoLevelBadge level={ws.automationLevel} />
      </div>

      {/* Sources */}
      <div style={{ marginBottom: 16 }}>
        <h3 style={{ fontSize: 11, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
          Sources ({ws.sources.length})
        </h3>
        {ws.sources.map(src => (
          <div key={src.id} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '7px 10px', borderRadius: 7, marginBottom: 4,
            background: 'rgba(24,24,27,0.6)', border: '1px solid rgba(63,63,70,0.4)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <GitBranch size={12} color="#60a5fa" />
              <div>
                <p style={{ fontSize: 12, color: '#d4d4d8', fontWeight: 500 }}>{src.url}</p>
                <p style={{ fontSize: 10, color: '#52525b' }}>{src.branch} · {src.role}</p>
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <p style={{ fontSize: 10, color: '#52525b' }}>{timeAgo(src.lastSyncedAt)}</p>
              <span style={{ fontSize: 10, color: '#10b981', display: 'flex', alignItems: 'center', gap: 3, justifyContent: 'flex-end' }}>
                <Wifi size={9} /> synced
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Kits */}
      <div>
        <h3 style={{ fontSize: 11, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
          Installed Kits ({ws.installedKitIds.length})
        </h3>
        {ws.installedKitIds.map(kitId => {
          const kit = KIT_DEFS.find(k => k.id === kitId)
          if (!kit) return null
          const upd = kit.latestVersion !== undefined && kit.latestVersion !== kit.version
          return (
            <div key={kitId} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '6px 10px', borderRadius: 6, marginBottom: 3,
              background: 'rgba(24,24,27,0.4)', border: '1px solid rgba(63,63,70,0.3)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Package size={11} color="#818cf8" />
                <span style={{ fontSize: 12, color: '#d4d4d8' }}>{kit.name}</span>
                <span style={{ fontSize: 10, color: '#52525b' }}>v{kit.version}</span>
              </div>
              {upd ? (
                <span style={{ fontSize: 10, color: '#f59e0b', display: 'flex', alignItems: 'center', gap: 3 }}>
                  <AlertTriangle size={10} /> v{kit.latestVersion}
                </span>
              ) : (
                <CheckCircle2 size={11} color="#10b981" />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Create Workspace Modal ───────────────────────────────────────────────────

function CreateWorkspaceModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [repoUrl, setRepoUrl] = useState('')
  const [step, setStep] = useState<'form' | 'creating' | 'done'>('form')

  const handleCreate = () => {
    if (!name.trim()) return
    setStep('creating')
    setTimeout(() => setStep('done'), 2000)
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
    }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.94, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        style={{
          width: 480, background: '#18181b', border: '1px solid rgba(63,63,70,0.6)',
          borderRadius: 14, overflow: 'hidden',
          boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
        }}
      >
        <div style={{ padding: '14px 18px', borderBottom: '1px solid rgba(63,63,70,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: '#e4e4e7' }}>Create Workspace</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#71717a', padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: '18px' }}>
          {step === 'form' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: '#a1a1aa', display: 'block', marginBottom: 4 }}>Workspace Name</label>
                <input
                  type="text"
                  placeholder="e.g. Payments Platform"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  style={{
                    width: '100%', padding: '8px 10px',
                    background: 'rgba(24,24,27,0.8)', border: '1px solid rgba(63,63,70,0.6)',
                    borderRadius: 7, fontSize: 13, color: '#d4d4d8', outline: 'none',
                  }}
                />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: '#a1a1aa', display: 'block', marginBottom: 4 }}>Repository URL</label>
                <input
                  type="text"
                  placeholder="github.com/org/repo"
                  value={repoUrl}
                  onChange={e => setRepoUrl(e.target.value)}
                  style={{
                    width: '100%', padding: '8px 10px',
                    background: 'rgba(24,24,27,0.8)', border: '1px solid rgba(63,63,70,0.6)',
                    borderRadius: 7, fontSize: 13, color: '#d4d4d8', outline: 'none',
                  }}
                />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: '#a1a1aa', display: 'block', marginBottom: 4 }}>Automation Level</label>
                <select style={{
                  width: '100%', padding: '8px 10px',
                  background: 'rgba(24,24,27,0.8)', border: '1px solid rgba(63,63,70,0.6)',
                  borderRadius: 7, fontSize: 13, color: '#d4d4d8', outline: 'none',
                }}>
                  <option value="recommendations">Recommendations only</option>
                  <option value="approved_automation">Approved automation</option>
                  <option value="enterprise">Enterprise</option>
                </select>
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 4 }}>
                <button onClick={onClose} style={{
                  padding: '7px 16px', borderRadius: 7, border: '1px solid rgba(63,63,70,0.6)',
                  background: 'transparent', color: '#a1a1aa', fontSize: 13, cursor: 'pointer',
                }}>Cancel</button>
                <button
                  onClick={handleCreate}
                  disabled={!name.trim()}
                  style={{
                    padding: '7px 16px', borderRadius: 7, border: 'none',
                    background: name.trim() ? '#4f46e5' : 'rgba(99,102,241,0.3)',
                    color: '#fff', fontSize: 13, fontWeight: 600, cursor: name.trim() ? 'pointer' : 'not-allowed',
                  }}
                >Create</button>
              </div>
            </div>
          )}

          {step === 'creating' && (
            <div style={{ textAlign: 'center', padding: '24px 0' }}>
              <RefreshCw size={24} color="#6366f1" style={{ margin: '0 auto 12px', animation: 'spin 1s linear infinite' }} />
              <p style={{ fontSize: 13, color: '#a1a1aa' }}>Creating workspace <strong style={{ color: '#e4e4e7' }}>{name}</strong>…</p>
              <p style={{ fontSize: 11, color: '#52525b', marginTop: 6 }}>Initializing git config, installing SDLC Kit</p>
            </div>
          )}

          {step === 'done' && (
            <div style={{ textAlign: 'center', padding: '24px 0' }}>
              <CheckCircle2 size={28} color="#10b981" style={{ margin: '0 auto 12px' }} />
              <p style={{ fontSize: 14, fontWeight: 600, color: '#e4e4e7', marginBottom: 4 }}>Workspace created!</p>
              <p style={{ fontSize: 11, color: '#71717a', marginBottom: 16 }}>{name} is ready. SDLC Kit installed.</p>
              <button onClick={onClose} style={{
                padding: '7px 20px', borderRadius: 7, border: 'none',
                background: '#4f46e5', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
              }}>Open Workspace</button>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  )
}

// ─── Main WorkspacesView ──────────────────────────────────────────────────────

export function WorkspacesView() {
  const [selectedId, setSelectedId] = useState<string>(WORKSPACE_DEFS[0].id)
  const [currentId, setCurrentId] = useState<string>('ws-billing')
  const [showCreate, setShowCreate] = useState(false)

  const selected = WORKSPACE_DEFS.find(w => w.id === selectedId) ?? WORKSPACE_DEFS[0]

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid rgba(63,63,70,0.5)',
        display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
      }}>
        <Layers size={16} color="#818cf8" />
        <h2 style={{ fontSize: 14, fontWeight: 700, color: '#e4e4e7', flex: 1 }}>Workspaces</h2>
        <button
          onClick={() => setShowCreate(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', borderRadius: 8, border: 'none',
            background: '#4f46e5', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
          }}
        >
          <Plus size={14} /> New Workspace
        </button>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left: list */}
        <div style={{
          width: 320, flexShrink: 0,
          borderRight: '1px solid rgba(63,63,70,0.4)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          background: 'rgba(9,9,11,0.3)',
        }}>
          <div style={{ padding: '10px 10px 6px', borderBottom: '1px solid rgba(63,63,70,0.3)' }}>
            <p style={{ fontSize: 10, fontWeight: 600, color: '#52525b', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {WORKSPACE_DEFS.length} workspaces
            </p>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 10px' }}>
            {WORKSPACE_DEFS.map(ws => (
              <WorkspaceCard
                key={ws.id}
                ws={ws}
                active={selectedId === ws.id}
                current={currentId === ws.id}
                onSelect={() => setSelectedId(ws.id)}
              />
            ))}
          </div>
        </div>

        {/* Right: detail */}
        <div style={{ flex: 1, overflow: 'hidden', background: 'rgba(9,9,11,0.2)' }}>
          <WorkspaceDetail
            ws={selected}
            onSwitch={() => setCurrentId(selected.id)}
            isCurrent={currentId === selected.id}
          />
        </div>
      </div>

      <AnimatePresence>
        {showCreate && <CreateWorkspaceModal onClose={() => setShowCreate(false)} />}
      </AnimatePresence>
    </div>
  )
}
