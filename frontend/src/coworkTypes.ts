export type CoworkBlock={type:string;text?:string;[key:string]:unknown}
export type CoworkMessage={id:number;role:'user'|'assistant'|'system';blocks:CoworkBlock[];sources:Array<{id?:string;title?:string;locator?:string}>;attachments:Array<{name:string;path?:string}>;created_at:string}
export type CoworkStep={id:number;position:number;title:string;description:string;status:string;retry_count:number;result_summary:string;error?:string|null}
export type CoworkTask={id:number;title:string;status:string;result_summary:string;steps:CoworkStep[]}
export type CoworkGrant={id:string;resource_type:string;resource_scope:string;normalized_path?:string|null;can_read:boolean;can_write:boolean;duration:string;granted_at:string}
export type CoworkToolCall={id:string;tool_name:string;risk_level:string;approval_status:string;status:string;arguments:Record<string,unknown>;summary:string;error?:string|null}
export type CoworkArtifact={id:string;type:string;title:string;local_path?:string|null;sources:Array<Record<string,unknown>>}
export type CoworkSession={id:string;title:string;goal:string;status:string;response_detail:'concise'|'rich';thinking_effort:'low'|'medium'|'high';created_at:string;updated_at:string;messages:CoworkMessage[];tasks:CoworkTask[];grants:CoworkGrant[];tool_calls:CoworkToolCall[];artifacts:CoworkArtifact[]}
export type CoworkSessionSummary=Omit<CoworkSession,'messages'|'tasks'|'grants'|'tool_calls'|'artifacts'>
export type CoworkSkill={id:string;name:string;description:string;version:string;allowed_tools:string[];source:string;license:string;enabled:boolean}

declare global{interface Window{pywebview?:{api?:{choose_folder?:()=>Promise<string>;choose_files?:()=>Promise<string[]>}}}}
