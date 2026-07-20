import { useState } from 'react'
import { ArrowRight, CalendarClock, CheckCircle2, FileText, FlaskConical, FolderKanban, NotebookPen, Plus, Radar, Sparkles } from 'lucide-react'
import { api } from './api'
import type { AppSettings, Batch, PlannerTask, SubmissionDeadline } from './types'
import './planner.css'

function deadlineState(value: string) {
  const days = Math.ceil((new Date(value).getTime() - Date.now()) / 86_400_000)
  if (days < 0) return { label: '已截止', tone: 'past' }
  if (days === 0) return { label: '今天截止', tone: 'urgent' }
  if (days === 1) return { label: '明天截止', tone: 'urgent' }
  return { label: `${days} 天后`, tone: days <= 7 ? 'urgent' : days <= 30 ? 'soon' : '' }
}

export default function HomePage({ tasks, deadlines, today, settings, onNavigate, onOpenAssistant, onPlannerChanged, onStartNote }: {
  tasks:PlannerTask[]; deadlines:SubmissionDeadline[]; today:Batch[]; settings:AppSettings|null
  onNavigate:(view:'today'|'planner'|'projects'|'notes')=>void; onOpenAssistant:()=>void; onPlannerChanged:()=>Promise<void>; onStartNote:()=>void
}) {
  const [taskTitle,setTaskTitle]=useState('')
  const [busy,setBusy]=useState(false)
  const papers=today.flatMap(batch=>batch.papers)
  const upcoming=deadlines.filter(item=>new Date(item.deadline_at).getTime()>=Date.now()-86_400_000).slice(0,4)
  const addTask=async()=>{if(!taskTitle.trim())return;setBusy(true);try{await api('/api/planner/tasks',{method:'POST',body:JSON.stringify({title:taskTitle.trim(),priority:'medium'})});setTaskTitle('');await onPlannerChanged()}finally{setBusy(false)}}
  const complete=async(item:PlannerTask)=>{await api(`/api/planner/tasks/${item.id}`,{method:'PUT',body:JSON.stringify({status:'completed'})});await onPlannerChanged()}
  return <section className="home-page page-content">
    <div className="home-welcome"><div><span>RESEARCH START</span><h2>今天从哪里开始？</h2><p>把阅读、研究计划和重要截稿日期集中在一个清晰的工作台。</p></div><button onClick={onOpenAssistant}><Sparkles/>询问研究助手</button></div>
    <div className="home-quick-grid">
      <button onClick={()=>onNavigate('today')}><i><Radar/></i><span><strong>开始推荐</strong><small>按专业与研究方向发现论文</small></span><ArrowRight/></button>
      <button onClick={onStartNote}><i><NotebookPen/></i><span><strong>开始写笔记</strong><small>记录想法或引用学习库论文</small></span><ArrowRight/></button>
      <button onClick={()=>onNavigate('projects')}><i><FolderKanban/></i><span><strong>继续研究项目</strong><small>查看阅读队列、实验和结论</small></span><ArrowRight/></button>
      <button onClick={()=>onNavigate('planner')}><i><CalendarClock/></i><span><strong>管理待办与 DDL</strong><small>跟踪任务和投稿截稿日期</small></span><ArrowRight/></button>
    </div>
    <div className="home-dashboard-grid">
      <section className="home-panel home-tasks"><header><div><span>TODAY</span><h3>待办事项</h3></div><button onClick={()=>onNavigate('planner')}>查看全部</button></header>
        <div className="home-task-add"><Plus/><input value={taskTitle} onChange={event=>setTaskTitle(event.target.value)} onKeyDown={event=>{if(event.key==='Enter')addTask()}} placeholder="添加一项待办…"/><button disabled={!taskTitle.trim()||busy} onClick={addTask}>添加</button></div>
        <div className="home-task-list">{tasks.slice(0,5).map(item=><div key={item.id}><button aria-label={`完成 ${item.title}`} onClick={()=>complete(item)}><CheckCircle2/></button><span><strong>{item.title}</strong><small>{item.due_at?new Date(item.due_at).toLocaleString('zh-CN',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'未设置日期'} · {item.priority==='high'?'高优先级':item.priority==='low'?'低优先级':'普通'}</small></span></div>)}{!tasks.length&&<div className="home-empty"><CheckCircle2/><span>今天没有待处理事项</span></div>}</div>
      </section>
      <section className="home-panel home-deadlines"><header><div><span>SUBMISSION</span><h3>临近 DDL</h3></div><button onClick={()=>onNavigate('planner')}>添加截稿日期</button></header>
        <div>{upcoming.map(item=>{const state=deadlineState(item.deadline_at);return <article key={item.id}><time className={state.tone}>{state.label}</time><span><strong>{item.venue_name}</strong><small>{item.venue_type==='conference'?'会议':'期刊'}{item.round_name?` · ${item.round_name}`:''}</small></span><em>{new Date(item.deadline_at).toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}</em></article>})}{!upcoming.length&&<div className="home-empty"><CalendarClock/><span>还没有添加会议或期刊 DDL</span></div>}</div>
      </section>
      <section className="home-panel home-reading"><header><div><span>READING</span><h3>今日阅读</h3></div><button onClick={()=>onNavigate('today')}>进入推荐</button></header><div className="home-reading-stat"><i><FileText/></i><strong>{papers.length}</strong><span>篇推荐论文</span></div><p>{papers.length?'继续阅读今天筛选出的论文，完成后会自动参与后续永久去重。':'尚未生成今日推荐，可以从专业广度或自定义研究方向开始。'}</p><button className="primary" onClick={()=>onNavigate('today')}><Radar/>{papers.length?'继续阅读':'开始推荐'}</button></section>
      <section className="home-panel home-routine"><header><div><span>ROUTINE</span><h3>研究节奏</h3></div></header><div><i><FlaskConical/></i><span><strong>{settings?.daily_enabled?'每日推荐正在运行':'建立你的每日节奏'}</strong><small>{settings?.daily_enabled?`每天 ${settings.daily_time} · ${settings.daily_count} 篇`:'设置固定推荐计划，重要阅读不会遗漏。'}</small></span></div><button onClick={()=>onNavigate('today')}>{settings?.daily_enabled?'查看今日推荐':'配置推荐方向'}<ArrowRight/></button></section>
    </div>
  </section>
}
