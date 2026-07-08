import { useState, useCallback, useRef, type DragEvent } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type Node,
  type Edge,
  type OnConnect,
  useReactFlow,
  Handle,
  Position,
  type NodeProps,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { ArrowLeft, Plus, Trash2, Save, GripVertical, Pencil } from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import { WORKER_DEFS } from '../../data/mock-data'
import type {
  FlowGraphDef,
  FlowGraphNode,
  FlowGraphEdge,
  FlowDef,
  FlowStep,
  WorkerDef,
  FlowEdgeKind,
} from '../../types/domain'

// ─── Types ────────────────────────────────────────────────────────────────────

interface DesignerNodeData extends Record<string, unknown> {
  nodeType: 'start' | 'end' | 'worker' | 'gate' | 'human'
  label: string
  workerId?: string
  workerProfile?: string
  maxRetries?: number
}

interface FlowDesignerProps {
  existingFlowId?: string
  onSave: (savedFlowId: string) => void
  onCancel: () => void
}

// ─── Edge kind cycling ────────────────────────────────────────────────────────

const EDGE_KIND_CYCLE: FlowEdgeKind[] = ['default', 'pass', 'fail']

function nextEdgeKind(current: FlowEdgeKind): FlowEdgeKind {
  const idx = EDGE_KIND_CYCLE.indexOf(current as 'default' | 'pass' | 'fail')
  return EDGE_KIND_CYCLE[(idx + 1) % EDGE_KIND_CYCLE.length]
}

function edgeKindColor(kind: FlowEdgeKind): string {
  if (kind === 'pass') return '#10b981'
  if (kind === 'fail') return '#ef4444'
  return '#71717a'
}

// ─── Custom Edge ──────────────────────────────────────────────────────────────

function DesignerEdge({
  id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data,
}: EdgeProps) {
  const edgeKind: FlowEdgeKind = (data?.edgeKind as FlowEdgeKind) ?? 'default'
  const color = edgeKindColor(edgeKind)
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition })
  const { setEdges } = useReactFlow()

  const cycleKind = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    setEdges(edges =>
      edges.map(ed => ed.id === id
        ? { ...ed, data: { ...ed.data, edgeKind: nextEdgeKind(edgeKind) } }
        : ed
      )
    )
  }, [id, edgeKind, setEdges])

  return (
    <>
      <BaseEdge path={edgePath} style={{ stroke: color, strokeWidth: 1.5 }} />
      <EdgeLabelRenderer>
        <div
          onClick={cycleKind}
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
            cursor: 'pointer',
            background: '#18181b',
            border: `1px solid ${color}`,
            borderRadius: 4,
            padding: '1px 5px',
            fontSize: 9,
            fontWeight: 600,
            color,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            userSelect: 'none',
          }}
        >
          {edgeKind}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

// ─── Custom Node ──────────────────────────────────────────────────────────────

