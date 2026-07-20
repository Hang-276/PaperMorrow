import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import {
  BookOpen, CalendarClock, Check, CheckCircle2, ChevronDown, ChevronRight, ChevronUp, CircleDashed, Code2,
  ExternalLink, FileText, History, Languages, Library, Menu, Network, NotebookPen,
  Radar, RefreshCw, Search, Settings as SettingsIcon, Sparkles, X, Moon, Sun,
  MessageCircle, Send, Plus, Bot, User,
  BarChart3, KeyRound, Link2, Pencil, Trash2, Type,
  FlaskConical, Layers3, FolderKanban, ClipboardCheck,
  Bell, House, ListTodo, PanelLeftClose, PanelLeftOpen,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from './api'
import { analysisLabels, hasBilingualSummary, localizedSummary } from './analysisLocale'
import ResearchProfiles from './ResearchProfiles'
import LibraryPage from './LibraryPage'
import ResearchPage from './ResearchPage'
import DomainPacksPage from './DomainPacksPage'
import ProjectsPage from './ProjectsPage'
import NotesPage from './NotesPage'
import GlobalAssistant from './GlobalAssistant'
import HomePage from './HomePage'
import PlannerPage from './PlannerPage'
import './features.css'
import './library.css'
import type { AppSettings, Batch, ChatMessage, ChatSession, DeepWikiJob, LLMProfile, Paper, PlannerTask, ResearchProfile, SubmissionDeadline, Tag, TokenUsageStats } from './types'

type View = 'home' | 'today' | 'planner' | 'research' | 'projects' | 'notes' | 'history' | 'learning' | 'deepwiki' | 'domains' | 'settings'

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

const dailyDomains=[['ai','人工智能','关注高质量会议、期刊与前沿工作'],['computer','计算机科学','系统、软件与计算基础'],['physics','物理学','理论、实验与交叉物理'],['math','数学','纯数、应用与统计'],['life-sciences','生命科学','分子、细胞与生物信息'],['clinical-medicine','临床医学','循证研究与临床试验'],['chemistry-materials','化学与材料','化学、催化与材料'],['economics-finance','经济学与金融','经济、计量与金融']] as const

export default function App() {
  const [view, setView] = useState<View>('home')
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
  const [noteFocusPaperId,setNoteFocusPaperId]=useState<number|null>(null)
  const [relatedPaper, setRelatedPaper] = useState<Paper | null>(null)
  const [related, setRelated] = useState<any[]>([])
  const [repoResult, setRepoResult] = useState<any | null>(null)
  const [wikiJob, setWikiJob] = useState<DeepWikiJob | null>(null)
  const [chatPaper, setChatPaper] = useState<Paper | null>(null)
  const [readerPaper, setReaderPaper] = useState<Paper | null>(null)
  const [recommendMode, setRecommendMode] = useState<'broad'|'focus'|'mixed'>('broad')
  const [selectedProfileId, setSelectedProfileId] = useState<number|''>('')
  const [activeDomain, setActiveDomain] = useState<string>('ai')
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [plannerTasks,setPlannerTasks]=useState<PlannerTask[]>([])
  const [submissionDeadlines,setSubmissionDeadlines]=useState<SubmissionDeadline[]>([])
  const [noteCreateSignal,setNoteCreateSignal]=useState(0)
  const [sidebarCollapsed,setSidebarCollapsed]=useState(()=>localStorage.getItem('papermorrow-sidebar-collapsed')==='1')

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('papermorrow-theme', theme) }, [theme])
  useEffect(() => {
    if (settings?.font_size) document.documentElement.style.setProperty('--app-font-size', `${settings.font_size}px`)
  }, [settings?.font_size])

  const load = async () => {
    const [tagData, settingData, todayData, historyData, jobData, researchData, taskData, deadlineData] = await Promise.all([
      api<Tag[]>('/api/tags'), api<AppSettings>('/api/settings'), api<Batch[]>('/api/recommendations/today'),
      api<Paper[]>('/api/recommendations/history'), api<DeepWikiJob[]>('/api/deepwiki/jobs'), api<ResearchProfile[]>('/api/research-profiles'),
      api<PlannerTask[]>('/api/planner/tasks'), api<SubmissionDeadline[]>('/api/planner/deadlines'),
    ])
    setTags(tagData); setSettings(settingData); setToday(todayData); setHistory(historyData); setJobs(jobData); setResearchProfiles(researchData)
    setPlannerTasks(taskData); setSubmissionDeadlines(deadlineData)
    if (!selectedTags.length) setSelectedTags(settingData.daily_tag_ids.length ? settingData.daily_tag_ids : tagData.filter(t=>t.domain==='ai').slice(0, 2).map(t => t.id))
  }

  const loadPlanner=async()=>{const [taskData,deadlineData]=await Promise.all([api<PlannerTask[]>('/api/planner/tasks'),api<SubmissionDeadline[]>('/api/planner/deadlines')]);setPlannerTasks(taskData);setSubmissionDeadlines(deadlineData)}

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

  const toggleDailyPlan = async () => {
    if (!settings) return
    if (!settings.daily_enabled && !settings.daily_tag_ids.length && !settings.daily_profile_ids.length) {
      setMessage('请先到设置中选择至少一个专业方向或自定义研究方向')
      return
    }
    try {
      const updated = await api<AppSettings>('/api/settings', { method:'PUT', body:JSON.stringify({ daily_enabled:!settings.daily_enabled }) })
      setSettings(updated)
      setMessage(updated.daily_enabled ? `每日 ${updated.daily_time} 的推荐计划已开启` : '每日推荐计划已暂停，手动推荐不受影响')
    } catch (error) { setMessage(error instanceof Error ? error.message : '计划更新失败') }
  }

  const toggleLearned = async (paper: Paper) => {
    await api(`/api/papers/${paper.id}/study-state`, { method: 'PATCH', body: JSON.stringify({ learned: !paper.learned }) })
    await load()
  }

  const openUnifiedNote=async(paper:Paper)=>{
    const template=`# ${paper.title_en}\n\n- 论文：${paper.primary_url}\n- 日期：${new Date().toLocaleDateString('zh-CN')}\n\n## 核心理解\n\n\n## 创新点\n\n\n## 实验与证据\n\n\n## 我的思考\n\n`
    try{if(!paper.note?.trim())await api(`/api/papers/${paper.id}/note`,{method:'PUT',body:JSON.stringify({content:template})});setNoteFocusPaperId(paper.id);setView('notes')}
    catch(error){setMessage(error instanceof Error?error.message:'暂时无法打开笔记')}
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
    ['home', House, '起始页'], ['today', Radar, '论文推荐'], ['planner', ListTodo, '待办与 DDL'], ['research', FlaskConical, '专题调研'], ['projects', FolderKanban, '研究项目'], ['notes', NotebookPen, '学习笔记'], ['history', History, '推荐历史'], ['learning', Library, '学习库'],
    ['deepwiki', Code2, 'DeepWiki'], ['domains', Layers3, '专业配置'], ['settings', SettingsIcon, '设置'],
  ] as const

  const reminderCount=submissionDeadlines.filter(item=>{const days=Math.ceil((new Date(item.deadline_at).getTime()-Date.now())/86_400_000);return days>=0&&days<=item.remind_days_before}).length+plannerTasks.filter(item=>item.due_at&&new Date(item.due_at).getTime()<=Date.now()+86_400_000).length

  return <div className={`app-shell ${sidebarCollapsed?'sidebar-collapsed':''}`}>
    <aside className={`sidebar-shell ${mobileMenu ? 'open' : ''}`}>
      <div className="brand"><div className="brand-mark"><img src="/papermorrow-logo.png" alt=""/></div><div><strong>PaperMorrow</strong><span>Read what matters next</span></div><button className="sidebar-collapse" title={sidebarCollapsed?'展开侧栏':'收起侧栏'} onClick={()=>setSidebarCollapsed(value=>{localStorage.setItem('papermorrow-sidebar-collapsed',value?'0':'1');return !value})}>{sidebarCollapsed?<PanelLeftOpen/>:<PanelLeftClose/>}</button></div>
      <nav>{nav.map(([id, Icon, label]) => <button key={id} title={sidebarCollapsed?label:undefined} className={view === id ? 'active' : ''} onClick={() => { setView(id); setMobileMenu(false) }}><Icon size={19}/><span>{label}</span>{view === id && <ChevronRight size={16}/>}</button>)}</nav>
      <button className="sidebar-foot" onClick={() => setAssistantOpen(true)}><Sparkles size={17}/><div><strong>研究助手</strong><span>{settings?.has_llm_api_key ? '随时询问当前页面' : '连接模型后开始'}</span></div><i className={settings?.has_llm_api_key ? 'online' : ''}/></button>
    </aside>

    <main className="main-shell">
      <header className="topbar"><button className="icon-button menu-button" onClick={() => setMobileMenu(!mobileMenu)}><Menu/></button><div><span className="eyebrow">PAPERMORROW · RESEARCH COMPANION</span><h1>{nav.find(item => item[0] === view)?.[2]}</h1></div><div className="topbar-actions"><button className="context-ai-button" aria-label="问当前页面" onClick={() => setAssistantOpen(true)}><Sparkles/><span>问当前页面</span></button><button className="theme-toggle planner-badge-button" aria-label="查看待办与截稿提醒" onClick={()=>setView('planner')}><Bell/>{reminderCount>0&&<b>{reminderCount>99?'99+':reminderCount}</b>}</button><span className="date-pill"><CalendarClock size={16}/>{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })}</span><button className="theme-toggle" aria-label={theme === 'light' ? '切换深色模式' : '切换浅色模式'} onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? <Moon size={18}/> : <Sun size={18}/>}</button></div></header>

      {message && <div className="toast"><span>{busy && <CircleDashed className="spin" size={17}/>} {message}</span><button onClick={() => setMessage('')}><X size={16}/></button></div>}

      {view === 'home' && <HomePage tasks={plannerTasks} deadlines={submissionDeadlines} today={today} settings={settings} onNavigate={setView} onOpenAssistant={()=>setAssistantOpen(true)} onPlannerChanged={loadPlanner} onStartNote={()=>{setNoteCreateSignal(value=>value+1);setView('notes')}}/>}
      {view === 'today' && <section className="page-content">
        <div className="hero-panel"><div><span className="section-kicker">TOMORROW'S READING, CURATED TODAY</span><h2>广度发现，也追踪你的细分问题</h2><p>规则多路召回与永久去重；LLM 同时判断方向关联、创新强度、研究价值和阅读性价比。</p></div><div className="generate-controls"><select value={recommendMode} onChange={e=>setRecommendMode(e.target.value as any)}><option value="broad">广度推荐</option><option value="mixed">聚焦 + 探索</option><option value="focus">仅聚焦方向</option></select>{recommendMode!=='broad'&&<select value={selectedProfileId} onChange={e=>{const id=Number(e.target.value)||'';setSelectedProfileId(id);const found=researchProfiles.find(item=>item.id===id);if(found)setActiveDomain(found.domain)}}><option value="">选择细分方向</option>{researchProfiles.map(profile=><option key={profile.id} value={profile.id}>{profile.name}</option>)}</select>}<select value={count} onChange={e => setCount(Number(e.target.value))}>{[3,5,8,10,15,20].map(n => <option key={n} value={n}>推荐 {n} 篇</option>)}</select><button className="primary" disabled={busy} onClick={generate}>{busy ? <RefreshCw className="spin" size={18}/> : <Sparkles size={18}/>}生成推荐</button></div></div>
        {settings&&<div className={`daily-home-plan ${settings.daily_enabled?'active':''}`}><div className="daily-home-icon"><CalendarClock/></div><div><span>今日计划</span><strong>{settings.daily_enabled?'每日推荐已开启':'每日推荐未开启'}</strong><small>{settings.daily_profile_ids.length?`${settings.daily_profile_ids.length} 个自定义研究方向轮换`:settings.daily_tag_ids.length?`${settings.daily_tag_ids.length} 个专业方向`:'尚未选择方向'} · {settings.daily_time} · 每日 {settings.daily_count} 篇</small></div><button className="daily-config-link" onClick={()=>setView('settings')}>编辑计划</button><button aria-label={settings.daily_enabled?'关闭每日推荐':'开启每日推荐'} className={`switch ${settings.daily_enabled?'on':''}`} onClick={toggleDailyPlan}><i/></button></div>}
        <div className="domain-switch">{([['ai','AI'],['computer','计算机'],['physics','物理'],['math','数学'],['life-sciences','生命'],['clinical-medicine','临床'],['chemistry-materials','化学材料'],['economics-finance','经济金融']] as const).map(([id,label])=><button key={id} className={activeDomain===id?'active':''} onClick={()=>{setActiveDomain(id);setSelectedTags(tags.filter(tag=>tag.domain===id).slice(0,2).map(tag=>tag.id))}}>{label}</button>)}</div>
        <div className="tag-strip"><span>{recommendMode==='broad'?'广度方向':'辅助召回'}</span><div>{tags.filter(tag=>tag.domain===activeDomain).map(tag => <button key={tag.id} className={selectedTags.includes(tag.id) ? 'selected' : ''} onClick={() => setSelectedTags(current => current.includes(tag.id) ? current.filter(id => id !== tag.id) : [...current, tag.id])}>{selectedTags.includes(tag.id) && <Check size={14}/>} {tag.name_zh}</button>)}</div></div>
        {papers.length ? <div className="paper-list">{papers.map(paper => <PaperCard key={paper.id} paper={paper} defaultLanguage={settings?.default_abstract_language || 'zh'} onLearned={toggleLearned} onNote={openUnifiedNote} onRelated={findRelated} onRepo={discoverRepo} onWiki={startWiki} onRetryAi={retryAI} onChat={setChatPaper} onRead={setReaderPaper}/>)}</div> : <EmptyState icon={Radar} title="今天还没有推荐" text="选择广度方向，或创建细分研究方向后生成第一批论文。"/>}
      </section>}

      {view === 'history' && <section className="page-content"><div className="list-toolbar"><div><span className="section-kicker">ARCHIVE</span><h2>全部推荐记录</h2><p>共 {history.length} 篇，永久保留并参与后续去重。</p></div><label className="search-box"><Search size={17}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索英文或中文标题"/></label></div><div className="paper-list">{filteredHistory.map(paper => <PaperCard compact key={paper.id} paper={paper} defaultLanguage={settings?.default_abstract_language || 'zh'} onLearned={toggleLearned} onNote={openUnifiedNote} onRelated={findRelated} onRepo={discoverRepo} onWiki={startWiki} onRetryAi={retryAI} onChat={setChatPaper} onRead={setReaderPaper}/>)}</div></section>}

      {view === 'learning' && <LibraryPage onRead={setReaderPaper} onNote={openUnifiedNote} onChat={setChatPaper} onRelated={findRelated} onRepo={discoverRepo} onWiki={startWiki} onOpenSettings={()=>setView('settings')} onDataChanged={load}/>}
      {view === 'research' && <ResearchPage onDataChanged={load}/>} 
      {view === 'projects' && <ProjectsPage/>}
      {view === 'notes' && <NotesPage focusPaperId={noteFocusPaperId} createSignal={noteCreateSignal}/>}
      {view === 'planner' && <PlannerPage tasks={plannerTasks} deadlines={submissionDeadlines} onChanged={loadPlanner}/>}

      {view === 'deepwiki' && <DeepWikiPage jobs={jobs} onOpen={setWikiJob} onRetry={retryWiki}/>} 
      {view === 'domains' && <DomainPacksPage/>}
      {view === 'settings' && settings && <SettingsPage settings={settings} tags={tags} researchProfiles={researchProfiles} onSaved={async () => { await load(); setMessage('设置已保存') }}/>} 
    </main>

    {relatedPaper && <Modal title="相关研究" subtitle={relatedPaper.title_en} onClose={() => setRelatedPaper(null)}><div className="related-list">{related.length ? related.map((item, index) => <a key={item.paper_id || index} href={item.url} target="_blank" rel="noreferrer"><span>{relationLabel(item.relation)} · {item.year || '—'} · {item.venue || 'Venue 未知'}</span><strong>{item.title}</strong><small>{(item.authors || []).join(', ')}</small><ExternalLink size={17}/></a>) : <div className="modal-loading"><CircleDashed className="spin"/>正在查找相似、前置与后续研究…</div>}</div></Modal>}
    {repoResult && <Modal title="代码仓库识别" subtitle={repoResult.paper.title_en} onClose={() => setRepoResult(null)}><RepositoryResult result={repoResult} onStart={() => startWiki(repoResult.paper)}/></Modal>}
    {wikiJob && <Suspense fallback={<div className="reader-boot"><RefreshCw className="spin" size={20}/><span>正在打开完整 Wiki…</span></div>}><WikiWorkspace job={wikiJob} fontSize={settings?.font_size || 16} onFontSizePreview={previewFontSize} onFontSizeSave={saveFontSize} onClose={() => setWikiJob(null)} onRetry={() => retryWiki(wikiJob)}/></Suspense>} 
    {chatPaper && <ChatPanel paper={chatPaper} configured={Boolean(settings?.has_llm_api_key)} onClose={() => setChatPaper(null)} onOpenSettings={() => { setChatPaper(null); setView('settings') }}/>} 
    {readerPaper && <Suspense fallback={<div className="reader-boot"><RefreshCw className="spin" size={20}/><span>正在准备智能阅读器…</span></div>}><ReaderWorkspace paper={readerPaper} configured={Boolean(settings?.has_llm_api_key)} onClose={()=>setReaderPaper(null)} onSaved={load} onOpenNotes={()=>{setNoteFocusPaperId(readerPaper.id);setView('notes')}}/></Suspense>}
    <GlobalAssistant open={assistantOpen} onOpen={() => setAssistantOpen(true)} onClose={() => setAssistantOpen(false)} showLauncher={Boolean(readerPaper||wikiJob||chatPaper)} pageId={readerPaper ? 'reader' : wikiJob ? 'deepwiki' : chatPaper ? 'paper-chat' : view} pageTitle={readerPaper ? (readerPaper.title_zh || readerPaper.title_en) : wikiJob ? 'DeepWiki' : chatPaper ? (chatPaper.title_zh || chatPaper.title_en) : (nav.find(item => item[0] === view)?.[2] || 'PaperMorrow')} configured={Boolean(settings?.has_llm_api_key)} onOpenSettings={() => { setReaderPaper(null); setWikiJob(null); setChatPaper(null); setView('settings'); setAssistantOpen(false) }}/>
  </div>
}

