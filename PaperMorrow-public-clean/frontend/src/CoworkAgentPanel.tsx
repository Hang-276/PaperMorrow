import { BrainCircuit,Check,ChevronRight,Clock3,Eye,FileSearch,Gauge,LoaderCircle,Pause,Play,ShieldCheck,Square,UserPlus,Users,X } from 'lucide-react'
import { useMemo,useState } from 'react'
import type { CoworkAgent,CoworkAgentBudget,CoworkAgentGroup,CoworkAgentStatus } from './coworkTypes'

const statusText:Record<CoworkAgentStatus,string>={idle:'待命',queued:'排队中',planning:'规划中',running:'执行中',waiting_approval:'等待审批',paused:'已暂停',completed:'已完成',failed:'失败',cancelled:'已停止'}
const roleText:Record<string,string>={literature_evidence:'文献检索与证据',experiment_analysis:'实验分析',research_synthesis:'笔记与综述',document_presentation:'PPT 与文档',project_planning:'研究规划',supervisor:'主监督 Agent'}

const ratio=(used:number,limit:number)=>limit>0?Math.min(100,Math.max(0,used/limit*100)):0
const compact=(value:number)=>value>=1000?`${(value/1000).toFixed(value>=10000?0:1)}k`:`${value}`

function BudgetBars({budget,compactMode=false}:{budget:CoworkAgentBudget;compactMode?:boolean}){
  const rows=[
    {label:'Token',used:budget.tokens_used,limit:budget.token_limit,value:`${compact(budget.tokens_used)} / ${compact(budget.token_limit)}`},
    {label:'工具',used:budget.tool_calls_used,limit:budget.tool_call_limit,value:`${budget.tool_calls_used} / ${budget.tool_call_limit}`},
  ]
  return <div className={`agent-budget ${compactMode?'compact':''}`}>{rows.map(row=><div key={row.label}><span>{row.label}</span><i aria-label={`${row.label} 已用 ${Math.round(ratio(row.used,row.limit))}%`}><b style={{width:`${ratio(row.used,row.limit)}%`}}/></i><small>{row.value}</small></div>)}</div>
}

function StatusIcon({status}:{status:CoworkAgentStatus}){
  if(status==='running'||status==='planning')return <LoaderCircle className="spin"/>
  if(status==='completed')return <Check/>
  if(status==='waiting_approval'||status==='paused')return <Pause/>
  return <span/>
}

const budgetFor=(agent:CoworkAgent):CoworkAgentBudget=>({token_limit:agent.token_budget,tokens_used:agent.tokens_used,tool_call_limit:agent.max_iterations,tool_calls_used:agent.iterations_used})
const agentSummary=(agent:CoworkAgent)=>agent.objective||agent.result?.summary||agent.error||'等待主 Agent 分配一个明确步骤'

