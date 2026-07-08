import { useState } from 'react'
import { Search, Package, CheckCircle2, Download, Trash2, RefreshCw, ChevronRight, AlertTriangle, Zap, Shield, Code2, Link2, Star } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { KIT_DEFS } from '../../data/mock-data'
import type { KitDef } from '../../types/domain'

// ─── Mock marketplace kits (not yet installed) ────────────────────────────────

const MARKETPLACE_KITS: KitDef[] = [
  {
    id: 'kit-pagerduty',
    name: 'PagerDuty Connector',
    description: 'Sync incidents, alerts, and on-call schedules from PagerDuty',
    version: '1.0.0',
    status: 'active',
    category: 'connector',
    workerCount: 5,
    connectorCount: 1,
    author: 'Constructor Fabric',
    tags: ['pagerduty', 'ops', 'incidents'],
    installedAt: '',
    workers: [
      { id: 'pd_sync', label: 'PagerDuty Sync', category: 'ops' },
      { id: 'pd_incident', label: 'Create Incident', category: 'ops' },
    ],
  },
  {
    id: 'kit-confluence',
    name: 'Confluence Connector',
    description: 'Import PRDs and design docs from Confluence spaces',
    version: '1.2.0',
    status: 'active',
    category: 'connector',
    workerCount: 3,
    connectorCount: 1,
    author: 'Constructor Fabric',
    tags: ['confluence', 'docs', 'import'],
    installedAt: '',
    workers: [
      { id: 'confluence_sync', label: 'Confluence Sync', category: 'platform' },
    ],
  },
  {
    id: 'kit-linear',
    name: 'Linear Connector',
    description: 'Sync issues and cycles from Linear; write tasks back on state changes',
    version: '0.8.0',
    status: 'active',
    category: 'connector',
    workerCount: 4,
    connectorCount: 1,
    author: 'Community',
    tags: ['linear', 'tasks', 'connector'],
    installedAt: '',
    workers: [],
  },
  {
    id: 'kit-ai-cost',
    name: 'AI Cost Analyzer',
    description: 'Track and optimize AI spend per worker, model, and workspace',
    version: '0.5.0',
    status: 'active',
    category: 'ai-cost',
    workerCount: 6,
    connectorCount: 0,
    author: 'Constructor Fabric',
    tags: ['ai-cost', 'observability', 'optimization'],
    installedAt: '',
    workers: [],
  },
  {
    id: 'kit-on-call',
    name: 'On-Call Runbook Kit',
    description: 'Incident → postmortem → prevention task automation for SRE teams',
    version: '1.1.0',
    status: 'active',
    category: 'ops',
    workerCount: 9,
    connectorCount: 0,
    author: 'Constructor Fabric',
    tags: ['sre', 'ops', 'runbook', 'incidents'],
    installedAt: '',
    workers: [],
  },
]

const INSTALLED_IDS = new Set(KIT_DEFS.map(k => k.id))

// ─── Category colors ──────────────────────────────────────────────────────────

const categoryStyle: Record<string, { color: string; bg: string; border: string }> = {
  sdlc:         { color: '#818cf8', bg: 'rgba(99,102,241,0.12)',  border: 'rgba(99,102,241,0.3)' },
  connector:    { color: '#22d3ee', bg: 'rgba(6,182,212,0.10)',   border: 'rgba(6,182,212,0.3)' },
  security:     { color: '#f87171', bg: 'rgba(239,68,68,0.10)',   border: 'rgba(239,68,68,0.3)' },
  architecture: { color: '#60a5fa', bg: 'rgba(59,130,246,0.10)',  border: 'rgba(59,130,246,0.3)' },
  'ai-cost':    { color: '#34d399', bg: 'rgba(16,185,129,0.10)',  border: 'rgba(16,185,129,0.3)' },
  ops:          { color: '#fbbf24', bg: 'rgba(245,158,11,0.10)',  border: 'rgba(245,158,11,0.3)' },
}

function catStyle(cat: string) {
  return categoryStyle[cat] ?? { color: '#a1a1aa', bg: 'rgba(63,63,70,0.3)', border: 'rgba(63,63,70,0.5)' }
}

function categoryIcon(cat: string) {
  switch (cat) {
    case 'sdlc':         return <Code2 size={11} />
    case 'connector':    return <Link2 size={11} />
    case 'security':     return <Shield size={11} />
    case 'architecture': return <Zap size={11} />
    case 'ai-cost':      return <Star size={11} />
    default:             return <Package size={11} />
  }
}

