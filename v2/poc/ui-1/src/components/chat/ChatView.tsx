import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Cpu, Loader2, CheckCircle2, XCircle, ChevronDown, Zap, AlertTriangle, GitBranch, FileText, Search, Wrench, TestTube2, Link2, X, Settings2, MessageSquare, ChevronRight } from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import { WORKER_DEFS, MOCK_RECOMMENDATIONS, MOCK_OBJECTS } from '../../data/mock-data'

// ─── Chat config types ────────────────────────────────────────────────────────

type ModelId = 'claude-sonnet-4-6' | 'claude-opus-4-8' | 'claude-haiku-4-5'
type ChatMode = 'normal' | 'extended_thinking' | 'code_focus' | 'autonomous'
type ReasoningEffort = 'low' | 'medium' | 'high' | 'max'
type ContextWindow = '8k' | '32k' | '200k' | '1m'

interface ChatConfig {
  model: ModelId
  mode: ChatMode
  effort: ReasoningEffort
  context: ContextWindow
}

const MODELS: { id: ModelId; label: string; description: string; tier: 'fast' | 'balanced' | 'powerful' }[] = [
  { id: 'claude-haiku-4-5',  label: 'Haiku 4.5',  description: 'Fastest, lowest cost',     tier: 'fast' },
  { id: 'claude-sonnet-4-6', label: 'Sonnet 4.6',  description: 'Balanced speed & quality', tier: 'balanced' },
  { id: 'claude-opus-4-8',   label: 'Opus 4.8',    description: 'Most capable, slowest',    tier: 'powerful' },
]

const MODES: { id: ChatMode; label: string; description: string }[] = [
  { id: 'normal',           label: 'Normal',           description: 'Standard responses' },
  { id: 'extended_thinking', label: 'Extended Thinking', description: 'Visible reasoning chain' },
  { id: 'code_focus',       label: 'Code Focus',        description: 'Optimised for code tasks' },
  { id: 'autonomous',       label: 'Autonomous',        description: 'Agent acts without confirmation' },
]

const EFFORTS: { id: ReasoningEffort; label: string; tokens: string }[] = [
  { id: 'low',    label: 'Low',    tokens: '~1k' },
  { id: 'medium', label: 'Medium', tokens: '~8k' },
  { id: 'high',   label: 'High',   tokens: '~32k' },
  { id: 'max',    label: 'Max',    tokens: '~64k' },
]

const CONTEXTS: { id: ContextWindow; label: string; description: string }[] = [
  { id: '8k',   label: '8k',   description: 'Light — quick tasks' },
  { id: '32k',  label: '32k',  description: 'Standard' },
  { id: '200k', label: '200k', description: 'Large — full codebase' },
  { id: '1m',   label: '1M',   description: 'Maximum — entire repo' },
]

const DEFAULT_CONFIG: ChatConfig = { model: 'claude-sonnet-4-6', mode: 'normal', effort: 'medium', context: '32k' }

// ─── Config Tab ───────────────────────────────────────────────────────────────

