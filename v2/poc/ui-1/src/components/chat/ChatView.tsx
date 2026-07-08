import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Cpu, User, Loader2, Play, CheckCircle2, XCircle, ChevronDown, Zap, AlertTriangle, GitBranch, FileText, Search, Wrench, TestTube2, Link2, X } from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import { WORKER_DEFS, MOCK_RECOMMENDATIONS, MOCK_OBJECTS } from '../../data/mock-data'

// ─── Types ────────────────────────────────────────────────────────────────────

type Role = 'user' | 'assistant'
type MsgKind = 'text' | 'tool_use' | 'tool_result' | 'suggestion_row'

interface ToolCall {
  workerId: string
  workerLabel: string
  status: 'running' | 'done' | 'failed'
  objectTitle?: string
  output?: string
  costUsd?: number
  durationMs?: number
}

interface Message {
  id: string
  role: Role
  kind: MsgKind
  text?: string
  streaming?: boolean
  toolCall?: ToolCall
  suggestions?: SlashCommand[]
}

interface SlashCommand {
  cmd: string
  label: string
  description: string
  icon: React.ReactNode
  workerId?: string
}

// ─── Slash commands ───────────────────────────────────────────────────────────

const SLASH_COMMANDS: SlashCommand[] = [
  { cmd: '/analyze',    label: '/analyze',    description: 'Run gap analysis on selected object',          icon: <Search size={13} />,    workerId: 'gap_analysis_validator' },
  { cmd: '/trace',      label: '/trace',      description: 'Run traceability analysis',                    icon: <Link2 size={13} />,     workerId: 'traceability_analysis' },
  { cmd: '/implement',  label: '/implement',  description: 'Implement code for selected feature/task',     icon: <Wrench size={13} />,    workerId: 'implement_code_worker' },
  { cmd: '/design',     label: '/design',     description: 'Create design from PRD',                       icon: <FileText size={13} />,  workerId: 'create_design_worker' },
  { cmd: '/test',       label: '/test',       description: 'Generate tests for selected object',           icon: <TestTube2 size={13} />, workerId: 'implement_code_worker' },
  { cmd: '/decompose',  label: '/decompose',  description: 'Decompose design into tasks',                  icon: <GitBranch size={13} />, workerId: 'decompose_feature_worker' },
  { cmd: '/validate',   label: '/validate',   description: 'Validate PR against design',                   icon: <CheckCircle2 size={13} />, workerId: 'pr_design_validator' },
  { cmd: '/security',   label: '/security',   description: 'Run security impact analysis',                 icon: <AlertTriangle size={13} />, workerId: 'security_impact_analysis' },
  { cmd: '/recs',       label: '/recs',       description: 'List active recommendations',                   icon: <Zap size={13} /> },
  { cmd: '/score',      label: '/score',      description: 'Show quality score for selected object',        icon: <Zap size={13} /> },
  { cmd: '/explain',    label: '/explain',    description: 'Explain the selected object in plain language', icon: <FileText size={13} /> },
]

// ─── AI response generator ────────────────────────────────────────────────────