export default function CoworkAgentPanel({group,busy,onStopAgent,onStopAll}:{group:CoworkAgentGroup|null;busy:boolean;onStopAgent:(agent:CoworkAgent)=>void;onStopAll:()=>void}){
  const [selected,setSelected]=useState<CoworkAgent|null>(null)
  const active=useMemo(()=>group?.agents.filter(agent=>['planning','running','waiting_approval'].includes(agent.status)).length||0,[group])
  const queued=useMemo(()=>group?.agents.filter(agent=>agent.status==='queued').length||0,[group])
  if(!group)return <section className="cowork-agent-panel empty"><header><Users/><strong>专家 Agent 群</strong><span>载入中</span></header><p>正在读取本会话的专家、上下文与预算状态。</p></section>
  return <section className="cowork-agent-panel">
    <header><Users/><div><strong>专家 Agent 群</strong><small>{active} 个执行 · {queued} 个排队 · 并行上限 {group.max_parallel}</small></div>{group.agents.length===0&&<button className="agent-action" disabled={busy} onClick={onStopAll}><UserPlus/>召集</button>}{queued>0&&<button className="agent-action primary" disabled={busy} onClick={onStopAll}><Play/>运行</button>}{active>0&&queued===0&&<button className="agent-stop-all" disabled={busy} onClick={onStopAll}><Square/>停止全部</button>}</header>
    <div className="agent-supervisor"><span className={`agent-state ${group.supervisor_status}`}><BrainCircuit/>{statusText[group.supervisor_status]}</span><div><strong>主 Agent 监督与验收</strong><small>分配最小资料、控制预算并汇总可追溯结果</small></div></div>
    <BudgetBars budget={{token_limit:group.budget.limit,tokens_used:group.budget.used,tool_call_limit:group.budget.delegations_limit,tool_calls_used:group.budget.delegations_used}} compactMode/>
    {!group.agents.length&&<p className="agent-empty-context">尚未委派。点击“召集”创建文献证据、研究综合和项目规划专家；它们不会自动读取未授权资料。</p>}<div className="agent-queue" aria-label="专家 Agent 队列">{group.agents.map(agent=><article key={agent.id} className={`agent-card ${agent.status}`}>
      <button className="agent-card-main" onClick={()=>setSelected(agent)} aria-label={`查看 ${agent.display_name} 详情`}><span className={`agent-status-dot ${agent.status}`}><StatusIcon status={agent.status}/></span><div><strong>{agent.display_name}</strong><small>{roleText[agent.role]||agent.role} · {statusText[agent.status]}</small><p>{agentSummary(agent)}</p></div><ChevronRight/></button>
      <footer><span><FileSearch/>{agent.context_refs.length} 项最小上下文</span><span><Gauge/>{compact(agent.tokens_used)} / {compact(agent.token_budget)}</span>{!['completed','failed','cancelled'].includes(agent.status)&&<button disabled={busy} onClick={()=>onStopAgent(agent)}><Square/>停止</button>}</footer>
    </article>)}</div>
    {selected&&<div className="agent-detail-backdrop" onMouseDown={()=>setSelected(null)}><section className="agent-detail" onMouseDown={event=>event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`${selected.display_name} 详情`}>
      <header><div><span className={`agent-status-dot ${selected.status}`}><StatusIcon status={selected.status}/></span><span><strong>{selected.display_name}</strong><small>{roleText[selected.role]||selected.role} · {statusText[selected.status]}</small></span></div><button onClick={()=>setSelected(null)} aria-label="关闭详情"><X/></button></header>
      <div className="agent-detail-summary"><Eye/><div><strong>当前职责</strong><p>{agentSummary(selected)}</p>{selected.delegation_id&&<small>可审计委派：{selected.delegation_id.slice(0,8)}</small>}</div></div>
      <section><header><FileSearch/><strong>最小上下文</strong><span>{selected.context_refs.length} 项</span></header>{selected.context_refs.length?selected.context_refs.map(item=><article key={`${item.source_id}:${item.resource_id}`}><span>{item.resource_type} · {item.evidence_scope}</span><strong>{item.label||item.resource_id}</strong>{item.excerpt&&<p>{item.excerpt}</p>}<small>来源 {item.source_id} · 仅本次委派可读</small></article>):<p className="agent-empty-context">尚未下发资料。专家不能自动读取会话外内容。</p>}</section>
      <section><header><Gauge/><strong>独立预算</strong></header><BudgetBars budget={budgetFor(selected)}/><div className="agent-time"><Clock3/><span>迭代 {selected.iterations_used} / {selected.max_iterations} · 工具仅限 {selected.allowed_tools.length} 项只读能力</span></div></section>
      <div className="agent-safety"><ShieldCheck/><span><strong>受主 Agent 约束</strong><small>不能扩展资料范围、修改原文件或绕过审批；只返回结构化结果。</small></span></div>
      {!['completed','failed','cancelled'].includes(selected.status)&&<button className="agent-detail-stop" disabled={busy} onClick={()=>{onStopAgent(selected);setSelected(null)}}><Square/>停止这个专家 Agent</button>}
    </section></div>}
  </section>
}