// ─── Kit card ─────────────────────────────────────────────────────────────────

function KitCard({
  kit,
  installed,
  installing,
  updating,
  updateAvailable,
  onInstall,
  onUninstall,
  onUpdate,
  onClick,
  selected,
}: {
  kit: KitDef
  installed: boolean
  installing: boolean
  updating: boolean
  updateAvailable: boolean
  onInstall: () => void
  onUninstall: () => void
  onUpdate: () => void
  onClick: () => void
  selected: boolean
}) {
  const cs = catStyle(kit.category)

  return (
    <motion.div
      layout
      onClick={onClick}
      style={{
        padding: '10px 12px',
        borderRadius: 8,
        border: selected ? '1.5px solid rgba(99,102,241,0.5)' : '1px solid rgba(63,63,70,0.5)',
        background: selected ? 'rgba(99,102,241,0.06)' : 'rgba(24,24,27,0.5)',
        cursor: 'pointer',
        marginBottom: 4,
        transition: 'border-color 0.15s, background 0.15s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        {/* Icon */}
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: cs.bg, border: `1px solid ${cs.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0, color: cs.color,
        }}>
          {categoryIcon(kit.category)}
        </div>

        {/* Info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#e4e4e7' }}>{kit.name}</span>
            {installed && !updateAvailable && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 10, color: '#10b981' }}>
                <CheckCircle2 size={10} /> installed
              </span>
            )}
            {updateAvailable && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 10, color: '#f59e0b', fontWeight: 600 }}>
                <AlertTriangle size={10} /> update
              </span>
            )}
          </div>
          <p style={{ fontSize: 11, color: '#71717a', lineHeight: 1.4, marginBottom: 6 }}>{kit.description}</p>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{
              fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 4,
              background: cs.bg, border: `1px solid ${cs.border}`, color: cs.color,
              textTransform: 'uppercase', letterSpacing: '0.06em',
            }}>
              {kit.category}
            </span>
            <span style={{ fontSize: 10, color: '#52525b' }}>v{kit.version}</span>
            <span style={{ fontSize: 10, color: '#52525b' }}>{kit.author}</span>
            <span style={{ fontSize: 10, color: '#52525b' }}>·</span>
            <span style={{ fontSize: 10, color: '#71717a' }}>{kit.workerCount} workers</span>
            {kit.connectorCount > 0 && (
              <>
                <span style={{ fontSize: 10, color: '#52525b' }}>·</span>
                <span style={{ fontSize: 10, color: '#22d3ee' }}>{kit.connectorCount} connector</span>
              </>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
          {!installed && (
            <button
              onClick={onInstall}
              disabled={installing}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', borderRadius: 6, border: 'none',
                background: installing ? 'rgba(99,102,241,0.3)' : '#4f46e5',
                color: '#fff', fontSize: 11, fontWeight: 600, cursor: 'pointer',
                opacity: installing ? 0.7 : 1,
              }}
            >
              {installing ? <Loader size={11} /> : <Download size={11} />}
              {installing ? 'Installing…' : 'Install'}
            </button>
          )}
          {installed && !updateAvailable && (
            <button
              onClick={onUninstall}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', borderRadius: 6,
                border: '1px solid rgba(239,68,68,0.3)',
                background: 'rgba(239,68,68,0.06)',
                color: '#f87171', fontSize: 11, fontWeight: 500, cursor: 'pointer',
              }}
            >
              <Trash2 size={11} /> Uninstall
            </button>
          )}
          {updateAvailable && (
            <button
              onClick={onUpdate}
              disabled={updating}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', borderRadius: 6, border: 'none',
                background: updating ? 'rgba(217,119,6,0.4)' : '#d97706',
                color: '#fff', fontSize: 11, fontWeight: 600,
                cursor: updating ? 'not-allowed' : 'pointer',
                opacity: updating ? 0.8 : 1,
              }}
            >
              <RefreshCw size={11} style={updating ? { animation: 'spin 1s linear infinite' } : {}} />
              {updating ? 'Updating…' : 'Update'}
            </button>
          )}
        </div>
      </div>
    </motion.div>
  )
}

function Loader({ size }: { size: number }) {
  return <RefreshCw size={size} style={{ animation: 'spin 1s linear infinite' }} />
}

// ─── Kit Detail Panel ─────────────────────────────────────────────────────────

function KitDetail({ kit, installed }: { kit: KitDef; installed: boolean }) {
  const cs = catStyle(kit.category)
  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '16px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 16 }}>
        <div style={{
          width: 48, height: 48, borderRadius: 10,
          background: cs.bg, border: `1px solid ${cs.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: cs.color, flexShrink: 0,
        }}>
          <Package size={20} />
        </div>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: '#e4e4e7', marginBottom: 2 }}>{kit.name}</h2>
          <p style={{ fontSize: 11, color: '#71717a' }}>by {kit.author} · v{kit.version}</p>
          {installed && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#10b981', marginTop: 4 }}>
              <CheckCircle2 size={10} /> Installed
            </span>
          )}
        </div>
      </div>

      <p style={{ fontSize: 13, color: '#a1a1aa', lineHeight: 1.6, marginBottom: 16 }}>{kit.description}</p>

      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {kit.tags.map(tag => (
            <span key={tag} style={{
              fontSize: 10, padding: '2px 8px', borderRadius: 20,
              background: 'rgba(63,63,70,0.4)', border: '1px solid rgba(63,63,70,0.6)',
              color: '#71717a',
            }}>#{tag}</span>
          ))}
        </div>
      </div>

      {kit.workers.length > 0 && (
        <div>
          <h3 style={{ fontSize: 11, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Workers ({kit.workers.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {kit.workers.map(w => {
              const wcs = catStyle(w.category)
              return (
                <div key={w.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '6px 8px', borderRadius: 6,
                  background: 'rgba(24,24,27,0.5)', border: '1px solid rgba(63,63,70,0.3)',
                }}>
                  <span style={{ fontSize: 12, color: '#d4d4d8' }}>{w.label}</span>
                  <span style={{
                    fontSize: 9, padding: '1px 6px', borderRadius: 4,
                    background: wcs.bg, border: `1px solid ${wcs.border}`, color: wcs.color,
                    fontWeight: 700, textTransform: 'uppercase',
                  }}>{w.category}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main KitsView ────────────────────────────────────────────────────────────

type Tab = 'installed' | 'browse'

export function KitsView() {
  const [tab, setTab] = useState<Tab>('installed')
  const [search, setSearch] = useState('')
  const [selectedKitId, setSelectedKitId] = useState<string | null>(KIT_DEFS[0]?.id ?? null)
  const [installedIds, setInstalledIds] = useState<Set<string>>(INSTALLED_IDS)
  const [installingIds, setInstallingIds] = useState<Set<string>>(new Set())
  const [updatingIds, setUpdatingIds] = useState<Set<string>>(new Set())
  const [updatedIds, setUpdatedIds] = useState<Set<string>>(new Set())
  const [filterCat, setFilterCat] = useState<string | null>(null)

  const allKits = tab === 'installed'
    ? KIT_DEFS
    : [...KIT_DEFS, ...MARKETPLACE_KITS].filter(k => !installedIds.has(k.id))

  const displayed = allKits.filter(k => {
    const matchSearch = !search || k.name.toLowerCase().includes(search.toLowerCase()) || k.description.toLowerCase().includes(search.toLowerCase()) || k.tags.some(t => t.includes(search.toLowerCase()))
    const matchCat = !filterCat || k.category === filterCat
    return matchSearch && matchCat
  })

  const browseKits = [...KIT_DEFS, ...MARKETPLACE_KITS].filter(k => {
    const matchSearch = !search || k.name.toLowerCase().includes(search.toLowerCase()) || k.description.toLowerCase().includes(search.toLowerCase())
    const matchCat = !filterCat || k.category === filterCat
    return matchSearch && matchCat
  })

  const listKits = tab === 'installed' ? displayed : browseKits

  const selectedKit = [...KIT_DEFS, ...MARKETPLACE_KITS].find(k => k.id === selectedKitId)

  const handleInstall = (kitId: string) => {
    setInstallingIds(s => new Set([...s, kitId]))
    setTimeout(() => {
      setInstallingIds(s => { const n = new Set(s); n.delete(kitId); return n })
      setInstalledIds(s => new Set([...s, kitId]))
    }, 2000)
  }

  const handleUninstall = (kitId: string) => {
    setInstalledIds(s => { const n = new Set(s); n.delete(kitId); return n })
    if (selectedKitId === kitId) setSelectedKitId(null)
  }

  const handleUpdate = (kitId: string) => {
    setUpdatingIds(s => new Set([...s, kitId]))
    setTimeout(() => {
      setUpdatingIds(s => { const n = new Set(s); n.delete(kitId); return n })
      setUpdatedIds(s => new Set([...s, kitId]))
    }, 2000)
  }

  const categories = Array.from(new Set([...KIT_DEFS, ...MARKETPLACE_KITS].map(k => k.category)))

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid rgba(63,63,70,0.5)',
        display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
      }}>
        <Package size={16} color="#818cf8" />
        <h2 style={{ fontSize: 14, fontWeight: 700, color: '#e4e4e7', flex: 1 }}>Kit Marketplace</h2>
        {/* Tabs */}
        <div style={{ display: 'flex', gap: 2, background: 'rgba(24,24,27,0.8)', padding: 2, borderRadius: 8, border: '1px solid rgba(63,63,70,0.4)' }}>
          {(['installed', 'browse'] as Tab[]).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding: '4px 14px', borderRadius: 6, border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer',
              background: tab === t ? '#4f46e5' : 'transparent',
              color: tab === t ? '#fff' : '#71717a',
              transition: 'all 0.15s',
            }}>
              {t === 'installed' ? `Installed (${installedIds.size})` : 'Browse'}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left: list */}
        <div style={{
          width: 380, flexShrink: 0,
          borderRight: '1px solid rgba(63,63,70,0.4)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>
          {/* Search + filter */}
          <div style={{ padding: '10px 12px', borderBottom: '1px solid rgba(63,63,70,0.3)', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ position: 'relative' }}>
              <Search size={12} color="#52525b" style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)' }} />
              <input
                type="text"
                placeholder="Search kits…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{
                  width: '100%', paddingLeft: 28, paddingRight: 10, paddingTop: 6, paddingBottom: 6,
                  background: 'rgba(24,24,27,0.8)', border: '1px solid rgba(63,63,70,0.5)',
                  borderRadius: 6, fontSize: 12, color: '#d4d4d8', outline: 'none',
                }}
              />
            </div>
            {/* Category pills */}
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              <button onClick={() => setFilterCat(null)} style={{
                fontSize: 10, padding: '2px 8px', borderRadius: 20, cursor: 'pointer',
                background: !filterCat ? 'rgba(99,102,241,0.2)' : 'rgba(63,63,70,0.3)',
                border: `1px solid ${!filterCat ? 'rgba(99,102,241,0.4)' : 'rgba(63,63,70,0.4)'}`,
                color: !filterCat ? '#a5b4fc' : '#71717a',
              }}>All</button>
              {categories.map(cat => {
                const cs = catStyle(cat)
                return (
                  <button key={cat} onClick={() => setFilterCat(filterCat === cat ? null : cat)} style={{
                    fontSize: 10, padding: '2px 8px', borderRadius: 20, cursor: 'pointer',
                    background: filterCat === cat ? cs.bg : 'rgba(63,63,70,0.2)',
                    border: `1px solid ${filterCat === cat ? cs.border : 'rgba(63,63,70,0.3)'}`,
                    color: filterCat === cat ? cs.color : '#71717a',
                  }}>{cat}</button>
                )
              })}
            </div>
          </div>

          {/* Kit list */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 10px' }}>
            <AnimatePresence>
              {listKits.map(kit => {
                const inst = installedIds.has(kit.id)
                const installing = installingIds.has(kit.id)
                const upd = inst && !updatedIds.has(kit.id) && kit.latestVersion !== undefined && kit.latestVersion !== kit.version
                const updating = updatingIds.has(kit.id)
                return (
                  <KitCard
                    key={kit.id}
                    kit={kit}
                    installed={inst}
                    installing={installing}
                    updating={updating}
                    updateAvailable={upd}
                    onInstall={() => handleInstall(kit.id)}
                    onUninstall={() => handleUninstall(kit.id)}
                    onUpdate={() => handleUpdate(kit.id)}
                    onClick={() => setSelectedKitId(kit.id)}
                    selected={selectedKitId === kit.id}
                  />
                )
              })}
            </AnimatePresence>
            {listKits.length === 0 && (
              <div style={{ textAlign: 'center', padding: '32px 16px', color: '#52525b' }}>
                <Package size={24} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                <p style={{ fontSize: 12 }}>No kits found</p>
              </div>
            )}
          </div>
        </div>

        {/* Right: detail */}
        <div style={{ flex: 1, overflow: 'hidden', background: 'rgba(9,9,11,0.4)' }}>
          {selectedKit ? (
            <KitDetail kit={selectedKit} installed={installedIds.has(selectedKit.id)} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#52525b' }}>
              <Package size={32} style={{ marginBottom: 12, opacity: 0.3 }} />
              <p style={{ fontSize: 13 }}>Select a kit to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