function generateResponse(input: string, selectedObjectId: string | null): { text: string; workerId?: string } {
  const lower = input.toLowerCase().trim()
  const selectedObj = selectedObjectId ? MOCK_OBJECTS.find(o => o.id === selectedObjectId) : null
  const objName = selectedObj?.title ?? 'the workspace'

  if (lower.startsWith('/recs') || lower.includes('recommendation')) {
    const recs = MOCK_RECOMMENDATIONS.filter(r => r.state === 'pending')
    return { text: `Found **${recs.length} active recommendations** in the workspace:\n\n${recs.map(r => `- **${r.severity.toUpperCase()}** — ${r.title}`).join('\n')}\n\nWould you like me to accept and run any of these?` }
  }
  if (lower.startsWith('/score') || lower.includes('quality score') || lower.includes('health')) {
    if (selectedObj) {
      const scores: Record<string, number> = { 'prd-001': 82, 'design-001': 78, 'adr-001': 91, 'task-001': 70, 'fspec-001': 88, 'fspec-002': 45, 'pr-001': 72, 'incident-001': 40 }
      const score = scores[selectedObj.id] ?? 65
      const label = score >= 80 ? 'Good' : score >= 60 ? 'Needs attention' : 'Critical'
      return { text: `**Quality Score for ${selectedObj.title}: ${score}/100** (${label})\n\nKey signals:\n- **State:** ${selectedObj.state}\n- **Validation:** ${selectedObj.validationStatus}\n- **Staleness:** ${selectedObj.stalenessScore}%\n- **Links:** ${selectedObj.links.length} connected objects\n\nOpen the **Score tab** in the right panel for full charts and trends.` }
    }
    return { text: 'Please select an object in the graph first to see its quality score.' }
  }
  if (lower.startsWith('/explain') || lower.includes('explain') || lower.includes('what is')) {
    if (selectedObj) {
      const typeDescriptions: Record<string, string> = {
        prd: 'a **Product Requirements Document** — defines actors, functional/non-functional requirements, use cases, and success criteria that downstream SDLC artifacts must satisfy.',
        design: 'a **System Design** artifact — specifies components, interfaces, architecture drivers, and constraints. Implementation tasks and PRs must conform to it.',
        adr: 'an **Architecture Decision Record** — documents a significant architectural choice with context, options, decision outcome, and consequences.',
        task: 'a **Development Task** — a concrete unit of implementation work linked to a feature spec and covered by at least one requirement ID.',
        feature_spec: 'a **Feature Specification** — GIVEN/WHEN/THEN flows, algorithms, test scenarios, and Definition of Done for one task scope.',
        pull_request: 'a **Pull Request** — implementation artifact validated against the design. Evidence from pr_design_validator must be attached before merge.',
        incident: 'an **Incident** — a production event requiring root cause analysis, postmortem, and prevention tasks.',
        build: 'a **Build artifact** — CI/CD execution result linked to commits and deployments.',
      }
      return { text: `**${selectedObj.title}** is ${typeDescriptions[selectedObj.typeId] ?? 'a Studio object'}\n\nCurrent state: **${selectedObj.state}** · Validation: **${selectedObj.validationStatus}**\n\n${selectedObj.description ?? ''}` }
    }
    return { text: 'Select an object in the graph to explain it.' }
  }
  if (lower.includes('traceability') || lower.includes('coverage') || lower.includes('trace')) {
    return { text: `**Traceability Coverage Analysis** for ${objName}:\n\nThe current SDLC chain looks like:\n\`\`\`\nPRD (87% covered) → Design (92%) → Tasks (78%) → PRs (80%)\n\`\`\`\n\nGaps detected:\n- R-005 in PRD has no linked test case\n- Invoice Generation feature spec not approved\n- Event-driven pattern (ADR-001) has no code implementation\n\nShall I run \`/trace\` to get a full analysis?`, workerId: undefined }
  }
  if (lower.includes('cost') || lower.includes('spend') || lower.includes('expensive')) {
    return { text: `**AI Cost Summary** for workspace:\n\nTotal spent this month: **$4.82**\n\nBy artifact:\n- task-001 (Stripe Webhook): $1.35 — 5 runs\n- design-001 (Architecture): $0.82 — 5 runs\n- prd-001 (Billing PRD): $0.66 — 4 runs\n- fspec-001 (Stripe Flow): $0.50 — 2 runs\n\nMost expensive worker: **implement_code_worker** ($0.71 avg)\nCheapest: **gap_analysis_validator** ($0.07 avg)` }
  }
  if (lower.includes('help') || lower === '?') {
    return { text: `I'm the **Constructor Studio AI Agent**. I can help you:\n\n**Run workers** — type \`/analyze\`, \`/trace\`, \`/implement\`, \`/design\`, \`/validate\`\n\n**Query the graph** — ask about objects, links, recommendations, costs\n\n**Navigate** — "show me critical issues", "what tasks are in progress?"\n\n**Explain** — "explain this design", "what is a feature spec?"\n\nSelect an object in the graph for context, or just ask!` }
  }
  if (lower.includes('critical') || lower.includes('problem') || lower.includes('issue') || lower.includes('broken')) {
    return { text: `**Critical issues in workspace:**\n\n🔴 **fspec-002** (Invoice Generation Flow) — no test scenarios, missing algo blocks, feature spec not approved\n🔴 **incident-001** (INC-441) — no postmortem, root cause not identified\n🔴 **decomp-001** — tasks missing prd fr[] coverage\n\n⚠️ **task-001** — no traceability markers in source code\n⚠️ **design-001** — event bus pattern not implemented\n\nWould you like me to create a remediation plan?` }
  }
  if (lower.includes('task') && (lower.includes('progress') || lower.includes('status'))) {
    return { text: `**Task status overview:**\n\n- ✅ task-003 (Schema Migration) — **done**\n- 🟡 task-001 (Stripe Webhook) — **in_progress** · PR in review\n- 📋 task-002 (Invoice Generation) — **planned** · no feature spec yet\n\nBlocker: task-002 is waiting on an approved feature spec. Run \`/design\` or \`/decompose\` to unblock it.` }
  }
  if (selectedObj) {
    return { text: `I can see you have **${selectedObj.title}** selected (${selectedObj.typeId}, state: ${selectedObj.state}).\n\nWhat would you like to do? I can:\n- Run \`/analyze\` to check for gaps\n- Run \`/trace\` for traceability coverage\n- Run \`/explain\` for a plain-language summary\n- Show the Score tab for quality metrics` }
  }
  return { text: `I'm your Studio AI agent. Select an object in the graph for context, or ask me about the workspace. Type \`/\` to see available commands.` }
}

