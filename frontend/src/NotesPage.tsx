import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  AlignLeft, Bold, BookOpen, Braces, Check, ChevronRight, Code2, FileCode2,
  FileText, GitBranch, Heading1, Heading2, ImagePlus, Italic, Link2, List,
  ListOrdered, LoaderCircle, Network, PanelLeftClose, Plus, Presentation,
  Quote, Search, Sigma, Sparkles, X,
} from 'lucide-react'
import { api } from './api'
import type { NoteArtifact, NoteEditorMode, NoteFormat, Paper, UnifiedNote } from './types'
import './notes.css'
import PresentationOutlineEditor from './PresentationOutlineEditor'

const blankMarkdown = `# 新笔记\n\n从一个问题、想法或阅读线索开始。\n\n## 关键发现\n\n`
const blankLatex = `\\documentclass[UTF8]{ctexart}\n\\usepackage{amsmath,amssymb,graphicx}\n\\title{新笔记}\n\\begin{document}\n\\maketitle\n\n\\section{研究问题}\n\n\\end{document}\n`

const formatLabels: Record<NoteFormat, string> = { markdown: 'Markdown', latex: 'LaTeX' }
const artifactMeta = {
  flowchart: { label: '生成流程图', icon: GitBranch },
  mindmap: { label: '生成思维导图', icon: Network },
  presentation: { label: '制作组会 PPT', icon: Presentation },
} as const

function dateLabel(value?: string) {
  if (!value) return '刚刚更新'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}

function escapeHtml(value: string) {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function inlineMarkdown(value: string) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2">$1</a>')
}

function markdownToEditorHtml(markdown: string) {
  const lines = markdown.split('\n')
  const html: string[] = []
  let list: 'ul' | 'ol' | null = null
  const closeList = () => { if (list) html.push(`</${list}>`); list = null }
  for (const line of lines) {
    const bullet = line.match(/^[-*] (.*)$/)
    const ordered = line.match(/^\d+\. (.*)$/)
    if (bullet || ordered) {
      const kind = bullet ? 'ul' : 'ol'
      if (list !== kind) { closeList(); list = kind; html.push(`<${kind}>`) }
      html.push(`<li>${inlineMarkdown((bullet || ordered)![1])}</li>`)
      continue
    }
    closeList()
    if (line.startsWith('# ')) html.push(`<h1>${inlineMarkdown(line.slice(2))}</h1>`)
    else if (line.startsWith('## ')) html.push(`<h2>${inlineMarkdown(line.slice(3))}</h2>`)
    else if (line.startsWith('> ')) html.push(`<blockquote>${inlineMarkdown(line.slice(2))}</blockquote>`)
    else if (line.trim()) html.push(`<p>${inlineMarkdown(line)}</p>`)
    else html.push('<p><br></p>')
  }
  closeList()
  return html.join('')
}

function editorHtmlToMarkdown(root: HTMLElement) {
  const renderInline = (node: Node): string => {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent || ''
    if (!(node instanceof HTMLElement)) return ''
    const content = Array.from(node.childNodes).map(renderInline).join('')
    if (node.tagName === 'STRONG' || node.tagName === 'B') return `**${content}**`
    if (node.tagName === 'EM' || node.tagName === 'I') return `*${content}*`
    if (node.tagName === 'CODE') return `\`${content}\``
    if (node.tagName === 'A') return `[${content}](${node.getAttribute('href') || ''})`
    if (node.tagName === 'BR') return '\n'
    return content
  }
  return Array.from(root.children).map(element => {
    const text = renderInline(element).trimEnd()
    if (element.tagName === 'H1') return `# ${text}`
    if (element.tagName === 'H2') return `## ${text}`
    if (element.tagName === 'BLOCKQUOTE') return `> ${text}`
    if (element.tagName === 'UL') return Array.from(element.children).map(item => `- ${renderInline(item)}`).join('\n')
    if (element.tagName === 'OL') return Array.from(element.children).map((item, index) => `${index + 1}. ${renderInline(item)}`).join('\n')
    return text
  }).join('\n\n').replace(/\n{3,}/g, '\n\n')
}

