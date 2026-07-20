import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowUp, Bot, Check, FilePlus2, MessageCircle, NotebookPen, Settings, Sparkles, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from './api'
import type { UnifiedNote } from './types'
import './global-assistant.css'

type Message = { id: string; role: 'user' | 'assistant'; content: string; pageTitle: string }

const suggestions: Record<string, string[]> = {
  home: ['根据起始页帮我安排今天的研究工作', '哪些待办和截稿日期最紧急？', '建议我先阅读、做实验还是整理笔记？'],
  today: ['概括当前推荐中最值得优先阅读的论文', '这些论文覆盖了哪些研究路线？', '帮我制定今天的阅读顺序'],
  research: ['总结当前专题调研的主要结论', '哪些结论证据最充分？', '还有哪些研究空白值得追踪？'],
  projects: ['根据当前项目状态建议下一步', '梳理尚未解决的问题', '哪些论文与当前结论存在冲突？'],
  notes: ['整理这篇笔记的逻辑结构', '指出仍需补充证据的观点', '把当前内容改写成组会汇报提纲'],
  history: ['从当前记录中总结研究趋势', '找出值得重新关注的论文', '这些论文有哪些共同方法？'],
  learning: ['总结当前学习库的知识结构', '推荐下一篇应该精读的论文', '找出可能互相支持或冲突的工作'],
  deepwiki: ['概括当前 Wiki 的核心实现', '哪些模块最值得优先复现？', '指出论文与代码之间仍需核验的部分'],
  domains: ['检查当前专业配置是否完整', '这些评分规则可能有哪些偏差？', '给出更稳健的数据源配置建议'],
  settings: ['解释当前设置会如何影响推荐', '检查还缺少哪些必要配置', '怎样配置更适合本地优先使用？'],
  planner: ['帮我按紧急程度整理待办', '根据当前 DDL 制定投稿准备计划', '哪些任务应该提前完成以降低截稿风险？'],
}

function visibleContext(fallbackTitle: string) {
  const selectors = ['.reader-workspace', '.wiki-workspace', '.domain-wizard', '.modal', '.chat-panel', '.main-shell']
  const element = selectors.map(selector => document.querySelector<HTMLElement>(selector)).find(node => {
    if (!node) return false
    const style = window.getComputedStyle(node)
    const rect = node.getBoundingClientRect()
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
  })
  const heading = element?.querySelector<HTMLElement>('h1, h2, h3')?.innerText.trim()
  const title = heading || fallbackTitle
  const text = (element?.innerText || '').replace(/\n{3,}/g, '\n\n').trim().slice(0, 48_000)
  return { title, text: `当前页面：${title}\n\n${text}` }
}

