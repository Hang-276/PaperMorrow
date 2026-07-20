export type CoworkBlock={type:string;text?:string;[key:string]:unknown}
export type CoworkMessage={id:number;role:'user'|'assistant'|'system';blocks:CoworkBlock[];sources:Array<{id?:string;title?:string;locator?:string}>;attachments:Array<{name:string;path?:string}>;created_at:string}
export type CoworkStep={id:number;position:number;title:string;description:string;status:string;retry_count:number;result_summary:string;error?:string|null}
export type CoworkTask={id:number;title:string;status:string;result_summary:string;steps:CoworkStep[]}
export type CoworkGrant={id:string;resource_type:string;resource_scope:string;normalized_path?:string|null;can_read:boolean;can_write:boolean;duration:string;granted_at:string}
export type CoworkToolCall={id:string;tool_name:string;risk_level:string;approval_status:string;status:string;arguments:Record<string,unknown>;summary:string;error?:string|null}
export type CoworkArtifact={id:string;type:string;title:string;local_path?:string|null;sources:Array<Record<string,unknown>>}
export type CoworkAgentStatus='idle'|'queued'|'planning'|'running'|'waiting_approval'|'paused'|'completed'|'failed'|'cancelled'
export type CoworkAgentContextItem={resource_type:string;resource_id:string;source_id:string;label:string;excerpt?:string;evidence_scope:string}
export type CoworkAgentBudget={token_limit:number;tokens_used:number;tool_call_limit:number;tool_calls_used:number;time_limit_seconds?:number;elapsed_seconds?:number}
export type CoworkAgent={id:string;role:string;display_name:string;status:CoworkAgentStatus;objective:string;allowed_tools:string[];context_refs:CoworkAgentContextItem[];token_budget:number;tokens_used:number;max_iterations:number;iterations_used:number;error?:string|null;parent_agent_id?:string|null;delegation_id?:string|null;result?:{summary?:string;limitations?:string[];next_actions?:string[];[key:string]:unknown};created_at?:string}
export type CoworkAgentGroup={supervisor_status:CoworkAgentStatus;max_parallel:number;budget:{limit:number;used:number;remaining:number;delegations_limit:number;delegations_used:number};agents:CoworkAgent[]}
export type CoworkSession={id:string;title:string;goal:string;status:string;response_detail:'concise'|'rich';thinking_effort:'low'|'medium'|'high';created_at:string;updated_at:string;messages:CoworkMessage[];tasks:CoworkTask[];grants:CoworkGrant[];tool_calls:CoworkToolCall[];artifacts:CoworkArtifact[];agent_group?:CoworkAgentGroup|null}
export type CoworkSessionSummary=Omit<CoworkSession,'messages'|'tasks'|'grants'|'tool_calls'|'artifacts'>
export type CoworkSkill={id:string;name:string;description:string;version:string;allowed_tools:string[];source:string;license:string;enabled:boolean}

declare global{interface Window{pywebview?:{api?:{choose_folder?:()=>Promise<string>;choose_files?:()=>Promise<string[]>}}}}
