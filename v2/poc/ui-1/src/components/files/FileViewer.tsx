import { useRef, useState, useEffect, useMemo } from 'react'
import Editor from '@monaco-editor/react'
import type { editor as MonacoEditor } from 'monaco-editor'
import { Save, Link2, Eye, Code2, Columns2 } from 'lucide-react'
import { useAppStore } from '../../store/app-store'
import { FILE_TREE, type FileNode } from '../../data/file-mock-data'
import { MOCK_OBJECTS } from '../../data/mock-data'
import { getCptById, type CptIdentifier } from '../../data/cpt-registry'
import { CptPopup } from './CptPopup'

// ─── CPT regex ────────────────────────────────────────────────────────────────
const CPT_RE = /\bcpt-[a-z]+-[a-z]+-[a-z0-9-]+\b/g

// Find line number (1-based) of the first occurrence of a CPT id in text
function findCptLine(content: string, cptId: string): number {
  const lines = content.split('\n')
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes(cptId)) return i + 1
  }
  return 1
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function findFileById(nodes: FileNode[], id: string): FileNode | null {
  for (const node of nodes) {
    if (node.id === id) return node
    if (node.children) {
      const found = findFileById(node.children, id)
      if (found) return found
    }
  }
  return null
}

function getFilePath(nodes: FileNode[], targetId: string, path: string[] = []): string[] | null {
  for (const node of nodes) {
    const current = [...path, node.name]
    if (node.id === targetId) return current
    if (node.children) {
      const found = getFilePath(node.children, targetId, current)
      if (found) return found
    }
  }
  return null
}

const LANGUAGE_MAP: Record<string, string> = {
  markdown: 'markdown', typescript: 'typescript',
  sql: 'sql', toml: 'ini', text: 'plaintext',
}

const FILE_TO_OBJECT: Record<string, string> = {
  'file-prd': 'prd-001', 'file-design': 'design-001',
  'file-adr-001': 'adr-001', 'file-adr-002': 'adr-002',
  'file-feat-stripe': 'fspec-001', 'file-feat-invoice': 'fspec-002',
  'file-webhook-handler': 'pr-001',
}

// ─── Inline Markdown Renderer ─────────────────────────────────────────────────