export default function GlobalAssistant({ open, onOpen, onClose, pageId, pageTitle, configured, onOpenSettings, showLauncher = true }: {
  open: boolean
  onOpen: () => void
  onClose: () => void
  pageId: string
  pageTitle: string
  configured: boolean
  onOpenSettings: () => void
  showLauncher?: boolean
}) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [contextTitle, setContextTitle] = useState(pageTitle)
  const [saving, setSaving] = useState<Message | null>(null)
  const [notes, setNotes] = useState<UnifiedNote[]>([])
  const [newTitle, setNewTitle] = useState('')
  const [notice, setNotice] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const quickQuestions = useMemo(() => suggestions[pageId] || ['总结当前页面', '指出最重要的信息', '建议下一步行动'], [pageId])

  useEffect(() => { if (open) setContextTitle(visibleContext(pageTitle).title) }, [open, pageId, pageTitle])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy])

  const send = async (question = input) => {
    const message = question.trim()
    if (!message || busy || !configured) return
    const context = visibleContext(pageTitle)
    setContextTitle(context.title)
    const userMessage: Message = { id: crypto.randomUUID(), role: 'user', content: message, pageTitle: context.title }
    const prior = messages.slice(-16)
    setMessages(items => [...items, userMessage]); setInput(''); setBusy(true); setNotice('')
    try {
      const result = await api<{ answer: string }>('/api/assistant/chat', {
        method: 'POST', body: JSON.stringify({
          page_id: pageId, page_title: context.title, context: context.text, message,
          history: prior.map(item => ({ role: item.role, content: item.content })),
        }),
      })
      setMessages(items => [...items, { id: crypto.randomUUID(), role: 'assistant', content: result.answer, pageTitle: context.title }])
    } catch (error) { setNotice(error instanceof Error ? error.message : '助手暂时无法回答，请稍后重试') }
    finally { setBusy(false) }
  }

  const chooseNote = async (message: Message) => {
    setSaving(message); setNewTitle(`${message.pageTitle} · AI 对话`); setNotice('')
    try { setNotes((await api<UnifiedNote[]>('/api/notes')).filter(note => note.document_format === 'markdown')) }
    catch (error) { setNotice(error instanceof Error ? error.message : '暂时无法读取笔记') }
  }

  const append = async (note: UnifiedNote) => {
    if (!saving) return
    try {
      const updated = await api<UnifiedNote>(`/api/notes/${note.id}/append`, { method: 'POST', body: JSON.stringify({ content: saving.content, source_label: `${saving.pageTitle} · AI 回复` }) })
      window.dispatchEvent(new CustomEvent('papermorrow:note-updated', { detail: updated }))
      setSaving(null); setNotice(`已存入《${note.title}》`)
    } catch (error) { setNotice(error instanceof Error ? error.message : '保存到笔记时遇到问题') }
  }

  const createNote = async () => {
    if (!saving || !newTitle.trim()) return
    try {
      const created = await api<UnifiedNote>('/api/notes', { method: 'POST', body: JSON.stringify({
        title: newTitle.trim(), document_format: 'markdown', editor_mode: 'standard', origin: 'standalone',
        content: `# ${newTitle.trim()}\n\n## ${saving.pageTitle} · AI 回复\n\n${saving.content}\n`, paper_ids: [],
      }) })
      window.dispatchEvent(new CustomEvent('papermorrow:note-updated', { detail: created }))
      setSaving(null); setNotice(`已创建《${newTitle.trim()}》`)
    } catch (error) { setNotice(error instanceof Error ? error.message : '创建笔记时遇到问题') }
  }

  if (!open) return showLauncher ? <button className="global-assistant-launcher" onClick={onOpen} aria-label="打开全局助手"><Sparkles/><span>问 AI</span></button> : null
  return <aside className="global-assistant" aria-label="全局研究助手">
    <header className="global-assistant-head">
      <div className="global-assistant-mark"><Sparkles/></div>
      <div><strong>研究助手</strong><span>正在阅读 · {contextTitle}</span></div>
      <button onClick={onClose} aria-label="关闭助手"><X/></button>
    </header>
    {!configured ? <div className="global-assistant-empty"><Bot/><h3>连接模型后即可开始</h3><p>助手会读取你当前可见的页面内容，回答问题，并把有价值的回复归档到笔记。</p><button onClick={onOpenSettings}><Settings/>前往模型设置</button></div> : <>
      <div className="global-assistant-thread">
        {!messages.length && <div className="global-assistant-welcome"><MessageCircle/><h3>针对当前页面提问</h3><p>只会在你发送问题时读取当前可见内容；输入框、API Key 与隐藏页面不会被采集。</p><div>{quickQuestions.map(question => <button key={question} onClick={() => send(question)}>{question}</button>)}</div></div>}
        {messages.map(message => <article key={message.id} className={`global-assistant-message ${message.role}`}>
          <span>{message.role === 'assistant' ? 'AI' : '你'} · {message.pageTitle}</span>
          <div>{message.role === 'assistant' ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown> : message.content}</div>
          {message.role === 'assistant' && <button className="assistant-save-note" onClick={() => chooseNote(message)}><NotebookPen/>存入笔记</button>}
        </article>)}
        {busy && <div className="global-assistant-thinking"><i/><i/><i/><span>正在结合当前页面思考</span></div>}
        <div ref={endRef}/>
      </div>
      {notice && <div className="global-assistant-notice"><Check/>{notice}</div>}
      <div className="global-assistant-compose"><textarea value={input} onChange={event => setInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send() } }} placeholder={`询问“${contextTitle}”中的内容…`}/><button disabled={!input.trim() || busy} onClick={() => send()}><ArrowUp/></button><small>Enter 发送 · Shift + Enter 换行</small></div>
    </>}
    {saving && <div className="assistant-note-picker">
      <header><div><FilePlus2/><strong>保存这段回复</strong></div><button onClick={() => setSaving(null)}><X/></button></header>
      <label>创建新笔记<div><input value={newTitle} onChange={event => setNewTitle(event.target.value)}/><button onClick={createNote}>创建并存入</button></div></label>
      <span>或追加到已有 Markdown 笔记</span>
      <div className="assistant-note-list">{notes.map(note => <button key={note.id} onClick={() => append(note)}><NotebookPen/><span><strong>{note.title}</strong><small>{note.paper_ids.length ? `${note.paper_ids.length} 篇论文引用` : '独立笔记'}</small></span></button>)}{!notes.length && <p>还没有 Markdown 笔记。</p>}</div>
    </div>}
  </aside>
}