function PaperCard({ paper, defaultLanguage, onLearned, onNote, onRelated, onRepo, onWiki, onRetryAi, onChat, onRead, compact = false }: { paper: Paper; defaultLanguage: 'zh'|'en'; onLearned: (p: Paper) => void; onNote: (p: Paper) => void; onRelated: (p: Paper) => void; onRepo: (p: Paper) => void; onWiki: (p: Paper) => void; onRetryAi: (p: Paper) => void; onChat: (p: Paper) => void; onRead: (p:Paper)=>void; compact?: boolean }) {
  const [language, setLanguage] = useState<'zh'|'en'>(defaultLanguage)
  const [expanded, setExpanded] = useState(!compact)
  const [expanding, setExpanding] = useState(false)
  const [timeline,setTimeline] = useState<any|null>(null)
  const [timelineOpen,setTimelineOpen] = useState(false)
  const abstract = language === 'zh' ? paper.abstract_zh : paper.abstract_en
  const analysis = paper.summary ? localizedSummary(paper.summary, language) : null
  const labels = analysisLabels[language]
  const needsBilingualUpgrade = Boolean(paper.summary && !hasBilingualSummary(paper.summary))
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
  const openTimeline=async()=>{if(timelineOpen)return setTimelineOpen(false);setTimelineOpen(true);setTimeline(await api(`/api/papers/${paper.id}/versions`))}
  const versionAction=async(action:'confirm'|'split'|'undo')=>setTimeline(await api(`/api/papers/${paper.id}/versions/${action}`,{method:'POST'}))
  return <article className={`paper-card ${compact && !expanded ? 'compact' : ''}`}>
    <div className="paper-head"><div className="paper-number">{paper.arxiv_id ? `arXiv ${paper.arxiv_id}` : `PAPER ${paper.id}`}</div><button className={`learn-button ${paper.learned ? 'done' : ''}`} onClick={() => onLearned(paper)}>{paper.learned ? <CheckCircle2 size={18}/> : <CircleDashed size={18}/>} {paper.learned ? '已学习' : '标记完成'}</button></div>
    <h2 className="english-title">{paper.title_en}</h2>
    {paper.title_zh && <h3 className="chinese-title">{paper.title_zh}</h3>}
    <div className="paper-meta"><span>{date}</span><span>·</span><span>{paper.authors.slice(0, 5).join(', ')}{paper.authors.length > 5 ? ' et al.' : ''}</span></div>
    <div className="badges"><span className={['CCF-A/top','field-top'].includes(paper.venue_tier) ? 'tier top' : 'tier'}>{paper.venue_name || 'arXiv 预印本'}{paper.venue_tier === 'CCF-A/top' ? ' · CCF-A/Top' : paper.venue_tier === 'field-top' ? ' · 领域顶刊' : ''}</span>{paper.tags.map(tag => <span key={tag.id}>{tag.name_zh}</span>)}</div>
    {paper.direction_match && <div className={`direction-match ${paper.direction_match.lane}`}><div><strong>{Math.round(paper.direction_match.relevance_score)}%</strong><span>方向关联度</span></div><article><header><span>{paper.direction_match.lane==='focused'?'高度相关':paper.direction_match.lane==='adjacent'?'相邻研究':'广度探索'}</span><small>置信度 {Math.round(paper.direction_match.confidence)}%</small></header><p>{paper.direction_match.reason}</p>{paper.direction_match.matched_concepts.length>0&&<div>{paper.direction_match.matched_concepts.map(item=><i key={item}>{item}</i>)}</div>}</article></div>}
    {paper.recommendation_assessment && <div className="morrow-pick"><div className="morrow-score"><Sparkles size={16}/><strong>{Math.round(paper.recommendation_assessment.taste_score)}</strong><span>Morrow<br/>Taste</span></div><div><span>为什么值得读</span><p>{paper.recommendation_assessment.reason}</p>{paper.recommendation_assessment.caution && <small>留意：{paper.recommendation_assessment.caution}</small>}</div></div>}
    {showDetails && <>
      <div className="abstract-toolbar"><strong>{labels.abstract}</strong><div className="analysis-toolbar-actions">{needsBilingualUpgrade&&<button className="analysis-upgrade" onClick={()=>onRetryAi(paper)}><Languages size={14}/>{labels.upgrade}</button>}<div className="language-toggle"><button className={language === 'zh' ? 'active' : ''} onClick={() => setLanguage('zh')}>中文</button><button className={language === 'en' ? 'active' : ''} onClick={() => setLanguage('en')}>English</button></div></div></div>
      <div className={`abstract ${!abstract ? 'missing' : ''}`}>{abstract || (language === 'zh' ? '中文摘要尚未生成。配置模型后可补充，英文原摘要始终可用。' : 'No abstract available.')}</div>
      {paper.summary&&<div className="evidence-scope"><strong>{paper.analysis_scope==='full_text'?labels.fullText:labels.abstractOnly}</strong><span>{paper.analysis_scope==='full_text'?labels.fullScope:labels.abstractScope}</span>{paper.analysis_evidence?.slice(0,3).map(item=><small key={item.id}>{item.section||'Abstract'}{item.page_number?` · ${language==='zh'?`第 ${item.page_number} 页`:`p. ${item.page_number}`}`:''} · {language==='zh'?(item.conclusion_type==='ai_judgment'?'AI 判断':item.conclusion_type==='author_claim'?'作者主张':'论文事实'):(item.conclusion_type==='ai_judgment'?'AI judgment':item.conclusion_type==='author_claim'?'Author claim':'Paper fact')}</small>)}</div>}
      {analysis ? <div className="insight-grid"><Insight title={labels.method} text={analysis.method}/><Insight title={labels.researchProblem} text={analysis.research_problem}/><Insight title={labels.innovations} list={analysis.innovations}/><Insight title={labels.value} list={analysis.value}/>{analysis.limitations?.length ? <Insight title={labels.limitations} list={analysis.limitations}/> : null}{analysis.recommended_for?.length?<Insight title={labels.audience} list={analysis.recommended_for}/>:null}</div> : <div className="ai-pending"><Sparkles size={17}/><span>{paper.ai_status === 'failed' ? 'AI 分析失败，可在配置模型后重试。' : '等待配置模型生成双语摘要、创新点和研究价值。'}</span><button onClick={() => onRetryAi(paper)}>生成 AI 分析</button></div>}
    </>}
    <div className="paper-actions">{compact&&<button className="expand-paper" disabled={expanding} onClick={toggleExpanded}>{expanding?<RefreshCw className="spin" size={17}/>:expanded?<ChevronUp size={17}/>:<ChevronDown size={17}/>} {expanded?'收起详情':paper.summary&&paper.abstract_zh?'展开详情':'展开并生成分析'}</button>}{paper.pdf_url&&<button className="reader-action" onClick={()=>onRead(paper)}><BookOpen size={17}/>智能阅读</button>}<button className="chat-action" onClick={() => onChat(paper)}><MessageCircle size={17}/>和 AI 讨论</button><a href={paper.primary_url} target="_blank" rel="noreferrer"><FileText size={17}/>论文页面</a>{paper.pdf_url && <a href={paper.pdf_url} target="_blank" rel="noreferrer"><ExternalLink size={17}/>PDF</a>}<button onClick={() => onRelated(paper)}><Network size={17}/>相关研究</button><button onClick={openTimeline}><History size={17}/>版本时间线</button><button onClick={() => onNote(paper)}><NotebookPen size={17}/>学习笔记</button>{paper.repository_url ? <button onClick={() => onWiki(paper)}><Code2 size={17}/>解析代码</button> : <button onClick={() => onRepo(paper)}><Search size={17}/>查找代码</button>}</div>
    {timelineOpen&&<div className="version-timeline">{timeline?<><header><div><span>WORK #{timeline.work_id}</span><strong>{timeline.canonical_title}</strong></div><div><button onClick={()=>versionAction('split')}>拆分当前版本</button><button onClick={()=>versionAction('undo')}>撤销上次操作</button></div></header>{timeline.versions.map((item:any)=><article key={item.paper_id} className={!item.confirmed?'unconfirmed':''}><i/><div><strong>{item.version_label}</strong><span>{item.title}</span><small>{item.version_date?new Date(item.version_date).toLocaleDateString('zh-CN'):'日期未知'} · 置信度 {Math.round(item.confidence*100)}% · {item.match_reason}</small>{item.important_changes&&<p>{item.important_changes}</p>}</div>{!item.confirmed&&item.paper_id===paper.id?<button onClick={()=>versionAction('confirm')}>确认关系</button>:<em>{item.confirmed?'已确认':'待确认'}</em>}</article>)}</>:<div className="version-loading"><RefreshCw className="spin"/>正在读取版本关系…</div>}</div>}
  </article>
}

function Insight({ title, text, list }: { title: string; text?: string; list?: string[] }) { if (!text && !list?.length) return null; return <div className="insight"><span>{title}</span>{text && <p>{text}</p>}{list && <ul>{list.map((item, i) => <li key={i}>{item}</li>)}</ul>}</div> }

function relationLabel(relation: string) { return relation === 'reference' ? '前置研究' : relation === 'citation' ? '后续研究' : '相似工作' }

function EmptyState({ icon: Icon, title, text }: { icon: any; title: string; text: string }) { return <div className="empty-state"><div><Icon size={30}/></div><h3>{title}</h3><p>{text}</p></div> }

function Modal({ title, subtitle, onClose, children, wide = false }: { title: string; subtitle?: string; onClose: () => void; children: any; wide?: boolean }) { return <div className="modal-backdrop" onMouseDown={event => event.target === event.currentTarget && onClose()}><div className={`modal ${wide ? 'wide' : ''}`}><header><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" onClick={onClose}><X/></button></header><div className="modal-body">{children}</div></div></div> }

function RepositoryResult({ result, onStart }: { result: any; onStart: () => void }) { return <div className="repo-result">{result.repository_url ? <><div className="success-mark"><CheckCircle2/></div><h3>{result.status === 'verified' ? '已发现高置信度仓库' : '发现候选仓库'}</h3><a href={result.repository_url} target="_blank" rel="noreferrer">{result.repository_url}<ExternalLink size={16}/></a><p>DeepWiki 将只进行静态分析，不会执行仓库中的代码。</p><button className="primary" onClick={onStart}><Code2 size={18}/>开始 DeepWiki 解析</button></> : <><div className="success-mark muted"><Search/></div><h3>暂未发现公开代码</h3><p>系统已检索论文元数据和 GitHub。你仍可稍后重新检测或通过 API 手动绑定仓库。</p></>}</div> }

function DeepWikiPage({ jobs, onOpen, onRetry }: { jobs: DeepWikiJob[]; onOpen: (job: DeepWikiJob) => void; onRetry: (job: DeepWikiJob) => Promise<void> }) {
  return <section className="page-content"><div className="list-toolbar"><div><span className="section-kicker">CODE INTELLIGENCE</span><h2>论文代码知识库</h2><p>完整运行原版 DeepWiki 研究图，生成 8–15 个主题页；任何页面未完成都不会标记成功。</p></div></div>{jobs.length ? <div className="job-grid">{jobs.map(job => <article className={`job-card ${job.needs_regeneration ? 'legacy-wiki-job' : ''}`} key={job.id}><div className="job-icon"><Code2/></div><div className="job-copy"><span>{job.repository_url.replace('https://github.com/', '')}</span><h3>{job.paper_title}</h3><div className="progress"><i style={{ width: `${job.progress}%` }}/></div><div className="job-status"><span className={`status-dot ${job.status}`}/>{job.message}{job.wiki_mode==='full'&&<em>完整原版</em>}{job.wiki_mode==='legacy'&&<em className="legacy">旧版简化</em>}<strong>{job.progress}%</strong></div>{job.error && <p className="job-error">{job.error}</p>}</div><div className="job-actions">{job.wiki_available && <button className="secondary" onClick={() => onOpen(job)}><BookOpen size={17}/>{job.wiki_mode==='full'?'打开完整 Wiki':'查看旧版内容'}</button>}{['completed','failed'].includes(job.status)&&<button className="secondary" onClick={()=>onRetry(job)}><RefreshCw size={16}/>重新生成</button>}<ReproductionChecklistButton job={job}/></div></article>)}</div> : <EmptyState icon={Code2} title="还没有代码解析任务" text="在论文卡片中查找代码仓库，然后一键启动 DeepWiki。"/>}</section>
}

function ReproductionChecklistButton({job}:{job:DeepWikiJob}){const [result,setResult]=useState<any|null>(null);const [busy,setBusy]=useState(false);const labels:Record<string,string>={confirmed:'已确认',possibly_consistent:'可能一致',missing:'缺失',unable_to_confirm:'无法确认'};const run=async()=>{setBusy(true);try{setResult(await api(`/api/papers/${job.paper_id}/reproduction-checklist?deepwiki_job_id=${job.id}`,{method:'POST'}))}finally{setBusy(false)}};return <>{<button className="secondary" disabled={busy} onClick={run}>{busy?<RefreshCw className="spin" size={16}/>:<ClipboardCheck size={16}/>}复现准备清单</button>}{result&&<div className="reproduction-checks">{result.items.map((item:any)=><div key={item.check_key}><strong>{item.title}</strong><span className={`check-${item.status}`}>{labels[item.status]}</span><small>{item.evidence}</small></div>)}</div>}</>}

function SettingsPage({ settings, tags, researchProfiles, onSaved }: { settings: AppSettings; tags: Tag[]; researchProfiles:ResearchProfile[]; onSaved: () => Promise<void> }) {
  const [form, setForm] = useState<any>({ ...settings, github_token: '', zotero_api_key: '' })
  const [profiles, setProfiles] = useState<LLMProfile[]>([])
  const [usage, setUsage] = useState<TokenUsageStats | null>(null)
  const [draft, setDraft] = useState<any | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [apiBusy, setApiBusy] = useState(false)
  const [zoteroStatus, setZoteroStatus] = useState('')
  const [dailyDomain,setDailyDomain] = useState('ai')

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
  const dailyDomainTags=tags.filter(tag=>tag.domain===dailyDomain)
  const dailyDomainProfiles=researchProfiles.filter(profile=>profile.enabled&&profile.domain===dailyDomain)
  const toggleDailyTag=(tagId:number)=>setForm({...form,daily_tag_ids:form.daily_tag_ids.includes(tagId)?form.daily_tag_ids.filter((id:number)=>id!==tagId):[...form.daily_tag_ids,tagId]})
  const toggleDailyProfile=(profileId:number)=>setForm({...form,daily_profile_ids:form.daily_profile_ids.includes(profileId)?form.daily_profile_ids.filter((id:number)=>id!==profileId):[...form.daily_profile_ids,profileId]})
  const setDailyDomainTags=(selectAll:boolean)=>{const ids=tags.filter(tag=>tag.domain===dailyDomain).map(tag=>tag.id);setForm({...form,daily_tag_ids:selectAll?Array.from(new Set([...form.daily_tag_ids,...ids])):form.daily_tag_ids.filter((id:number)=>!ids.includes(id))})}

  return <section className="page-content settings-page">
    <div className="list-toolbar"><div><span className="section-kicker">PREFERENCES</span><h2>推荐、API 与用量</h2><p>可保存多个模型接口，选择一个后开始阅读；每日推荐默认关闭。</p></div><button className="primary" disabled={saving} onClick={save}>{saving ? <RefreshCw className="spin" size={18}/> : <Check size={18}/>}保存设置</button></div>
    <div className="settings-grid">
      <div className="settings-card"><header><Languages/><div><h3>阅读语言</h3><p>英文标题始终显示，只切换摘要默认语言。</p></div></header><label>摘要默认显示<select value={form.default_abstract_language} onChange={e => setForm({ ...form, default_abstract_language:e.target.value })}><option value="zh">中文摘要</option><option value="en">English abstract</option></select></label></div>
      <div className="settings-card font-size-card"><header><Type/><div><h3>字体与阅读缩放</h3><p>调整后立即应用到主页面、智能阅读器和 DeepWiki。</p></div><span className="setting-badge">13–20px</span></header><label>全局字号 <strong>{form.font_size || 16}px</strong><input aria-label="全局字号" type="range" min="13" max="20" step="1" value={form.font_size || 16} onInput={e => previewFontSize(Number((e.target as HTMLInputElement).value))}/></label><div className="font-size-labels"><span>A− 紧凑</span><span>标准</span><span>大字 A+</span></div></div>
      <div className="settings-card full daily-recommend-card"><header><CalendarClock/><div><h3>每日推荐计划</h3><p>按专业分别组织广度方向与自定义研究方向，让每天的阅读更聚焦，也保留适量跨方向发现。</p></div><span className="daily-summary">{form.daily_profile_ids.length} 个自定义 · {form.daily_tag_ids.length} 个通用</span><button aria-label="启用每日推荐" className={`switch ${form.daily_enabled ? 'on' : ''}`} onClick={() => setForm({ ...form, daily_enabled:!form.daily_enabled })}><i/></button></header><div className={!form.daily_enabled ? 'disabled-fields' : ''}><div className="daily-schedule"><label>推荐时间<input type="time" value={form.daily_time} onChange={e => setForm({ ...form, daily_time:e.target.value })}/></label><label>时区<select value={form.timezone} onChange={e => setForm({ ...form, timezone:e.target.value })}>{settings.timezone_options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><label>每日总篇数<input type="number" min="1" max="30" value={form.daily_count} onChange={e => setForm({ ...form, daily_count:Number(e.target.value) })}/></label><div className="daily-plan-note"><strong>{form.daily_enabled?'计划已启用':'计划暂未启用'}</strong><span>关闭后仍可在推荐页手动生成。</span></div></div><div className="daily-domain-layout"><nav>{dailyDomains.map(([slug,name,description])=>{const domainTags=tags.filter(tag=>tag.domain===slug);const tagCount=domainTags.filter(tag=>form.daily_tag_ids.includes(tag.id)).length;const profileCount=researchProfiles.filter(profile=>profile.domain===slug&&form.daily_profile_ids.includes(profile.id)).length;return <button key={slug} className={dailyDomain===slug?'active':''} onClick={()=>setDailyDomain(slug)}><i className={`domain-dot ${slug}`}/><div><strong>{name}{slug==='ai'&&<em>重点优化</em>}</strong><span>{description}</span></div><b>{profileCount?`${profileCount} 自定`: `${tagCount}/${domainTags.length}`}</b></button>})}</nav><section><header><div><span>当前专业</span><h4>{dailyDomains.find(item=>item[0]===dailyDomain)?.[1]}</h4></div><div><button onClick={()=>setDailyDomainTags(true)}>全选通用</button><button onClick={()=>setDailyDomainTags(false)}>清空通用</button></div></header><div className="daily-profile-section"><div className="daily-subhead"><div><strong>我的研究方向</strong><span>按方向分别检索，多个方向会逐日轮换</span></div><label>推荐方式<select value={form.daily_profile_mode} onChange={e=>setForm({...form,daily_profile_mode:e.target.value})}><option value="mixed">聚焦 + 少量探索</option><option value="focus">仅聚焦方向</option></select></label></div>{dailyDomainProfiles.length?<div className="daily-profile-grid">{dailyDomainProfiles.map(profile=><button key={profile.id} className={form.daily_profile_ids.includes(profile.id)?'selected':''} onClick={()=>toggleDailyProfile(profile.id)}><i>{form.daily_profile_ids.includes(profile.id)?<Check/>:<Radar/>}</i><span><strong>{profile.name}</strong><small>{profile.description}</small></span></button>)}</div>:<div className="daily-domain-empty compact">该专业还没有自定义研究方向。可在下方“研究方向”中新建。</div>}</div><div className="daily-generic-section"><div className="daily-subhead"><div><strong>专业通用方向</strong><span>用于广度发现，也作为自定义方向的辅助召回</span></div></div>{dailyDomainTags.length?<div className="daily-direction-grid">{dailyDomainTags.map(tag=><button key={tag.id} className={form.daily_tag_ids.includes(tag.id)?'selected':''} onClick={()=>toggleDailyTag(tag.id)}><i>{form.daily_tag_ids.includes(tag.id)&&<Check/>}</i><span>{tag.name_zh}<small>{tag.name_en}</small></span></button>)}</div>:<div className="daily-domain-empty">该专业暂未配置通用方向，可通过自定义研究方向继续聚焦推荐。</div>}</div></section></div></div></div>

      <div className="settings-card full zotero-card"><header><Link2/><div><h3>Zotero 文献整理</h3><p>将论文元数据、个人标签和可选 Collection 同步到 Zotero；不上传 PDF，也不会远程删除条目。</p></div><span className={`connection ${settings.has_zotero_api_key&&settings.zotero_library_id?'connected':''}`}>{settings.has_zotero_api_key&&settings.zotero_library_id?'已配置':'未连接'}</span></header><div className="zotero-fields"><label>文献库类型<select value={form.zotero_library_type} onChange={e=>setForm({...form,zotero_library_type:e.target.value})}><option value="user">个人文献库</option><option value="group">群组文献库</option></select></label><label>Library ID<input value={form.zotero_library_id} onChange={e=>setForm({...form,zotero_library_id:e.target.value})} placeholder="Zotero 数字 ID"/></label><label>API Key<input type="password" value={form.zotero_api_key} onChange={e=>setForm({...form,zotero_api_key:e.target.value})} placeholder={settings.has_zotero_api_key?'已保存，留空不修改':'需要写入权限'}/></label><label>默认 Collection Key<input value={form.zotero_collection_key} onChange={e=>setForm({...form,zotero_collection_key:e.target.value})} placeholder="可选"/></label></div><div className="zotero-actions"><label className="checkbox-row"><input type="checkbox" checked={form.zotero_sync_tags} onChange={e=>setForm({...form,zotero_sync_tags:e.target.checked})}/>同步 PaperMorrow 个人标签</label><span>{zoteroStatus||'Library ID 可在 Zotero API Keys 页面查看。'}</span><button className="secondary" disabled={!form.zotero_library_id} onClick={testZotero}><Link2 size={15}/>保存并测试连接</button></div></div>

      <ResearchProfiles profiles={researchProfiles} onChanged={onSaved}/>

      <div className="settings-card full api-manager"><header><KeyRound/><div><h3>模型 API</h3><p>密钥独立保存在本机；智增增作为自定义中转预设，也可填写任意 OpenAI 兼容地址。</p></div><span className={`connection ${profiles.some(item => item.is_active && item.has_api_key) ? 'connected' : ''}`}>{profiles.some(item => item.is_active && item.has_api_key) ? '当前接口可用' : '等待配置'}</span></header>
        <div className="preset-row"><span>快捷添加</span>{apiPresets.map(preset => <button key={preset.label} onClick={() => choosePreset(preset)}><Plus size={13}/>{preset.label}</button>)}</div>
        {draft && <div className="api-editor"><div><strong>{editingId ? '编辑 API 配置' : '新增 API 配置'}</strong><span>自定义接口按 OpenAI Chat Completions 规范调用；Claude 预设使用原生协议。</span></div><div className="api-form"><label>配置名称<input autoFocus value={draft.name} onChange={e => setDraft({ ...draft, name:e.target.value })} placeholder="例如：我的中转站"/></label><label>协议<select value={draft.provider} onChange={e => setDraft({ ...draft, provider:e.target.value })}><option value="custom">OpenAI 兼容</option><option value="openai">OpenAI</option><option value="claude">Claude 原生</option><option value="glm">GLM 兼容</option><option value="deepseek">DeepSeek 兼容</option></select></label><label className="wide">API 地址<input value={draft.base_url} onChange={e => setDraft({ ...draft, base_url:e.target.value })} placeholder="https://example.com/v1"/></label><label>模型名称<input value={draft.model} onChange={e => setDraft({ ...draft, model:e.target.value })} placeholder="模型 ID"/></label><label>API Key<input type="password" value={draft.api_key} onChange={e => setDraft({ ...draft, api_key:e.target.value })} placeholder={editingId ? '留空则不修改' : '输入密钥'}/></label></div><div className="editor-actions"><button className="secondary" onClick={() => { setDraft(null); setEditingId(null) }}>取消</button><button className="primary" disabled={apiBusy || !draft.name || !draft.base_url || !draft.model} onClick={saveProfile}>{apiBusy ? <RefreshCw className="spin" size={16}/> : <Check size={16}/>}保存 API</button></div></div>}
        <div className="profile-list">{profiles.map(profile => <article key={profile.id} className={profile.is_active ? 'active' : ''}><button className="profile-select" disabled={apiBusy} onClick={() => !profile.is_active && activateProfile(profile.id)}><i>{profile.is_active && <Check size={13}/>}</i><div><strong>{profile.name}</strong><span>{profile.model} · {profile.base_url}</span></div></button><span className={`key-state ${profile.has_api_key ? 'ready' : ''}`}>{profile.has_api_key ? '密钥已保存' : '缺少密钥'}</span><button className="icon-button" title="编辑" onClick={() => editProfile(profile)}><Pencil size={15}/></button><button className="icon-button danger" title="删除" onClick={() => removeProfile(profile)}><Trash2 size={15}/></button></article>)}</div>
      </div>

      <div className="settings-card full usage-card"><header><BarChart3/><div><h3>Token 用量</h3><p>按所选时区统计；接口未返回 usage 时会进行近似估算并明确标记。</p></div><button className="icon-button" title="刷新" onClick={reloadAI}><RefreshCw size={16}/></button></header>{usage ? <><div className="usage-overview"><div><span>今日用量</span><strong>{fmt(usage.today.total_tokens)}</strong><small>{usage.today.requests} 次请求 · 输入 {fmt(usage.today.prompt_tokens)} / 输出 {fmt(usage.today.completion_tokens)}</small></div><div><span>累计用量</span><strong>{fmt(usage.total.total_tokens)}</strong><small>{usage.total.requests} 次请求{usage.total.estimated_requests ? ` · ${usage.total.estimated_requests} 次为估算` : ' · 均为接口返回'}</small></div></div><div className="usage-details"><div><h4>近 {Math.max(usage.daily.length, 1)} 个有用量的日期</h4><div className="usage-chart">{usage.daily.length ? usage.daily.map(item => <div key={item.date} title={`${item.date}: ${item.total_tokens.toLocaleString()} tokens`}><i style={{ height:`${Math.max(7, item.total_tokens / maxDaily * 100)}%` }}/><span>{item.date.slice(5)}</span></div>) : <p>产生第一条 AI 请求后，这里会显示趋势。</p>}</div></div><div><h4>按用途</h4><div className="usage-breakdown">{usage.by_purpose.length ? usage.by_purpose.map(item => <div key={item.purpose}><span>{item.label}</span><i><b style={{ width:`${usage.total.total_tokens ? item.total_tokens / usage.total.total_tokens * 100 : 0}%` }}/></i><strong>{fmt(item.total_tokens)}</strong></div>) : <p>暂无用量</p>}</div></div></div><div className="usage-profiles"><h4>按 API</h4>{usage.by_profile.length ? usage.by_profile.map(item => <span key={item.profile_id || item.name}><b>{item.name}</b>{fmt(item.total_tokens)} tokens · {item.requests} 次</span>) : <p>暂无用量记录</p>}</div></> : <div className="usage-loading"><CircleDashed className="spin"/>正在读取用量…</div>}</div>

      <div className="settings-card full"><header><Radar/><div><h3>推荐策略</h3><p>基础排序综合方向匹配、时效、出版来源和永久去重；启用模型后，还会评估创新性、研究价值与可信度。</p></div><button className={`switch ${form.llm_rerank_enabled ? 'on' : ''}`} onClick={() => setForm({ ...form, llm_rerank_enabled:!form.llm_rerank_enabled })}><i/></button></header><div className={!form.llm_rerank_enabled ? 'disabled-fields' : ''}><label>AI 综合判断权重 <strong>{Math.round(form.llm_rerank_weight * 100)}%</strong><input type="range" min="0.1" max="0.8" step="0.05" value={form.llm_rerank_weight} onChange={e => setForm({ ...form, llm_rerank_weight:Number(e.target.value) })}/></label></div><label>顶会顶刊目标比例 <strong>{Math.round(form.top_venue_ratio * 100)}%</strong><input type="range" min="0" max="1" step="0.1" value={form.top_venue_ratio} onChange={e => setForm({ ...form, top_venue_ratio:Number(e.target.value) })}/></label><label className="checkbox-row"><input type="checkbox" checked={form.only_verified_top_venues} onChange={e => setForm({ ...form, only_verified_top_venues:e.target.checked })}/>只显示已核验的高等级会议与期刊（结果数量可能减少）</label></div>
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
