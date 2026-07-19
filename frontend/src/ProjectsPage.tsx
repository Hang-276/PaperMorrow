import { useEffect, useMemo, useState } from 'react'
import { BookOpenCheck, ChevronRight, FlaskConical, LayoutDashboard, MessageCircle, Plus, Search, Send } from 'lucide-react'
import { api } from './api'
import type { DeepWikiJob, Paper, ResearchProject, ResearchStudy } from './types'
import './projects.css'
import ExperimentsPanel from './ExperimentsPanel'

const roleLabels:Record<string,string>={core:'核心',support:'支持',conflict:'冲突',background:'背景',to_verify:'待验证'}
const statusLabels:Record<string,string>={to_screen:'待筛选',to_read:'待读',reading:'阅读中',read_to_organize:'已读待整理',completed:'已完成',shelved:'暂时搁置'}

export default function ProjectsPage(){
  const [projects,setProjects]=useState<ResearchProject[]>([])
  const [active,setActive]=useState<ResearchProject|null>(null)
  const [library,setLibrary]=useState<Paper[]>([])
  const [studies,setStudies]=useState<ResearchStudy[]>([])
  const [jobs,setJobs]=useState<DeepWikiJob[]>([])
  const [creating,setCreating]=useState(false)
  const [projectTab,setProjectTab]=useState<'overview'|'experiments'>('overview')
  const [title,setTitle]=useState(''),[question,setQuestion]=useState('')
  const [chat,setChat]=useState(''),[answer,setAnswer]=useState<any|null>(null)
  const [noteTitle,setNoteTitle]=useState('项目笔记'),[noteContent,setNoteContent]=useState('')
  const load=async()=>{const list=await api<ResearchProject[]>('/api/projects');setProjects(list);if(active)setActive(await api(`/api/projects/${active.id}`))}
  useEffect(()=>{load();api<Paper[]>('/api/library/papers').then(setLibrary);api<ResearchStudy[]>('/api/research/studies').then(setStudies);api<DeepWikiJob[]>('/api/deepwiki/jobs').then(setJobs)},[])
  const available=useMemo(()=>library.filter(p=>!active?.papers?.some(link=>link.paper_id===p.id)),[library,active])
  const create=async()=>{const item=await api<ResearchProject>('/api/projects',{method:'POST',body:JSON.stringify({title,research_question:question})});setCreating(false);setTitle('');setQuestion('');setActive(item);await load()}
  const saveFields=async(values:any)=>setActive(await api(`/api/projects/${active!.id}`,{method:'PUT',body:JSON.stringify(values)}))
  const addPaper=async(paperId:number)=>setActive(await api(`/api/projects/${active!.id}/papers`,{method:'POST',body:JSON.stringify({paper_id:paperId,role:'to_verify',reading_status:'to_screen'})}))
  const updatePaper=async(paperId:number,values:any)=>setActive(await api(`/api/projects/${active!.id}/papers/${paperId}`,{method:'PUT',body:JSON.stringify(values)}))
  const addNote=async()=>{await api(`/api/projects/${active!.id}/notes`,{method:'POST',body:JSON.stringify({title:noteTitle,content:noteContent})});setNoteContent('');setActive(await api(`/api/projects/${active!.id}`))}
  const linkStudy=async(studyId:number)=>{if(studyId)setActive(await api(`/api/projects/${active!.id}/studies/${studyId}`,{method:'POST'}))}
  const ask=async()=>{const result=await api(`/api/projects/${active!.id}/chat`,{method:'POST',body:JSON.stringify({message:chat})});setAnswer(result);setChat('')}
  if(active)return <section className="page-content project-page">
    <button className="project-back" onClick={()=>{setActive(null);load()}}>← 所有项目</button>
    <header className="project-hero"><div><span className="section-kicker">RESEARCH PROJECT</span><h2>{active.title}</h2><p>{active.research_question||'尚未填写研究问题'}</p></div><div><strong>{active.papers?.length||0}</strong><span>项目论文</span></div></header>
    <nav className="project-tabs"><button className={projectTab==='overview'?'active':''} onClick={()=>setProjectTab('overview')}><LayoutDashboard/>项目总览</button><button className={projectTab==='experiments'?'active':''} onClick={()=>setProjectTab('experiments')}><FlaskConical/>实验记录</button></nav>
    {projectTab==='experiments'?<ExperimentsPanel projectId={active.id}/>:<div className="project-columns"><main>
      <section className="project-panel"><h3>阅读队列</h3>{active.papers?.length?<div className="project-papers">{active.papers.map(link=><article key={link.paper_id}><div><span>{roleLabels[link.role]}</span><strong>{link.title_zh||link.title}</strong><small>{link.title}</small></div><select value={link.role} onChange={e=>updatePaper(link.paper_id,{role:e.target.value})}>{Object.entries(roleLabels).map(([v,l])=><option value={v} key={v}>{l}</option>)}</select><select value={link.reading_status} onChange={e=>updatePaper(link.paper_id,{reading_status:e.target.value})}>{Object.entries(statusLabels).map(([v,l])=><option value={v} key={v}>{l}</option>)}</select></article>)}</div>:<p className="project-muted">从学习库加入核心论文，建立阅读队列。</p>}</section>
      <section className="project-panel"><h3>从学习库加入</h3><div className="project-add-list">{available.slice(0,8).map(p=><button key={p.id} onClick={()=>addPaper(p.id)}><Plus/><span>{p.title_zh||p.title_en}</span></button>)}</div></section>
      <section className="project-panel"><h3>项目笔记</h3>{active.notes?.map(note=><article className="project-note" key={note.id}><strong>{note.title}</strong><p>{note.content}</p></article>)}<div className="project-note-compose"><input value={noteTitle} onChange={e=>setNoteTitle(e.target.value)} placeholder="笔记标题"/><textarea value={noteContent} onChange={e=>setNoteContent(e.target.value)} placeholder="记录仅属于当前项目的判断、计划或问题"/><button disabled={!noteContent.trim()} onClick={addNote}>保存项目笔记</button></div></section>
    </main><aside>
      <section className="project-panel project-chat"><h3><MessageCircle/>项目级 AI 对话</h3><p>只检索本项目的论文、笔记、专题调研和 Wiki，结果标注来源。</p><div className="project-chat-input"><input value={chat} onChange={e=>setChat(e.target.value)} placeholder="询问当前项目的证据…"/><button disabled={!chat.trim()} onClick={ask}><Send/></button></div>{answer&&<div className="project-answer"><p>{answer.answer}</p><div>{answer.sources.map((s:any,i:number)=><span key={i}>{s.source_label} · {s.title}</span>)}</div></div>}</section>
      <section className="project-panel"><h3>研究状态</h3><label>研究方向<textarea value={active.research_direction} onChange={e=>setActive({...active,research_direction:e.target.value})} onBlur={()=>saveFields({research_direction:active.research_direction})}/></label><label>当前结论<textarea value={active.current_conclusion} onChange={e=>setActive({...active,current_conclusion:e.target.value})} onBlur={()=>saveFields({current_conclusion:active.current_conclusion})}/></label><label>待解决问题（每行一项）<textarea value={active.unresolved_questions.join('\n')} onChange={e=>setActive({...active,unresolved_questions:e.target.value.split('\n').filter(Boolean)})} onBlur={()=>saveFields({unresolved_questions:active.unresolved_questions})}/></label><label>下一篇阅读建议<textarea value={active.next_reading_suggestion} onChange={e=>setActive({...active,next_reading_suggestion:e.target.value})} onBlur={()=>saveFields({next_reading_suggestion:active.next_reading_suggestion})}/></label></section>
      <section className="project-panel"><h3>关联资产</h3><label>代码仓库<input value={active.repository_url||''} onChange={e=>setActive({...active,repository_url:e.target.value})} onBlur={()=>saveFields({repository_url:active.repository_url||null})}/></label><label>DeepWiki<select value={active.deepwiki_job_id||''} onChange={e=>saveFields({deepwiki_job_id:Number(e.target.value)||null})}><option value="">未关联</option>{jobs.map(job=><option value={job.id} key={job.id}>{job.paper_title||job.repository_url}</option>)}</select></label><label>专题调研<select value="" onChange={e=>linkStudy(Number(e.target.value))}><option value="">选择要关联的调研</option>{studies.filter(s=>!active.study_ids?.includes(s.id)).map(study=><option value={study.id} key={study.id}>{study.title}</option>)}</select></label>{active.study_ids?.length?<small>已关联 {active.study_ids.length} 项专题调研</small>:null}</section>
    </aside></div>}
  </section>
  return <section className="page-content project-page"><header className="project-list-head"><div><span className="section-kicker">PROJECT WORKSPACE</span><h2>研究项目</h2><p>把研究问题、论文角色、阅读队列、笔记、专题调研和 DeepWiki 汇集到一个可追溯工作流。</p></div><button className="primary" onClick={()=>setCreating(true)}><Plus/>新建项目</button></header>{creating&&<div className="project-create"><input value={title} onChange={e=>setTitle(e.target.value)} placeholder="项目名称"/><textarea value={question} onChange={e=>setQuestion(e.target.value)} placeholder="研究问题"/><button disabled={!title.trim()} onClick={create}>创建</button></div>}<div className="project-list">{projects.map(p=><button key={p.id} onClick={()=>api<ResearchProject>(`/api/projects/${p.id}`).then(setActive)}><BookOpenCheck/><div><strong>{p.title}</strong><span>{p.research_question||'等待定义研究问题'}</span></div><ChevronRight/></button>)}</div>{!projects.length&&!creating&&<div className="project-empty"><Search/><h3>从一个明确问题开始</h3><p>创建项目后，再从现有学习库加入论文。</p></div>}</section>
}
