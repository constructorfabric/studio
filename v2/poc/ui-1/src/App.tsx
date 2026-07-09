import { ReactFlowProvider } from '@xyflow/react'
import { useAppStore } from './store/app-store'
import { TopBar } from './components/layout/TopBar'
import { Sidebar } from './components/layout/Sidebar'
import { RightPanel } from './components/layout/RightPanel'
import { ObjectGraph } from './components/graph/ObjectGraph'
import { ActivityFeed } from './components/workers/ActivityFeed'
import { FlowsView } from './components/flows/FlowsView'
import { RecommendationsPanel } from './components/recommendations/RecommendationsPanel'
import { WorkerRunSimulator } from './components/workers/WorkerRunSimulator'
import { WorkersMonitor } from './components/workers/WorkersMonitor'
import { WorkersCatalog } from './components/workers/WorkersCatalog'
import { AgenticLoopView } from './components/workers/AgenticLoopView'
import { WorkerInteractionModal } from './components/workers/WorkerInteractionModal'
import { AuditLog } from './components/audit/AuditLog'
import { FileTree } from './components/files/FileTree'
import { FileViewer } from './components/files/FileViewer'
import { LineActionBar } from './components/files/LineActionBar'
import { KitsView } from './components/kits/KitsView'
import { WorkspacesView } from './components/workspaces/WorkspacesView'
import { ChatView } from './components/chat/ChatView'
import { BottomPanel } from './components/chat/BottomPanel'

export default function App() {
  const activeView = useAppStore(s => s.activeView)

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* Top bar */}
      <TopBar />

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <Sidebar />

        {/* Main content */}
        <main className="flex-1 flex overflow-hidden relative">
          {activeView === 'graph' && (
            <ReactFlowProvider>
              <ObjectGraph />
            </ReactFlowProvider>
          )}

          {activeView === 'flows' && (
            <div className="flex-1 flex overflow-hidden">
              <FlowsView />
            </div>
          )}

          {activeView === 'activity' && (
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="p-4 border-b border-zinc-800">
                <h2 className="text-base font-semibold text-zinc-100">Activity Feed</h2>
                <p className="text-xs text-zinc-500 mt-0.5">All worker runs across this workspace</p>
              </div>
              <ActivityFeed />
            </div>
          )}

          {activeView === 'recommendations' && (
            <div className="flex-1 flex flex-col overflow-hidden">
              <RecommendationsPanel />
            </div>
          )}

          {activeView === 'files' && (
            <div className="flex-1 flex overflow-hidden">
              <FileTree />
              <FileViewer />
            </div>
          )}

          {activeView === 'kits' && (
            <div className="flex-1 flex overflow-hidden">
              <KitsView />
            </div>
          )}

          {activeView === 'workspaces' && (
            <div className="flex-1 flex overflow-hidden">
              <WorkspacesView />
            </div>
          )}

          {activeView === 'workers' && (
            <div className="flex-1 flex overflow-hidden">
              <WorkersMonitor />
            </div>
          )}

          {activeView === 'catalog' && (
            <div className="flex-1 flex overflow-hidden">
              <WorkersCatalog />
            </div>
          )}

          {activeView === 'audit' && (
            <div className="flex-1 flex overflow-hidden">
              <AuditLog />
            </div>
          )}

          {activeView === 'loop' && (
            <div className="flex-1 flex overflow-hidden">
              <AgenticLoopView />
            </div>
          )}

        </main>

        {/* Right panel (slides in) */}
        <RightPanel />
      </div>

      {/* Bottom AI Chat panel */}
      <BottomPanel />

      {/* Floating overlays */}
      <WorkerRunSimulator />
      <WorkerInteractionModal />
      <LineActionBar />
    </div>
  )
}
