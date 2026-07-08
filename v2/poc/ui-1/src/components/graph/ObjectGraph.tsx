import { useCallback, useMemo, useState } from 'react'
import type React from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  useReactFlow,
  ReactFlowProvider,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  type NodeChange,
  applyNodeChanges,
} from '@xyflow/react'
import { useAppStore } from '../../store/app-store'
import { CustomNode } from './CustomNode'
import { SmartBackEdge, SmartBackEdgeBelow } from './SmartBackEdge'
import { NODE_POSITIONS } from '../../data/mock-data'
import type { StudioObject } from '../../types/domain'

const NODE_WIDTH = 210
const NODE_HEIGHT = 100  // approximate

const nodeTypes: NodeTypes = { customNode: CustomNode }
const edgeTypes: EdgeTypes = {
  'back-above': SmartBackEdge,
  'back-below': SmartBackEdgeBelow,
}

const EDGE_KIND_COLORS: Record<string, string> = {
  derived_from:    '#6366f1',
  decomposes_into: '#06b6d4',
  implements:      '#10b981',
  validates:       '#f59e0b',
  references:      '#8b5cf6',
  incorporates:    '#ec4899',
  supersedes:      '#ef4444',
  informs:         '#71717a',
}

/** Is the edge primarily going right→left? */
function isBackEdge(srcPos: {x:number;y:number}, tgtPos: {x:number;y:number}) {
  return tgtPos.x < srcPos.x
}

/** Connection point on the right edge of a node */
function rightHandle(pos: {x:number;y:number}): {x:number;y:number} {
  return { x: pos.x + NODE_WIDTH, y: pos.y + NODE_HEIGHT / 2 }
}

/** Connection point on the left edge of a node */
function leftHandle(pos: {x:number;y:number}): {x:number;y:number} {
  return { x: pos.x, y: pos.y + NODE_HEIGHT / 2 }
}

/** Connection point on the top edge of a node, at a given X fraction (0–1) */
function topHandle(pos: {x:number;y:number}, xFrac = 0.5): {x:number;y:number} {
  return { x: pos.x + NODE_WIDTH * xFrac, y: pos.y }
}

/** Connection point on the bottom edge of a node, at a given X fraction */
function bottomHandle(pos: {x:number;y:number}, xFrac = 0.5): {x:number;y:number} {
  return { x: pos.x + NODE_WIDTH * xFrac, y: pos.y + NODE_HEIGHT }
}

