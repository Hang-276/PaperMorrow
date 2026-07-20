import { useEffect, useMemo, useState } from 'react'
import {
  BookOpen, Braces, Check, ChevronRight, Code2, FileCode2, FileText, GitBranch,
  LoaderCircle, Network, PanelLeftClose, Plus, Presentation, Search, Sparkles, X,
} from 'lucide-react'
import { api } from './api'
import type { NoteArtifact, NoteEditorMode, NoteFormat, Paper, UnifiedNote } from './types'
import './notes.css'
import PresentationOutlineEditor from './PresentationOutlineEditor'
import MarkdownLiveEditor from './MarkdownLiveEditor'

const blankMarkdown = `# 新笔记\n\n从一个问题、想法或阅读线索开始。\n\n## 关键发现\n\n`
const formatLabels: Record<NoteFormat, string> = { markdown: 'Markdown', latex: '历史 LaTeX · 只读' }
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

function CreateNoteDialog({ onClose, onCreate }: { onClose: () => void; onCreate: (title: string, mode: NoteEditorMode) => Promise<void> }) {
  const [title, setTitle] = useState('')
  const [mode, setMode] = useState<NoteEditorMode>('standard')
  const [busy, setBusy] = useState(false)
  return <div className="notes-dialog-backdrop" onMouseDown={onClose}><section className="notes-dialog" onMouseDown={event => event.stopPropagation()}>
    <header><div><span>NEW NOTE</span><h3>创建 Markdown 学习笔记</h3><p>公式可直接使用 LaTeX 语法写入 Markdown，笔记始终保持便携、可检索。</p></div><button onClick={onClose}><X/></button></header>
    <label>笔记名称<input autoFocus value={title} onChange={event => setTitle(event.target.value)} placeholder="例如：多模态 Agent 的评测设计"/></label>
    <div className="notes-mode-choice"><span>编辑界面</span><div><button className={mode === 'standard' ? 'active' : ''} onClick={() => setMode('standard')}>常规 · 完整工具</button><button className={mode === 'professional' ? 'active' : ''} onClick={() => setMode('professional')}>专业 · 极简写作</button></div></div>
    <footer><button onClick={onClose}>取消</button><button className="primary" disabled={!title.trim() || busy} onClick={async () => { setBusy(true); await onCreate(title.trim(), mode).finally(() => setBusy(false)) }}>{busy && <LoaderCircle className="spin"/>}开始记录</button></footer>
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

export default function NotesPage({focusPaperId,createSignal=0}:{focusPaperId?:number|null;createSignal?:number}) {
  const [notes, setNotes] = useState<UnifiedNote[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [papers, setPapers] = useState<Paper[]>([])
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)
  const [pickingPapers, setPickingPapers] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 680)
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

  useEffect(()=>{if(createSignal>0)setCreating(true)},[createSignal])

  useEffect(() => {
    const receiveExternalUpdate = (event: Event) => {
      const updated = (event as CustomEvent<UnifiedNote>).detail
      if (!updated?.id) return
      setNotes(items => items.some(note => note.id === updated.id) ? items.map(note => note.id === updated.id ? updated : note) : [updated, ...items])
      setSaveState('saved')
    }
    window.addEventListener('papermorrow:note-updated', receiveExternalUpdate)
    return () => window.removeEventListener('papermorrow:note-updated', receiveExternalUpdate)
  }, [])

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

  const createNote = async (title: string, mode: NoteEditorMode) => {
    const created = await api<UnifiedNote>('/api/notes', { method: 'POST', body: JSON.stringify({ title, document_format: 'markdown', editor_mode: mode, origin: 'standalone', content: blankMarkdown, paper_ids: [] }) })
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
      <div className="notes-list">{filtered.map(note => <button key={note.id} className={note.id === activeId ? 'active' : ''} onClick={() => { setActiveId(note.id); if (window.innerWidth <= 680) setSidebarOpen(false) }}><i>{note.document_format === 'latex' ? <FileCode2/> : <FileText/>}</i><div><strong>{note.title}</strong><span>{formatLabels[note.document_format]} · {note.paper_ids.length ? `${note.paper_ids.length} 篇引用` : '独立笔记'}</span><small>{dateLabel(note.updated_at)}</small></div><ChevronRight/></button>)}{!filtered.length && <div className="notes-list-empty"><FileText/><strong>{query ? '没有匹配的笔记' : '写下第一条研究线索'}</strong><span>{query ? '尝试更换关键词。' : '笔记可以独立创建，也可以从论文阅读器进入。'}</span></div>}</div>
    </aside>
    <main className="notes-workspace">
      {!active ? <div className="notes-welcome"><div><Braces/></div><span>RESEARCH MEMORY</span><h2>让阅读、推导与灵感留在同一处</h2><p>使用 Markdown 记录研究过程、插入公式、引用学习库论文，并继续生成流程图、思维导图与组会材料。</p><button className="primary" onClick={() => setCreating(true)}><Plus/>创建第一篇笔记</button></div> : <>
        <header className="notes-editor-head">
          <button className="notes-sidebar-toggle" onClick={() => setSidebarOpen(value => !value)} title={sidebarOpen ? '收起笔记列表' : '展开笔记列表'}><PanelLeftClose/></button>
          <div className="notes-title-field"><input readOnly={active.document_format === 'latex'} value={active.title} onChange={event => updateLocal({ title: event.target.value })}/><span>{formatLabels[active.document_format]} · {active.origin === 'reader' ? '来自论文阅读' : '独立笔记'} · {active.document_format === 'latex' ? '内容已完整保留' : saveState === 'saved' ? '已保存' : saveState === 'saving' ? '正在保存' : '保存遇到问题'}</span></div>
          {active.document_format === 'markdown' && <div className="notes-mode-toggle" title="两种模式都使用逐行 Markdown 实时编辑"><button className={active.editor_mode === 'standard' ? 'active' : ''} onClick={() => updateLocal({ editor_mode: 'standard' })}>常规</button><button className={active.editor_mode === 'professional' ? 'active' : ''} onClick={() => updateLocal({ editor_mode: 'professional' })}><Code2/>专业</button></div>}
        </header>
        {active.document_format === 'markdown' && <div className="notes-reference-bar"><button onClick={() => setPickingPapers(true)}><BookOpen/><span>{active.paper_ids.length ? `已引用 ${active.paper_ids.length} 篇论文` : '引用学习库论文'}</span><Plus/></button>{active.papers?.slice(0, 3).map(paper => <span key={paper.id}>{paper.title_zh || paper.title}</span>)}</div>}
        <div className="notes-editor-body" key={`${active.id}-${active.editor_mode}`}>
          {active.document_format === 'latex'
            ? <section className="notes-legacy-readonly"><FileCode2/><span>LEGACY NOTE</span><h3>LaTeX 编辑功能已暂停</h3><p>这篇历史笔记的原始内容已完整保留。你可以复制源码继续使用；PaperMorrow 不会自动转换或覆盖它。</p><button onClick={() => navigator.clipboard.writeText(active.content).then(() => setNotice('LaTeX 源码已复制'))}>复制原始源码</button><pre>{active.content}</pre></section>
            : <MarkdownLiveEditor value={active.content} mode={active.editor_mode} onChange={content => updateLocal({ content })} onInsertPaper={() => setPickingPapers(true)}/>}
        </div>
        {active.document_format === 'markdown' && <footer className="notes-create-bar"><div><Sparkles/><span><strong>把笔记变成研究表达</strong><small>生成内容会保留当前笔记与论文引用关系。</small></span></div><div>{(Object.entries(artifactMeta) as [keyof typeof artifactMeta, typeof artifactMeta[keyof typeof artifactMeta]][]).map(([type, meta]) => { const Icon = meta.icon; return <button key={type} disabled={!!artifactBusy} onClick={() => createArtifact(type)}>{artifactBusy === type ? <LoaderCircle className="spin"/> : <Icon/>}{meta.label}</button> })}</div></footer>}
      </>}
    </main>
    {creating && <CreateNoteDialog onClose={() => setCreating(false)} onCreate={createNote}/>} 
    {pickingPapers && active && <PaperPicker papers={papers} selected={active.paper_ids} onClose={() => setPickingPapers(false)} onConfirm={ids => { updateLocal({ paper_ids: ids }); setPickingPapers(false) }}/>} 
    {presentationNoteId&&<PresentationOutlineEditor noteId={presentationNoteId} onClose={()=>setPresentationNoteId(null)}/>} 
  </section>
}
