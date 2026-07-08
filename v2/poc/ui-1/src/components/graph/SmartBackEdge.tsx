import { BaseEdge, type EdgeProps } from '@xyflow/react'

interface BackEdgeData extends Record<string, unknown> {
  arcOffset?: number   // vertical offset for parallel arcs (px, positive = higher)
  color?: string
  opacity?: number
  label?: string
  labelColor?: string
}

/**
 * Custom edge for backward (right→left) connections.
 * Draws an explicit cubic bezier that arcs above (or below for bottom arcs)
 * the nodes by a fixed height, with per-edge vertical offset so parallel
 * back-edges spread out instead of overlapping.
 */
export function SmartBackEdge({
  id,
  sourceX, sourceY,
  targetX, targetY,
  data,
  markerEnd,
  style,
}: EdgeProps) {
  const { arcOffset = 0, color = '#52525b', opacity = 1, label, labelColor = '#a1a1aa' } = (data ?? {}) as BackEdgeData

  // Horizontal span — use it to scale arc height so short edges still curve visibly
  const span = Math.abs(sourceX - targetX)
  const baseArcHeight = Math.max(60, span * 0.35)  // at least 60px above
  const arcHeight = baseArcHeight + arcOffset

  // Control points go straight up from source/target handle positions
  const cx1 = sourceX
  const cy1 = sourceY - arcHeight
  const cx2 = targetX
  const cy2 = targetY - arcHeight

  const path = `M${sourceX},${sourceY} C${cx1},${cy1} ${cx2},${cy2} ${targetX},${targetY}`

  // Label midpoint — peak of the arc
  const labelX = (sourceX + targetX) / 2
  const labelY = (cy1 + cy2) / 2 - 6

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{ ...style, stroke: color, opacity }}
      />
      {label && (
        <g transform={`translate(${labelX},${labelY})`}>
          <rect
            x={-label.length * 3 - 4}
            y={-8}
            width={label.length * 6 + 8}
            height={14}
            rx={3}
            fill="#09090b"
            fillOpacity={0.9}
          />
          <text
            fontSize={9}
            fill={labelColor}
            textAnchor="middle"
            dominantBaseline="middle"
            fontFamily="Inter, sans-serif"
          >
            {label}
          </text>
        </g>
      )}
    </>
  )
}

export function SmartBackEdgeBelow({
  id,
  sourceX, sourceY,
  targetX, targetY,
  data,
  markerEnd,
  style,
}: EdgeProps) {
  const { arcOffset = 0, color = '#52525b', opacity = 1, label, labelColor = '#a1a1aa' } = (data ?? {}) as BackEdgeData

  const span = Math.abs(sourceX - targetX)
  const baseArcHeight = Math.max(60, span * 0.35)
  const arcHeight = baseArcHeight + arcOffset

  // Control points go downward (positive Y)
  const cx1 = sourceX
  const cy1 = sourceY + arcHeight
  const cx2 = targetX
  const cy2 = targetY + arcHeight

  const path = `M${sourceX},${sourceY} C${cx1},${cy1} ${cx2},${cy2} ${targetX},${targetY}`

  const labelX = (sourceX + targetX) / 2
  const labelY = (cy1 + cy2) / 2 + 14

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{ ...style, stroke: color, opacity }}
      />
      {label && (
        <g transform={`translate(${labelX},${labelY})`}>
          <rect x={-label.length * 3 - 4} y={-8} width={label.length * 6 + 8} height={14} rx={3} fill="#09090b" fillOpacity={0.9} />
          <text fontSize={9} fill={labelColor} textAnchor="middle" dominantBaseline="middle" fontFamily="Inter, sans-serif">
            {label}
          </text>
        </g>
      )}
    </>
  )
}