function DesignerNode({ data, selected }: NodeProps) {
  const nd = data as DesignerNodeData
  const isStartEnd = nd.nodeType === 'start' || nd.nodeType === 'end'
  const isGate = nd.nodeType === 'gate'

  const borderColor = isStartEnd
    ? '#6366f1'
    : isGate
    ? '#f59e0b'
    : nd.nodeType === 'human'
    ? '#38bdf8'
    : '#a78bfa'

  const nodeTypeBadge = nd.nodeType.toUpperCase()

  if (isStartEnd) {
    return (
      <div style={{
        width: 64, height: 64, borderRadius: '50%',
        background: selected ? 'rgba(99,102,241,0.18)' : 'rgba(24,24,27,0.9)',
        border: `2px solid ${selected ? '#818cf8' : borderColor}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: selected ? '0 0 0 2px rgba(99,102,241,0.3)' : '0 2px 8px rgba(0,0,0,0.4)',
        transition: 'all 0.15s',
        position: 'relative',
      }}>
        {nd.nodeType === 'end' && (
          <Handle type="target" position={Position.Left} style={{ background: '#52525b', width: 8, height: 8, border: '2px solid #09090b' }} />
        )}
        <span style={{ fontSize: 10, fontWeight: 700, color: '#c4b5fd', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {nd.label}
        </span>
        {nd.nodeType === 'start' && (
          <Handle type="source" position={Position.Right} style={{ background: '#52525b', width: 8, height: 8, border: '2px solid #09090b' }} />
        )}
      </div>
    )
  }

  if (isGate) {
    return (
      <div style={{
        width: 80, height: 80,
        transform: 'rotate(45deg)',
        background: selected ? 'rgba(245,158,11,0.18)' : 'rgba(24,24,27,0.9)',
        border: `2px solid ${selected ? '#fbbf24' : borderColor}`,
        boxShadow: selected ? '0 0 0 2px rgba(245,158,11,0.3)' : '0 2px 8px rgba(0,0,0,0.4)',
        transition: 'all 0.15s',
        position: 'relative',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Handle type="target" position={Position.Left} style={{ background: '#52525b', width: 8, height: 8, border: '2px solid #09090b', left: -5 }} />
        <div style={{ transform: 'rotate(-45deg)', textAlign: 'center', padding: 4 }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: '#fbbf24', textTransform: 'uppercase', letterSpacing: '0.04em' }}>GATE</div>
          <div style={{ fontSize: 10, fontWeight: 600, color: '#e4e4e7', lineHeight: 1.2, marginTop: 2, maxWidth: 60, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {nd.label}
          </div>
        </div>
        <Handle type="source" position={Position.Right} style={{ background: '#52525b', width: 8, height: 8, border: '2px solid #09090b', right: -5 }} />
        <Handle type="source" id="fail" position={Position.Bottom} style={{ background: '#ef4444', width: 8, height: 8, border: '2px solid #09090b', bottom: -5 }} />
      </div>
    )
  }

  // worker / human
  return (
    <div style={{
      width: 180, minHeight: 60,
      background: selected ? 'rgba(99,102,241,0.1)' : 'rgba(24,24,27,0.9)',
      border: `1.5px solid ${selected ? '#818cf8' : '#3f3f46'}`,
      borderLeft: `4px solid ${borderColor}`,
      borderRadius: 8,
      padding: '8px 10px',
      boxShadow: selected ? '0 0 0 2px rgba(99,102,241,0.25)' : '0 2px 8px rgba(0,0,0,0.3)',
      transition: 'all 0.15s',
      position: 'relative',
    }}>
      <Handle type="target" position={Position.Left} style={{ background: '#52525b', width: 8, height: 8, border: '2px solid #09090b' }} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontSize: 9, fontWeight: 700, color: borderColor, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {nodeTypeBadge}
        </span>
      </div>
      <p style={{ fontSize: 12, fontWeight: 600, color: '#e4e4e7', lineHeight: 1.3, margin: 0 }}>{nd.label}</p>
      {nd.workerId && (
        <p style={{ fontSize: 9, color: '#71717a', marginTop: 3, margin: '3px 0 0' }}>{nd.workerId}</p>
      )}
      <Handle type="source" position={Position.Right} style={{ background: '#52525b', width: 8, height: 8, border: '2px solid #09090b' }} />
    </div>
  )
}

const nodeTypes = { designerNode: DesignerNode }
const edgeTypes = { designerEdge: DesignerEdge }

// ─── Initial nodes ────────────────────────────────────────────────────────────

const INITIAL_NODES: Node[] = [
  { id: 'start', type: 'designerNode', position: { x: 60, y: 200 }, data: { nodeType: 'start', label: 'START' } as DesignerNodeData },
  { id: 'end',   type: 'designerNode', position: { x: 700, y: 200 }, data: { nodeType: 'end', label: 'END' } as DesignerNodeData },
]

// ─── Worker Palette ───────────────────────────────────────────────────────────

const PALETTE_CATEGORIES: { label: string; category: string }[] = [
  { label: 'Quality', category: 'quality' },
  { label: 'Security', category: 'security' },
  { label: 'Traceability', category: 'traceability' },
  { label: 'Platform', category: 'platform' },
  { label: 'Retrieval', category: 'retrieval' },
  { label: 'Ops', category: 'ops' },
  { label: 'AI Cost', category: 'ai-cost' },
]

function WorkerPalette() {
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set(['quality', 'platform']))

  const toggleCat = (cat: string) => setExpandedCats(prev => {
    const next = new Set(prev)
    next.has(cat) ? next.delete(cat) : next.add(cat)
    return next
  })

  const onDragStart = (e: DragEvent<HTMLDivElement>, worker: WorkerDef) => {
    e.dataTransfer.setData('workerJson', JSON.stringify(worker))
    e.dataTransfer.effectAllowed = 'move'
  }

  const profileBadge = (profile: string) => {
    const color =
      profile === 'validator' ? '#f59e0b' :
      profile === 'analyzer' ? '#38bdf8' :
      profile === 'on_demand' ? '#a78bfa' :
      profile === 'scheduled' ? '#6366f1' :
      '#71717a'
    return (
      <span style={{
        fontSize: 8, fontWeight: 700, color, background: `${color}20`,
        borderRadius: 3, padding: '1px 4px', textTransform: 'uppercase', letterSpacing: '0.05em',
      }}>{profile}</span>
    )
  }

  return (
    <div style={{
      width: 200, flexShrink: 0,
      borderRight: '1px solid rgba(63,63,70,0.6)',
      background: 'rgba(9,9,11,0.8)',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{ padding: '10px 12px 8px', borderBottom: '1px solid rgba(63,63,70,0.4)' }}>
        <p style={{ fontSize: 11, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0 }}>
          Workers
        </p>
        <p style={{ fontSize: 9, color: '#52525b', margin: '2px 0 0' }}>Drag onto canvas</p>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 8px' }}>
        {PALETTE_CATEGORIES.map(({ label, category }) => {
          const workers = WORKER_DEFS.filter(w => w.category === category)
          if (workers.length === 0) return null
          const open = expandedCats.has(category)
          return (
            <div key={category}>
              <button
                onClick={() => toggleCat(category)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '4px 2px 3px', background: 'none', border: 'none',
                  cursor: 'pointer', width: '100%',
                }}
              >
                <span style={{ fontSize: 9, color: open ? '#71717a' : '#3f3f46' }}>{open ? '▾' : '▸'}</span>
                <span style={{ fontSize: 9, fontWeight: 700, color: '#52525b', textTransform: 'uppercase', letterSpacing: '0.08em', flex: 1, textAlign: 'left' }}>
                  {label}
                </span>
                <span style={{ fontSize: 9, color: '#3f3f46' }}>{workers.length}</span>
              </button>
              {open && workers.map(worker => (
                <div
                  key={worker.id}
                  draggable
                  onDragStart={e => onDragStart(e, worker)}
                  style={{
                    padding: '6px 8px', marginBottom: 3, borderRadius: 6,
                    background: 'rgba(24,24,27,0.8)',
                    border: '1px solid rgba(63,63,70,0.5)',
                    cursor: 'grab',
                    display: 'flex', flexDirection: 'column', gap: 3,
                    transition: 'border-color 0.12s',
                  }}
                  onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(99,102,241,0.4)'}
                  onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(63,63,70,0.5)'}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <GripVertical size={10} color="#3f3f46" style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: 11, fontWeight: 500, color: '#d4d4d8', lineHeight: 1.2, flex: 1 }}>{worker.label}</span>
                  </div>
                  <div style={{ paddingLeft: 15 }}>
                    {profileBadge(worker.profile)}
                  </div>
                </div>
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Properties Panel ─────────────────────────────────────────────────────────

interface PropsPanelProps {
  nodeId: string
  nodes: Node[]
  setNodes: (updater: (nds: Node[]) => Node[]) => void
  onDelete: (nodeId: string) => void
}

function PropertiesPanel({ nodeId, nodes, setNodes, onDelete }: PropsPanelProps) {
  const node = nodes.find(n => n.id === nodeId)
  if (!node) return null
  const nd = node.data as DesignerNodeData
  const isStartEnd = nd.nodeType === 'start' || nd.nodeType === 'end'

  const updateData = (patch: Partial<DesignerNodeData>) => {
    setNodes(nds => nds.map(n => n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n))
  }

  const availableWorkers = WORKER_DEFS.filter(w => {
    if (nd.nodeType === 'gate') return w.profile === 'validator' || w.profile === 'analyzer'
    return w.profile === 'on_demand' || w.profile === 'scheduled' || w.profile === 'realtime'
  })

  return (
    <div style={{
      width: 260, flexShrink: 0,
      borderLeft: '1px solid rgba(63,63,70,0.6)',
      background: 'rgba(9,9,11,0.8)',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{ padding: '10px 14px 8px', borderBottom: '1px solid rgba(63,63,70,0.4)' }}>
        <p style={{ fontSize: 11, fontWeight: 700, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0 }}>
          Node Properties
        </p>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* Node type */}
        <div>
          <label style={{ fontSize: 10, fontWeight: 600, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }}>
            Node Type
          </label>
          <select
            value={nd.nodeType}
            disabled={isStartEnd}
            onChange={e => updateData({ nodeType: e.target.value as DesignerNodeData['nodeType'] })}
            style={{
              width: '100%', padding: '5px 8px', borderRadius: 6, fontSize: 12,
              background: '#18181b', border: '1px solid rgba(63,63,70,0.6)',
              color: isStartEnd ? '#52525b' : '#e4e4e7', cursor: isStartEnd ? 'not-allowed' : 'pointer',
            }}
          >
            <option value="worker">Worker</option>
            <option value="gate">Gate</option>
            <option value="human">Human</option>
            <option value="start" disabled>Start</option>
            <option value="end" disabled>End</option>
          </select>
        </div>

        {/* Label */}
        <div>
          <label style={{ fontSize: 10, fontWeight: 600, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }}>
            Label
          </label>
          <input
            value={nd.label}
            onChange={e => updateData({ label: e.target.value })}
            style={{
              width: '100%', padding: '5px 8px', borderRadius: 6, fontSize: 12,
              background: '#18181b', border: '1px solid rgba(63,63,70,0.6)',
              color: '#e4e4e7', outline: 'none', boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Worker selector */}
        {!isStartEnd && (
          <div>
            <label style={{ fontSize: 10, fontWeight: 600, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }}>
              Worker
            </label>
            <select
              value={nd.workerId ?? ''}
              onChange={e => {
                const w = WORKER_DEFS.find(wr => wr.id === e.target.value)
                updateData({ workerId: e.target.value || undefined, workerProfile: w?.profile, label: w?.label ?? nd.label })
              }}
              style={{
                width: '100%', padding: '5px 8px', borderRadius: 6, fontSize: 11,
                background: '#18181b', border: '1px solid rgba(63,63,70,0.6)',
                color: '#e4e4e7', cursor: 'pointer',
              }}
            >
              <option value="">— none —</option>
              {availableWorkers.map(w => (
                <option key={w.id} value={w.id}>{w.label}</option>
              ))}
            </select>
          </div>
        )}

        {/* Max retries — only for gate nodes */}
        {nd.nodeType === 'gate' && (
          <div>
            <label style={{ fontSize: 10, fontWeight: 600, color: '#71717a', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }}>
              Max Retries
            </label>
            <input
              type="number"
              min={0}
              max={10}
              value={nd.maxRetries ?? 3}
              onChange={e => updateData({ maxRetries: parseInt(e.target.value, 10) })}
              style={{
                width: '100%', padding: '5px 8px', borderRadius: 6, fontSize: 12,
                background: '#18181b', border: '1px solid rgba(63,63,70,0.6)',
                color: '#e4e4e7', outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>
        )}

        {/* Delete */}
        <button
          onClick={() => !isStartEnd && onDelete(nodeId)}
          disabled={isStartEnd}
          style={{
            width: '100%', padding: '7px', borderRadius: 6, fontSize: 12,
            background: isStartEnd ? 'rgba(39,39,42,0.4)' : 'rgba(239,68,68,0.12)',
            border: `1px solid ${isStartEnd ? 'rgba(63,63,70,0.3)' : 'rgba(239,68,68,0.4)'}`,
            color: isStartEnd ? '#52525b' : '#ef4444',
            cursor: isStartEnd ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            marginTop: 6,
          }}
        >
          <Trash2 size={12} /> Delete Node
        </button>
      </div>
    </div>
  )
}

// ─── Canvas inner (needs useReactFlow) ────────────────────────────────────────

interface CanvasInnerProps {
  nodes: Node[]
  edges: Edge[]
  setNodes: (updater: (nds: Node[]) => Node[]) => void
  setEdges: (updater: (eds: Edge[]) => Edge[]) => void
  onConnect: OnConnect
  selectedNodeId: string | null
  setSelectedNodeId: (id: string | null) => void
}

function CanvasInner({ nodes, edges, setNodes, setEdges, onConnect, selectedNodeId, setSelectedNodeId }: CanvasInnerProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const { screenToFlowPosition } = useReactFlow()

  const onDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const workerJson = e.dataTransfer.getData('workerJson')
    if (!workerJson) return
    const worker: WorkerDef = JSON.parse(workerJson)
    const reactFlowBounds = reactFlowWrapper.current?.getBoundingClientRect()
    if (!reactFlowBounds) return
    const position = screenToFlowPosition({
      x: e.clientX - reactFlowBounds.left,
      y: e.clientY - reactFlowBounds.top,
    })
    const nodeType: DesignerNodeData['nodeType'] =
      worker.profile === 'validator' || worker.profile === 'analyzer' ? 'gate' : 'worker'
    const newNode: Node = {
      id: `node-${Date.now()}`,
      type: 'designerNode',
      position,
      data: {
        nodeType,
        label: worker.label,
        workerId: worker.id,
        workerProfile: worker.profile,
        maxRetries: nodeType === 'gate' ? 3 : undefined,
      } as DesignerNodeData,
    }
    setNodes(nds => [...nds, newNode])
  }, [screenToFlowPosition, setNodes])

  return (
    <div ref={reactFlowWrapper} style={{ flex: 1, position: 'relative' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={(changes) => {
          // Apply changes manually
          setNodes(nds => {
            let next = [...nds]
            for (const change of changes) {
              if (change.type === 'position' && change.position) {
                next = next.map(n => n.id === change.id ? { ...n, position: change.position! } : n)
              } else if (change.type === 'remove') {
                next = next.filter(n => n.id !== change.id)
              } else if (change.type === 'select') {
                next = next.map(n => n.id === change.id ? { ...n, selected: change.selected } : n)
              }
            }
            return next
          })
        }}
        onEdgesChange={(changes) => {
          setEdges(eds => {
            let next = [...eds]
            for (const change of changes) {
              if (change.type === 'remove') {
                next = next.filter(e => e.id !== change.id)
              } else if (change.type === 'select') {
                next = next.map(e => e.id === change.id ? { ...e, selected: change.selected } : e)
              }
            }
            return next
          })
        }}
        onConnect={onConnect}
        onNodeClick={(_e, node) => setSelectedNodeId(node.id)}
        onPaneClick={() => setSelectedNodeId(null)}
        onDragOver={onDragOver}
        onDrop={onDrop}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={{ type: 'designerEdge', data: { edgeKind: 'default' } }}
        fitView
        style={{ background: '#0c0c0e' }}
      >
        <Background variant={BackgroundVariant.Dots} color="#27272a" gap={20} />
        <Controls />
      </ReactFlow>
    </div>
  )
}

// ─── Main FlowDesigner ────────────────────────────────────────────────────────

export function FlowDesigner({ existingFlowId, onSave, onCancel }: FlowDesignerProps) {
  const addCustomFlow   = useAppStore(s => s.addCustomFlow)
  const updateCustomFlow = useAppStore(s => s.updateCustomFlow)
  const deleteCustomFlow = useAppStore(s => s.deleteCustomFlow)
  const customFlowDefs  = useAppStore(s => s.customFlowDefs)
  const customGraphDefs = useAppStore(s => s.customFlowGraphDefs)

  // Load existing flow if editing
  const existingGraph = existingFlowId ? customGraphDefs.find(g => g.id === existingFlowId) : undefined
  const existingFlow  = existingFlowId ? customFlowDefs.find(f => f.id === existingFlowId) : undefined

  const [flowName, setFlowName]   = useState(existingFlow?.label ?? 'New Flow')
  const [flowDesc, setFlowDesc]   = useState(existingFlow?.description ?? '')
  const [category, setCategory]   = useState(existingGraph?.category ?? 'sdlc')

  const toRfNode = (gn: FlowGraphNode): Node => ({
    id: gn.id, type: 'designerNode', position: gn.position,
    data: {
      nodeType: gn.nodeType as DesignerNodeData['nodeType'],
      label: gn.label,
      workerId: gn.workerId,
      maxRetries: gn.maxRetries,
    } as DesignerNodeData,
  })

  const toRfEdge = (ge: FlowGraphEdge): Edge => ({
    id: ge.id, source: ge.source, target: ge.target,
    type: 'designerEdge',
    data: { edgeKind: ge.edgeKind },
    label: ge.label,
  })

  const [nodes, setNodes] = useNodesState(
    existingGraph ? existingGraph.nodes.map(toRfNode) : INITIAL_NODES
  )
  const [edges, setEdges] = useEdgesState(
    existingGraph ? existingGraph.edges.map(toRfEdge) : []
  )

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  const onConnect: OnConnect = useCallback((connection: Connection) => {
    setEdges(eds => addEdge({ ...connection, type: 'designerEdge', data: { edgeKind: 'default' } }, eds))
  }, [setEdges])

  const deleteNode = useCallback((nodeId: string) => {
    setNodes(nds => nds.filter(n => n.id !== nodeId))
    setEdges(eds => eds.filter(e => e.source !== nodeId && e.target !== nodeId))
    setSelectedNodeId(null)
  }, [setNodes, setEdges])

  const handleSave = useCallback(() => {
    const flowId = existingFlowId ?? `custom-flow-${Date.now()}`

    // Convert nodes to FlowGraphNodes
    const graphNodes: FlowGraphNode[] = nodes.map(n => {
      const nd = n.data as DesignerNodeData
      return {
        id: n.id,
        nodeType: nd.nodeType,
        label: nd.label,
        workerId: nd.workerId,
        maxRetries: nd.maxRetries,
        position: n.position,
      }
    })

    // Convert edges to FlowGraphEdges
    const graphEdges: FlowGraphEdge[] = edges.map(e => ({
      id: e.id,
      source: e.source,
      target: e.target,
      edgeKind: (e.data?.edgeKind as FlowEdgeKind) ?? 'default',
      label: typeof e.label === 'string' ? e.label : undefined,
    }))

    const graphDef: FlowGraphDef = {
      id: flowId,
      name: flowName,
      description: flowDesc,
      category,
      nodes: graphNodes,
      edges: graphEdges,
    }

    // Derive FlowDef steps from worker nodes in rough order (left to right)
    const workerNodes = nodes
      .filter(n => {
        const nd = n.data as DesignerNodeData
        return nd.nodeType === 'worker' || nd.nodeType === 'gate' || nd.nodeType === 'human'
      })
      .sort((a, b) => a.position.x - b.position.x)

    const steps: FlowStep[] = workerNodes.map(n => {
      const nd = n.data as DesignerNodeData
      const workerDef = nd.workerId ? WORKER_DEFS.find(w => w.id === nd.workerId) : null
      return {
        id: n.id,
        workerId: nd.workerId ?? nd.nodeType,
        workerLabel: nd.label,
        objectTypeTarget: workerDef?.applicableTypes[0] ?? 'prd',
        status: 'pending' as const,
      }
    })

    const flowDef: FlowDef = {
      id: flowId,
      label: flowName,
      description: flowDesc,
      steps,
    }

    if (existingFlowId) {
      updateCustomFlow(flowDef, graphDef)
    } else {
      addCustomFlow(flowDef, graphDef)
    }
    onSave(flowId)
  }, [nodes, edges, flowName, flowDesc, category, existingFlowId, addCustomFlow, updateCustomFlow, onSave])

  const handleDelete = useCallback(() => {
    if (!existingFlowId) return
    deleteCustomFlow(existingFlowId)
    onCancel()
  }, [existingFlowId, deleteCustomFlow, onCancel])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', background: '#09090b' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '8px 16px',
        borderBottom: '1px solid rgba(63,63,70,0.6)',
        background: 'rgba(9,9,11,0.95)',
        flexShrink: 0,
      }}>
        <button
          onClick={onCancel}
          style={{
            display: 'flex', alignItems: 'center', gap: 5, padding: '5px 10px',
            borderRadius: 6, background: 'rgba(39,39,42,0.6)',
            border: '1px solid rgba(63,63,70,0.5)',
            color: '#a1a1aa', fontSize: 12, cursor: 'pointer',
          }}
        >
          <ArrowLeft size={12} /> Flows
        </button>

        <div style={{ flex: 1, display: 'flex', gap: 10, alignItems: 'center' }}>
          <input
            value={flowName}
            onChange={e => setFlowName(e.target.value)}
            placeholder="Flow name"
            style={{
              padding: '5px 10px', borderRadius: 6, fontSize: 13, fontWeight: 600,
              background: '#18181b', border: '1px solid rgba(63,63,70,0.6)',
              color: '#e4e4e7', outline: 'none', minWidth: 180,
            }}
          />
          <input
            value={flowDesc}
            onChange={e => setFlowDesc(e.target.value)}
            placeholder="Description (optional)"
            style={{
              padding: '5px 10px', borderRadius: 6, fontSize: 11, flex: 1,
              background: '#18181b', border: '1px solid rgba(63,63,70,0.6)',
              color: '#a1a1aa', outline: 'none',
            }}
          />
          <select
            value={category}
            onChange={e => setCategory(e.target.value)}
            style={{
              padding: '5px 8px', borderRadius: 6, fontSize: 11,
              background: '#18181b', border: '1px solid rgba(63,63,70,0.6)',
              color: '#a1a1aa', cursor: 'pointer',
            }}
          >
            <option value="sdlc">SDLC</option>
            <option value="ops">Ops</option>
          </select>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          {existingFlowId && (
            <button
              onClick={handleDelete}
              style={{
                display: 'flex', alignItems: 'center', gap: 5, padding: '5px 12px',
                borderRadius: 6, background: 'rgba(239,68,68,0.1)',
                border: '1px solid rgba(239,68,68,0.35)',
                color: '#ef4444', fontSize: 12, cursor: 'pointer',
              }}
            >
              <Trash2 size={12} /> Delete
            </button>
          )}
          <button
            onClick={handleSave}
            style={{
              display: 'flex', alignItems: 'center', gap: 5, padding: '5px 14px',
              borderRadius: 6, background: '#4f46e5',
              border: '1px solid #6366f1',
              color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}
          >
            <Save size={12} /> Save Flow
          </button>
        </div>
      </div>

      {/* Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <WorkerPalette />

        <CanvasInner
          nodes={nodes}
          edges={edges}
          setNodes={setNodes}
          setEdges={setEdges}
          onConnect={onConnect}
          selectedNodeId={selectedNodeId}
          setSelectedNodeId={setSelectedNodeId}
        />

        {selectedNodeId && (
          <PropertiesPanel
            nodeId={selectedNodeId}
            nodes={nodes}
            setNodes={setNodes}
            onDelete={deleteNode}
          />
        )}
      </div>
    </div>
  )
}
