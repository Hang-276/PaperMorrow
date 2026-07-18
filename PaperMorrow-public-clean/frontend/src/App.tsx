import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import {
  BookOpen, CalendarClock, Check, CheckCircle2, ChevronDown, ChevronRight, ChevronUp, CircleDashed, Code2,
  ExternalLink, FileText, History, Languages, Library, Menu, Network, NotebookPen,
  Radar, RefreshCw, Search, Settings as SettingsIcon, Sparkles, X, Moon, Sun,
  MessageCircle, Send, Plus, Bot, User,
  BarChart3, KeyRound, Link2, Pencil, Trash2, Type,
  FlaskConical,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from './api'
import ResearchProfiles from './ResearchProfiles'
import LibraryPage from './LibraryPage'
import ResearchPage from './ResearchPage'
import './features.css'
import './library.css'
import type { AppSettings, Batch, ChatMessage, ChatSession, DeepWikiJob, LLMProfile, Paper, ResearchProfile, Tag, TokenUsageStats } from './types'

type View = 'today' | 'research' | 'history' | 'learning' | 'deepwiki' | 'settings'

const ReaderWorkspace = lazy(() => import('./ReaderWorkspace'))
const WikiWorkspace = lazy(() => import('./WikiWorkspace'))

const apiPresets = [
  { label:'OpenAI', name:'OpenAI', provider:'openai', base_url:'https://api.openai.com/v1', model:'gpt-4.1-mini' },
  { label:'Claude', name:'Claude', provider:'claude', base_url:'https://api.anthropic.com/v1', model:'claude-sonnet-4-5' },
  { label:'GLM', name:'GLM', provider:'glm', base_url:'https://open.bigmodel.cn/api/paas/v4', model:'glm-4.5' },
  { label:'DeepSeek', name:'DeepSeek', provider:'deepseek', base_url:'https://api.deepseek.com/v1', model:'deepseek-chat' },
  { label:'智增增', name:'智增增中转', provider:'custom', base_url:'https://api.zhizengzeng.com/v1', model:'gpt-4.1-mini' },
  { label:'自定义', name:'我的 API', provider:'custom', base_url:'', model:'' },
] as const

export default function App() {
  const [view, setView] = useState<View>('today')
  const [theme, setTheme] = useState<'light'|'dark'>(() => (localStorage.getItem('papermorrow-theme') as 'light'|'dark') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'))
  const [mobileMenu, setMobileMenu] = useState(false)
  const [tags, setTags] = useState<Tag[]>([])
  const [researchProfiles, setResearchProfiles] = useState<ResearchProfile[]>([])
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [today, setToday] = useState<Batch[]>([])
  const [history, setHistory] = useState<Paper[]>([])
  const [jobs, setJobs] = useState<DeepWikiJob[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [selectedTags, setSelectedTags] = useState<number[]>([])
  const [count, setCount] = useState(5)
  const [search, setSearch] = useState('')
  const [notePaper, setNotePaper] = useState<Paper | null>(null)
  const [relatedPaper, setRelatedPaper] = useState<Paper | null>(null)
  const [related, setRelated] = useState<any[]>([])
  const [repoResult, setRepoResult] = useState<any | null>(null)
  const [wikiJob, setWikiJob] = useState<DeepWikiJob | null>(null)
  const [chatPaper, setChatPaper] = useState<Paper | null>(null)
  const [readerPaper, setReaderPaper] = useState<Paper | null>(null)
  const [recommendMode, setRecommendMode] = useState<'broad'|'focus'|'mixed'>('broad')
  const [selectedProfileId, setSelectedProfileId] = useState<number|''>('')
  const [activeDomain, setActiveDomain] = useState<'ai'|'computer'|'physics'|'math'>('ai')

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('papermorrow-theme', theme) }, [theme])
  useEffect(() => {
    if (settings?.font_size) document.documentElement.style.setProperty('--app-font-size', `${settings.font_size}px`)
  }, [settings?.font_size])

  const load = async () => {
    const [tagData, settingData, todayData, historyData, jobData, researchData] = await Promise.all([
      api<Tag[]>('/api/tags'), api<AppSettings>('/api/settings'), api<Batch[]>('/api/recommendations/today'),
      api<Paper[]>('/api/recommendations/history'), api<DeepWikiJob[]>('/api/deepwiki/jobs'), api<ResearchProfile[]>('/api/research-profiles'),
    ])
    setTags(tagData); setSettings(settingData); setToday(todayData); setHistory(historyData); setJobs(jobData); setResearchProfiles(researchData)
    if (!selectedTags.length) setSelectedTags(settingData.daily_tag_ids.length ? settingData.daily_tag_ids : tagData.filter(t=>t.domain==='ai').slice(0, 2).map(t => t.id))
  }

  useEffect(() => { load().catch(error => setMessage(error.message)) }, [])
  useEffect(() => {
    if (!jobs.some(job => ['queued', 'running'].includes(job.status))) return
    const timer = window.setInterval(() => api<DeepWikiJob[]>('/api/deepwiki/jobs').then(setJobs), 2000)
    return () => window.clearInterval(timer)
  }, [jobs])

  const papers = useMemo(() => today.flatMap(batch => batch.papers), [today])
  const filteredHistory = history.filter(paper => `${paper.title_en} ${paper.title_zh || ''}`.toLowerCase().includes(search.toLowerCase()))

  const generate = async () => {
    if (recommendMode === 'broad' && !selectedTags.length) return setMessage('请至少选择一个广度研究方向')
    if (recommendMode !== 'broad' && !selectedProfileId) return setMessage('请先选择或创建一个细分研究方向')
    setBusy(true); setMessage('正在检索最新论文并永久去重…')
    try {
      const batch = await api<Batch>('/api/recommendations/generate', { method: 'POST', body: JSON.stringify({ tag_ids: selectedTags, count, mode:recommendMode, profile_id:selectedProfileId||null }) })
      setToday(current => [batch, ...current]); setMessage(batch.message || '推荐完成'); await load()
    } catch (error) { setMessage(error instanceof Error ? error.message : '推荐失败') }
    finally { setBusy(false) }
  }

  const toggleLearned = async (paper: Paper) => {
    await api(`/api/papers/${paper.id}/study-state`, { method: 'PATCH', body: JSON.stringify({ learned: !paper.learned }) })
    await load()
  }

  const findRelated = async (paper: Paper) => {
    setRelatedPaper(paper); setRelated([])
    try { const result = await api<{ items: any[] }>(`/api/papers/${paper.id}/related`); setRelated(result.items) }
    catch (error) { setMessage(error instanceof Error ? error.message : '查询失败') }
  }

  const discoverRepo = async (paper: Paper) => {
    setBusy(true); setMessage('正在核验论文的公开代码仓库…')
    try {
      const result = await api<any>(`/api/papers/${paper.id}/repository/discover`, { method: 'POST' })
      setRepoResult({ paper, ...result }); setMessage(result.repository_url ? '发现代码仓库' : '暂未发现公开代码'); await load()
    } catch (error) { setMessage(error instanceof Error ? error.message : '仓库检索失败') }
    finally { setBusy(false) }
  }

  const retryAI = async (paper: Paper) => {
    setBusy(true); setMessage('正在生成中文摘要与论文分析…')
    try { await api(`/api/papers/${paper.id}/ai/retry`, { method: 'POST' }); await load(); setMessage('AI 分析已更新') }
    catch (error) { setMessage(error instanceof Error ? error.message : 'AI 分析失败') }
    finally { setBusy(false) }
  }

  const startWiki = async (paper: Paper) => {
    try {
      const job = await api<DeepWikiJob>(`/api/deepwiki/jobs?paper_id=${paper.id}`, { method: 'POST' })
      setJobs(current => [job, ...current.filter(item => item.id !== job.id)]); setMessage('DeepWiki 已开始解析'); setView('deepwiki'); setRepoResult(null)
    } catch (error) { setMessage(error instanceof Error ? error.message : '任务启动失败') }
  }

  const retryWiki = async (job: DeepWikiJob) => {
    try {
      const updated = await api<DeepWikiJob>(`/api/deepwiki/jobs/${job.id}/retry`, { method: 'POST' })
      setJobs(current => current.map(item => item.id === updated.id ? updated : item))
      setWikiJob(null)
      setMessage('DeepWiki 已重新开始生成')
    } catch (error) { setMessage(error instanceof Error ? error.message : '重新生成失败') }
  }

  const previewFontSize = (value: number) => {
    const fontSize = Math.max(13, Math.min(20, Math.round(value)))
    document.documentElement.style.setProperty('--app-font-size', `${fontSize}px`)
    setSettings(current => current ? { ...current, font_size:fontSize } : current)
  }

  const saveFontSize = async (value: number) => {
    const fontSize = Math.max(13, Math.min(20, Math.round(value)))
    previewFontSize(fontSize)
    try {
      await api('/api/settings', { method:'PUT', body:JSON.stringify({ font_size:fontSize }) })
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '字号保存失败')
    }
  }

  const nav = [
    ['today', Radar, '今日推荐'], ['research', FlaskConical, '专题调研'], ['history', History, '推荐历史'], ['learning', Library, '学习库'],
    ['deepwiki', Code2, 'DeepWiki'], ['settings', SettingsIcon, '设置'],
  ] as const

  return <div className="app-shell">
    <aside className={`sidebar-shell ${mobileMenu ? 'open' : ''}`}>
      <div className="brand"><div className="brand-mark"><img src="/papermorrow-logo.png" alt=""/></div><div><strong>PaperMorrow</strong><span>Read what matters next</span></div></div>
      <nav>{nav.map(([id, Icon, label]) => <button key={id} className={view === id ? 'active' : ''} onClick={() => { setView(id); setMobileMenu(false) }}><Icon size={19}/><span>{label}</span>{view === id && <ChevronRight size={16}/>}</button>)}</nav>
      <div className="sidebar-foot"><Sparkles size={17}/><div><strong>AI 分析</strong><span>{settings?.has_llm_api_key ? '模型已连接' : '等待配置 API'}</span></div><i className={settings?.has_llm_api_key ? 'online' : ''}/></div>
    </aside>

    <main className="main-shell">
      <header className="topbar"><button className="icon-button menu-button" onClick={() => setMobileMenu(!mobileMenu)}><Menu/></button><div><span className="eyebrow">PAPERMORROW · RESEARCH COMPANION</span><h1>{nav.find(item => item[0] === view)?.[2]}</h1></div><div className="topbar-actions"><span className="date-pill"><CalendarClock size={16}/>{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })}</span><button className="theme-toggle" aria-label={theme === 'light' ? '切换深色模式' : '切换浅色模式'} onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? <Moon size={18}/> : <Sun size={18}/>}</button></div></header>

      {message && <div className="toast"><span>{busy && <CircleDashed className="spin" size={17}/>} {message}</span><button onClick={() => setMessage('')}><X size={16}/></button></div>}

      {view === 'today' && <section className="page-content">
        <div className="hero-panel"><div><span className="section-kicker">TOMORROW'S READING, CURATED TODAY</span><h2>广度发现，也追踪你的细分问题</h2><p>规则多路召回与永久去重；LLM 同时判断方向关联、创新强度、研究价值和阅读性价比。</p></div><div className="generate-controls"><select value={recommendMode} onChange={e=>setRecommendMode(e.target.value as any)}><option value="broad">广度推荐</option><option value="mixed">聚焦 + 探索</option><option value="focus">仅聚焦方向</option></select>{recommendMode!=='broad'&&<select value={selectedProfileId} onChange={e=>{const id=Number(e.target.value)||'';setSelectedProfileId(id);const found=researchProfiles.find(item=>item.id===id);if(found)setActiveDomain(found.domain)}}><option value="">选择细分方向</option>{researchProfiles.map(profile=><option key={profile.id} value={profile.id}>{profile.name}</option>)}</select>}<select value={count} onChange={e => setCount(Number(e.target.value))}>{[3,5,8,10,15,20].map(n => <option key={n} value={n}>推荐 {n} 篇</option>)}</select><button className="primary" disabled={busy} onClick={generate}>{busy ? <RefreshCw className="spin" size={18}/> : <Sparkles size={18}/>}生成推荐</button></div></div>
        <div className="domain-switch">{([['ai','AI'],['computer','计算机'],['physics','物理'],['math','数学']] as const).map(([id,label])=><button key={id} className={activeDomain===id?'active':''} onClick={()=>{setActiveDomain(id);setSelectedTags(tags.filter(tag=>tag.domain===id).slice(0,2).map(tag=>tag.id))}}>{label}</button>)}</div>
        <div className="tag-strip"><span>{recommendMode==='broad'?'广度方向':'辅助召回'}</span><div>{tags.filter(tag=>tag.domain===activeDomain).map(tag => <button key={tag.id} className={selectedTags.includes(tag.id) ? 'selected' : ''} onClick={() => setSelectedTags(current => current.includes(tag.id) ? current.filter(id => id !== tag.id) : [...current, tag.id])}>{selectedTags.includes(tag.id) && <Check size={14}/>} {tag.name_zh}</button>)}</div></div>
        {papers.length ? <div className="paper-list">{papers.map(paper => <PaperCard key={paper.id} paper={paper} defaultLanguage={settings?.default_abstract_language || 'zh'} onLearned={toggleLearned} onNote={setNotePaper} onRelated={findRelated} onRepo={discoverRepo} onWiki={startWiki} onRetryAi={retryAI} onChat={setChatPaper} onRead={setReaderPaper}/>)}</div> : <EmptyState icon={Radar} title="今天还没有推荐" text="选择广度方向，或创建细分研究方向后生成第一批论文。"/>}
      </section>}

      {view === 'history' && <section className="page-content"><div className="list-toolbar"><div><span className="section-kicker">ARCHIVE</span><h2>全部推荐记录</h2><p>共 {history.length} 篇，永久保留并参与后续去重。</p></div><label className="search-box"><Search size={17}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索英文或中文标题"/></label></div><div className="paper-list">{filteredHistory.map(paper => <PaperCard compact key={paper.id} paper={paper} defaultLanguage={settings?.default_abstract_language || 'zh'} onLearned={toggleLearned} onNote={setNotePaper} onRelated={findRelated} onRepo={discoverRepo} onWiki={startWiki} onRetryAi={retryAI} onChat={setChatPaper} onRead={setReaderPaper}/>)}</div></section>}

      {view === 'learning' && <LibraryPage onRead={setReaderPaper} onNote={setNotePaper} onChat={setChatPaper} onRelated={findRelated} onRepo={discoverRepo} onWiki={startWiki} onOpenSettings={()=>setView('settings')} onDataChanged={load}/>} 
      {view === 'research' && <ResearchPage onDataChanged={load}/>} 

      {view === 'deepwiki' && <DeepWikiPage jobs={jobs} onOpen={setWikiJob} onRetry={retryWiki}/>} 
      {view === 'settings' && settings && <SettingsPage settings={settings} tags={tags} researchProfiles={researchProfiles} onSaved={async () => { await load(); setMessage('设置已保存') }}/>} 
    </main>

    {notePaper && <NoteModal paper={notePaper} onClose={() => setNotePaper(null)} onSaved={load}/>} 
    {relatedPaper && <Modal title="相关研究" subtitle={relatedPaper.title_en} onClose={() => setRelatedPaper(null)}><div className="related-list">{related.length ? related.map((item, index) => <a key={item.paper_id || index} href={item.url} target="_blank" rel="noreferrer"><span>{relationLabel(item.relation)} · {item.year || '—'} · {item.venue || 'Venue 未知'}</span><strong>{item.title}</strong><small>{(item.authors || []).join(', ')}</small><ExternalLink size={17}/></a>) : <div className="modal-loading"><CircleDashed className="spin"/>正在查找相似、前置与后续研究…</div>}</div></Modal>}
    {repoResult && <Modal title="代码仓库识别" subtitle={repoResult.paper.title_en} onClose={() => setRepoResult(null)}><RepositoryResult result={repoResult} onStart={() => startWiki(repoResult.paper)}/></Modal>}
    {wikiJob && <Suspense fallback={<div className="reader-boot"><RefreshCw className="spin" size={20}/><span>正在打开完整 Wiki…</span></div>}><WikiWorkspace job={wikiJob} fontSize={settings?.font_size || 16} onFontSizePreview={previewFontSize} onFontSizeSave={saveFontSize} onClose={() => setWikiJob(null)} onRetry={() => retryWiki(wikiJob)}/></Suspense>} 
    {chatPaper && <ChatPanel paper={chatPaper} configured={Boolean(settings?.has_llm_api_key)} onClose={() => setChatPaper(null)} onOpenSettings={() => { setChatPaper(null); setView('settings') }}/>} 
    {readerPaper && <Suspense fallback={<div className="reader-boot"><RefreshCw className="spin" size={20}/><span>正在准备智能阅读器…</span></div>}><ReaderWorkspace paper={readerPaper} configured={Boolean(settings?.has_llm_api_key)} onClose={()=>setReaderPaper(null)} onSaved={load}/></Suspense>} 
  </div>
}

