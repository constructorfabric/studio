import { useState, useCallback, useMemo, useEffect } from 'react'
import { ReactFlowProvider, ReactFlow, Background, BackgroundVariant, Controls, Handle, Position, type NodeProps, type Node, type Edge } from '@xyflow/react'
import { Play, Square, CheckCircle2, Loader2, AlertTriangle, User, RefreshCw, Zap, GitBranch, Split, MessageSquare, ThumbsUp, ThumbsDown, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../../store/app-store'
import { FLOW_GRAPH_DEFS } from '../../data/mock-data'
import type { FlowGraphDef, FlowGraphNode, FlowNodeExecState, FlowInteractionOption } from '../../types/domain'

// ─── Node exec state styling ──────────────────────────────────────────────────

function nodeExecStyle(state: FlowNodeExecState | undefined): { border: string; bg: string; glow: string } {
  switch (state) {
    case 'running':  return { border: '#6366f1', bg: 'rgba(99,102,241,0.12)', glow: '0 0 0 2px rgba(99,102,241,0.4)' }
    case 'done':     return { border: '#10b981', bg: 'rgba(16,185,129,0.10)', glow: '' }
    case 'passed':   return { border: '#10b981', bg: 'rgba(16,185,129,0.12)', glow: '0 0 12px rgba(16,185,129,0.25)' }
    case 'failed':   return { border: '#ef4444', bg: 'rgba(239,68,68,0.10)', glow: '' }
    case 'retrying': return { border: '#f59e0b', bg: 'rgba(245,158,11,0.12)', glow: '0 0 10px rgba(245,158,11,0.25)' }
    case 'waiting':  return { border: '#a78bfa', bg: 'rgba(167,139,250,0.12)', glow: '0 0 12px rgba(167,139,250,0.3)' }
    default:         return { border: '#3f3f46', bg: 'rgba(24,24,27,0.8)', glow: '' }
  }
}

// ─── Worker Node ──────────────────────────────────────────────────────────────

interface FlowNodeData extends Record<string, unknown> {
  node: FlowGraphNode
  execState?: FlowNodeExecState
  retryCount?: number
}

function WorkerNodeComponent({ data }: NodeProps) {
  const { node, execState, retryCount } = data as FlowNodeData
  const style = nodeExecStyle(execState)
  return (
    <div style={{
      width: 180, minHeight: 64,
      background: style.bg,
      border: `1.5px solid ${style.border}`,
      borderLeft: `4px solid ${style.border}`,
      borderRadius: 8,
      padding: '8px 12px',
      boxShadow: style.glow || '0 2px 8px rgba(0,0,0,0.3)',
      transition: 'all 0.25s ease',
      position: 'relative',
    }}>
      <Handle type="target" position={Position.Top} style={{ background: '#52525b', width: 8, height: 8, border: '2px solid #09090b' }} />

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 9, fontWeight: 700, color: '#a78bfa', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          WORKER
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {execState === 'running' && <Loader2 size={12} color="#6366f1" style={{ animation: 'spin 1s linear infinite' }} />}
          {execState === 'done' && <CheckCircle2 size={12} color="#10b981" />}
          {execState === 'retrying' && (
            <span style={{ fontSize: 9, color: '#f59e0b', fontWeight: 600 }}>↻ {retryCount}×</span>
          )}
        </span>
      </div>

      <p style={{ fontSize: 12, fontWeight: 600, color: '#e4e4e7', lineHeight: 1.3, marginBottom: 2 }}>{node.label}</p>
      {node.sublabel && (
        <p style={{ fontSize: 10, color: '#71717a', marginTop: 2 }}>{node.sublabel}</p>
      )}

      {execState === 'running' && (
        <div style={{ position: 'absolute', inset: 0, borderRadius: 8, border: '1.5px solid rgba(99,102,241,0.4)', animation: 'pulse 1.5s ease-in-out infinite', pointerEvents: 'none' }} />
      )}
      <Handle type="source" position={Position.Bottom} style={{ background: '#52525b', width: 8, height: 8, border: '2px solid #09090b' }} />
    </div>
  )
}
WorkerNodeComponent.displayName = 'WorkerNode'

// ─── Gate Node (Diamond) ──────────────────────────────────────────────────────

function GateNodeComponent({ data }: NodeProps) {
  const { node, execState, retryCount } = data as FlowNodeData
  const style = nodeExecStyle(execState)
  const size = 88

  return (
    <div style={{ width: size, height: size, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      {/* Diamond shape */}
      <div style={{
        width: size * 0.72,
        height: size * 0.72,
        transform: 'rotate(45deg)',
        background: style.bg,
        border: `2px solid ${style.border}`,
        boxShadow: style.glow || '0 2px 8px rgba(0,0,0,0.3)',
        transition: 'all 0.25s ease',
        position: 'absolute',
      }} />
      {/* Label (un-rotated) */}
      <div style={{ position: 'relative', zIndex: 1, textAlign: 'center', padding: '0 4px' }}>
        <p style={{ fontSize: 10, fontWeight: 700, color: execState === 'passed' ? '#10b981' : execState === 'failed' || execState === 'retrying' ? '#f59e0b' : '#e4e4e7', lineHeight: 1.2, whiteSpace: 'nowrap' }}>
          {node.label}
        </p>
        {execState === 'running' && <Loader2 size={10} color="#6366f1" style={{ margin: '2px auto 0', display: 'block', animation: 'spin 1s linear infinite' }} />}
        {execState === 'passed' && <CheckCircle2 size={10} color="#10b981" style={{ margin: '2px auto 0', display: 'block' }} />}
        {execState === 'retrying' && (
          <span style={{ fontSize: 9, color: '#f59e0b', fontWeight: 700, display: 'block', marginTop: 2 }}>retry {retryCount}×</span>
        )}
        {node.maxRetries !== undefined && execState === 'idle' && (
          <span style={{ fontSize: 9, color: '#52525b', display: 'block', marginTop: 1 }}>max {node.maxRetries}×</span>
        )}
      </div>

      {/* Handles */}
      <Handle type="target"  position={Position.Top}    id="in"     style={{ background: '#6366f1', width: 8, height: 8, border: '2px solid #09090b', top: 0 }} />
      <Handle type="source"  position={Position.Bottom} id="pass"   style={{ background: '#10b981', width: 8, height: 8, border: '2px solid #09090b', bottom: 0 }} />
      <Handle type="source"  position={Position.Right}  id="fail"   style={{ background: '#ef4444', width: 8, height: 8, border: '2px solid #09090b', right: 0 }} />
      <Handle type="source"  position={Position.Left}   id="retry"  style={{ background: '#f59e0b', width: 8, height: 8, border: '2px solid #09090b', left: 0 }} />
    </div>
  )
}
GateNodeComponent.displayName = 'GateNode'

// ─── Start Node ───────────────────────────────────────────────────────────────

function StartNodeComponent({ data }: NodeProps) {
  const { node, execState } = data as FlowNodeData
  return (
    <div style={{
      width: 56, height: 56, borderRadius: '50%',
      background: execState === 'done' ? 'rgba(16,185,129,0.2)' : 'rgba(16,185,129,0.1)',
      border: `2px solid ${execState === 'done' ? '#10b981' : '#059669'}`,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      boxShadow: execState === 'done' ? '0 0 12px rgba(16,185,129,0.3)' : 'none',
      transition: 'all 0.25s ease',
    }}>
      <Zap size={14} color="#10b981" />
      <p style={{ fontSize: 8, color: '#6ee7b7', fontWeight: 700, marginTop: 1 }}>{node.label.length > 6 ? 'START' : node.label}</p>
      <Handle type="source" position={Position.Bottom} style={{ background: '#10b981', width: 8, height: 8, border: '2px solid #09090b' }} />
    </div>
  )
}
StartNodeComponent.displayName = 'StartNode'

// ─── End Node ─────────────────────────────────────────────────────────────────

function EndNodeComponent({ data }: NodeProps) {
  const { node, execState } = data as FlowNodeData
  const done = execState === 'done'
  return (
    <div style={{
      width: 60, height: 60, borderRadius: '50%',
      background: done ? 'rgba(16,185,129,0.2)' : 'rgba(39,39,42,0.8)',
      border: `2px solid ${done ? '#10b981' : '#3f3f46'}`,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      boxShadow: done ? '0 0 16px rgba(16,185,129,0.4)' : 'none',
      transition: 'all 0.35s ease',
    }}>
      <Handle type="target" position={Position.Top} style={{ background: '#52525b', width: 8, height: 8, border: '2px solid #09090b' }} />
      {done ? <CheckCircle2 size={16} color="#10b981" /> : <div style={{ width: 12, height: 12, borderRadius: '50%', border: '2px solid #52525b' }} />}
      <p style={{ fontSize: 8, color: done ? '#6ee7b7' : '#52525b', fontWeight: 700, marginTop: 2, textAlign: 'center', maxWidth: 52 }}>
        {node.label.length > 8 ? 'END' : node.label}
      </p>
    </div>
  )
}
EndNodeComponent.displayName = 'EndNode'

// ─── Human Node ──────────────────────────────────────────────────────────────

function HumanNodeComponent({ data }: NodeProps) {
  const { node, execState } = data as FlowNodeData
  const style = nodeExecStyle(execState)
  return (
    <div style={{
      width: 160, minHeight: 60,
      background: execState === 'running' ? 'rgba(139,92,246,0.15)' : 'rgba(109,40,217,0.08)',
      border: `1.5px solid ${execState === 'running' ? '#8b5cf6' : '#6d28d9'}`,
      borderLeft: '4px solid #8b5cf6',
      borderRadius: 8, padding: '8px 12px',
      boxShadow: style.glow || 'none',
      transition: 'all 0.25s ease',
    }}>
      <Handle type="target" position={Position.Top} style={{ background: '#8b5cf6', width: 8, height: 8, border: '2px solid #09090b' }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <User size={12} color="#a78bfa" />
        <span style={{ fontSize: 9, fontWeight: 700, color: '#a78bfa', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Human</span>
        {execState === 'running' && <Loader2 size={10} color="#8b5cf6" style={{ animation: 'spin 1.5s linear infinite' }} />}
        {execState === 'done' && <CheckCircle2 size={10} color="#10b981" />}
      </div>
      <p style={{ fontSize: 11, fontWeight: 600, color: '#e4e4e7' }}>{node.label}</p>
      <Handle type="source" position={Position.Bottom} style={{ background: '#8b5cf6', width: 8, height: 8, border: '2px solid #09090b' }} />
    </div>
  )
}
HumanNodeComponent.displayName = 'HumanNode'

// ─── Escalation Node ──────────────────────────────────────────────────────────

function EscalationNodeComponent({ data }: NodeProps) {
  const { node, execState } = data as FlowNodeData
  const active = execState === 'running' || execState === 'done'
  return (
    <div style={{
      width: 130, minHeight: 54,
      background: active ? 'rgba(239,68,68,0.15)' : 'rgba(239,68,68,0.06)',
      border: `1.5px solid ${active ? '#ef4444' : '#7f1d1d'}`,
      borderLeft: '4px solid #ef4444',
      borderRadius: 8, padding: '7px 10px',
      transition: 'all 0.25s ease',
    }}>
      <Handle type="target" position={Position.Left} style={{ background: '#ef4444', width: 8, height: 8, border: '2px solid #09090b' }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3 }}>
        <AlertTriangle size={11} color="#f87171" />
        <span style={{ fontSize: 9, fontWeight: 700, color: '#f87171', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Escalate</span>
        {execState === 'done' && <CheckCircle2 size={10} color="#f87171" />}
      </div>
      <p style={{ fontSize: 11, fontWeight: 600, color: '#fca5a5' }}>{node.label}</p>
    </div>
  )
}
EscalationNodeComponent.displayName = 'EscalationNode'


// ─── Decision Node (rhombus with multiple outputs) ────────────────────────────

function DecisionNodeComponent({ data }: NodeProps) {
  const { node, execState } = data as FlowNodeData
  const style = nodeExecStyle(execState)
  const size = 100
  const isWaiting = execState === 'waiting'
  return (
    <div style={{ width: size, height: size, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{
        width: size * 0.72, height: size * 0.72, transform: 'rotate(45deg)',
        background: isWaiting ? 'rgba(167,139,250,0.18)' : style.bg,
        border: `2px solid ${isWaiting ? '#a78bfa' : style.border}`,
        boxShadow: style.glow || '0 2px 8px rgba(0,0,0,0.3)',
        transition: 'all 0.25s ease', position: 'absolute',
      }} />
      <div style={{ position: 'relative', zIndex: 1, textAlign: 'center', padding: '0 4px' }}>
        <Split size={11} color={isWaiting ? '#c4b5fd' : '#a1a1aa'} style={{ display: 'block', margin: '0 auto 2px' }} />
        <p style={{ fontSize: 9, fontWeight: 700, color: isWaiting ? '#c4b5fd' : '#e4e4e7', lineHeight: 1.2, whiteSpace: 'nowrap' }}>
          {node.label}
        </p>
        {isWaiting && <p style={{ fontSize: 8, color: '#a78bfa', marginTop: 1 }}>choose</p>}
        {execState === 'running' && <Loader2 size={9} color="#6366f1" style={{ display: 'block', margin: '2px auto 0', animation: 'spin 1s linear infinite' }} />}
        {execState === 'done' && <CheckCircle2 size={9} color="#10b981" style={{ display: 'block', margin: '2px auto 0' }} />}
      </div>
      <Handle type="target"  position={Position.Top}    id="in"    style={{ background: '#a78bfa', width: 8, height: 8, border: '2px solid #09090b', top: 0 }} />
      <Handle type="source"  position={Position.Bottom} id="out-1" style={{ background: '#10b981', width: 8, height: 8, border: '2px solid #09090b', bottom: 0 }} />
      <Handle type="source"  position={Position.Left}   id="out-2" style={{ background: '#22d3ee', width: 8, height: 8, border: '2px solid #09090b', left: 0 }} />
      <Handle type="source"  position={Position.Right}  id="out-3" style={{ background: '#f59e0b', width: 8, height: 8, border: '2px solid #09090b', right: 0 }} />
    </div>
  )
}
DecisionNodeComponent.displayName = 'DecisionNode'

// ─── Node Types Map ───────────────────────────────────────────────────────────

const nodeTypes = {
  workerNode:     WorkerNodeComponent,
  gateNode:       GateNodeComponent,
  startNode:      StartNodeComponent,
  endNode:        EndNodeComponent,
  humanNode:      HumanNodeComponent,
  escalationNode: EscalationNodeComponent,
  decisionNode:   DecisionNodeComponent,
}

function flowNodeTypeKey(nodeType: string): string {
  const map: Record<string, string> = {
    worker: 'workerNode', gate: 'gateNode', start: 'startNode',
    end: 'endNode', human: 'humanNode', escalation: 'escalationNode', decision: 'decisionNode',
  }
  return map[nodeType] ?? 'workerNode'
}

// ─── Edge styling ─────────────────────────────────────────────────────────────

function buildEdgeStyle(edgeKind: string): Partial<Edge> {
  switch (edgeKind) {
    case 'pass':   return { style: { stroke: '#10b981', strokeWidth: 2 }, labelStyle: { fill: '#10b981', fontSize: 9 }, labelBgStyle: { fill: '#09090b', fillOpacity: 0.9 }, labelBgPadding: [2, 4] as [number, number] }
    case 'fail':   return { style: { stroke: '#ef4444', strokeWidth: 1.5, strokeDasharray: '5 3' }, labelStyle: { fill: '#f87171', fontSize: 9 }, labelBgStyle: { fill: '#09090b', fillOpacity: 0.9 }, labelBgPadding: [2, 4] as [number, number] }
    case 'retry':  return { style: { stroke: '#f59e0b', strokeWidth: 1.5, strokeDasharray: '6 3' }, animated: true, labelStyle: { fill: '#fbbf24', fontSize: 9 }, labelBgStyle: { fill: '#09090b', fillOpacity: 0.9 }, labelBgPadding: [2, 4] as [number, number] }
    default:       return { style: { stroke: '#52525b', strokeWidth: 1.5 }, labelStyle: { fill: '#71717a', fontSize: 9 } }
  }
}

// ─── Flow Graph component ─────────────────────────────────────────────────────

function FlowGraph({ flow }: { flow: FlowGraphDef }) {
  const flowExecState = useAppStore(s => s.flowExecState)
  const exec = flowExecState?.flowId === flow.id ? flowExecState : null

  const nodes: Node[] = useMemo(() => flow.nodes.map(n => ({
    id: n.id,
    type: flowNodeTypeKey(n.nodeType),
    position: n.position,
    data: {
      node: n,
      execState: (exec?.pendingInteraction?.nodeId === n.id ? 'waiting' : exec?.nodeStates[n.id]) ?? 'idle',
      retryCount: exec?.retryCounters[n.id] ?? 0,
    } satisfies FlowNodeData,
    draggable: false,
  })), [flow, exec])

  const edges: Edge[] = useMemo(() => flow.edges.map(e => ({
    id: e.id,
    source: e.source,
    target: e.target,
    sourceHandle: e.edgeKind === 'pass' ? 'pass' : e.edgeKind === 'fail' ? 'fail' : e.edgeKind === 'retry' ? 'retry' : undefined,
    label: e.label,
    type: e.edgeKind === 'retry' ? 'smoothstep' : 'smoothstep',
    ...buildEdgeStyle(e.edgeKind),
  })), [flow])

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.3}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        panOnDrag
        zoomOnScroll
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#27272a" />
        <Controls />
      </ReactFlow>
      <FlowInteractionModal />
    </div>
  )
}

// ─── Flow Card ────────────────────────────────────────────────────────────────

function FlowCard({ flow, selected, onSelect }: { flow: FlowGraphDef; selected: boolean; onSelect: () => void }) {
  const flowExecState = useAppStore(s => s.flowExecState)
  const startFlowGraph = useAppStore(s => s.startFlowGraph)
  const stopFlowGraph = useAppStore(s => s.stopFlowGraph)

  const exec = flowExecState?.flowId === flow.id ? flowExecState : null
  const isRunning = exec?.status === 'running'
  const isDone = exec?.status === 'done'

  const gateCount = flow.nodes.filter(n => n.nodeType === 'gate').length
  const workerCount = flow.nodes.filter(n => n.nodeType === 'worker').length

  const categoryColor: Record<string, string> = {
    sdlc: 'text-indigo-400 bg-indigo-900/30 border-indigo-700/40',
    ops:  'text-amber-400 bg-amber-900/30 border-amber-700/40',
  }

  return (
    <button
      onClick={onSelect}
      className="w-full text-left"
    >
      <div style={{
        padding: '10px 12px',
        borderRadius: 10,
        border: selected ? '1.5px solid rgba(99,102,241,0.6)' : '1px solid rgba(63,63,70,0.6)',
        background: selected ? 'rgba(99,102,241,0.08)' : 'rgba(24,24,27,0.6)',
        marginBottom: 6,
        transition: 'all 0.15s ease',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
              <GitBranch size={12} color={selected ? '#818cf8' : '#71717a'} />
              <span style={{ fontSize: 12, fontWeight: 600, color: selected ? '#e4e4e7' : '#a1a1aa' }}>{flow.name}</span>
              {isRunning && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#6366f1', display: 'inline-block', animation: 'pulse 1s ease-in-out infinite' }} />}
              {isDone && <CheckCircle2 size={11} color="#10b981" />}
            </div>
            <p style={{ fontSize: 10, color: '#71717a', lineHeight: 1.4, marginBottom: 6 }}>{flow.description}</p>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${categoryColor[flow.category] ?? 'text-zinc-400 bg-zinc-800 border-zinc-700'}`}>{flow.category}</span>
              <span style={{ fontSize: 10, color: '#52525b' }}>{workerCount} workers</span>
              <span style={{ fontSize: 10, color: '#52525b' }}>·</span>
              <span style={{ fontSize: 10, color: '#f59e0b' }}>{gateCount} gates</span>
            </div>
          </div>
        </div>

        {/* Run / Stop buttons */}
        <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
          {isRunning ? (
            <button
              onClick={e => { e.stopPropagation(); stopFlowGraph() }}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', borderRadius: 6, border: '1px solid #52525b',
                background: 'rgba(63,63,70,0.5)', color: '#a1a1aa',
                fontSize: 11, fontWeight: 600, cursor: 'pointer',
              }}
            >
              <Square size={11} /> Stop
            </button>
          ) : (
            <button
              onClick={e => { e.stopPropagation(); startFlowGraph(flow.id) }}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', borderRadius: 6, border: 'none',
                background: selected ? '#4f46e5' : '#27272a', color: selected ? '#fff' : '#a1a1aa',
                fontSize: 11, fontWeight: 600, cursor: 'pointer',
                boxShadow: selected ? '0 2px 8px rgba(79,70,229,0.4)' : 'none',
              }}
            >
              <Play size={11} /> {isDone ? 'Re-run' : 'Run'}
            </button>
          )}
          {isDone && !isRunning && (
            <span style={{ fontSize: 10, color: '#10b981', display: 'flex', alignItems: 'center', gap: 3 }}>
              <CheckCircle2 size={11} /> Done
            </span>
          )}
        </div>
      </div>
    </button>
  )
}

// ─── Artifacts strip ──────────────────────────────────────────────────────────

function ArtifactsStrip({ flowId }: { flowId: string }) {
  const flowExecState = useAppStore(s => s.flowExecState)
  const exec = flowExecState?.flowId === flowId ? flowExecState : null
  if (!exec || exec.producedArtifacts.length === 0) return null

  const elapsed = exec.status === 'done'
    ? Math.round((Date.now() - exec.startedAt) / 100) / 10
    : null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          padding: '8px 14px',
          borderTop: '1px solid rgba(63,63,70,0.6)',
          background: 'rgba(9,9,11,0.8)',
          display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
        }}
      >
        <span style={{ fontSize: 10, color: '#52525b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
          Artifacts
        </span>
        {exec.producedArtifacts.map((a, i) => (
          <span key={i} style={{
            fontSize: 10, padding: '2px 8px', borderRadius: 20,
            background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.3)',
            color: '#a5b4fc', fontWeight: 500, whiteSpace: 'nowrap',
          }}>
            {a.label}
          </span>
        ))}
        {exec.status === 'running' && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#6366f1', marginLeft: 'auto' }}>
            <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} /> Running…
          </span>
        )}
        {elapsed !== null && (
          <span style={{ fontSize: 10, color: '#52525b', marginLeft: 'auto' }}>
            ✓ {elapsed}s
          </span>
        )}
      </motion.div>
    </AnimatePresence>
  )
}

// ─── Legend ───────────────────────────────────────────────────────────────────

function Legend() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '6px 14px', borderTop: '1px solid rgba(63,63,70,0.4)', fontSize: 10, color: '#52525b' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <span style={{ width: 20, height: 2, background: '#52525b', display: 'inline-block' }} /> default
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <span style={{ width: 20, height: 2, background: '#10b981', display: 'inline-block' }} /> PASS
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <span style={{ width: 20, height: 2, background: '#ef4444', borderTop: '2px dashed #ef4444', display: 'inline-block' }} /> FAIL
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <RefreshCw size={10} color="#f59e0b" /> retry loop
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <span style={{ width: 12, height: 12, transform: 'rotate(45deg)', border: '1.5px solid #f59e0b', display: 'inline-block', marginRight: 2 }} /> gate
      </span>
    </div>
  )
}


// ─── Flow Interaction Modal ───────────────────────────────────────────────────

function FlowInteractionModal() {
  const flowExecState = useAppStore(s => s.flowExecState)
  const respondToFlowInteraction = useAppStore(s => s.respondToFlowInteraction)
  const [textInput, setTextInput] = useState('')

  const pending = flowExecState?.pendingInteraction
  if (!pending) return null

  const { interaction } = pending
  const isApproval = interaction.kind === 'approval'
  const isMenu = interaction.kind === 'menu'
  const isInput = interaction.kind === 'input'

  const handleChoice = (optionId: string) => {
    respondToFlowInteraction(optionId, textInput || undefined)
    setTextInput('')
  }

  const optionColors: Record<string, string> = {
    '#10b981': 'rgba(16,185,129,0.15)', '#60a5fa': 'rgba(96,165,250,0.15)',
    '#f59e0b': 'rgba(245,158,11,0.12)', '#f87171': 'rgba(248,113,113,0.12)',
    '#818cf8': 'rgba(129,140,248,0.15)', '#22d3ee': 'rgba(34,211,238,0.12)',
    '#a78bfa': 'rgba(167,139,250,0.15)',
  }

  return (
    <AnimatePresence>
      <div style={{
        position: 'absolute', inset: 0, zIndex: 60,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.45)', backdropFilter: 'blur(3px)',
        pointerEvents: 'all',
      }}>
        <motion.div
          initial={{ opacity: 0, scale: 0.94, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.94 }}
          transition={{ duration: 0.15 }}
          style={{
            background: '#111113', border: '1px solid rgba(167,139,250,0.4)',
            borderRadius: 14, padding: '18px 20px', maxWidth: 440, width: '90%',
            boxShadow: '0 24px 60px rgba(0,0,0,0.7), 0 0 0 1px rgba(167,139,250,0.15)',
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <div style={{ width: 28, height: 28, borderRadius: 8, background: 'rgba(167,139,250,0.2)', border: '1px solid rgba(167,139,250,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {isApproval ? <ThumbsUp size={13} color="#a78bfa" /> : isInput ? <MessageSquare size={13} color="#a78bfa" /> : <Split size={13} color="#a78bfa" />}
            </div>
            <div>
              <p style={{ fontSize: 11, fontWeight: 700, color: '#c4b5fd', textTransform: 'uppercase', letterSpacing: '0.06em', margin: 0 }}>
                {isApproval ? 'Approval Required' : isInput ? 'Input Required' : 'Worker Interaction'}
              </p>
            </div>
          </div>

          <p style={{ fontSize: 13, color: '#d4d4d8', lineHeight: 1.55, marginBottom: 14 }}>
            {interaction.prompt}
          </p>

          {/* Options */}
          {(isMenu || isApproval) && interaction.options && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {interaction.options.map(opt => (
                <button
                  key={opt.id}
                  onClick={() => handleChoice(opt.id)}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 12px',
                    borderRadius: 8, cursor: 'pointer', textAlign: 'left', border: 'none',
                    background: opt.color ? (optionColors[opt.color] ?? 'rgba(63,63,70,0.3)') : 'rgba(39,39,42,0.6)',
                    borderLeft: `3px solid ${opt.color ?? '#52525b'}`,
                    transition: 'all 0.12s',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.filter = 'brightness(1.25)' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.filter = 'brightness(1)' }}
                >
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: 12, fontWeight: 700, color: opt.color ?? '#d4d4d8', margin: 0, marginBottom: opt.description ? 2 : 0 }}>{opt.label}</p>
                    {opt.description && <p style={{ fontSize: 11, color: '#71717a', margin: 0, lineHeight: 1.4 }}>{opt.description}</p>}
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Text input */}
          {isInput && (
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                value={textInput}
                onChange={e => setTextInput(e.target.value)}
                placeholder={interaction.inputPlaceholder ?? 'Enter response…'}
                onKeyDown={e => e.key === 'Enter' && textInput.trim() && handleChoice('submit')}
                style={{
                  flex: 1, padding: '8px 10px', background: 'rgba(24,24,27,0.8)',
                  border: '1px solid rgba(167,139,250,0.35)', borderRadius: 7,
                  color: '#e4e4e7', fontSize: 13, outline: 'none',
                }}
                autoFocus
              />
              <button
                onClick={() => textInput.trim() && handleChoice('submit')}
                style={{
                  padding: '8px 14px', borderRadius: 7, border: 'none',
                  background: '#7c3aed', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                }}
              >
                Submit
              </button>
            </div>
          )}
        </motion.div>
      </div>
    </AnimatePresence>
  )
}

// ─── Main FlowsView ───────────────────────────────────────────────────────────

export function FlowsView() {
  const [selectedFlowId, setSelectedFlowId] = useState<string>(FLOW_GRAPH_DEFS[0].id)
  const selectedFlow = FLOW_GRAPH_DEFS.find(f => f.id === selectedFlowId) ?? FLOW_GRAPH_DEFS[0]

  const handleSelect = useCallback((id: string) => setSelectedFlowId(id), [])

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
      {/* Left: flow list */}
      <div style={{
        width: 260, flexShrink: 0,
        borderRight: '1px solid rgba(63,63,70,0.6)',
        background: 'rgba(9,9,11,0.5)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid rgba(63,63,70,0.4)' }}>
          <h2 style={{ fontSize: 13, fontWeight: 700, color: '#e4e4e7', marginBottom: 2 }}>Flows</h2>
          <p style={{ fontSize: 10, color: '#71717a' }}>State machine pipelines with validator gates</p>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 10px' }}>
          {FLOW_GRAPH_DEFS.map(flow => (
            <FlowCard key={flow.id} flow={flow} selected={selectedFlowId === flow.id} onSelect={() => handleSelect(flow.id)} />
          ))}
        </div>
      </div>

      {/* Right: graph */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <ReactFlowProvider>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <FlowGraph key={selectedFlowId} flow={selectedFlow} />
          </div>
        </ReactFlowProvider>
        <ArtifactsStrip flowId={selectedFlowId} />
        <Legend />
      </div>
    </div>
  )
}
