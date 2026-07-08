import { ChevronRight, ChevronDown, Folder, FolderOpen, FileText, Code2, Database, Settings, File } from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import { FILE_TREE, type FileNode } from '../../data/file-mock-data'

function getFileIcon(node: FileNode) {
  if (node.type === 'folder') return null
  switch (node.language) {
    case 'markdown': return <FileText size={13} className="text-blue-400 flex-shrink-0" />
    case 'typescript': return <Code2 size={13} className="text-sky-400 flex-shrink-0" />
    case 'sql': return <Database size={13} className="text-orange-400 flex-shrink-0" />
    case 'toml': return <Settings size={13} className="text-zinc-400 flex-shrink-0" />
    default: return <File size={13} className="text-zinc-400 flex-shrink-0" />
  }
}

function TreeNode({ node, depth }: { node: FileNode; depth: number }) {
  const openFileId = useAppStore(s => s.openFileId)
  const openFile = useAppStore(s => s.openFile)
  const expandedFolders = useAppStore(s => s.expandedFolders)
  const toggleFolder = useAppStore(s => s.toggleFolder)
  const modifiedFiles = useAppStore(s => s.modifiedFiles)

  const isActive = openFileId === node.id
  const isExpanded = expandedFolders.has(node.id)
  const isModified = modifiedFiles.has(node.id)
  const indentPx = depth * 12

  if (node.type === 'folder') {
    return (
      <div>
        <div
          className="flex items-center gap-1 py-0.5 px-2 cursor-pointer hover:bg-zinc-800/60 select-none"
          style={{ paddingLeft: indentPx + 8 }}
          onClick={() => toggleFolder(node.id)}
        >
          <span className="text-zinc-500 flex-shrink-0">
            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
          {isExpanded
            ? <FolderOpen size={13} className="text-yellow-500/80 flex-shrink-0" />
            : <Folder size={13} className="text-yellow-500/80 flex-shrink-0" />
          }
          <span className="text-xs text-zinc-300 truncate ml-0.5">{node.name}</span>
        </div>
        {isExpanded && node.children?.map(child => (
          <TreeNode key={child.id} node={child} depth={depth + 1} />
        ))}
      </div>
    )
  }

  return (
    <div
      className={`flex items-center gap-1.5 py-0.5 px-2 cursor-pointer select-none group ${
        isActive ? 'bg-indigo-500/20 text-indigo-300' : 'hover:bg-zinc-800/60'
      }`}
      style={{ paddingLeft: indentPx + 8 }}
      onClick={() => openFile(node.id)}
    >
      {getFileIcon(node)}
      <span className={`text-xs truncate flex-1 ${
        node.isDraft ? 'text-amber-400' : isActive ? 'text-indigo-300' : 'text-zinc-300'
      }`}>
        {node.name}
      </span>
      {isModified && (
        <span className="text-amber-400 text-xs flex-shrink-0">•</span>
      )}
      {node.linkedObjectId && !isModified && (
        <span
          className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-indigo-400/70"
          title={`Linked: ${node.linkedObjectId}`}
        />
      )}
    </div>
  )
}

export function FileTree() {
  return (
    <div
      className="flex-shrink-0 flex flex-col border-r border-zinc-800 overflow-y-auto"
      style={{ width: 240, height: '100%' }}
    >
      <div className="px-3 py-2 border-b border-zinc-800 flex-shrink-0">
        <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
          billing-service
        </span>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {FILE_TREE.map(node => (
          <TreeNode key={node.id} node={node} depth={0} />
        ))}
      </div>
    </div>
  )
}