function PaperCard({ paper, defaultLanguage, onLearned, onNote, onRelated, onRepo, onWiki, onRetryAi, onChat, onRead, compact = false }: { paper: Paper; defaultLanguage: 'zh'|'en'; onLearned: (p: Paper) => void; onNote: (p: Paper) => void; onRelated: (p: Paper) => void; onRepo: (p: Paper) => void; onWiki: (p: Paper) => void; onRetryAi: (p: Paper) => void; onChat: (p: Paper) => void; onRead: (p:Paper)=>void; compact?: boolean }) {
  const [language, setLanguage] = useState<'zh'|'en'>(defaultLanguage)
  const [expanded, setExpanded] = useState(!compact)
  const [expanding, setExpanding] = useState(false)
  const abstract = language === 'zh' ? paper.abstract_zh : paper.abstract_en
  const date = paper.published_at ? new Date(paper.published_at).toLocaleDateString('zh-CN') : '日期未知'
  const showDetails = !compact || expanded
  const toggleExpanded = async () => {
    if (expanded) return setExpanded(false)
    setExpanded(true)
    if (!paper.summary || !paper.abstract_zh) {
      setExpanding(true)
      try { await onRetryAi(paper) } finally { setExpanding(false) }
    }
  }
  return <article className={`paper-card ${compact && !expanded ? 'compact' : ''}`}>
    <div className="paper-head"><div className="paper-number">{paper.arxiv_id ? `arXiv ${paper.arxiv_id}` : `PAPER ${paper.id}`}</div><button className={`learn-button ${paper.learned ? 'done' : ''}`} onClick={() => onLearned(paper)}>{paper.learned ? <CheckCircle2 size={18}/> : <CircleDashed size={18}/>} {paper.learned ? '已学习' : '标记完成'}</button></div>
    <h2 className="english-title">{paper.title_en}</h2>
    {paper.title_zh && <h3 className="chinese-title">{paper.title_zh}</h3>}
    <div className="paper-meta"><span>{date}</span><span>·</span><span>{paper.authors.slice(0, 5).join(', ')}{paper.authors.length > 5 ? ' et al.' : ''}</span></div>
    <div className="badges"><span className={['CCF-A/top','field-top'].includes(paper.venue_tier) ? 'tier top' : 'tier'}>{paper.venue_name || 'arXiv 预印本'}{paper.venue_tier === 'CCF-A/top' ? ' · CCF-A/Top' : paper.venue_tier === 'field-top' ? ' · 领域顶刊' : ''}</span>{paper.tags.map(tag => <span key={tag.id}>{tag.name_zh}</span>)}</div>
    {paper.direction_match && <div className={`direction-match ${paper.direction_match.lane}`}><div><strong>{Math.round(paper.direction_match.relevance_score)}%</strong><span>方向关联度</span></div><article><header><span>{paper.direction_match.lane==='focused'?'高度相关':paper.direction_match.lane==='adjacent'?'相邻研究':'广度探索'}</span><small>置信度 {Math.round(paper.direction_match.confidence)}%</small></header><p>{paper.direction_match.reason}</p>{paper.direction_match.matched_concepts.length>0&&<div>{paper.direction_match.matched_concepts.map(item=><i key={item}>{item}</i>)}</div>}</article></div>}
    {paper.recommendation_assessment && <div className="morrow-pick"><div className="morrow-score"><Sparkles size={16}/><strong>{Math.round(paper.recommendation_assessment.taste_score)}</strong><span>Morrow<br/>Taste</span></div><div><span>为什么值得读</span><p>{paper.recommendation_assessment.reason}</p>{paper.recommendation_assessment.caution && <small>留意：{paper.recommendation_assessment.caution}</small>}</div></div>}
    {showDetails && <>
      <div className="abstract-toolbar"><strong>摘要</strong><div className="language-toggle"><button className={language === 'zh' ? 'active' : ''} onClick={() => setLanguage('zh')}>中文</button><button className={language === 'en' ? 'active' : ''} onClick={() => setLanguage('en')}>English</button></div></div>
      <div className={`abstract ${!abstract ? 'missing' : ''}`}>{abstract || (language === 'zh' ? '中文摘要尚未生成。配置模型后可补充，英文原摘要始终可用。' : 'No abstract available.')}</div>
      {paper.summary ? <div className="insight-grid"><Insight title="核心方法" text={paper.summary.method}/><Insight title="研究问题" text={paper.summary.research_problem}/><Insight title="主要创新" list={paper.summary.innovations}/><Insight title="研究价值" list={paper.summary.value}/>{paper.summary.limitations?.length ? <Insight title="值得留意" list={paper.summary.limitations}/> : null}</div> : <div className="ai-pending"><Sparkles size={17}/><span>{paper.ai_status === 'failed' ? 'AI 分析失败，可在配置模型后重试。' : '等待配置模型生成中文摘要、创新点和研究价值。'}</span><button onClick={() => onRetryAi(paper)}>生成 AI 分析</button></div>}
    </>}
    <div className="paper-actions">{compact&&<button className="expand-paper" disabled={expanding} onClick={toggleExpanded}>{expanding?<RefreshCw className="spin" size={17}/>:expanded?<ChevronUp size={17}/>:<ChevronDown size={17}/>} {expanded?'收起详情':paper.summary&&paper.abstract_zh?'展开详情':'展开并生成分析'}</button>}{paper.pdf_url&&<button className="reader-action" onClick={()=>onRead(paper)}><BookOpen size={17}/>智能阅读</button>}<button className="chat-action" onClick={() => onChat(paper)}><MessageCircle size={17}/>和 AI 讨论</button><a href={paper.primary_url} target="_blank" rel="noreferrer"><FileText size={17}/>论文页面</a>{paper.pdf_url && <a href={paper.pdf_url} target="_blank" rel="noreferrer"><ExternalLink size={17}/>PDF</a>}<button onClick={() => onRelated(paper)}><Network size={17}/>相关研究</button><button onClick={() => onNote(paper)}><NotebookPen size={17}/>学习笔记</button>{paper.repository_url ? <button onClick={() => onWiki(paper)}><Code2 size={17}/>解析代码</button> : <button onClick={() => onRepo(paper)}><Search size={17}/>查找代码</button>}</div>
  </article>
}