function ToolbarButton({ title, onClick, children }: { title: string; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" title={title} aria-label={title} onMouseDown={event => event.preventDefault()} onClick={onClick}>{children}</button>
}

function StandardMarkdownEditor({ value, onChange, onInsertPaper }: { value: string; onChange: (value: string) => void; onInsertPaper: () => void }) {
  const editor = useRef<HTMLDivElement>(null)
  useEffect(() => { if (editor.current) editor.current.innerHTML = markdownToEditorHtml(value) }, [])
  const command = (name: string, commandValue?: string) => {
    editor.current?.focus()
    document.execCommand(name, false, commandValue)
    if (editor.current) onChange(editorHtmlToMarkdown(editor.current))
  }
  const insertText = (text: string) => {
    editor.current?.focus()
    document.execCommand('insertText', false, text)
    if (editor.current) onChange(editorHtmlToMarkdown(editor.current))
  }
  return <div className="notes-standard-editor">
    <div className="notes-rich-toolbar" aria-label="文本格式">
      <div><ToolbarButton title="正文" onClick={() => command('formatBlock', 'p')}><AlignLeft/></ToolbarButton><ToolbarButton title="一级标题" onClick={() => command('formatBlock', 'h1')}><Heading1/></ToolbarButton><ToolbarButton title="二级标题" onClick={() => command('formatBlock', 'h2')}><Heading2/></ToolbarButton></div>
      <div><ToolbarButton title="加粗" onClick={() => command('bold')}><Bold/></ToolbarButton><ToolbarButton title="斜体" onClick={() => command('italic')}><Italic/></ToolbarButton><ToolbarButton title="引用" onClick={() => command('formatBlock', 'blockquote')}><Quote/></ToolbarButton></div>
      <div><ToolbarButton title="项目符号" onClick={() => command('insertUnorderedList')}><List/></ToolbarButton><ToolbarButton title="编号列表" onClick={() => command('insertOrderedList')}><ListOrdered/></ToolbarButton><ToolbarButton title="插入链接" onClick={() => { const url = window.prompt('粘贴链接地址'); if (url) command('createLink', url) }}><Link2/></ToolbarButton></div>
      <div><ToolbarButton title="插入公式" onClick={() => insertText(' $E = mc^2$ ')}><Sigma/></ToolbarButton><ToolbarButton title="引用论文" onClick={onInsertPaper}><BookOpen/></ToolbarButton><ToolbarButton title="插入图片说明" onClick={() => insertText(' ![图片说明](图片地址) ')}><ImagePlus/></ToolbarButton></div>
    </div>
    <div ref={editor} className="notes-contenteditable" contentEditable suppressContentEditableWarning spellCheck onInput={() => editor.current && onChange(editorHtmlToMarkdown(editor.current))}/>
  </div>
}

function MarkdownSourceEditor({ value, onChange, view, setView }: { value: string; onChange: (value: string) => void; view: 'source' | 'split' | 'preview'; setView: (value: 'source' | 'split' | 'preview') => void }) {
  return <div className={`notes-source-workspace view-${view}`}>
    <div className="notes-view-switch">{([['source', '源码'], ['split', '并排'], ['preview', '预览']] as const).map(([key, label]) => <button className={view === key ? 'active' : ''} key={key} onClick={() => setView(key)}>{label}</button>)}</div>
    {view !== 'preview' && <textarea className="notes-source" value={value} onChange={event => onChange(event.target.value)} spellCheck={false}/>} 
    {view !== 'source' && <article className="notes-markdown-preview"><ReactMarkdown remarkPlugins={[remarkGfm]}>{value || '*从左侧开始记录*'}</ReactMarkdown></article>}
  </div>
}

function LatexEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [preview, setPreview] = useState(true)
  const documentBody = value.match(/\\begin\{document\}([\s\S]*?)\\end\{document\}/)?.[1]?.trim() || value
  return <div className={`notes-latex-editor ${preview ? '' : 'source-only'}`}>
    <div className="notes-view-switch"><button className={!preview ? 'active' : ''} onClick={() => setPreview(false)}>源码</button><button className={preview ? 'active' : ''} onClick={() => setPreview(true)}>源码与预览</button></div>
    <textarea className="notes-source" value={value} onChange={event => onChange(event.target.value)} spellCheck={false}/>
    {preview && <article className="notes-latex-preview"><span>排版预览</span><pre>{documentBody}</pre><small>导出时将使用完整 LaTeX 引擎排版公式、引用与图表。</small></article>}
  </div>
}

