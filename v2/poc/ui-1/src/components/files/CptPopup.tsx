import { X, FileText, ArrowRight } from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import type { CptIdentifier } from '../../data/cpt-registry'

const KIND_COLORS: Record<string, string> = {
  fr: 'text-purple-400 bg-purple-900/20 border-purple-700/40',
  nfr: 'text-violet-400 bg-violet-900/20 border-violet-700/40',
  actor: 'text-blue-400 bg-blue-900/20 border-blue-700/40',
  usecase: 'text-cyan-400 bg-cyan-900/20 border-cyan-700/40',
  component: 'text-indigo-400 bg-indigo-900/20 border-indigo-700/40',
  constraint: 'text-red-400 bg-red-900/20 border-red-700/40',
  principle: 'text-amber-400 bg-amber-900/20 border-amber-700/40',
  seq: 'text-teal-400 bg-teal-900/20 border-teal-700/40',
  dbtable: 'text-lime-400 bg-lime-900/20 border-lime-700/40',
  adr: 'text-violet-400 bg-violet-900/20 border-violet-700/40',
  flow: 'text-emerald-400 bg-emerald-900/20 border-emerald-700/40',
  dod: 'text-green-400 bg-green-900/20 border-green-700/40',
  feature: 'text-cyan-400 bg-cyan-900/20 border-cyan-700/40',
}

const KIND_LABELS: Record<string, string> = {
  fr: 'Functional Requirement', nfr: 'Non-Functional Requirement',
  actor: 'Actor', usecase: 'Use Case', component: 'Component',
  constraint: 'Constraint', principle: 'Design Principle',
  seq: 'Sequence', dbtable: 'Database Table', db: 'Database',
  adr: 'Architecture Decision', flow: 'Flow', algo: 'Algorithm',
  dod: 'Definition of Done', state: 'State Machine', feature: 'Feature',
}

interface Props {
  cpt: CptIdentifier
  isDefinition: boolean   // true if we're viewing the defining document
  position: { x: number; y: number }
  onClose: () => void
}

export function CptPopup({ cpt, isDefinition, position, onClose }: Props) {
  const openFile = useAppStore(s => s.openFile)
  const setActiveView = useAppStore(s => s.setActiveView)

  const kindClass = KIND_COLORS[cpt.kind] ?? 'text-zinc-400 bg-zinc-800 border-zinc-700'

  const navigateTo = (fileId: string) => {
    openFile(fileId)
    setActiveView('files')
    onClose()
  }

  // Position popup near the click, keeping it on screen
  const style: React.CSSProperties = {
    position: 'fixed',
    top: Math.min(position.y, window.innerHeight - 280),
    left: Math.min(position.x, window.innerWidth - 360),
    zIndex: 1000,
    width: 340,
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[999]" onClick={onClose} />

      {/* Popup */}
      <div style={style} className="z-[1000] bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-4 py-3 border-b border-zinc-800 flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${kindClass}`}>
                {KIND_LABELS[cpt.kind] ?? cpt.kind}
              </span>
              {isDefinition && (
                <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border bg-emerald-900/20 border-emerald-700/40 text-emerald-400">
                  definition
                </span>
              )}
            </div>
            <p className="text-sm font-semibold text-zinc-100 leading-tight">{cpt.name}</p>
            <p className="text-[10px] font-mono text-zinc-500 mt-0.5 break-all">{cpt.id}</p>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 transition-colors shrink-0 p-0.5">
            <X size={14} />
          </button>
        </div>

        {/* Description */}
        <div className="px-4 py-2.5 border-b border-zinc-800">
          <p className="text-xs text-zinc-400 leading-relaxed">{cpt.description}</p>
        </div>

        {/* Defined in */}
        <div className="px-4 py-2 border-b border-zinc-800">
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-1.5">Defined in</p>
          <button
            onClick={() => navigateTo(cpt.definedIn.fileId)}
            className="flex items-center gap-2 text-xs text-indigo-300 hover:text-indigo-200 transition-colors w-full text-left"
          >
            <FileText size={11} className="shrink-0" />
            <span className="flex-1 truncate">{cpt.definedIn.documentTitle}</span>
            <span className="text-[9px] font-bold uppercase text-zinc-600 shrink-0">{cpt.definedIn.artifactType}</span>
            <ArrowRight size={10} className="shrink-0 text-zinc-600" />
          </button>
        </div>

        {/* References */}
        {cpt.references.length > 0 && (
          <div className="px-4 py-2">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-1.5">
              Referenced in ({cpt.references.length})
            </p>
            <div className="space-y-1.5">
              {cpt.references.map((ref, i) => (
                <button
                  key={i}
                  onClick={() => navigateTo(ref.fileId)}
                  className="flex items-start gap-2 text-xs text-zinc-400 hover:text-zinc-200 transition-colors w-full text-left"
                >
                  <FileText size={11} className="shrink-0 mt-0.5 text-zinc-600" />
                  <div className="flex-1 min-w-0">
                    <p className="text-zinc-300 truncate">{ref.documentTitle}</p>
                    <p className="text-[10px] text-zinc-600 truncate">{ref.context}</p>
                  </div>
                  <span className="text-[9px] font-bold uppercase text-zinc-600 shrink-0">{ref.artifactType}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {cpt.references.length === 0 && (
          <div className="px-4 py-2">
            <p className="text-[10px] text-zinc-600 italic">No cross-references found</p>
          </div>
        )}
      </div>
    </>
  )
}