function ConfigTab({ config, onChange }: { config: ChatConfig; onChange: (c: ChatConfig) => void }) {
  function Section({ title, children }: { title: string; children: React.ReactNode }) {
    return (
      <div style={{ marginBottom: 20 }}>
        <p style={{ fontSize: 10, fontWeight: 700, color: '#52525b', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>{title}</p>
        {children}
      </div>
    )
  }

  function OptionGrid<T extends string>({ items, value, onChange: onChg, renderLabel }: {
    items: { id: T; label: string; description?: string }[]
    value: T
    onChange: (v: T) => void
    renderLabel?: (item: { id: T; label: string; description?: string }) => React.ReactNode
  }) {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(items.length, 2)}, 1fr)`, gap: 6 }}>
        {items.map(item => (
          <button
            key={item.id}
            onClick={() => onChg(item.id)}
            style={{
              padding: '8px 10px', borderRadius: 8, border: `1px solid ${value === item.id ? 'rgba(99,102,241,0.6)' : 'rgba(63,63,70,0.5)'}`,
              background: value === item.id ? 'rgba(99,102,241,0.12)' : 'rgba(24,24,27,0.6)',
              cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
            }}
          >
            {renderLabel ? renderLabel(item) : (
              <>
                <p style={{ fontSize: 12, fontWeight: 600, color: value === item.id ? '#a5b4fc' : '#d4d4d8', margin: 0 }}>{item.label}</p>
                {item.description && <p style={{ fontSize: 10, color: '#71717a', margin: '2px 0 0' }}>{item.description}</p>}
              </>
            )}
          </button>
        ))}
      </div>
    )
  }

  const tierColor = { fast: '#10b981', balanced: '#6366f1', powerful: '#f59e0b' }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
      <Section title="Model">
        <OptionGrid
          items={MODELS}
          value={config.model}
          onChange={m => onChange({ ...config, model: m })}
          renderLabel={item => (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: tierColor[(item as typeof MODELS[0]).tier], display: 'inline-block', flexShrink: 0 }} />
                <p style={{ fontSize: 12, fontWeight: 600, color: config.model === item.id ? '#a5b4fc' : '#d4d4d8', margin: 0 }}>{item.label}</p>
              </div>
              <p style={{ fontSize: 10, color: '#71717a', margin: 0 }}>{item.description}</p>
            </>
          )}
        />
      </Section>

      <Section title="Mode">
        <OptionGrid items={MODES} value={config.mode} onChange={m => onChange({ ...config, mode: m })} />
      </Section>

      <Section title="Reasoning Effort">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
          {EFFORTS.map(e => (
            <button
              key={e.id}
              onClick={() => onChange({ ...config, effort: e.id })}
              style={{
                padding: '7px 6px', borderRadius: 8, border: `1px solid ${config.effort === e.id ? 'rgba(99,102,241,0.6)' : 'rgba(63,63,70,0.5)'}`,
                background: config.effort === e.id ? 'rgba(99,102,241,0.12)' : 'rgba(24,24,27,0.6)',
                cursor: 'pointer', textAlign: 'center', transition: 'all 0.15s',
              }}
            >
              <p style={{ fontSize: 11, fontWeight: 600, color: config.effort === e.id ? '#a5b4fc' : '#d4d4d8', margin: 0 }}>{e.label}</p>
              <p style={{ fontSize: 9, color: '#52525b', margin: '2px 0 0' }}>{e.tokens}</p>
            </button>
          ))}
        </div>
        {(config.effort === 'high' || config.effort === 'max') && (
          <p style={{ fontSize: 10, color: '#f59e0b', marginTop: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
            ⚠ Higher effort increases latency and cost
          </p>
        )}
      </Section>

      <Section title="Context Window">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
          {CONTEXTS.map(c => (
            <button
              key={c.id}
              onClick={() => onChange({ ...config, context: c.id })}
              style={{
                padding: '7px 6px', borderRadius: 8, border: `1px solid ${config.context === c.id ? 'rgba(16,185,129,0.5)' : 'rgba(63,63,70,0.5)'}`,
                background: config.context === c.id ? 'rgba(16,185,129,0.1)' : 'rgba(24,24,27,0.6)',
                cursor: 'pointer', textAlign: 'center', transition: 'all 0.15s',
              }}
            >
              <p style={{ fontSize: 11, fontWeight: 700, color: config.context === c.id ? '#6ee7b7' : '#d4d4d8', margin: 0 }}>{c.label}</p>
              <p style={{ fontSize: 9, color: '#52525b', margin: '2px 0 0' }}>{c.description}</p>
            </button>
          ))}
        </div>
      </Section>

      {/* Summary */}
      <div style={{ padding: '10px 12px', background: 'rgba(24,24,27,0.6)', borderRadius: 8, border: '1px solid rgba(63,63,70,0.4)' }}>
        <p style={{ fontSize: 10, color: '#52525b', margin: '0 0 6px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Current Config</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {[
            { label: MODELS.find(m => m.id === config.model)?.label ?? config.model, color: '#818cf8' },
            { label: MODES.find(m => m.id === config.mode)?.label ?? config.mode, color: '#a78bfa' },
            { label: `Effort: ${config.effort}`, color: '#6ee7b7' },
            { label: `${config.context} ctx`, color: '#fbbf24' },
          ].map(b => (
            <span key={b.label} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: `${b.color}15`, border: `1px solid ${b.color}30`, color: b.color }}>
              {b.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

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

type ChatTab = 'chat' | 'config'

export function ChatView() {
  const selectedObjectId = useAppStore(s => s.selectedObjectId)
  const runWorker = useAppStore(s => s.runWorker)
  const objects = useAppStore(s => s.objects)

  const [tab, setTab] = useState<ChatTab>('chat')
  const [config, setConfig] = useState<ChatConfig>(DEFAULT_CONFIG)
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

  const currentModel = MODELS.find(m => m.id === config.model)
  const tierColor = { fast: '#10b981', balanced: '#6366f1', powerful: '#f59e0b' }

  return (
    <div style={{ display: 'flex', flex: 1, flexDirection: 'column', overflow: 'hidden', background: '#09090b' }}>
      {/* Header */}
      <div style={{
        padding: '8px 12px 0', borderBottom: '1px solid rgba(63,63,70,0.5)', flexShrink: 0,
        background: 'rgba(9,9,11,0.95)',
      }}>
        {/* Top row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <div style={{ width: 26, height: 26, borderRadius: 7, background: 'linear-gradient(135deg, #4f46e5, #7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <Cpu size={13} color="#fff" />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 12, fontWeight: 700, color: '#e4e4e7', margin: 0 }}>Studio AI</p>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: tierColor[currentModel?.tier ?? 'balanced'], display: 'inline-block' }} />
              <span style={{ fontSize: 9, color: '#71717a' }}>{currentModel?.label}</span>
              <span style={{ fontSize: 9, color: '#3f3f46' }}>·</span>
              <span style={{ fontSize: 9, color: '#71717a', textTransform: 'capitalize' }}>{config.mode.replace('_', ' ')}</span>
              <span style={{ fontSize: 9, color: '#3f3f46' }}>·</span>
              <span style={{ fontSize: 9, color: '#71717a' }}>effort:{config.effort}</span>
              <span style={{ fontSize: 9, color: '#3f3f46' }}>·</span>
              <span style={{ fontSize: 9, color: '#71717a' }}>{config.context} ctx</span>
            </div>
          </div>
          {selectedObj && (
            <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 20, background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.3)', color: '#818cf8', flexShrink: 0, maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {selectedObj.title.length > 14 ? selectedObj.title.slice(0, 14) + '…' : selectedObj.title}
            </span>
          )}
          {tab === 'chat' && (
            <button onClick={clearChat} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#52525b', padding: '2px 4px', fontSize: 10 }} title="Clear">
              Clear
            </button>
          )}
        </div>
        {/* Tabs */}
        <div style={{ display: 'flex', gap: 0 }}>
          {([['chat', 'Chat', MessageSquare], ['config', 'Config', Settings2]] as const).map(([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 5, padding: '5px 12px',
                background: 'none', border: 'none', cursor: 'pointer',
                borderBottom: `2px solid ${tab === id ? '#6366f1' : 'transparent'}`,
                color: tab === id ? '#818cf8' : '#52525b',
                fontSize: 11, fontWeight: tab === id ? 600 : 400,
                transition: 'all 0.15s',
              }}
            >
              <Icon size={11} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Config tab */}
      {tab === 'config' && <ConfigTab config={config} onChange={setConfig} />}

      {/* Messages */}
      {tab === 'chat' && <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
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
      </div>}

      {/* Chat tab — quick chips + input */}
      {tab === 'chat' && (
        <>
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
                placeholder="Ask anything, or type / for commands…"
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
              Enter · Shift+Enter new line · / commands · {currentModel?.label} · {config.effort} effort
            </p>
          </div>
        </>
      )}
    </div>
  )
}
