import { useEffect, useState } from 'react'
import { BookOpen, Check, ChevronDown, ChevronUp, ExternalLink, FilePlus2, FlaskConical, History, RefreshCw, Search, Sparkles } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from './api'
import type { Paper, ResearchStudy } from './types'
import './research.css'

const domainLabels={ai:'人工智能',computer:'计算机',physics:'物理',math:'数学'} as const

export default function ResearchPage({onDataChanged}:{onDataChanged:()=>Promise<void>}){
  const [domain,setDomain]=useState<keyof typeof domainLabels>('ai')
  const [prompt,setPrompt]=useState('')
  const [count,setCount]=useState(12)
  const [studies,setStudies]=useState<ResearchStudy[]>([])
  const [active,setActive]=useState<ResearchStudy|null>(null)
  const [running,setRunning]=useState(false)
  const [reviewing,setReviewing]=useState(false)
  const [expandedPaper,setExpandedPaper]=useState<number|null>(null)
  const [analyzingPaper,setAnalyzingPaper]=useState<number|null>(null)
  const [paperDetails,setPaperDetails]=useState<Record<number,Paper>>({})
  const [detailLanguages,setDetailLanguages]=useState<Record<number,'zh'|'en'>>({})
  const [message,setMessage]=useState('')

  const loadHistory=async()=>setStudies(await api<ResearchStudy[]>('/api/research/studies'))
  useEffect(()=>{loadHistory().catch(error=>setMessage(error.message))},[])

  const run=async()=>{
    if(prompt.trim().length<8)return
    setRunning(true);setMessage('LLM 正在扩展检索语义，并从 arXiv 与 Semantic Scholar 汇总候选文献…')
    try{
      const result=await api<ResearchStudy>('/api/research/studies',{method:'POST',body:JSON.stringify({domain,prompt,count})})
      setActive(result);setStudies(rows=>[result,...rows.filter(row=>row.id!==result.id)]);setMessage(`调研完成，筛选出 ${result.paper_count} 篇文献`)
    }catch(error){setMessage(error instanceof Error?error.message:'调研失败')}
    finally{setRunning(false)}
  }
  const openStudy=async(id:number)=>{try{setActive(await api<ResearchStudy>(`/api/research/studies/${id}`))}catch(error){setMessage(error instanceof Error?error.message:'读取失败')}}
  const review=async()=>{if(!active)return;setReviewing(true);setMessage('正在基于已排序文献生成带引用的中文综述…');try{const updated=await api<ResearchStudy>(`/api/research/studies/${active.id}/review`,{method:'POST'});setActive(updated);setStudies(rows=>rows.map(row=>row.id===updated.id?updated:row));setMessage('综述已生成并保存')}catch(error){setMessage(error instanceof Error?error.message:'综述生成失败')}finally{setReviewing(false)}}
  const addPaper=async(paperId:number)=>{try{await api(`/api/library/papers/${paperId}`,{method:'POST'});setActive(current=>current?{...current,papers:current.papers?.map(item=>item.paper.id===paperId?{...item,paper:{...item.paper,in_library:true}}:item)}:current);await onDataChanged();setMessage('已加入学习库，后续推荐会自动排除')}catch(error){setMessage(error instanceof Error?error.message:'加入失败')}}
  const togglePaperDetail=async(paperId:number)=>{
    if(expandedPaper===paperId){setExpandedPaper(null);return}
    setExpandedPaper(paperId)
    if(paperDetails[paperId])return
    setAnalyzingPaper(paperId);setMessage('正在读取论文详情；缺少完整分析时会调用当前模型生成…')
    try{
      let detail=await api<Paper>(`/api/papers/${paperId}`)
      if(!detail.summary||!detail.abstract_zh)detail=await api<Paper>(`/api/papers/${paperId}/ai/retry`,{method:'POST'})
      setPaperDetails(current=>({...current,[paperId]:detail}));setMessage('AI 论文详情已准备完成')
    }catch(error){setMessage(error instanceof Error?error.message:'论文详情生成失败')}
    finally{setAnalyzingPaper(null)}
  }

  return <section className="page-content research-page">
    <div className="list-toolbar"><div><span className="section-kicker">LLM RESEARCH DESK</span><h2>专题调研</h2><p>输入真正想研究的问题，由 LLM 规划检索词、聚合学术来源并综合评估关联度与研究价值。</p></div></div>
    {message&&<div className="research-message">{running||reviewing?<RefreshCw className="spin"/>:<Sparkles/>}{message}</div>}
    <div className="research-compose">
      <div className="research-compose-head"><FlaskConical/><div><strong>创建一项调研</strong><span>结果会计入已发现论文，避免之后重复推荐。</span></div></div>
      <div className="research-fields"><label>领域<select value={domain} onChange={event=>setDomain(event.target.value as keyof typeof domainLabels)}>{Object.entries(domainLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><label>返回篇数<select value={count} onChange={event=>setCount(Number(event.target.value))}>{[8,12,16,20,30].map(value=><option key={value} value={value}>{value} 篇</option>)}</select></label></div>
      <textarea value={prompt} onChange={event=>setPrompt(event.target.value)} placeholder="例如：调研 LLM 自进化中不依赖人工反馈的闭环训练方法，重点关注可验证奖励、经验积累、失败模式和 2025–2026 年的新工作。"/>
      <button className="primary" disabled={running||prompt.trim().length<8} onClick={run}>{running?<RefreshCw className="spin"/>:<Search/>}{running?'正在调研…':'开始 LLM 调研'}</button>
    </div>

    <div className="research-workspace">
      <aside className="research-history"><header><History/><strong>调研记录</strong></header>{studies.length?studies.map(study=><button key={study.id} className={active?.id===study.id?'active':''} onClick={()=>openStudy(study.id)}><span>{domainLabels[study.domain]}</span><strong>{study.title}</strong><small>{study.paper_count} 篇 · {new Date(study.created_at).toLocaleDateString('zh-CN')}</small></button>):<p>还没有历史调研。</p>}</aside>
      <main className="research-result">
        {!active?<div className="research-empty"><FlaskConical/><h3>从一个具体研究问题开始</h3><p>描述越具体，检索词扩展和价值排序越准确。</p></div>:<>
          <header className="research-result-head"><div><span>{domainLabels[active.domain]} · {active.model||'当前模型'}</span><h2>{active.prompt}</h2><div className="research-concepts">{active.core_concepts.map(item=><i key={item}>{item}</i>)}</div></div><button className="primary" disabled={reviewing||!active.papers?.length} onClick={review}>{reviewing?<RefreshCw className="spin"/>:<BookOpen/>}{active.review_markdown?'重新生成综述':'一键生成综述'}</button></header>
          {active.search_terms.length>0&&<details className="research-queries"><summary>查看 LLM 使用的检索语义</summary><div>{active.search_terms.map(item=><code key={item}>{item}</code>)}</div></details>}
          {active.review_markdown&&<article className="research-review"><div className="review-title"><BookOpen/><strong>自动文献综述</strong><span>仅根据当前文献元数据与摘要生成</span></div><ReactMarkdown remarkPlugins={[remarkGfm]}>{active.review_markdown}</ReactMarkdown></article>}
          <div className="research-paper-list">{active.papers?.map(item=>{const expanded=expandedPaper===item.paper.id;const detail=paperDetails[item.paper.id];const language=detailLanguages[item.paper.id]||'zh';const abstract=detail&&(language==='zh'?detail.abstract_zh:detail.abstract_en);return <article className={expanded?'expanded':''} key={item.paper.id}><div className="research-rank">#{item.rank}<strong>{Math.round(item.final_score)}</strong><small>综合分</small></div><div className="research-paper-copy"><span>{item.paper.venue_name||'预印本'} · {item.paper.published_at?new Date(item.paper.published_at).getFullYear():'年份未知'}</span><h3>{item.paper.title_en}</h3><p>{item.reason}</p>{item.caution&&<small>注意：{item.caution}</small>}<div className="score-row"><Score label="关联" value={item.relevance_score}/><Score label="价值" value={item.value_score}/><Score label="创新" value={item.novelty_score}/><Score label="置信" value={item.confidence}/></div></div><div className="research-paper-actions"><button className="secondary detail-button" disabled={analyzingPaper===item.paper.id} onClick={()=>togglePaperDetail(item.paper.id)}>{analyzingPaper===item.paper.id?<RefreshCw className="spin"/>:expanded?<ChevronUp/>:<ChevronDown/>}{expanded?'收起 AI 详情':'展开 AI 详情'}</button><button className={item.paper.in_library?'secondary done':'secondary'} disabled={item.paper.in_library} onClick={()=>addPaper(item.paper.id)}>{item.paper.in_library?<Check/>:<FilePlus2/>}{item.paper.in_library?'已收录':'加入学习库'}</button><a href={item.paper.primary_url} target="_blank" rel="noreferrer"><ExternalLink/>论文页面</a></div>{expanded&&<div className="research-paper-detail">{detail?<><header><div><span>AI PAPER ANALYSIS</span><strong>{detail.title_zh||detail.title_en}</strong></div><div className="language-toggle"><button className={language==='zh'?'active':''} onClick={()=>setDetailLanguages(current=>({...current,[item.paper.id]:'zh'}))}>中文</button><button className={language==='en'?'active':''} onClick={()=>setDetailLanguages(current=>({...current,[item.paper.id]:'en'}))}>English</button></div></header><div className="research-detail-abstract">{abstract||(language==='zh'?'暂无中文摘要，可切换英文查看。':'No abstract available.')}</div>{detail.summary?<div className="research-insight-grid"><ResearchInsight title="研究问题" text={detail.summary.research_problem}/><ResearchInsight title="核心方法" text={detail.summary.method}/><ResearchInsight title="主要创新" list={detail.summary.innovations}/><ResearchInsight title="研究价值" list={detail.summary.value}/><ResearchInsight title="局限与风险" list={detail.summary.limitations}/><ResearchInsight title="适合谁阅读" list={detail.summary.recommended_for}/></div>:<div className="research-detail-pending"><Sparkles/>当前模型尚未返回结构化分析。</div>}</>:<div className="research-detail-pending"><RefreshCw className="spin"/>正在生成中文摘要、方法、创新点、价值与局限…</div>}</div>}</article>})}</div>
        </>}
      </main>
    </div>
  </section>
}

function Score({label,value}:{label:string;value:number}){return <div><span>{label}</span><i><b style={{width:`${Math.max(2,Math.min(100,value))}%`}}/></i><strong>{Math.round(value)}</strong></div>}
function ResearchInsight({title,text,list}:{title:string;text?:string;list?:string[]}){if(!text&&!list?.length)return null;return <section><span>{title}</span>{text&&<p>{text}</p>}{list&&<ul>{list.map((item,index)=><li key={index}>{item}</li>)}</ul>}</section>}