// ─── Message components ───────────────────────────────────────────────────────

function StreamingText({ text, onDone }: { text: string; onDone: () => void }) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone] = useState(false)
  const idx = useRef(0)

  useEffect(() => {
    idx.current = 0
    setDisplayed('')
    setDone(false)
    const interval = setInterval(() => {
      idx.current += Math.floor(Math.random() * 4) + 2
      if (idx.current >= text.length) {
        setDisplayed(text)
        setDone(true)
        clearInterval(interval)
        onDone()
      } else {
        setDisplayed(text.slice(0, idx.current))
      }
    }, 18)
    return () => clearInterval(interval)
  }, [text])

  return <FormattedText text={displayed} />
}

function FormattedText({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\n)/g)
  return (
    <span>
      {parts.map((p, i) => {
        if (p === '\n') return <br key={i} />
        if (p.startsWith('**') && p.endsWith('**')) return <strong key={i} style={{ color: '#f4f4f5', fontWeight: 700 }}>{p.slice(2, -2)}</strong>
        if (p.startsWith('`') && p.endsWith('`')) return <code key={i} style={{ fontFamily: 'monospace', fontSize: 11, background: 'rgba(39,39,42,0.8)', color: '#86efac', padding: '1px 5px', borderRadius: 4 }}>{p.slice(1, -1)}</code>
        return <span key={i}>{p}</span>
      })}
    </span>
  )
}

