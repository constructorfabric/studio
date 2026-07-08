import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, Send, X } from 'lucide-react'
import { useState } from 'react'
import { useAppStore } from '../../store/app-store'

export function WorkerInteractionModal() {
  const pendingId = useAppStore(s => s.pendingInteractionRunId)
  const workerRuns = useAppStore(s => s.workerRuns)
  const respondToInteraction = useAppStore(s => s.respondToInteraction)
  const cancelWorkerRun = useAppStore(s => s.cancelWorkerRun)

  const [inputValue, setInputValue] = useState('')
  const [selectedOption, setSelectedOption] = useState<string | null>(null)

  const run = pendingId ? workerRuns.find(r => r.id === pendingId) : null

  const handleSubmit = () => {
    if (!run || !pendingId) return
    const response = run.interaction?.kind === 'menu' ? (selectedOption ?? '') : inputValue.trim()
    if (!response) return
    respondToInteraction(pendingId, response)
    setInputValue('')
    setSelectedOption(null)
  }

  const handleDismiss = () => {
    if (!pendingId) return
    cancelWorkerRun(pendingId)
    setInputValue('')
    setSelectedOption(null)
  }

  return (
    <AnimatePresence>
      {run && run.interaction && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
            onClick={handleDismiss}
          />

          {/* Modal */}
          <motion.div
            key="modal"
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ type: 'spring', stiffness: 400, damping: 28 }}
            className="fixed inset-0 flex items-center justify-center z-50 pointer-events-none"
          >
            <div
              className="bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl w-full max-w-md mx-4 pointer-events-auto"
              onClick={e => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-start justify-between p-5 border-b border-zinc-800">
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-xl bg-amber-900/40 border border-amber-700/50 flex items-center justify-center shrink-0 mt-0.5">
                    <AlertCircle size={18} className="text-amber-400" />
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-zinc-100">Worker Needs Input</h2>
                    <p className="text-xs text-zinc-500 mt-0.5">{run.workerLabel} • {run.objectTitle}</p>
                  </div>
                </div>
                <button
                  onClick={handleDismiss}
                  className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Body */}
              <div className="p-5 space-y-4">
                {/* Interaction prompt */}
                <div className="bg-zinc-800/60 rounded-xl p-4 border border-zinc-700/50">
                  <p className="text-sm text-zinc-200 leading-relaxed">{run.interaction.prompt}</p>
                </div>

                {/* Menu options */}
                {run.interaction.kind === 'menu' && run.interaction.options && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-zinc-400">Choose an option:</p>
                    {run.interaction.options.map(option => (
                      <button
                        key={option}
                        onClick={() => setSelectedOption(option)}
                        className={`
                          w-full text-left px-4 py-3 rounded-xl border text-sm font-medium transition-all
                          ${selectedOption === option
                            ? 'bg-indigo-900/50 border-indigo-600 text-indigo-200 shadow-sm shadow-indigo-900/30'
                            : 'bg-zinc-800 border-zinc-700 text-zinc-300 hover:border-zinc-500 hover:text-zinc-100'
                          }
                        `}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors ${
                            selectedOption === option
                              ? 'border-indigo-500 bg-indigo-500'
                              : 'border-zinc-600'
                          }`}>
                            {selectedOption === option && (
                              <div className="w-1.5 h-1.5 rounded-full bg-white" />
                            )}
                          </div>
                          {option}
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                {/* Text input */}
                {(run.interaction.kind === 'input_request' || run.interaction.kind === 'free_form_intent') && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-zinc-400">Your response:</p>
                    <textarea
                      value={inputValue}
                      onChange={e => setInputValue(e.target.value)}
                      placeholder="Type your response here…"
                      rows={4}
                      className="w-full px-3 py-2.5 bg-zinc-800 border border-zinc-700 rounded-xl text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 resize-none transition-colors"
                      onKeyDown={e => {
                        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit()
                      }}
                    />
                    <p className="text-[10px] text-zinc-600">Press ⌘↵ to submit</p>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="flex items-center justify-end gap-2 p-4 border-t border-zinc-800">
                <button
                  onClick={handleDismiss}
                  className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={run.interaction.kind === 'menu' ? !selectedOption : !inputValue.trim()}
                  className={`
                    flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all
                    ${(run.interaction.kind === 'menu' ? selectedOption : inputValue.trim())
                      ? 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm shadow-indigo-900/40'
                      : 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
                    }
                  `}
                >
                  <Send size={14} />
                  Continue
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
