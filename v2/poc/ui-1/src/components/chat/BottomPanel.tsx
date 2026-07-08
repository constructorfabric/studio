import { useRef, useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Cpu, X, Maximize2, Plus, ChevronDown, Pencil, Check } from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import { ChatView } from './ChatView'

const MIN_H = 240
const MAX_H = 680

interface ChatTab {
  id: string
  title: string
}

let tabCounter = 1
function newTab(): ChatTab {
  tabCounter++
  return { id: `tab-${Date.now()}`, title: `Chat ${tabCounter}` }
}

export function BottomPanel() {
  const chatOpen    = useAppStore(s => s.chatOpen)
  const chatHeight  = useAppStore(s => s.chatHeight)
  const toggleChat  = useAppStore(s => s.toggleChat)
  const setChatHeight = useAppStore(s => s.setChatHeight)

  const [tabs, setTabs] = useState<ChatTab[]>([{ id: 'tab-1', title: 'Chat 1' }])
  const [activeTabId, setActiveTabId] = useState('tab-1')
  const [editingTabId, setEditingTabId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')

  const dragging = useRef(false)
  const startY   = useRef(0)
  const startH   = useRef(chatHeight)

  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    startY.current   = e.clientY
    startH.current   = chatHeight
    document.body.style.cursor     = 'ns-resize'
    document.body.style.userSelect = 'none'
  }, [chatHeight])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const delta = startY.current - e.clientY
      setChatHeight(Math.max(MIN_H, Math.min(MAX_H, startH.current + delta)))
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.style.cursor     = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup',   onUp)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
  }, [setChatHeight])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'j') { e.preventDefault(); toggleChat() }
      // Cmd/Ctrl+T → new tab (when chat open)
      if ((e.metaKey || e.ctrlKey) && e.key === 't' && chatOpen) { e.preventDefault(); addTab() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggleChat, chatOpen])

  const addTab = () => {
    if (!chatOpen) toggleChat()
    const t = newTab()
    setTabs(prev => [...prev, t])
    setActiveTabId(t.id)
  }

  const closeTab = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setTabs(prev => {
      if (prev.length === 1) return prev  // keep at least one
      const next = prev.filter(t => t.id !== id)
      if (activeTabId === id) {
        const idx = prev.findIndex(t => t.id === id)
        setActiveTabId(next[Math.max(0, idx - 1)].id)
      }
      return next
    })
  }

  const startRename = (tab: ChatTab, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingTabId(tab.id)
    setEditTitle(tab.title)
  }

  const commitRename = () => {
    if (editingTabId && editTitle.trim()) {
      setTabs(prev => prev.map(t => t.id === editingTabId ? { ...t, title: editTitle.trim() } : t))
    }
    setEditingTabId(null)
  }

  return (
    <div style={{ flexShrink: 0, borderTop: '1px solid rgba(63,63,70,0.6)', background: '#09090b', position: 'relative', zIndex: 40 }}>
      {/* Tab bar */}
      <div style={{
        height: 32, display: 'flex', alignItems: 'stretch', gap: 0,
        background: 'rgba(9,9,11,0.95)',
        borderBottom: chatOpen ? '1px solid rgba(63,63,70,0.4)' : 'none',
        overflowX: 'auto', overflowY: 'hidden',
      }}>
        {/* Drag handle */}
        {chatOpen && (
          <div
            onMouseDown={onDragStart}
            style={{
              position: 'absolute', top: -3, left: 0, right: 0, height: 6,
              cursor: 'ns-resize', zIndex: 10,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <div style={{ width: 32, height: 3, borderRadius: 2, background: 'rgba(99,102,241,0.3)' }} />
          </div>
        )}

        {/* AI icon */}
        <div style={{
          display: 'flex', alignItems: 'center', padding: '0 10px',
          borderRight: '1px solid rgba(63,63,70,0.4)', flexShrink: 0,
        }}>
          <Cpu size={12} color="#6366f1" />
        </div>

        {/* Tabs */}
        {tabs.map(tab => {
          const isActive = tab.id === activeTabId
          const isEditing = editingTabId === tab.id
          return (
            <div
              key={tab.id}
              onClick={() => { if (!chatOpen) toggleChat(); setActiveTabId(tab.id) }}
              style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '0 10px', height: '100%', cursor: 'pointer', flexShrink: 0,
                background: isActive && chatOpen ? 'rgba(99,102,241,0.1)' : 'transparent',
                borderRight: '1px solid rgba(63,63,70,0.35)',
                borderBottom: isActive && chatOpen ? '2px solid #6366f1' : '2px solid transparent',
                color: isActive && chatOpen ? '#a5b4fc' : '#52525b',
                fontSize: 12, fontWeight: isActive ? 500 : 400,
                transition: 'all 0.12s', minWidth: 80, maxWidth: 160,
                position: 'relative',
              }}
            >
              {isEditing ? (
                <input
                  autoFocus
                  value={editTitle}
                  onChange={e => setEditTitle(e.target.value)}
                  onBlur={commitRename}
                  onKeyDown={e => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setEditingTabId(null) }}
                  onClick={e => e.stopPropagation()}
                  style={{
                    width: 90, fontSize: 11, background: 'rgba(99,102,241,0.15)',
                    border: '1px solid rgba(99,102,241,0.4)', borderRadius: 4,
                    color: '#e4e4e7', padding: '1px 4px', outline: 'none',
                  }}
                />
              ) : (
                <span
                  style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  onDoubleClick={e => startRename(tab, e)}
                  title="Double-click to rename"
                >
                  {tab.title}
                </span>
              )}
              {/* Close button — only show on hover or when multiple tabs */}
              {tabs.length > 1 && (
                <button
                  onClick={e => closeTab(tab.id, e)}
                  style={{
                    width: 14, height: 14, borderRadius: 3, border: 'none', background: 'transparent',
                    cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#52525b', flexShrink: 0, padding: 0,
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(239,68,68,0.2)'; (e.currentTarget as HTMLElement).style.color = '#f87171' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = '#52525b' }}
                  title="Close tab"
                >
                  <X size={10} />
                </button>
              )}
            </div>
          )
        })}

        {/* New tab button */}
        <button
          onClick={addTab}
          title="New chat (⌘T)"
          style={{
            width: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: 'none', background: 'transparent', cursor: 'pointer',
            color: '#3f3f46', borderRight: '1px solid rgba(63,63,70,0.35)',
            flexShrink: 0, transition: 'all 0.12s',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = '#a1a1aa'; (e.currentTarget as HTMLElement).style.background = 'rgba(63,63,70,0.2)' }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = '#3f3f46'; (e.currentTarget as HTMLElement).style.background = 'transparent' }}
        >
          <Plus size={12} />
        </button>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Controls */}
        <div style={{ display: 'flex', alignItems: 'center', padding: '0 8px', gap: 2, flexShrink: 0 }}>
          <span style={{ fontSize: 10, color: '#3f3f46', marginRight: 4 }}>⌘J</span>
          {chatOpen && (
            <button
              onClick={() => setChatHeight(Math.min(MAX_H, chatHeight + 100))}
              title="Expand"
              style={{ width: 22, height: 22, borderRadius: 4, border: 'none', background: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#52525b' }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(63,63,70,0.3)'; (e.currentTarget as HTMLElement).style.color = '#a1a1aa' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = '#52525b' }}
            >
              <Maximize2 size={11} />
            </button>
          )}
          <button
            onClick={toggleChat}
            title={chatOpen ? 'Close' : 'Open'}
            style={{ width: 22, height: 22, borderRadius: 4, border: 'none', background: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#52525b' }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(63,63,70,0.3)'; (e.currentTarget as HTMLElement).style.color = '#a1a1aa' }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = '#52525b' }}
          >
            {chatOpen ? <X size={11} /> : <ChevronDown size={11} style={{ transform: 'rotate(180deg)' }} />}
          </button>
        </div>
      </div>

      {/* Panel body — render all tabs, show only active */}
      <AnimatePresence initial={false}>
        {chatOpen && (
          <motion.div
            key="chat-panel"
            initial={{ height: 0 }}
            animate={{ height: chatHeight }}
            exit={{ height: 0 }}
            transition={{ type: 'spring', stiffness: 400, damping: 35, mass: 0.8 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ height: chatHeight, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              {tabs.map(tab => (
                <div
                  key={tab.id}
                  style={{
                    display: tab.id === activeTabId ? 'flex' : 'none',
                    flexDirection: 'column', flex: 1, overflow: 'hidden',
                  }}
                >
                  {/* ChatView keyed by tabId so each tab has independent state */}
                  <ChatView key={tab.id} />
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