function ToolCard({ toolCall }: { toolCall: ToolCall }) {
  return (
    <div style={{
      background: 'rgba(24,24,27,0.8)', border: `1px solid ${toolCall.status === 'done' ? 'rgba(16,185,129,0.3)' : toolCall.status === 'failed' ? 'rgba(239,68,68,0.3)' : 'rgba(99,102,241,0.3)'}`,
      borderRadius: 8, padding: '8px 12px', marginBottom: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: toolCall.output ? 6 : 0 }}>
        {toolCall.status === 'running' && <Loader2 size={12} color="#6366f1" style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }} />}
        {toolCall.status === 'done' && <CheckCircle2 size={12} color="#10b981" style={{ flexShrink: 0 }} />}
        {toolCall.status === 'failed' && <XCircle size={12} color="#f87171" style={{ flexShrink: 0 }} />}
        <span style={{ fontSize: 11, fontWeight: 600, color: '#d4d4d8' }}>{toolCall.workerLabel}</span>
        {toolCall.objectTitle && <span style={{ fontSize: 10, color: '#71717a' }}>on {toolCall.objectTitle}</span>}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {toolCall.costUsd && <span style={{ fontSize: 10, color: '#a1a1aa' }}>${toolCall.costUsd.toFixed(2)}</span>}
          {toolCall.durationMs && <span style={{ fontSize: 10, color: '#71717a' }}>{(toolCall.durationMs / 1000).toFixed(1)}s</span>}
        </div>
      </div>
      {toolCall.output && (
        <p style={{ fontSize: 11, color: '#a1a1aa', lineHeight: 1.5, borderTop: '1px solid rgba(63,63,70,0.4)', paddingTop: 6, margin: 0 }}>
          {toolCall.output}
        </p>
      )}
    </div>
  )
}

function AssistantBubble({ msg, onStreamDone }: { msg: Message; onStreamDone: (id: string) => void }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', maxWidth: '90%' }}>
      <div style={{
        width: 26, height: 26, borderRadius: 8, background: 'linear-gradient(135deg, #4f46e5, #7c3aed)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 2,
      }}>
        <Cpu size={13} color="#fff" />
      </div>
      <div>
        {msg.toolCall && <ToolCard toolCall={msg.toolCall} />}
        {msg.text && (
          <div style={{
            background: 'rgba(24,24,27,0.7)', border: '1px solid rgba(63,63,70,0.5)',
            borderRadius: '4px 10px 10px 10px', padding: '9px 12px',
            fontSize: 12, color: '#d4d4d8', lineHeight: 1.65,
          }}>
            {msg.streaming
              ? <StreamingText text={msg.text} onDone={() => onStreamDone(msg.id)} />
              : <FormattedText text={msg.text} />
            }
          </div>
        )}
      </div>
    </div>
  )
}

function UserBubble({ msg }: { msg: Message }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', maxWidth: '90%', alignSelf: 'flex-end' }}>
      <div style={{
        background: 'linear-gradient(135deg, rgba(79,70,229,0.3), rgba(99,102,241,0.2))',
        border: '1px solid rgba(99,102,241,0.35)',
        borderRadius: '10px 4px 10px 10px', padding: '9px 12px',
        fontSize: 12, color: '#e4e4e7', lineHeight: 1.5,
      }}>
        {msg.text}
      </div>
    </div>
  )
}

// ─── Slash command palette ────────────────────────────────────────────────────

function CommandPalette({ query, onSelect, onClose }: {
  query: string
  onSelect: (cmd: SlashCommand) => void
  onClose: () => void
}) {
  const filtered = SLASH_COMMANDS.filter(c =>
    c.cmd.includes(query.toLowerCase()) || c.description.toLowerCase().includes(query.toLowerCase())
  )
  if (filtered.length === 0) return null
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 6 }}
      style={{
        position: 'absolute', bottom: '100%', left: 0, right: 0, marginBottom: 4,
        background: '#18181b', border: '1px solid rgba(99,102,241,0.35)',
        borderRadius: 10, overflow: 'hidden',
        boxShadow: '0 -8px 32px rgba(0,0,0,0.5)',
      }}
    >
      <div style={{ padding: '6px 10px', borderBottom: '1px solid rgba(63,63,70,0.4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Commands</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#52525b', padding: 2 }}><X size={11} /></button>
      </div>
      <div style={{ maxHeight: 220, overflowY: 'auto' }}>
        {filtered.map(cmd => (
          <button
            key={cmd.cmd}
            onClick={() => onSelect(cmd)}
            style={{
              display: 'flex', alignItems: 'center', gap: 10, width: '100%',
              padding: '8px 12px', border: 'none', background: 'transparent', cursor: 'pointer', textAlign: 'left',
              transition: 'background 0.1s',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(99,102,241,0.1)' }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
          >
            <span style={{ color: '#818cf8', flexShrink: 0 }}>{cmd.icon}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: '#a5b4fc', display: 'block' }}>{cmd.label}</span>
              <span style={{ fontSize: 10, color: '#71717a' }}>{cmd.description}</span>
            </div>
            {cmd.workerId && (
              <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: 'rgba(99,102,241,0.12)', color: '#6366f1', flexShrink: 0 }}>worker</span>
            )}
          </button>
        ))}
      </div>
    </motion.div>
  )
}