function Insight({ title, text, list }: { title: string; text?: string; list?: string[] }) { if (!text && !list?.length) return null; return <div className="insight"><span>{title}</span>{text && <p>{text}</p>}{list && <ul>{list.map((item, i) => <li key={i}>{item}</li>)}</ul>}</div> }

function relationLabel(relation: string) { return relation === 'reference' ? '前置研究' : relation === 'citation' ? '后续研究' : '相似工作' }

function EmptyState({ icon: Icon, title, text }: { icon: any; title: string; text: string }) { return <div className="empty-state"><div><Icon size={30}/></div><h3>{title}</h3><p>{text}</p></div> }

function Modal({ title, subtitle, onClose, children, wide = false }: { title: string; subtitle?: string; onClose: () => void; children: any; wide?: boolean }) { return <div className="modal-backdrop" onMouseDown={event => event.target === event.currentTarget && onClose()}><div className={`modal ${wide ? 'wide' : ''}`}><header><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" onClick={onClose}><X/></button></header><div className="modal-body">{children}</div></div></div> }

function NoteModal({ paper, onClose, onSaved }: { paper: Paper; onClose: () => void; onSaved: () => Promise<void> }) {
  const template = `# ${paper.title_en}\n\n- 论文：${paper.primary_url}\n- 日期：${new Date().toLocaleDateString('zh-CN')}\n\n## 核心理解\n\n\n## 创新点\n\n\n## 实验与证据\n\n\n## 我的思考\n\n`
  const [content, setContent] = useState(paper.note || template)
  const [saved, setSaved] = useState('已加载')
  useEffect(() => { const timer = window.setTimeout(async () => { setSaved('保存中…'); await api(`/api/papers/${paper.id}/note`, { method: 'PUT', body: JSON.stringify({ content }) }); setSaved('已自动保存'); await onSaved() }, 900); return () => window.clearTimeout(timer) }, [content])
  return <Modal wide title="学习笔记" subtitle={paper.title_en} onClose={onClose}><div className="note-status"><span>Markdown</span><small>{saved}</small></div><div className="note-editor"><textarea value={content} onChange={e => setContent(e.target.value)} spellCheck={false}/><div className="markdown-preview"><ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown></div></div></Modal>
}

function RepositoryResult({ result, onStart }: { result: any; onStart: () => void }) { return <div className="repo-result">{result.repository_url ? <><div className="success-mark"><CheckCircle2/></div><h3>{result.status === 'verified' ? '已发现高置信度仓库' : '发现候选仓库'}</h3><a href={result.repository_url} target="_blank" rel="noreferrer">{result.repository_url}<ExternalLink size={16}/></a><p>DeepWiki 将只进行静态分析，不会执行仓库中的代码。</p><button className="primary" onClick={onStart}><Code2 size={18}/>开始 DeepWiki 解析</button></> : <><div className="success-mark muted"><Search/></div><h3>暂未发现公开代码</h3><p>系统已检索论文元数据和 GitHub。你仍可稍后重新检测或通过 API 手动绑定仓库。</p></>}</div> }

function DeepWikiPage({ jobs, onOpen, onRetry }: { jobs: DeepWikiJob[]; onOpen: (job: DeepWikiJob) => void; onRetry: (job: DeepWikiJob) => Promise<void> }) {
  return <section className="page-content"><div className="list-toolbar"><div><span className="section-kicker">CODE INTELLIGENCE</span><h2>论文代码知识库</h2><p>完整运行原版 DeepWiki 研究图，生成 8–15 个主题页；任何页面未完成都不会标记成功。</p></div></div>{jobs.length ? <div className="job-grid">{jobs.map(job => <article className={`job-card ${job.needs_regeneration ? 'legacy-wiki-job' : ''}`} key={job.id}><div className="job-icon"><Code2/></div><div className="job-copy"><span>{job.repository_url.replace('https://github.com/', '')}</span><h3>{job.paper_title}</h3><div className="progress"><i style={{ width: `${job.progress}%` }}/></div><div className="job-status"><span className={`status-dot ${job.status}`}/>{job.message}{job.wiki_mode==='full'&&<em>完整原版</em>}{job.wiki_mode==='legacy'&&<em className="legacy">旧版简化</em>}<strong>{job.progress}%</strong></div>{job.error && <p className="job-error">{job.error}</p>}</div><div className="job-actions">{job.wiki_available && <button className="secondary" onClick={() => onOpen(job)}><BookOpen size={17}/>{job.wiki_mode==='full'?'打开完整 Wiki':'查看旧版内容'}</button>}{['completed','failed'].includes(job.status)&&<button className="secondary" onClick={()=>onRetry(job)}><RefreshCw size={16}/>重新生成</button>}</div></article>)}</div> : <EmptyState icon={Code2} title="还没有代码解析任务" text="在论文卡片中查找代码仓库，然后一键启动 DeepWiki。"/>}</section>
}

function SettingsPage({ settings, tags, researchProfiles, onSaved }: { settings: AppSettings; tags: Tag[]; researchProfiles:ResearchProfile[]; onSaved: () => Promise<void> }) {
  const [form, setForm] = useState<any>({ ...settings, github_token: '', zotero_api_key: '' })
  const [profiles, setProfiles] = useState<LLMProfile[]>([])
  const [usage, setUsage] = useState<TokenUsageStats | null>(null)
  const [draft, setDraft] = useState<any | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [apiBusy, setApiBusy] = useState(false)
  const [zoteroStatus, setZoteroStatus] = useState('')

  const reloadAI = async () => {
    const [profileData, usageData] = await Promise.all([api<LLMProfile[]>('/api/llm/profiles'), api<TokenUsageStats>('/api/llm/usage')])
    setProfiles(profileData); setUsage(usageData)
  }
  useEffect(() => { reloadAI().catch(() => undefined) }, [])
  useEffect(() => () => {
    document.documentElement.style.setProperty('--app-font-size', `${settings.font_size || 16}px`)
  }, [settings.font_size])

  const previewFontSize = (value: number) => {
    setForm((current: any) => ({ ...current, font_size:value }))
    document.documentElement.style.setProperty('--app-font-size', `${value}px`)
  }

  const choosePreset = (preset: typeof apiPresets[number]) => {
    setEditingId(null)
    setDraft({ name:preset.name, provider:preset.provider, base_url:preset.base_url, model:preset.model, api_key:'' })
  }
  const editProfile = (profile: LLMProfile) => {
    setEditingId(profile.id)
    setDraft({ name:profile.name, provider:profile.provider, base_url:profile.base_url, model:profile.model, api_key:'' })
  }
  const saveProfile = async () => {
    if (!draft?.name?.trim() || !draft?.base_url?.trim() || !draft?.model?.trim()) return
    setApiBusy(true)
    try {
      const payload = { ...draft }; if (!payload.api_key) delete payload.api_key
      await api(editingId ? `/api/llm/profiles/${editingId}` : '/api/llm/profiles', { method:editingId ? 'PUT' : 'POST', body:JSON.stringify(payload) })
      setDraft(null); setEditingId(null); await reloadAI(); await onSaved()
    } finally { setApiBusy(false) }
  }
  const activateProfile = async (id: string) => {
    setApiBusy(true)
    try { await api(`/api/llm/profiles/${id}/activate`, { method:'POST' }); await reloadAI(); await onSaved() }
    finally { setApiBusy(false) }
  }
  const removeProfile = async (profile: LLMProfile) => {
    if (!window.confirm(`删除“${profile.name}”？已记录的 Token 统计会保留。`)) return
    setApiBusy(true)
    try { await api(`/api/llm/profiles/${profile.id}`, { method:'DELETE' }); await reloadAI(); await onSaved() }
    finally { setApiBusy(false) }
  }
  const save = async () => {
    setSaving(true)
    try {
      const payload = { ...form }
      ;['has_llm_api_key','has_github_token','has_zotero_api_key','timezone_options','active_llm_profile','llm_provider','llm_model','llm_base_url'].forEach(key => delete payload[key])
      if (!payload.github_token) delete payload.github_token
      if (!payload.zotero_api_key) delete payload.zotero_api_key
      await api('/api/settings', { method:'PUT', body:JSON.stringify(payload) }); await onSaved(); await reloadAI()
    } finally { setSaving(false) }
  }
  const testZotero = async () => {
    setZoteroStatus('正在连接…')
    try {
      const payload:any={zotero_library_type:form.zotero_library_type,zotero_library_id:form.zotero_library_id,zotero_collection_key:form.zotero_collection_key,zotero_sync_tags:form.zotero_sync_tags}
      if(form.zotero_api_key)payload.zotero_api_key=form.zotero_api_key
      await api('/api/settings',{method:'PUT',body:JSON.stringify(payload)})
      await api('/api/zotero/test',{method:'POST'});setZoteroStatus('连接成功');await onSaved()
    } catch(error){setZoteroStatus(error instanceof Error?error.message:'连接失败')}
  }
  const fmt = (value: number) => value >= 1_000_000 ? `${(value / 1_000_000).toFixed(2)}M` : value >= 1_000 ? `${(value / 1_000).toFixed(1)}K` : value.toLocaleString()
  const maxDaily = Math.max(1, ...(usage?.daily.map(item => item.total_tokens) || [1]))

  return <section className="page-content settings-page">
    <div className="list-toolbar"><div><span className="section-kicker">PREFERENCES</span><h2>推荐、API 与用量</h2><p>可保存多个模型接口，选择一个后开始阅读；每日推荐默认关闭。</p></div><button className="primary" disabled={saving} onClick={save}>{saving ? <RefreshCw className="spin" size={18}/> : <Check size={18}/>}保存设置</button></div>
    <div className="settings-grid">
      <div className="settings-card"><header><Languages/><div><h3>阅读语言</h3><p>英文标题始终显示，只切换摘要默认语言。</p></div></header><label>摘要默认显示<select value={form.default_abstract_language} onChange={e => setForm({ ...form, default_abstract_language:e.target.value })}><option value="zh">中文摘要</option><option value="en">English abstract</option></select></label></div>
      <div className="settings-card font-size-card"><header><Type/><div><h3>字体与阅读缩放</h3><p>调整后立即应用到主页面、智能阅读器和 DeepWiki。</p></div><span className="setting-badge">13–20px</span></header><label>全局字号 <strong>{form.font_size || 16}px</strong><input aria-label="全局字号" type="range" min="13" max="20" step="1" value={form.font_size || 16} onInput={e => previewFontSize(Number((e.target as HTMLInputElement).value))}/></label><div className="font-size-labels"><span>A− 紧凑</span><span>标准</span><span>大字 A+</span></div></div>
      <div className="settings-card"><header><CalendarClock/><div><h3>每日推荐</h3><p>关闭时仍可随时手动生成。</p></div><button className={`switch ${form.daily_enabled ? 'on' : ''}`} onClick={() => setForm({ ...form, daily_enabled:!form.daily_enabled })}><i/></button></header><div className={!form.daily_enabled ? 'disabled-fields' : ''}><div className="field-row"><label>推荐时间<input type="time" value={form.daily_time} onChange={e => setForm({ ...form, daily_time:e.target.value })}/></label><label>时区<select value={form.timezone} onChange={e => setForm({ ...form, timezone:e.target.value })}>{settings.timezone_options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><label>篇数<input type="number" min="1" max="30" value={form.daily_count} onChange={e => setForm({ ...form, daily_count:Number(e.target.value) })}/></label></div><div className="settings-tags">{tags.map(tag => <button key={tag.id} className={form.daily_tag_ids.includes(tag.id) ? 'selected' : ''} onClick={() => setForm({ ...form, daily_tag_ids:form.daily_tag_ids.includes(tag.id) ? form.daily_tag_ids.filter((id:number) => id !== tag.id) : [...form.daily_tag_ids, tag.id] })}>{form.daily_tag_ids.includes(tag.id) && <Check size={14}/>} {tag.name_zh}</button>)}</div></div></div>

      <div className="settings-card full zotero-card"><header><Link2/><div><h3>Zotero 文献整理</h3><p>将论文元数据、个人标签和可选 Collection 同步到 Zotero；不上传 PDF，也不会远程删除条目。</p></div><span className={`connection ${settings.has_zotero_api_key&&settings.zotero_library_id?'connected':''}`}>{settings.has_zotero_api_key&&settings.zotero_library_id?'已配置':'未连接'}</span></header><div className="zotero-fields"><label>文献库类型<select value={form.zotero_library_type} onChange={e=>setForm({...form,zotero_library_type:e.target.value})}><option value="user">个人文献库</option><option value="group">群组文献库</option></select></label><label>Library ID<input value={form.zotero_library_id} onChange={e=>setForm({...form,zotero_library_id:e.target.value})} placeholder="Zotero 数字 ID"/></label><label>API Key<input type="password" value={form.zotero_api_key} onChange={e=>setForm({...form,zotero_api_key:e.target.value})} placeholder={settings.has_zotero_api_key?'已保存，留空不修改':'需要写入权限'}/></label><label>默认 Collection Key<input value={form.zotero_collection_key} onChange={e=>setForm({...form,zotero_collection_key:e.target.value})} placeholder="可选"/></label></div><div className="zotero-actions"><label className="checkbox-row"><input type="checkbox" checked={form.zotero_sync_tags} onChange={e=>setForm({...form,zotero_sync_tags:e.target.checked})}/>同步 PaperMorrow 个人标签</label><span>{zoteroStatus||'Library ID 可在 Zotero API Keys 页面查看。'}</span><button className="secondary" disabled={!form.zotero_library_id} onClick={testZotero}><Link2 size={15}/>保存并测试连接</button></div></div>

      <ResearchProfiles profiles={researchProfiles} onChanged={onSaved}/>

      <div className="settings-card full api-manager"><header><KeyRound/><div><h3>模型 API</h3><p>密钥独立保存在本机；智增增作为自定义中转预设，也可填写任意 OpenAI 兼容地址。</p></div><span className={`connection ${profiles.some(item => item.is_active && item.has_api_key) ? 'connected' : ''}`}>{profiles.some(item => item.is_active && item.has_api_key) ? '当前接口可用' : '等待配置'}</span></header>
        <div className="preset-row"><span>快捷添加</span>{apiPresets.map(preset => <button key={preset.label} onClick={() => choosePreset(preset)}><Plus size={13}/>{preset.label}</button>)}</div>
        {draft && <div className="api-editor"><div><strong>{editingId ? '编辑 API 配置' : '新增 API 配置'}</strong><span>自定义接口按 OpenAI Chat Completions 规范调用；Claude 预设使用原生协议。</span></div><div className="api-form"><label>配置名称<input autoFocus value={draft.name} onChange={e => setDraft({ ...draft, name:e.target.value })} placeholder="例如：我的中转站"/></label><label>协议<select value={draft.provider} onChange={e => setDraft({ ...draft, provider:e.target.value })}><option value="custom">OpenAI 兼容</option><option value="openai">OpenAI</option><option value="claude">Claude 原生</option><option value="glm">GLM 兼容</option><option value="deepseek">DeepSeek 兼容</option></select></label><label className="wide">API 地址<input value={draft.base_url} onChange={e => setDraft({ ...draft, base_url:e.target.value })} placeholder="https://example.com/v1"/></label><label>模型名称<input value={draft.model} onChange={e => setDraft({ ...draft, model:e.target.value })} placeholder="模型 ID"/></label><label>API Key<input type="password" value={draft.api_key} onChange={e => setDraft({ ...draft, api_key:e.target.value })} placeholder={editingId ? '留空则不修改' : '输入密钥'}/></label></div><div className="editor-actions"><button className="secondary" onClick={() => { setDraft(null); setEditingId(null) }}>取消</button><button className="primary" disabled={apiBusy || !draft.name || !draft.base_url || !draft.model} onClick={saveProfile}>{apiBusy ? <RefreshCw className="spin" size={16}/> : <Check size={16}/>}保存 API</button></div></div>}
        <div className="profile-list">{profiles.map(profile => <article key={profile.id} className={profile.is_active ? 'active' : ''}><button className="profile-select" disabled={apiBusy} onClick={() => !profile.is_active && activateProfile(profile.id)}><i>{profile.is_active && <Check size={13}/>}</i><div><strong>{profile.name}</strong><span>{profile.model} · {profile.base_url}</span></div></button><span className={`key-state ${profile.has_api_key ? 'ready' : ''}`}>{profile.has_api_key ? '密钥已保存' : '缺少密钥'}</span><button className="icon-button" title="编辑" onClick={() => editProfile(profile)}><Pencil size={15}/></button><button className="icon-button danger" title="删除" onClick={() => removeProfile(profile)}><Trash2 size={15}/></button></article>)}</div>
      </div>

      <div className="settings-card full usage-card"><header><BarChart3/><div><h3>Token 用量</h3><p>按所选时区统计；接口未返回 usage 时会进行近似估算并明确标记。</p></div><button className="icon-button" title="刷新" onClick={reloadAI}><RefreshCw size={16}/></button></header>{usage ? <><div className="usage-overview"><div><span>今日用量</span><strong>{fmt(usage.today.total_tokens)}</strong><small>{usage.today.requests} 次请求 · 输入 {fmt(usage.today.prompt_tokens)} / 输出 {fmt(usage.today.completion_tokens)}</small></div><div><span>累计用量</span><strong>{fmt(usage.total.total_tokens)}</strong><small>{usage.total.requests} 次请求{usage.total.estimated_requests ? ` · ${usage.total.estimated_requests} 次为估算` : ' · 均为接口返回'}</small></div></div><div className="usage-details"><div><h4>近 {Math.max(usage.daily.length, 1)} 个有用量的日期</h4><div className="usage-chart">{usage.daily.length ? usage.daily.map(item => <div key={item.date} title={`${item.date}: ${item.total_tokens.toLocaleString()} tokens`}><i style={{ height:`${Math.max(7, item.total_tokens / maxDaily * 100)}%` }}/><span>{item.date.slice(5)}</span></div>) : <p>产生第一条 AI 请求后，这里会显示趋势。</p>}</div></div><div><h4>按用途</h4><div className="usage-breakdown">{usage.by_purpose.length ? usage.by_purpose.map(item => <div key={item.purpose}><span>{item.label}</span><i><b style={{ width:`${usage.total.total_tokens ? item.total_tokens / usage.total.total_tokens * 100 : 0}%` }}/></i><strong>{fmt(item.total_tokens)}</strong></div>) : <p>暂无用量</p>}</div></div></div><div className="usage-profiles"><h4>按 API</h4>{usage.by_profile.length ? usage.by_profile.map(item => <span key={item.profile_id || item.name}><b>{item.name}</b>{fmt(item.total_tokens)} tokens · {item.requests} 次</span>) : <p>暂无用量记录</p>}</div></> : <div className="usage-loading"><CircleDashed className="spin"/>正在读取用量…</div>}</div>

      <div className="settings-card full"><header><Radar/><div><h3>推荐策略</h3><p>规则负责召回、时效、Venue 和去重；当前 API 负责创新、价值、可信度与阅读品味。</p></div><button className={`switch ${form.llm_rerank_enabled ? 'on' : ''}`} onClick={() => setForm({ ...form, llm_rerank_enabled:!form.llm_rerank_enabled })}><i/></button></header><div className={!form.llm_rerank_enabled ? 'disabled-fields' : ''}><label>LLM 复排影响力 <strong>{Math.round(form.llm_rerank_weight * 100)}%</strong><input type="range" min="0.1" max="0.8" step="0.05" value={form.llm_rerank_weight} onChange={e => setForm({ ...form, llm_rerank_weight:Number(e.target.value) })}/></label></div><label>顶会顶刊目标比例 <strong>{Math.round(form.top_venue_ratio * 100)}%</strong><input type="range" min="0" max="1" step="0.1" value={form.top_venue_ratio} onChange={e => setForm({ ...form, top_venue_ratio:Number(e.target.value) })}/></label><label className="checkbox-row"><input type="checkbox" checked={form.only_verified_top_venues} onChange={e => setForm({ ...form, only_verified_top_venues:e.target.checked })}/>仅推荐已核验顶会顶刊（可能不足指定篇数）</label></div>
      <div className="settings-card full"><header><Code2/><div><h3>GitHub</h3><p>公开仓库可不配置 Token；配置后限额更高且识别更稳定。</p></div><span className={`connection ${settings.has_github_token ? 'connected' : ''}`}>{settings.has_github_token ? '已配置' : '可选'}</span></header><label>GitHub Token<input type="password" placeholder={settings.has_github_token ? '已保存，留空则不修改' : '可选'} value={form.github_token} onChange={e => setForm({ ...form, github_token:e.target.value })}/></label></div>
    </div>
  </section>
}

function ChatPanel({ paper, configured, onClose, onOpenSettings }: { paper: Paper; configured: boolean; onClose: () => void; onOpenSettings: () => void }) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api<ChatSession[]>(`/api/papers/${paper.id}/chat/sessions`).then(async items => {
      setSessions(items)
      if (items.length) {
        setSessionId(items[0].id)
        setMessages(await api<ChatMessage[]>(`/api/papers/${paper.id}/chat/sessions/${items[0].id}/messages`))
      }
    }).catch(err => setError(err.message))
  }, [paper.id])

  const switchSession = async (id: string) => {
    setSessionId(id || null); setError('')
    setMessages(id ? await api<ChatMessage[]>(`/api/papers/${paper.id}/chat/sessions/${id}/messages`) : [])
  }
  const newChat = () => { setSessionId(null); setMessages([]); setInput(''); setError('') }
  const send = async (preset?: string) => {
    const content = (preset || input).trim()
    if (!content || sending || !configured) return
    setInput(''); setError(''); setSending(true)
    setMessages(current => [...current, { role:'user', content }])
    try {
      const response = await api<{session_id:string; answer:string}>(`/api/papers/${paper.id}/chat`, { method:'POST', body:JSON.stringify({ message:content, session_id:sessionId }) })
      setSessionId(response.session_id)
      setMessages(current => [...current, { role:'assistant', content:response.answer }])
      setSessions(await api<ChatSession[]>(`/api/papers/${paper.id}/chat/sessions`))
    } catch (err) { setError(err instanceof Error ? err.message : '对话失败') }
    finally { setSending(false) }
  }
  return <div className="chat-backdrop" onMouseDown={event => event.target === event.currentTarget && onClose()}><aside className="chat-panel">
    <header><div className="chat-orb"><Sparkles size={19}/></div><div><span>PaperMorrow AI</span><h2>{paper.title_en}</h2></div><button className="icon-button" onClick={onClose}><X/></button></header>
    <div className="chat-tools">{sessions.length ? <select value={sessionId || ''} onChange={e => switchSession(e.target.value)}><option value="">新对话</option>{sessions.map(session => <option key={session.id} value={session.id}>{session.title}</option>)}</select> : <span>优先读取公开全文，失败时使用摘要</span>}<button onClick={newChat}><Plus size={15}/>新对话</button></div>
    {!configured ? <div className="chat-empty"><div><Bot size={28}/></div><h3>先连接一个模型</h3><p>配置 OpenAI、Claude、GLM、DeepSeek 或智增增后，即可围绕这篇论文连续对话。</p><button className="primary" onClick={onOpenSettings}>前往模型设置</button></div> : messages.length === 0 ? <div className="chat-empty"><div><MessageCircle size={28}/></div><h3>从一个好问题开始</h3><p>系统会优先提取公开 arXiv 全文；拿不到全文时退回摘要，并明确说明上下文限制。</p><div className="chat-suggestions">{['用直觉解释这篇论文的核心方法','它真正的新意是什么？','帮我批判性分析实验与局限','给我设计一个复现和延伸研究计划'].map(item => <button key={item} onClick={() => send(item)}>{item}<ChevronRight size={15}/></button>)}</div></div> : <div className="chat-messages">{messages.map((message,index) => <div key={message.id || index} className={`chat-message ${message.role}`}><div>{message.role === 'assistant' ? <Sparkles size={15}/> : <User size={15}/>}</div><article><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></article></div>)}{sending && <div className="chat-message assistant"><div><Sparkles size={15}/></div><article className="thinking"><i/><i/><i/></article></div>}</div>}
    {error && <div className="chat-error">{error}</div>}
    <footer><textarea value={input} disabled={!configured} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} placeholder="针对论文提问，Enter 发送，Shift+Enter 换行"/><button disabled={!configured || !input.trim() || sending} onClick={() => send()}><Send size={18}/></button><small>AI 可能犯错，请以论文原文为准。</small></footer>
  </aside></div>
}
