import { useCallback, useMemo } from 'react'
import type React from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  type Node,
  type Edge,
  type NodeTypes,
} from '@xyflow/react'
import { useAppStore } from '../../store/app-store'
import { CustomNode } from './CustomNode'
import { MOCK_OBJECTS, NODE_POSITIONS } from '../../data/mock-data'
import type { StudioObject } from '../../types/domain'

type HandleSide = 'left' | 'right' | 'top' | 'bottom'

function getEdgeHandles(
  srcPos: { x: number; y: number },
  tgtPos: { x: number; y: number },
  hasReverse: boolean,
  isFirstOfPair: boolean,
): { sourceHandle: HandleSide; targetHandle: HandleSide } {
  const dx = tgtPos.x - srcPos.x
  const dy = tgtPos.y - srcPos.y
  const absDx = Math.abs(dx)
  const absDy = Math.abs(dy)

  // Primarily horizontal movement
  if (absDx >= absDy) {
    if (dx > 0) {
      // Forward left→right: connect right→left directly
      if (hasReverse) {
        // Bidirectional: offset one via top, one via bottom
        return isFirstOfPair
          ? { sourceHandle: 'top', targetHandle: 'top' }
          : { sourceHandle: 'bottom', targetHandle: 'bottom' }
      }
      return { sourceHandle: 'right', targetHandle: 'left' }
    } else {
      // Backward right→left: always arc over or under to avoid crossing forward edges
      return dy <= 0
        ? { sourceHandle: 'top', targetHandle: 'top' }
        : { sourceHandle: 'bottom', targetHandle: 'bottom' }
    }
  }

  // Primarily vertical
  if (dy > 0) {
    return { sourceHandle: 'bottom', targetHandle: 'top' }
  }
  return { sourceHandle: 'top', targetHandle: 'bottom' }
}

const nodeTypes: NodeTypes = {
  customNode: CustomNode,
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

export function ObjectGraph() {
  const objects = useAppStore(s => s.objects)
  const selectedObjectId = useAppStore(s => s.selectedObjectId)
  const selectObject = useAppStore(s => s.selectObject)

  // When a node is selected, find its direct neighbors (connected via links)
  const connectedIds = useMemo(() => {
    if (!selectedObjectId) return new Set<string>()
    const ids = new Set<string>([selectedObjectId])
    objects.forEach(obj => {
      if (obj.id === selectedObjectId) {
        obj.links.forEach(l => ids.add(l.targetId))
      }
      obj.links.forEach(l => {
        if (l.targetId === selectedObjectId) ids.add(obj.id)
      })
    })
    return ids
  }, [objects, selectedObjectId])

  const nodes: Node[] = useMemo(() =>
    objects.map(obj => {
      const dimmed = selectedObjectId !== null && !connectedIds.has(obj.id)
      return {
        id: obj.id,
        type: 'customNode',
        position: NODE_POSITIONS[obj.id] ?? { x: 0, y: 0 },
        data: { object: obj, dimmed },
        selected: obj.id === selectedObjectId,
      }
    }),
    [objects, selectedObjectId, connectedIds]
  )

  const edges: Edge[] = useMemo(() => {
    // Pre-build a set of all (source, target) pairs to detect bidirectional edges
    const allPairs = new Set<string>()
    objects.forEach((obj: StudioObject) => {
      obj.links.forEach(link => allPairs.add(`${obj.id}→${link.targetId}`))
    })

    // Track which bidirectional pairs we've seen (to alternate top/bottom)
    const biDirSeen = new Set<string>()

    const result: Edge[] = []
    const seen = new Set<string>()

    objects.forEach((obj: StudioObject) => {
      obj.links.forEach(link => {
        const edgeId = `${obj.id}-${link.targetId}-${link.kind}`
        if (seen.has(edgeId)) return
        seen.add(edgeId)

        const isConnected = selectedObjectId !== null &&
          (obj.id === selectedObjectId || link.targetId === selectedObjectId)

        const opacity = selectedObjectId === null ? 0 : isConnected ? 1 : 0.08
        const color = isConnected ? (EDGE_KIND_COLORS[link.kind] ?? '#52525b') : '#52525b'

        // Determine smart handles based on node positions
        const srcPos = NODE_POSITIONS[obj.id] ?? { x: 0, y: 0 }
        const tgtPos = NODE_POSITIONS[link.targetId] ?? { x: 0, y: 0 }
        const reverseKey = `${link.targetId}→${obj.id}`
        const hasReverse = allPairs.has(reverseKey)
        const pairKey = [obj.id, link.targetId].sort().join('↔')
        const isFirstOfPair = !biDirSeen.has(pairKey)
        if (hasReverse) biDirSeen.add(pairKey)

        const { sourceHandle, targetHandle } = getEdgeHandles(
          srcPos, tgtPos, hasReverse, isFirstOfPair,
        )

        result.push({
          id: edgeId,
          source: obj.id,
          target: link.targetId,
          sourceHandle,
          targetHandle,
          type: 'bezier',
          label: isConnected ? link.kind.replace(/_/g, ' ') : undefined,
          labelStyle: { fontSize: 9, fill: '#a1a1aa', fontFamily: 'Inter, sans-serif' },
          labelBgStyle: { fill: '#09090b', fillOpacity: 0.9 },
          labelBgPadding: [3, 4] as [number, number],
          style: {
            stroke: color,
            strokeWidth: isConnected ? 2 : 1,
            opacity,
            transition: 'opacity 0.2s ease, stroke-width 0.2s ease',
          },
          markerEnd: {
            type: 'arrowclosed' as const,
            color,
            width: 16,
            height: 16,
          },
          animated: false,
        })
      })
    })
    return result
  }, [objects, selectedObjectId])

  const onNodeClick = useCallback((_evt: React.MouseEvent, node: Node) => {
    selectObject(node.id === selectedObjectId ? null : node.id)
  }, [selectObject, selectedObjectId])

  const onPaneClick = useCallback(() => {
    selectObject(null)
  }, [selectObject])

  return (
    <div className="w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.2}
        maxZoom={2}
        defaultEdgeOptions={{
          type: 'bezier',
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={24}
          size={1}
          color="#27272a"
        />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            const obj = (node.data as { object: StudioObject }).object
            const stateColors: Record<string, string> = {
              approved: '#10b981',
              done: '#10b981',
              in_progress: '#f59e0b',
              running: '#f59e0b',
              review: '#f59e0b',
              failed: '#ef4444',
              open: '#ef4444',
              draft: '#52525b',
              planned: '#3b82f6',
            }
            return stateColors[obj?.state] ?? '#52525b'
          }}
          maskColor="rgba(9,9,11,0.7)"
        />
      </ReactFlow>
    </div>
  )
}