function CreateNoteDialog({ onClose, onCreate }: { onClose: () => void; onCreate: (title: string, format: NoteFormat, mode: NoteEditorMode) => Promise<void> }) {
  const [title, setTitle] = useState('')
  const [format, setFormat] = useState<NoteFormat>('markdown')
  const [mode, setMode] = useState<NoteEditorMode>('standard')
  const [busy, setBusy] = useState(false)
  return <div className="notes-dialog-backdrop" onMouseDown={onClose}><section className="notes-dialog" onMouseDown={event => event.stopPropagation()}>
    <header><div><span>NEW NOTE</span><h3>创建学习笔记</h3><p>选择适合当前工作的写作方式，之后仍可继续调整。</p></div><button onClick={onClose}><X/></button></header>
    <label>笔记名称<input autoFocus value={title} onChange={event => setTitle(event.target.value)} placeholder="例如：多模态 Agent 的评测设计"/></label>
    <div className="notes-format-grid">
      <button className={format === 'markdown' ? 'selected' : ''} onClick={() => setFormat('markdown')}><FileText/><strong>Markdown</strong><span>适合阅读记录、研究思路与组会材料</span></button>
      <button className={format === 'latex' ? 'selected' : ''} onClick={() => setFormat('latex')}><FileCode2/><strong>LaTeX</strong><span>适合公式密集的推导与正式技术文稿</span></button>
    </div>
    {format === 'markdown' && <div className="notes-mode-choice"><span>初始编辑模式</span><div><button className={mode === 'standard' ? 'active' : ''} onClick={() => setMode('standard')}>常规编辑</button><button className={mode === 'professional' ? 'active' : ''} onClick={() => setMode('professional')}>专业源码</button></div></div>}
    <footer><button onClick={onClose}>取消</button><button className="primary" disabled={!title.trim() || busy} onClick={async () => { setBusy(true); await onCreate(title.trim(), format, mode).finally(() => setBusy(false)) }}>{busy && <LoaderCircle className="spin"/>}开始记录</button></footer>
  </section></div>
}

function PaperPicker({ papers, selected, onClose, onConfirm }: { papers: Paper[]; selected: number[]; onClose: () => void; onConfirm: (ids: number[]) => void }) {
  const [query, setQuery] = useState('')
  const [choice, setChoice] = useState(selected)
  const results = useMemo(() => papers.filter(p => `${p.title_zh || ''} ${p.title_en} ${p.authors.join(' ')}`.toLowerCase().includes(query.toLowerCase())), [papers, query])
  return <div className="notes-dialog-backdrop" onMouseDown={onClose}><section className="notes-dialog notes-paper-picker" onMouseDown={event => event.stopPropagation()}>
    <header><div><span>REFERENCES</span><h3>引用学习库论文</h3><p>引用会跟随笔记保存，生成图表或组会材料时可继续追溯来源。</p></div><button onClick={onClose}><X/></button></header>
    <div className="notes-paper-search"><Search/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索标题或作者"/></div>
    <div className="notes-paper-list">{results.map(paper => { const checked = choice.includes(paper.id); return <button className={checked ? 'selected' : ''} key={paper.id} onClick={() => setChoice(checked ? choice.filter(id => id !== paper.id) : [...choice, paper.id])}><i>{checked && <Check/>}</i><div><strong>{paper.title_zh || paper.title_en}</strong>{paper.title_zh && <span>{paper.title_en}</span>}<small>{paper.authors.slice(0, 3).join('、')}</small></div></button> })}{!results.length && <p>学习库中没有匹配的论文。</p>}</div>
    <footer><span>已选择 {choice.length} 篇</span><button className="primary" onClick={() => onConfirm(choice)}>确认引用</button></footer>
  </section></div>
}