// ─── Main ChatView ────────────────────────────────────────────────────────────

let msgCounter = 1000

function uid() { return `msg-${Date.now()}-${msgCounter++}` }

const WELCOME: Message = {
  id: uid(),
  role: 'assistant',
  kind: 'text',
  text: `Hello! I'm your **Constructor Studio AI Agent**.\n\nI can help you analyze objects, run workers, track recommendations, and navigate the SDLC graph.\n\nSelect an object in the graph for context, or type \`/\` to see available commands.`,
}

export function ChatView() {
  const selectedObjectId = useAppStore(s => s.selectedObjectId)
  const runWorker = useAppStore(s => s.runWorker)
  const objects = useAppStore(s => s.objects)

  const [messages, setMessages] = useState<Message[]>([WELCOME])
  const [input, setInput] = useState('')
  const [showPalette, setShowPalette] = useState(false)
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const selectedObj = selectedObjectId ? objects.find(o => o.id === selectedObjectId) : null

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const addMsg = (msg: Omit<Message, 'id'>) => {
    const m = { ...msg, id: uid() }
    setMessages(prev => [...prev, m])
    return m.id
  }

  const updateMsg = (id: string, patch: Partial<Message>) => {
    setMessages(prev => prev.map(m => m.id === id ? { ...m, ...patch } : m))
  }

  const streamDone = useCallback((id: string) => {
    updateMsg(id, { streaming: false })
  }, [])

  const executeCommand = async (cmd: SlashCommand, fullInput: string) => {
    setLoading(true)

    if (cmd.workerId && selectedObjectId) {
      // Tool use card — show running
      const toolId = addMsg({
        role: 'assistant', kind: 'tool_use',
        toolCall: { workerId: cmd.workerId, workerLabel: cmd.label, status: 'running', objectTitle: selectedObj?.title },
      })

      // Simulate worker execution
      runWorker(cmd.workerId, selectedObjectId)

      await new Promise(r => setTimeout(r, 2200))

      const cost = (Math.random() * 0.3 + 0.05)
      const duration = Math.floor(Math.random() * 4000 + 1500)
      const outputs: Record<string, string> = {
        gap_analysis_validator: `Analysis complete. ${selectedObj?.validationStatus === 'pass' ? 'No critical gaps found.' : 'Found 2 gaps: missing test coverage for R-005, 1 use-case without acceptance criteria.'}`,
        traceability_analysis: 'Traceability chain mapped. Coverage: PRD 87% → Design 92% → Code 80%. 3 broken links found.',
        implement_code_worker: 'Implementation generated. 342 lines, @cpt- markers for all flow IDs. Review suggested.',
        create_design_worker: 'System design created: 6 components, 12 API contracts, 3 Mermaid sequence diagrams.',
        pr_design_validator: 'PR validated against design. ' + (Math.random() > 0.3 ? 'PASS — Evidence attached.' : 'FAIL — 1 finding: missing error handling.'),
        security_impact_analysis: 'Security review complete. No critical vulnerabilities. Recommendation: add rate limiting on webhook endpoint.',
        decompose_feature_worker: 'Decomposed into 4 tasks with dependency order. All tasks have Definition of Done.',
      }
      updateMsg(toolId, {
        toolCall: { workerId: cmd.workerId, workerLabel: cmd.label, status: 'done', objectTitle: selectedObj?.title, output: outputs[cmd.workerId] ?? 'Worker completed successfully.', costUsd: cost, durationMs: duration },
      })

      // Follow-up AI message
      await new Promise(r => setTimeout(r, 300))
      addMsg({
        role: 'assistant', kind: 'text',
        text: `Done! ${outputs[cmd.workerId] ?? 'Worker completed.'}\n\nYou can see full details in the **History tab** of the right panel.`,
        streaming: true,
      })
    } else if (cmd.cmd === '/recs' || cmd.cmd === '/score' || cmd.cmd === '/explain') {
      const { text } = generateResponse(cmd.cmd, selectedObjectId)
      await new Promise(r => setTimeout(r, 600))
      addMsg({ role: 'assistant', kind: 'text', text, streaming: true })
    } else if (cmd.workerId && !selectedObjectId) {
      addMsg({
        role: 'assistant', kind: 'text',
        text: `To run **${cmd.label}**, please select an object in the graph first. Click any node to select it.`,
        streaming: true,
      })
    }

    setLoading(false)
  }

  const handleSubmit = async () => {
    const trimmed = input.trim()
    if (!trimmed || loading) return

    addMsg({ role: 'user', kind: 'text', text: trimmed })
    setInput('')
    setShowPalette(false)
    setLoading(true)

    // Check for slash command
    const cmd = SLASH_COMMANDS.find(c => trimmed.toLowerCase().startsWith(c.cmd))
    if (cmd) {
      await executeCommand(cmd, trimmed)
      return
    }

    // Regular AI response
    await new Promise(r => setTimeout(r, 700 + Math.random() * 500))
    const { text } = generateResponse(trimmed, selectedObjectId)
    addMsg({ role: 'assistant', kind: 'text', text, streaming: true })
    setLoading(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
    if (e.key === 'Escape') setShowPalette(false)
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const v = e.target.value
    setInput(v)
    setShowPalette(v === '/' || (v.startsWith('/') && !v.includes(' ')))
  }

  const handleCommandSelect = (cmd: SlashCommand) => {
    setInput(cmd.cmd + ' ')
    setShowPalette(false)
    inputRef.current?.focus()
  }

  const clearChat = () => setMessages([WELCOME])

  return (
    <div style={{ display: 'flex', flex: 1, flexDirection: 'column', overflow: 'hidden', background: '#09090b' }}>
      {/* Header */}
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid rgba(63,63,70,0.5)', flexShrink: 0,
        display: 'flex', alignItems: 'center', gap: 10, background: 'rgba(9,9,11,0.9)',
      }}>
        <div style={{ width: 28, height: 28, borderRadius: 8, background: 'linear-gradient(135deg, #4f46e5, #7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Cpu size={14} color="#fff" />
        </div>
        <div style={{ flex: 1 }}>
          <p style={{ fontSize: 13, fontWeight: 700, color: '#e4e4e7', margin: 0 }}>Studio AI Agent</p>
          <p style={{ fontSize: 10, color: '#52525b', margin: 0 }}>claude-sonnet-4-6 · Workers: {WORKER_DEFS.length} skills</p>
        </div>
        {selectedObj && (
          <span style={{
            fontSize: 10, padding: '3px 8px', borderRadius: 20,
            background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.3)', color: '#818cf8',
            display: 'flex', alignItems: 'center', gap: 4,
          }}>
            Context: {selectedObj.title.length > 22 ? selectedObj.title.slice(0, 22) + '…' : selectedObj.title}
          </span>
        )}
        <button
          onClick={clearChat}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#52525b', padding: 4, fontSize: 10 }}
          title="Clear chat"
        >
          Clear
        </button>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        {messages.map(msg => (
          <motion.div
            key={msg.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
            style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}
          >
            {msg.role === 'assistant'
              ? <AssistantBubble msg={msg} onStreamDone={streamDone} />
              : <UserBubble msg={msg} />
            }
          </motion.div>
        ))}
        {loading && !messages.find(m => m.streaming) && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <div style={{ width: 26, height: 26, borderRadius: 8, background: 'linear-gradient(135deg, #4f46e5, #7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Cpu size={13} color="#fff" />
            </div>
            <div style={{ display: 'flex', gap: 4, padding: '8px 12px', background: 'rgba(24,24,27,0.7)', border: '1px solid rgba(63,63,70,0.5)', borderRadius: '4px 10px 10px 10px' }}>
              {[0, 1, 2].map(i => (
                <span key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: '#6366f1', display: 'inline-block', animation: `pulse 1.2s ${i * 0.2}s ease-in-out infinite` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Quick command chips */}
      <div style={{ padding: '0 14px 8px', display: 'flex', gap: 5, flexWrap: 'nowrap', overflowX: 'auto' }}>
        {['/analyze', '/trace', '/explain', '/recs', '/score'].map(cmd => {
          const c = SLASH_COMMANDS.find(s => s.cmd === cmd)!
          return (
            <button
              key={cmd}
              onClick={() => { setInput(cmd); handleSubmit() }}
              disabled={loading}
              style={{
                display: 'flex', alignItems: 'center', gap: 4, padding: '3px 9px', borderRadius: 20,
                border: '1px solid rgba(99,102,241,0.25)', background: 'rgba(99,102,241,0.07)',
                color: '#818cf8', fontSize: 11, fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap',
                flexShrink: 0,
              }}
            >
              {c?.icon} {cmd}
            </button>
          )
        })}
      </div>

      {/* Input area */}
      <div style={{ padding: '0 14px 14px', position: 'relative' }}>
        <AnimatePresence>
          {showPalette && (
            <CommandPalette
              query={input.slice(1)}
              onSelect={handleCommandSelect}
              onClose={() => setShowPalette(false)}
            />
          )}
        </AnimatePresence>

        <div style={{
          display: 'flex', alignItems: 'flex-end', gap: 8,
          background: 'rgba(24,24,27,0.9)', border: '1px solid rgba(99,102,241,0.3)',
          borderRadius: 12, padding: '8px 8px 8px 12px',
          boxShadow: '0 0 0 1px rgba(99,102,241,0.1)',
        }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={`Ask anything, or type / for commands…`}
            rows={1}
            disabled={loading}
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none', resize: 'none',
              fontSize: 13, color: '#e4e4e7', lineHeight: 1.5,
              fontFamily: 'inherit', maxHeight: 120, overflowY: 'auto',
            }}
            onInput={e => {
              const el = e.currentTarget
              el.style.height = 'auto'
              el.style.height = Math.min(el.scrollHeight, 120) + 'px'
            }}
          />
          <button
            onClick={handleSubmit}
            disabled={!input.trim() || loading}
            style={{
              width: 32, height: 32, borderRadius: 8, border: 'none', flexShrink: 0,
              background: input.trim() && !loading ? '#4f46e5' : 'rgba(63,63,70,0.4)',
              color: input.trim() && !loading ? '#fff' : '#52525b',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: input.trim() && !loading ? 'pointer' : 'not-allowed',
              transition: 'all 0.15s',
            }}
          >
            {loading ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Send size={14} />}
          </button>
        </div>
        <p style={{ fontSize: 9, color: '#3f3f46', marginTop: 5, textAlign: 'center' }}>
          Enter to send · Shift+Enter for new line · / for commands
        </p>
      </div>
    </div>
  )
}