function renderMarkdown(md: string): string {
  if (!md) return ''
  let html = md

  // Fenced code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) =>
    `<pre class="md-code-block" data-lang="${lang}"><code>${escapeHtml(code.trim())}</code></pre>`)

  // Process line by line for block-level elements
  const lines = html.split('\n')
  const result: string[] = []
  let inList = false
  let inParagraph = false

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Already processed code blocks — pass through
    if (line.startsWith('<pre class="md-code-block"')) {
      if (inList) { result.push('</ul>'); inList = false }
      if (inParagraph) { result.push('</p>'); inParagraph = false }
      result.push(line)
      continue
    }

    // Headers
    const h3 = line.match(/^### (.+)/)
    const h2 = line.match(/^## (.+)/)
    const h1 = line.match(/^# (.+)/)
    if (h1 || h2 || h3) {
      if (inList) { result.push('</ul>'); inList = false }
      if (inParagraph) { result.push('</p>'); inParagraph = false }
      const [, text] = (h1 ?? h2 ?? h3)!
      const tag = h1 ? 'h1' : h2 ? 'h2' : 'h3'
      result.push(`<${tag}>${inlineMarkdown(text)}</${tag}>`)
      continue
    }

    // Blockquote
    const bq = line.match(/^> (.*)/)
    if (bq) {
      if (inList) { result.push('</ul>'); inList = false }
      if (inParagraph) { result.push('</p>'); inParagraph = false }
      result.push(`<blockquote>${inlineMarkdown(bq[1])}</blockquote>`)
      continue
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      if (inList) { result.push('</ul>'); inList = false }
      if (inParagraph) { result.push('</p>'); inParagraph = false }
      result.push('<hr/>')
      continue
    }

    // List items
    const li = line.match(/^[-*+] (.+)/) ?? line.match(/^\d+\. (.+)/)
    if (li) {
      if (!inList) { result.push('<ul>'); inList = true }
      if (inParagraph) { result.push('</p>'); inParagraph = false }
      result.push(`<li>${inlineMarkdown(li[1])}</li>`)
      continue
    }

    // Table row
    if (line.includes('|') && line.trim().startsWith('|')) {
      if (inList) { result.push('</ul>'); inList = false }
      if (inParagraph) { result.push('</p>'); inParagraph = false }
      // Check if separator row
      if (/^\|[\s-:|]+\|/.test(line)) {
        result.push('<tr class="md-table-sep"/>')
      } else {
        const cells = line.split('|').filter((_, i, a) => i > 0 && i < a.length - 1)
        result.push(`<tr>${cells.map(c => `<td>${inlineMarkdown(c.trim())}</td>`).join('')}</tr>`)
      }
      continue
    }

    // Empty line
    if (line.trim() === '') {
      if (inList) { result.push('</ul>'); inList = false }
      if (inParagraph) { result.push('</p>'); inParagraph = false }
      continue
    }

    // Paragraph text
    if (!inParagraph) { result.push('<p>'); inParagraph = true }
    else result.push('<br/>')
    result.push(inlineMarkdown(line))
  }

  if (inList) result.push('</ul>')
  if (inParagraph) result.push('</p>')

  // Wrap adjacent table rows in <table>
  let final = result.join('\n')
  final = final.replace(/<tr.*?<\/tr>(\n<tr.*?<\/tr>)*/gs, match => {
    const rows = match.split('\n').filter(Boolean)
    const header = rows[0]
    const rest = rows.slice(2) // skip separator
    const headerCells = header.match(/<td>(.*?)<\/td>/g) ?? []
    const thead = `<thead><tr>${headerCells.map(c => c.replace('<td>', '<th>').replace('</td>', '</th>')).join('')}</tr></thead>`
    const tbody = `<tbody>${rest.join('\n')}</tbody>`
    return `<table>${thead}${tbody}</table>`
  })

  return final
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const CPT_PATTERN = /\bcpt-[a-z]+-[a-z]+-[a-z0-9-]+\b/

function inlineMarkdown(text: string): string {
  return text
    .replace(/`([^`]+)`/g, (_m, inner: string) => {
      if (CPT_PATTERN.test(inner)) {
        return `<code class="md-cpt-chip" data-cpt-id="${inner}">${inner}</code>`
      }
      return `<code>${inner}</code>`
    })
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/_(.+?)_/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\*\[(\w+-\d+)\]\*/g, '<span class="md-req-id">$1</span>')
    .replace(/\*\*\[(\w+-\d+)\]\*\*/g, '<strong class="md-req-id">$1</strong>')
}

// ─── Markdown Preview Component ───────────────────────────────────────────────

const PREVIEW_CSS = `
.md-preview { font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; font-size: 13px; line-height: 1.7; color: #d4d4d8; padding: 20px 28px; max-width: 780px; }
.md-preview h1 { font-size: 22px; font-weight: 700; color: #f4f4f5; margin: 0 0 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(63,63,70,0.5); }
.md-preview h2 { font-size: 17px; font-weight: 700; color: #e4e4e7; margin: 24px 0 10px; padding-bottom: 5px; border-bottom: 1px solid rgba(63,63,70,0.3); }
.md-preview h3 { font-size: 14px; font-weight: 700; color: #d4d4d8; margin: 18px 0 8px; }
.md-preview p { margin: 0 0 12px; }
.md-preview strong { color: #f4f4f5; font-weight: 700; }
.md-preview em { color: #c4b5fd; font-style: italic; }
.md-preview code { font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 12px; background: rgba(39,39,42,0.8); color: #86efac; padding: 1px 5px; border-radius: 4px; border: 1px solid rgba(63,63,70,0.4); }
.md-preview pre.md-code-block { background: rgba(9,9,11,0.8); border: 1px solid rgba(63,63,70,0.5); border-radius: 8px; padding: 14px 16px; margin: 12px 0; overflow-x: auto; }
.md-preview pre.md-code-block code { background: none; border: none; padding: 0; color: #86efac; font-size: 12px; line-height: 1.6; }
.md-preview ul { margin: 6px 0 12px; padding-left: 20px; }
.md-preview li { margin-bottom: 4px; }
.md-preview blockquote { border-left: 3px solid rgba(99,102,241,0.5); margin: 12px 0; padding: 6px 14px; background: rgba(99,102,241,0.05); color: #a1a1aa; border-radius: 0 4px 4px 0; }
.md-preview hr { border: none; border-top: 1px solid rgba(63,63,70,0.4); margin: 20px 0; }
.md-preview table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 12px; }
.md-preview th { background: rgba(39,39,42,0.6); color: #a1a1aa; font-weight: 600; padding: 7px 12px; border: 1px solid rgba(63,63,70,0.4); text-align: left; }
.md-preview td { padding: 6px 12px; border: 1px solid rgba(63,63,70,0.3); }
.md-preview tr:nth-child(even) td { background: rgba(24,24,27,0.4); }
.md-preview a { color: #818cf8; text-decoration: none; }
.md-preview a:hover { text-decoration: underline; }
.md-preview .md-req-id { font-size: 11px; font-weight: 700; color: #34d399; background: rgba(52,211,153,0.1); border: 1px solid rgba(52,211,153,0.3); border-radius: 4px; padding: 1px 5px; font-family: monospace; }
.md-preview code.md-cpt-chip { color: #86efac; background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.2); cursor: pointer; transition: opacity 0.1s; }
.md-preview code.md-cpt-chip:hover { opacity: 0.75; }
.md-preview code.md-cpt-chip.md-cpt-definition { color: #a5b4fc; background: rgba(99,102,241,0.12); border: 1px solid rgba(99,102,241,0.3); }
`

// Inject Monaco decoration styles globally (once)
if (typeof document !== 'undefined' && !document.getElementById('cpt-monaco-styles')) {
  const s = document.createElement('style')
  s.id = 'cpt-monaco-styles'
  s.textContent = `
    .cpt-def-deco { color: #a5b4fc !important; background: rgba(99,102,241,0.15) !important; border-radius: 3px; cursor: pointer; }
    .cpt-ref-deco { color: #86efac !important; background: rgba(34,197,94,0.1) !important; border-radius: 3px; cursor: pointer; }
    .cpt-flash-line { background: rgba(99,102,241,0.08) !important; }
  `
  document.head.appendChild(s)
}

interface MarkdownPreviewProps {
  content: string
  openFileId: string | null
  onCptClick: (cpt: CptIdentifier, pos: { x: number; y: number }) => void
  outerRef?: React.RefObject<HTMLDivElement>
}

function MarkdownPreview({ content, openFileId, onCptClick, outerRef }: MarkdownPreviewProps) {
  const html = useMemo(() => renderMarkdown(content), [content])

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement
    if (target.tagName === 'CODE' && target.classList.contains('md-cpt-chip')) {
      const cptId = target.getAttribute('data-cpt-id')
      if (cptId) {
        const cpt = getCptById(cptId)
        if (cpt) {
          e.stopPropagation()
          onCptClick(cpt, { x: e.clientX + 10, y: e.clientY - 10 })
          return
        }
      }
    }
  }

  // After render, apply definition styling to chips whose definedIn matches current file
  const containerRef = useRef<HTMLDivElement>(null)
  // Merged ref: assigns to both internal containerRef and outer previewRef
  const setDivRef = (el: HTMLDivElement | null) => {
    (containerRef as React.MutableRefObject<HTMLDivElement | null>).current = el
    if (outerRef) (outerRef as React.MutableRefObject<HTMLDivElement | null>).current = el
  }
  useMemo(() => {
    // Run after paint via queueMicrotask
    if (typeof window !== 'undefined') {
      queueMicrotask(() => {
        const el = containerRef.current
        if (!el || !openFileId) return
        el.querySelectorAll<HTMLElement>('code.md-cpt-chip').forEach(chip => {
          const id = chip.getAttribute('data-cpt-id')
          if (!id) return
          const cpt = getCptById(id)
          if (cpt && cpt.definedIn.fileId === openFileId) {
            chip.classList.add('md-cpt-definition')
          } else {
            chip.classList.remove('md-cpt-definition')
          }
        })
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [html, openFileId])

  return (
    <>
      <style>{PREVIEW_CSS}</style>
      <div
        ref={setDivRef}
        className="md-preview flex-1 overflow-y-auto"
        dangerouslySetInnerHTML={{ __html: html }}
        style={{ background: '#09090b', height: '100%', overflowY: 'auto' }}
        onClick={handleClick}
      />
    </>
  )
}

// ─── View mode toggle ─────────────────────────────────────────────────────────

type ViewMode = 'preview' | 'source' | 'split'

function ViewModeToggle({ mode, onChange, isMarkdown }: {
  mode: ViewMode
  onChange: (m: ViewMode) => void
  isMarkdown: boolean
}) {
  if (!isMarkdown) return null
  const opts: { value: ViewMode; icon: typeof Eye; label: string }[] = [
    { value: 'preview', icon: Eye, label: 'Preview' },
    { value: 'split',   icon: Columns2, label: 'Split' },
    { value: 'source',  icon: Code2,    label: 'Source' },
  ]
  return (
    <div style={{
      display: 'flex', gap: 1, background: 'rgba(24,24,27,0.8)',
      border: '1px solid rgba(63,63,70,0.5)', borderRadius: 7, padding: 2,
    }}>
      {opts.map(o => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          title={o.label}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 9px', borderRadius: 5, border: 'none',
            background: mode === o.value ? 'rgba(99,102,241,0.3)' : 'transparent',
            color: mode === o.value ? '#a5b4fc' : '#71717a',
            fontSize: 11, fontWeight: 500, cursor: 'pointer',
            transition: 'all 0.15s',
          }}
        >
          <o.icon size={11} /> {o.label}
        </button>
      ))}
    </div>
  )
}

// ─── Main FileViewer ──────────────────────────────────────────────────────────

export function FileViewer() {
  const openFileId       = useAppStore(s => s.openFileId)
  const fileContents     = useAppStore(s => s.fileContents)
  const modifiedFiles    = useAppStore(s => s.modifiedFiles)
  const updateFileContent = useAppStore(s => s.updateFileContent)
  const saveFile         = useAppStore(s => s.saveFile)
  const setLineAction    = useAppStore(s => s.setLineAction)
  const selectObject     = useAppStore(s => s.selectObject)
  const scrollToCptId    = useAppStore(s => s.scrollToCptId)
  const setScrollToCptId = useAppStore(s => s.setScrollToCptId)
  const editorRef = useRef<MonacoEditor.IStandaloneCodeEditor | null>(null)
  const decorationIdsRef = useRef<string[]>([])

  const [activeCpt, setActiveCpt] = useState<{ cpt: CptIdentifier; pos: { x: number; y: number } } | null>(null)

  const file = openFileId ? findFileById(FILE_TREE, openFileId) : null
  const content = openFileId ? (fileContents[openFileId] ?? '') : ''
  const isModified = openFileId ? modifiedFiles.has(openFileId) : false
  const breadcrumb = openFileId ? (getFilePath(FILE_TREE, openFileId) ?? []) : []
  const isMarkdown = file?.language === 'markdown'

  // Default to preview for markdown, source for everything else
  const [viewMode, setViewMode] = useState<ViewMode>(isMarkdown ? 'preview' : 'source')

  // Update viewMode when file changes
  const prevFileId = useRef(openFileId)
  if (prevFileId.current !== openFileId) {
    prevFileId.current = openFileId
    if (isMarkdown && viewMode === 'source') {
      // keep source if user explicitly chose it
    } else if (isMarkdown) {
      // stay in preview by default (handled by initial state per file)
    }
  }

  const linkedObjectId = openFileId ? FILE_TO_OBJECT[openFileId] : null
  const linkedObject = linkedObjectId ? MOCK_OBJECTS.find(o => o.id === linkedObjectId) : null

  // Apply CPT decorations to Monaco editor (source view)
  const applyCptDecorations = (editorInstance: MonacoEditor.IStandaloneCodeEditor, text: string, fileId: string) => {
    const model = editorInstance.getModel()
    if (!model) return
    const newDecorations: MonacoEditor.IModelDeltaDecoration[] = []
    const lines = text.split('\n')
    for (let i = 0; i < lines.length; i++) {
      let m: RegExpExecArray | null
      CPT_RE.lastIndex = 0
      while ((m = CPT_RE.exec(lines[i])) !== null) {
        const cptDef = getCptById(m[0])
        if (!cptDef) continue
        const isDefinition = cptDef.definedIn.fileId === fileId
        newDecorations.push({
          range: {
            startLineNumber: i + 1, startColumn: m.index + 1,
            endLineNumber: i + 1, endColumn: m.index + m[0].length + 1,
          },
          options: {
            inlineClassName: isDefinition ? 'cpt-def-deco' : 'cpt-ref-deco',
            hoverMessage: { value: `**${cptDef.name}** (${cptDef.kind})\n\n${cptDef.description}` },
          },
        })
      }
    }
    decorationIdsRef.current = model.deltaDecorations(decorationIdsRef.current, newDecorations)
  }

  const previewRef = useRef<HTMLDivElement>(null)

  // Scroll to CPT id after navigation — works in both source (Monaco) and preview modes
  useEffect(() => {
    if (!scrollToCptId || !openFileId) return

    // Retry until content is available (Monaco loads asynchronously after file switch)
    let attempts = 0
    const MAX = 10

    const tryScroll = () => {
      attempts++

      // ── Preview mode: scroll the preview container via DOM ──────────────
      if (previewRef.current) {
        const chip = previewRef.current.querySelector<HTMLElement>(`[data-cpt-id="${scrollToCptId}"]`)
        if (chip) {
          chip.scrollIntoView({ behavior: 'smooth', block: 'center' })
          // Briefly highlight
          const prev = chip.style.outline
          chip.style.outline = '2px solid rgba(99,102,241,0.7)'
          chip.style.borderRadius = '4px'
          setTimeout(() => { chip.style.outline = prev }, 1500)
          setScrollToCptId(null)
          return
        }
        // Preview rendered but chip not found yet — retry
        if (attempts < MAX) { setTimeout(tryScroll, 80); return }
        setScrollToCptId(null)
        return
      }

      // ── Source mode: scroll Monaco editor ───────────────────────────────
      const editor = editorRef.current
      if (!editor) {
        if (attempts < MAX) { setTimeout(tryScroll, 80); return }
        setScrollToCptId(null)
        return
      }

      // Read content from store (always up-to-date)
      const text = useAppStore.getState().fileContents[openFileId] ?? ''
      if (!text && attempts < MAX) { setTimeout(tryScroll, 80); return }

      const line = findCptLine(text, scrollToCptId)

      // Verify Monaco model has caught up to the new file
      const modelLineCount = editor.getModel()?.getLineCount() ?? 0
      const expectedLines = text.split('\n').length
      if (modelLineCount !== expectedLines && attempts < MAX) {
        setTimeout(tryScroll, 80)
        return
      }

      editor.revealLineInCenter(line)
      const model = editor.getModel()
      if (model) {
        const flashDec = model.deltaDecorations([], [{
          range: { startLineNumber: line, startColumn: 1, endLineNumber: line, endColumn: 1000 },
          options: { isWholeLine: true, className: 'cpt-flash-line' },
        }])
        setTimeout(() => model.deltaDecorations(flashDec, []), 1500)
      }
      setScrollToCptId(null)
    }

    // Initial delay to let Monaco/preview render the new file
    const t = setTimeout(tryScroll, 100)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrollToCptId, openFileId])

  const handleEditorMount = (editorInstance: MonacoEditor.IStandaloneCodeEditor) => {
    editorRef.current = editorInstance

    editorInstance.onDidChangeCursorSelection((e) => {
      const sel = e.selection
      const isEmpty = sel.startLineNumber === sel.endLineNumber && sel.startColumn === sel.endColumn
      if (isEmpty) {
        setLineAction({ visible: false })
        return
      }
      const pos = editorInstance.getScrolledVisiblePosition({ lineNumber: sel.startLineNumber, column: 1 })
      if (!pos) { setLineAction({ visible: false }); return }
      const domNode = editorInstance.getDomNode()
      if (!domNode) { setLineAction({ visible: false }); return }
      const rect = domNode.getBoundingClientRect()
      setLineAction({
        visible: true,
        top: rect.top + pos.top - 44,
        left: rect.left + 56,
        startLine: sel.startLineNumber,
        endLine: sel.endLineNumber,
        selectedText: editorInstance.getModel()?.getValueInRange(sel) ?? '',
        fileId: openFileId ?? undefined,
        language: file?.language,
      })
    })

    // CPT click handler in source view
    editorInstance.onMouseDown((e) => {
      // Only handle content-text clicks (not gutter, minimap, etc.)
      if (e.target.position == null) return
      const position = e.target.position
      const model = editorInstance.getModel()
      if (!model) return
      const lineText = model.getLineContent(position.lineNumber)

      // Find all CPT ids on this line and check if click falls within one
      CPT_RE.lastIndex = 0
      let match: RegExpExecArray | null
      while ((match = CPT_RE.exec(lineText)) !== null) {
        const startCol = match.index + 1
        const endCol   = startCol + match[0].length - 1
        if (position.column >= startCol && position.column <= endCol) {
          const cpt = getCptById(match[0])
          if (cpt) {
            const domNode = editorInstance.getDomNode()
            const rect = domNode?.getBoundingClientRect()
            const visPos = editorInstance.getScrolledVisiblePosition(position)
            if (rect && visPos) {
              e.event.preventDefault()
              setActiveCpt({
                cpt,
                pos: { x: rect.left + visPos.left + 80, y: rect.top + visPos.top + 20 },
              })
            }
          }
          break
        }
      }
    })

    // Apply initial CPT decorations
    const initialContent = editorInstance.getModel()?.getValue() ?? ''
    if (openFileId) applyCptDecorations(editorInstance, initialContent, openFileId)
  }

  // Re-apply decorations when file or content changes
  useEffect(() => {
    if (editorRef.current && openFileId) {
      const text = fileContents[openFileId] ?? ''
      applyCptDecorations(editorRef.current, text, openFileId)
    }
  }, [openFileId, fileContents])

  if (!openFileId || !file) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-600">
        <div className="text-center">
          <p className="text-sm">No file open</p>
          <p className="text-xs mt-1 text-zinc-700">Select a file from the tree</p>
        </div>
      </div>
    )
  }

  const monacoLanguage = LANGUAGE_MAP[file.language ?? 'text'] ?? 'plaintext'
  const showPreview = isMarkdown && (viewMode === 'preview' || viewMode === 'split')
  const showSource = !isMarkdown || viewMode === 'source' || viewMode === 'split'

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header bar */}
      <div style={{
        height: 40, display: 'flex', alignItems: 'center', gap: 8, padding: '0 12px',
        borderBottom: '1px solid rgba(63,63,70,0.5)', flexShrink: 0,
        background: 'rgba(9,9,11,0.8)',
      }}>
        {/* Breadcrumb */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flex: 1, minWidth: 0, overflow: 'hidden' }}>
          {breadcrumb.map((part, i) => (
            <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, flexShrink: i < breadcrumb.length - 1 ? 1 : 0 }}>
              {i > 0 && <span style={{ color: '#3f3f46' }}>/</span>}
              <span style={{ color: i === breadcrumb.length - 1 ? '#d4d4d8' : '#52525b', fontWeight: i === breadcrumb.length - 1 ? 600 : 400 }}>
                {part}
              </span>
            </span>
          ))}
        </div>

        {/* View mode toggle */}
        <ViewModeToggle mode={viewMode} onChange={setViewMode} isMarkdown={isMarkdown} />

        {/* Language badge */}
        {file.language && !isMarkdown && (
          <span style={{
            fontSize: 10, padding: '2px 7px', borderRadius: 5,
            background: 'rgba(39,39,42,0.8)', border: '1px solid rgba(63,63,70,0.5)',
            color: '#71717a',
          }}>
            {file.language}
          </span>
        )}

        {/* Modified */}
        {isModified && (
          <span style={{ fontSize: 10, color: '#f59e0b', fontWeight: 600 }}>● modified</span>
        )}

        {/* Linked object chip */}
        {linkedObject && (
          <button
            onClick={() => selectObject(linkedObject.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              fontSize: 11, padding: '2px 8px', borderRadius: 20,
              background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.3)',
              color: '#818cf8', cursor: 'pointer', flexShrink: 0,
            }}
          >
            <Link2 size={10} />
            {linkedObject.title.length > 20 ? linkedObject.title.slice(0, 20) + '…' : linkedObject.title}
          </button>
        )}

        {/* Save */}
        {isModified && (
          <button
            onClick={() => saveFile(openFileId)}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              fontSize: 11, padding: '3px 10px', borderRadius: 6, border: 'none',
              background: '#4f46e5', color: '#fff', cursor: 'pointer', fontWeight: 600,
              flexShrink: 0,
            }}
          >
            <Save size={11} /> Save
          </button>
        )}
      </div>

      {/* Content area */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Preview pane */}
        {showPreview && (
          <div style={{
            flex: 1, overflow: 'hidden',
            borderRight: viewMode === 'split' ? '1px solid rgba(63,63,70,0.5)' : 'none',
          }}>
            <MarkdownPreview
              content={content}
              openFileId={openFileId}
              onCptClick={(cpt, pos) => setActiveCpt({ cpt, pos })}
              outerRef={previewRef}
            />
          </div>
        )}

        {/* Source / editor pane */}
        {showSource && (
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <Editor
              height="100%"
              theme="vs-dark"
              language={monacoLanguage}
              value={content}
              onChange={(val) => updateFileContent(openFileId, val ?? '')}
              onMount={handleEditorMount}
              options={{
                fontSize: 13,
                lineHeight: 20,
                fontFamily: '"JetBrains Mono", "Fira Code", Menlo, monospace',
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                padding: { top: 12, bottom: 12 },
                renderLineHighlight: 'line',
                cursorBlinking: 'smooth',
                smoothScrolling: true,
              }}
            />
          </div>
        )}
      </div>

      {/* CPT cross-reference popup */}
      {activeCpt && (
        <CptPopup
          cpt={activeCpt.cpt}
          isDefinition={activeCpt.cpt.definedIn.fileId === openFileId}
          position={activeCpt.pos}
          onClose={() => setActiveCpt(null)}
        />
      )}
    </div>
  )
}
