import { useRef, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Cpu, ChevronDown, X, Maximize2 } from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import { ChatView } from './ChatView'

const MIN_H = 240
const MAX_H = 680

export function BottomPanel() {
  const chatOpen = useAppStore(s => s.chatOpen)
  const chatHeight = useAppStore(s => s.chatHeight)
  const toggleChat = useAppStore(s => s.toggleChat)
  const setChatHeight = useAppStore(s => s.setChatHeight)

  const dragging = useRef(false)
  const startY = useRef(0)
  const startH = useRef(chatHeight)

  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    startY.current = e.clientY
    startH.current = chatHeight
    document.body.style.cursor = 'ns-resize'
    document.body.style.userSelect = 'none'
  }, [chatHeight])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const delta = startY.current - e.clientY
      const next = Math.max(MIN_H, Math.min(MAX_H, startH.current + delta))
      setChatHeight(next)
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
  }, [setChatHeight])

  // Keyboard shortcut: Cmd/Ctrl+J
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'j') { e.preventDefault(); toggleChat() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggleChat])

  return (
    <div style={{ flexShrink: 0, borderTop: '1px solid rgba(63,63,70,0.6)', background: '#09090b', position: 'relative', zIndex: 40 }}>
      {/* Tab bar — always visible */}
      <div style={{
        height: 32, display: 'flex', alignItems: 'center', gap: 0,
        background: 'rgba(9,9,11,0.95)', borderBottom: chatOpen ? '1px solid rgba(63,63,70,0.4)' : 'none',
      }}>
        {/* Drag handle (only when open) */}
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

        {/* Chat tab */}
        <button
          onClick={toggleChat}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '0 14px', height: '100%', border: 'none', cursor: 'pointer',
            background: chatOpen ? 'rgba(99,102,241,0.1)' : 'transparent',
            borderRight: '1px solid rgba(63,63,70,0.4)',
            borderBottom: chatOpen ? '1px solid #6366f1' : '1px solid transparent',
            color: chatOpen ? '#a5b4fc' : '#71717a',
            fontSize: 12, fontWeight: 500, transition: 'all 0.15s',
          }}
        >
          <Cpu size={12} />
          AI Chat
          {chatOpen && (
            <span style={{
              fontSize: 9, padding: '1px 5px', borderRadius: 10,
              background: 'rgba(99,102,241,0.2)', color: '#818cf8', fontWeight: 700,
            }}>
              ⌘J
            </span>
          )}
        </button>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Controls */}
        <div style={{ display: 'flex', alignItems: 'center', padding: '0 8px', gap: 2 }}>
          <span style={{ fontSize: 10, color: '#3f3f46', marginRight: 6 }}>⌘J</span>
          {chatOpen && (
            <>
              <button
                onClick={() => setChatHeight(Math.min(MAX_H, chatHeight + 100))}
                title="Expand"
                style={{ width: 22, height: 22, borderRadius: 4, border: 'none', background: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#52525b' }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(63,63,70,0.3)'; (e.currentTarget as HTMLElement).style.color = '#a1a1aa' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = '#52525b' }}
              >
                <Maximize2 size={11} />
              </button>
              <button
                onClick={toggleChat}
                title="Close"
                style={{ width: 22, height: 22, borderRadius: 4, border: 'none', background: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#52525b' }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(63,63,70,0.3)'; (e.currentTarget as HTMLElement).style.color = '#a1a1aa' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = '#52525b' }}
              >
                <X size={11} />
              </button>
            </>
          )}
          {!chatOpen && (
            <button
              onClick={toggleChat}
              style={{ width: 22, height: 22, borderRadius: 4, border: 'none', background: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#52525b' }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(63,63,70,0.3)'; (e.currentTarget as HTMLElement).style.color = '#a1a1aa' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = '#52525b' }}
            >
              <ChevronDown size={11} style={{ transform: 'rotate(180deg)' }} />
            </button>
          )}
        </div>
      </div>

      {/* Panel body */}
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
              <ChatView />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