export default function NotesPage({focusPaperId}:{focusPaperId?:number|null}) {
  const [notes, setNotes] = useState<UnifiedNote[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [papers, setPapers] = useState<Paper[]>([])
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)
  const [pickingPapers, setPickingPapers] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [sourceView, setSourceView] = useState<'source' | 'split' | 'preview'>('split')
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'error'>('saved')
  const [artifactBusy, setArtifactBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [presentationNoteId,setPresentationNoteId]=useState<number|null>(null)
  const active = notes.find(note => note.id === activeId) || null
  const filtered = useMemo(() => notes.filter(note => `${note.title} ${note.content}`.toLowerCase().includes(query.toLowerCase())), [notes, query])

  useEffect(() => {
    Promise.all([api<UnifiedNote[]>('/api/notes'), api<Paper[]>('/api/library/papers')]).then(([noteList, paperList]) => {
      setNotes(noteList); setPapers(paperList); setActiveId(noteList.find(note=>focusPaperId&&note.paper_ids.includes(focusPaperId))?.id||noteList[0]?.id||null)
    }).catch(error => setNotice(error instanceof Error ? error.message : '暂时无法加载笔记'))
  }, [focusPaperId])

  const updateLocal = (values: Partial<UnifiedNote>) => {
    if (!activeId) return
    setNotes(items => items.map(note => note.id === activeId ? { ...note, ...values } : note))
    setSaveState('saving')
  }
  useEffect(() => {
    if (!active || saveState !== 'saving') return
    const timer = window.setTimeout(() => api<UnifiedNote>(`/api/notes/${active.id}`, { method: 'PUT', body: JSON.stringify({ title: active.title, content: active.content, document_format: active.document_format, editor_mode: active.editor_mode, paper_ids: active.paper_ids }) }).then(saved => {
      setNotes(items => items.map(note => note.id === saved.id ? saved : note)); setSaveState('saved')
    }).catch(() => setSaveState('error')), 650)
    return () => window.clearTimeout(timer)
  }, [active?.title, active?.content, active?.editor_mode, active?.paper_ids.join(','), activeId, saveState])

  const createNote = async (title: string, format: NoteFormat, mode: NoteEditorMode) => {
    const created = await api<UnifiedNote>('/api/notes', { method: 'POST', body: JSON.stringify({ title, document_format: format, editor_mode: format === 'latex' ? 'professional' : mode, origin: 'standalone', content: format === 'latex' ? blankLatex : blankMarkdown, paper_ids: [] }) })
    setNotes(items => [created, ...items]); setActiveId(created.id); setCreating(false)
  }
  const createArtifact = async (type: keyof typeof artifactMeta) => {
    if (!active) return
    if(type==='presentation'){setPresentationNoteId(active.id);return}
    setArtifactBusy(type)
    try {
      const result = await api<NoteArtifact>(`/api/notes/${active.id}/artifacts`, { method: 'POST', body: JSON.stringify({ type }) })
      setNotice(result.message || result.error || (result.download_url ? '内容已生成，可以打开查看。' : '已加入生成队列。'))
      if (result.download_url) window.open(result.download_url, '_blank', 'noopener,noreferrer')
    } catch (error) { setNotice(error instanceof Error ? error.message : '生成未完成，请稍后重试') }
    finally { setArtifactBusy(null) }
  }

  return <section className={`notes-page ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
    {notice && <div className="notes-toast"><Sparkles/><span>{notice}</span><button onClick={() => setNotice(null)}><X/></button></div>}
    <aside className="notes-sidebar">
      <header><div><span>KNOWLEDGE NOTES</span><h2>学习笔记</h2></div><button className="notes-new-button" onClick={() => setCreating(true)} title="新建笔记"><Plus/></button></header>
      <div className="notes-search"><Search/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索笔记"/></div>
      <div className="notes-list">{filtered.map(note => <button key={note.id} className={note.id === activeId ? 'active' : ''} onClick={() => setActiveId(note.id)}><i>{note.document_format === 'latex' ? <FileCode2/> : <FileText/>}</i><div><strong>{note.title}</strong><span>{formatLabels[note.document_format]} · {note.paper_ids.length ? `${note.paper_ids.length} 篇引用` : '独立笔记'}</span><small>{dateLabel(note.updated_at)}</small></div><ChevronRight/></button>)}{!filtered.length && <div className="notes-list-empty"><FileText/><strong>{query ? '没有匹配的笔记' : '写下第一条研究线索'}</strong><span>{query ? '尝试更换关键词。' : '笔记可以独立创建，也可以从论文阅读器进入。'}</span></div>}</div>
    </aside>
    <main className="notes-workspace">
      {!active ? <div className="notes-welcome"><div><Braces/></div><span>RESEARCH MEMORY</span><h2>让阅读、推导与灵感留在同一处</h2><p>使用 Markdown 或 LaTeX 记录研究过程，引用学习库论文，并继续生成流程图、思维导图与组会材料。</p><button className="primary" onClick={() => setCreating(true)}><Plus/>创建第一篇笔记</button></div> : <>
        <header className="notes-editor-head">
          <button className="notes-sidebar-toggle" onClick={() => setSidebarOpen(value => !value)} title={sidebarOpen ? '收起笔记列表' : '展开笔记列表'}><PanelLeftClose/></button>
          <div className="notes-title-field"><input value={active.title} onChange={event => updateLocal({ title: event.target.value })}/><span>{formatLabels[active.document_format]} · {active.origin === 'reader' ? '来自论文阅读' : '独立笔记'} · {saveState === 'saved' ? '已保存' : saveState === 'saving' ? '正在保存' : '保存遇到问题'}</span></div>
          {active.document_format === 'markdown' && <div className="notes-mode-toggle"><button className={active.editor_mode === 'standard' ? 'active' : ''} onClick={() => updateLocal({ editor_mode: 'standard' })}>常规</button><button className={active.editor_mode === 'professional' ? 'active' : ''} onClick={() => updateLocal({ editor_mode: 'professional' })}><Code2/>专业</button></div>}
        </header>
        <div className="notes-reference-bar"><button onClick={() => setPickingPapers(true)}><BookOpen/><span>{active.paper_ids.length ? `已引用 ${active.paper_ids.length} 篇论文` : '引用学习库论文'}</span><Plus/></button>{active.papers?.slice(0, 3).map(paper => <span key={paper.id}>{paper.title_zh || paper.title}</span>)}</div>
        <div className="notes-editor-body" key={`${active.id}-${active.editor_mode}`}>
          {active.document_format === 'latex' ? <LatexEditor value={active.content} onChange={content => updateLocal({ content })}/> : active.editor_mode === 'standard' ? <StandardMarkdownEditor value={active.content} onChange={content => updateLocal({ content })} onInsertPaper={() => setPickingPapers(true)}/> : <MarkdownSourceEditor value={active.content} onChange={content => updateLocal({ content })} view={sourceView} setView={setSourceView}/>} 
        </div>
        <footer className="notes-create-bar"><div><Sparkles/><span><strong>把笔记变成研究表达</strong><small>生成内容会保留当前笔记与论文引用关系。</small></span></div><div>{(Object.entries(artifactMeta) as [keyof typeof artifactMeta, typeof artifactMeta[keyof typeof artifactMeta]][]).filter(([type]) => active.document_format === 'markdown' || type === 'presentation').map(([type, meta]) => { const Icon = meta.icon; return <button key={type} disabled={!!artifactBusy} onClick={() => createArtifact(type)}>{artifactBusy === type ? <LoaderCircle className="spin"/> : <Icon/>}{meta.label}</button> })}</div></footer>
      </>}
    </main>
    {creating && <CreateNoteDialog onClose={() => setCreating(false)} onCreate={createNote}/>} 
    {pickingPapers && active && <PaperPicker papers={papers} selected={active.paper_ids} onClose={() => setPickingPapers(false)} onConfirm={ids => { updateLocal({ paper_ids: ids }); setPickingPapers(false) }}/>} 
    {presentationNoteId&&<PresentationOutlineEditor noteId={presentationNoteId} onClose={()=>setPresentationNoteId(null)}/>} 
  </section>
}