// Inner component that has access to ReactFlow context (useReactFlow)
function ObjectGraphInner() {
  const objects = useAppStore(s => s.objects)
  const selectedObjectId = useAppStore(s => s.selectedObjectId)
  const selectObject = useAppStore(s => s.selectObject)
  const { setCenter } = useReactFlow()

  // Local draggable position overrides — start from static NODE_POSITIONS
  const [positions, setPositions] = useState<Record<string, {x:number;y:number}>>(
    () => ({ ...NODE_POSITIONS })
  )

  const connectedIds = useMemo(() => {
    if (!selectedObjectId) return new Set<string>()
    const ids = new Set<string>([selectedObjectId])
    objects.forEach(obj => {
      if (obj.id === selectedObjectId) obj.links.forEach(l => ids.add(l.targetId))
      obj.links.forEach(l => { if (l.targetId === selectedObjectId) ids.add(obj.id) })
    })
    return ids
  }, [objects, selectedObjectId])

  const nodes: Node[] = useMemo(() =>
    objects.map(obj => {
      const dimmed = selectedObjectId !== null && !connectedIds.has(obj.id)
      return {
        id: obj.id,
        type: 'customNode',
        position: positions[obj.id] ?? { x: 0, y: 0 },
        data: { object: obj, dimmed },
        selected: obj.id === selectedObjectId,
      }
    }),
    [objects, selectedObjectId, connectedIds, positions]
  )

  // Handle node drag — update positions state
  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setPositions(prev => {
      // Apply ReactFlow node changes to get updated positions
      const fakeNodes: Node[] = Object.entries(prev).map(([id, pos]) => ({
        id,
        type: 'customNode',
        position: pos,
        data: {},
      }))
      const updated = applyNodeChanges(changes, fakeNodes)
      const next = { ...prev }
      updated.forEach(n => { next[n.id] = n.position })
      return next
    })
  }, [])

  const edges: Edge[] = useMemo(() => {
    // Pre-pass: for each node side, collect back-edges grouped by (target, side)
    // so we can spread parallel arcs
    type EdgeInfo = { srcId: string; tgtId: string; kind: string }
    const backGroups = new Map<string, EdgeInfo[]>()

    objects.forEach((obj: StudioObject) => {
      obj.links.forEach(link => {
        const srcPos = positions[obj.id] ?? { x: 0, y: 0 }
        const tgtPos = positions[link.targetId] ?? { x: 0, y: 0 }
        if (!isBackEdge(srcPos, tgtPos)) return
        const dy = tgtPos.y - srcPos.y
        const side = dy > 0 ? 'below' : 'above'
        const key = `${link.targetId}:${side}`
        if (!backGroups.has(key)) backGroups.set(key, [])
        backGroups.get(key)!.push({ srcId: obj.id, tgtId: link.targetId, kind: link.kind })
      })
    })

    const result: Edge[] = []
    const seen = new Set<string>()
    // Track how many times we've used each group key
    const groupIdx = new Map<string, number>()

    objects.forEach((obj: StudioObject) => {
      obj.links.forEach(link => {
        const edgeId = `${obj.id}-${link.targetId}-${link.kind}`
        if (seen.has(edgeId)) return
        seen.add(edgeId)

        const isConnected = selectedObjectId !== null &&
          (obj.id === selectedObjectId || link.targetId === selectedObjectId)
        const opacity = selectedObjectId === null ? 0 : isConnected ? 1 : 0.08
        const color = isConnected ? (EDGE_KIND_COLORS[link.kind] ?? '#52525b') : '#52525b'
        const label = isConnected ? link.kind.replace(/_/g, ' ') : undefined

        const srcPos = positions[obj.id] ?? { x: 0, y: 0 }
        const tgtPos = positions[link.targetId] ?? { x: 0, y: 0 }
        const isBack = isBackEdge(srcPos, tgtPos)

        if (!isBack) {
          // ── Forward edge: bezier right→left with angle (use right/left handles) ──
          // Forward diagonal: compute proper source/target handle positions for the edge
          // ReactFlow uses sourceHandle/targetHandle IDs + node layout, so we keep
          // the 'right' / 'left' handle IDs and let the bezier use node edge midpoints.
          result.push({
            id: edgeId,
            source: obj.id,
            target: link.targetId,
            sourceHandle: 'right',
            targetHandle: 'left',
            type: 'bezier',
            label,
            labelStyle: { fontSize: 9, fill: '#a1a1aa', fontFamily: 'Inter, sans-serif' },
            labelBgStyle: { fill: '#09090b', fillOpacity: 0.9 },
            labelBgPadding: [3, 4] as [number, number],
            style: { stroke: color, strokeWidth: isConnected ? 2 : 1, opacity },
            markerEnd: { type: 'arrowclosed' as const, color, width: 14, height: 14 },
          })
          return
        }

        // ── Back edge: custom arc ──
        const dy = tgtPos.y - srcPos.y
        const side = dy > 0 ? 'below' : 'above'
        const groupKey = `${link.targetId}:${side}`
        const group = backGroups.get(groupKey) ?? []
        const myIdx = groupIdx.get(groupKey) ?? 0
        groupIdx.set(groupKey, myIdx + 1)
        const groupSize = group.length

        // Spread multiple arcs: space them 30px apart, centred
        const spread = 30
        const arcOffset = groupSize > 1
          ? (myIdx - (groupSize - 1) / 2) * spread
          : 0

        // Source handle: top (above) or bottom (below) — on the exit side of source node
        // Target handle: same side entry point
        // We manually compute the handle X/Y via node positions; ReactFlow will match
        // by handle id — but for custom edges the actual X/Y come from the DOM handle.
        // We place handles at appropriate X fractions to give the arc a proper angle:
        //   - source exits from 30% of node width (left side of right node)
        //   - target enters at 70% of node width (right side of left node)
        const srcHandle = side === 'above' ? 'top-exit' : 'bottom-exit'
        const tgtHandle = side === 'above' ? 'top-entry' : 'bottom-entry'

        result.push({
          id: edgeId,
          source: obj.id,
          target: link.targetId,
          sourceHandle: srcHandle,
          targetHandle: tgtHandle,
          type: side === 'above' ? 'back-above' : 'back-below',
          label,
          data: { arcOffset, color, opacity, label, labelColor: color },
          style: { stroke: color, strokeWidth: isConnected ? 2 : 1, opacity },
          markerEnd: { type: 'arrowclosed' as const, color, width: 14, height: 14 },
        })
      })
    })
    return result
  }, [objects, selectedObjectId, positions])

  const onNodeClick = useCallback((_evt: React.MouseEvent, node: Node) => {
    const newId = node.id === selectedObjectId ? null : node.id
    selectObject(newId)
    // Center the clicked node in the viewport
    if (newId) {
      const pos = positions[node.id] ?? { x: 0, y: 0 }
      setCenter(pos.x + NODE_WIDTH / 2, pos.y + NODE_HEIGHT / 2, { duration: 400, zoom: 1 })
    }
  }, [selectObject, selectedObjectId, positions, setCenter])

  const onPaneClick = useCallback(() => selectObject(null), [selectObject])

  return (
    <div className="w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodesDraggable
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.15}
        maxZoom={2.5}
        defaultEdgeOptions={{ type: 'bezier' }}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#27272a" />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            const obj = (node.data as { object: StudioObject }).object
            const stateColors: Record<string, string> = {
              approved: '#10b981', done: '#10b981',
              in_progress: '#f59e0b', running: '#f59e0b', review: '#f59e0b',
              failed: '#ef4444', open: '#ef4444',
              draft: '#52525b', planned: '#3b82f6',
            }
            return stateColors[obj?.state] ?? '#52525b'
          }}
          maskColor="rgba(9,9,11,0.7)"
        />
      </ReactFlow>
    </div>
  )
}

// Public export wraps in ReactFlowProvider so ObjectGraphInner can call useReactFlow()
export function ObjectGraph() {
  return (
    <ReactFlowProvider>
      <ObjectGraphInner />
    </ReactFlowProvider>
  )
}
