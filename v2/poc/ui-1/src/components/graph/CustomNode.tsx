import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { StudioObject } from '../../types/domain'

const TYPE_COLORS: Record<string, { border: string; bg: string; label: string; textColor: string }> = {
  prd:           { border: '#a855f7', bg: 'rgba(168,85,247,0.08)', label: 'PRD',     textColor: '#c084fc' },
  adr:           { border: '#8b5cf6', bg: 'rgba(139,92,246,0.08)', label: 'ADR',     textColor: '#a78bfa' },
  design:        { border: '#3b82f6', bg: 'rgba(59,130,246,0.08)', label: 'DESIGN',  textColor: '#60a5fa' },
  decomposition: { border: '#6366f1', bg: 'rgba(99,102,241,0.08)', label: 'DECOMP',  textColor: '#818cf8' },
  feature_spec:  { border: '#14b8a6', bg: 'rgba(20,184,166,0.08)', label: 'FSPEC',   textColor: '#2dd4bf' },
  task:          { border: '#06b6d4', bg: 'rgba(6,182,212,0.08)',  label: 'TASK',    textColor: '#22d3ee' },
  pull_request:  { border: '#f97316', bg: 'rgba(249,115,22,0.08)', label: 'PR',      textColor: '#fb923c' },
  build:         { border: '#84cc16', bg: 'rgba(132,204,22,0.08)', label: 'BUILD',   textColor: '#a3e635' },
  incident:      { border: '#ef4444', bg: 'rgba(239,68,68,0.08)',  label: 'INC',     textColor: '#f87171' },
}

function getStateColor(state: string): string {
  switch (state) {
    case 'approved': case 'done': case 'merged': return '#10b981'
    case 'in_progress': case 'running': case 'review': return '#f59e0b'
    case 'failed': case 'open': return '#ef4444'
    case 'draft': case 'planned': return '#71717a'
    default: return '#3b82f6'
  }
}

function getValidationIcon(status: string): string {
  switch (status) {
    case 'pass': return '✓'
    case 'fail': return '✗'
    case 'pending': return '○'
    default: return ''
  }
}

function getValidationColor(status: string): string {
  switch (status) {
    case 'pass': return '#10b981'
    case 'fail': return '#ef4444'
    case 'pending': return '#71717a'
    default: return 'transparent'
  }
}

interface CustomNodeData extends Record<string, unknown> {
  object: StudioObject
  dimmed?: boolean
}

export const CustomNode = memo(({ data, selected }: NodeProps) => {
  const nodeData = data as CustomNodeData
  const object = nodeData.object
  const dimmed = nodeData.dimmed ?? false
  const typeConfig = TYPE_COLORS[object.typeId] ?? { border: '#52525b', bg: 'rgba(82,82,91,0.08)', label: object.typeId.toUpperCase(), textColor: '#a1a1aa' }
  const stateColor = getStateColor(object.state)

  return (
    <div
      style={{
        width: 210,
        background: selected
          ? 'rgba(99,102,241,0.12)'
          : typeConfig.bg,
        border: selected
          ? '1.5px solid rgba(99,102,241,0.8)'
          : `1px solid ${typeConfig.border}30`,
        borderLeft: `3px solid ${typeConfig.border}`,
        borderRadius: 8,
        padding: '8px 10px',
        boxShadow: selected
          ? '0 0 0 2px rgba(99,102,241,0.3), 0 4px 16px rgba(0,0,0,0.4)'
          : '0 2px 8px rgba(0,0,0,0.3)',
        opacity: dimmed ? 0.25 : 1,
        transition: 'all 0.2s ease',
        cursor: 'pointer',
        position: 'relative',
      }}
    >
      {/* Type label + state dot */}
      <div className="flex items-center justify-between mb-1">
        <span style={{
          fontSize: 9,
          fontWeight: 700,
          color: typeConfig.textColor,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}>
          {typeConfig.label}
        </span>
        <div className="flex items-center gap-1">
          {object.validationStatus !== 'none' && (
            <span style={{ fontSize: 10, color: getValidationColor(object.validationStatus), fontWeight: 700 }}>
              {getValidationIcon(object.validationStatus)}
            </span>
          )}
          <div style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: stateColor,
            boxShadow: object.state === 'running' || object.state === 'in_progress'
              ? `0 0 6px ${stateColor}`
              : 'none',
          }} />
        </div>
      </div>

      {/* Title */}
      <p style={{
        fontSize: 12,
        fontWeight: 600,
        color: '#e4e4e7',
        lineHeight: 1.3,
        marginBottom: 6,
        wordBreak: 'break-word',
      }}>
        {object.title}
      </p>

      {/* State badge */}
      <div className="flex items-center justify-between">
        <span style={{
          fontSize: 9,
          color: stateColor,
          background: `${stateColor}18`,
          border: `1px solid ${stateColor}40`,
          borderRadius: 10,
          padding: '1px 6px',
          fontWeight: 500,
          textTransform: 'capitalize',
        }}>
          {object.state.replace('_', ' ')}
        </span>

        {/* Staleness bar */}
        {object.stalenessScore > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{
              width: 32,
              height: 3,
              background: '#27272a',
              borderRadius: 2,
              overflow: 'hidden',
            }}>
              <div style={{
                width: `${object.stalenessScore}%`,
                height: '100%',
                background: object.stalenessScore > 60 ? '#ef4444' : object.stalenessScore > 30 ? '#f59e0b' : '#3b82f6',
                borderRadius: 2,
              }} />
            </div>
            <span style={{ fontSize: 9, color: '#71717a' }}>{object.stalenessScore}%</span>
          </div>
        )}
      </div>

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: typeConfig.border, width: 8, height: 8, border: '2px solid #09090b' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: typeConfig.border, width: 8, height: 8, border: '2px solid #09090b' }}
      />
    </div>
  )
})

CustomNode.displayName = 'CustomNode'
