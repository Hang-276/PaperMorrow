export type Tag = {
  id: number
  slug: string
  name_zh: string
  name_en: string
  query: string
  domain: string
}

export type LibraryTag = {
  id: number
  name: string
  color: string
  created_at: string
}

export type LibraryFolder = {
  id: number
  name: string
  parent_id?: number | null
  relative_path: string
  paper_count: number
  file_count: number
}

export type LocalPaperFile = {
  id: number
  file_name: string
  relative_path: string
  folder_id: number
  size_bytes: number
  page_count: number
  status: string
  pdf_url: string
}

export type LibrarySearchResult = {
  identity: string
  paper_id?: number | null
  title: string
  abstract: string
  authors: string[]
  published_at?: string | null
  updated_at?: string | null
  arxiv_id?: string | null
  doi?: string | null
  semantic_scholar_id?: string | null
  primary_url: string
  pdf_url?: string | null
  venue?: string | null
  source: 'local' | 'arxiv' | 'semantic_scholar'
  in_library: boolean
}

export type Summary = {
  one_sentence?: string
  one_sentence_zh?: string
  one_sentence_en?: string
  research_problem?: string
  research_problem_zh?: string
  research_problem_en?: string
  method?: string
  method_zh?: string
  method_en?: string
  innovations?: string[]
  innovations_zh?: string[]
  innovations_en?: string[]
  value?: string[]
  value_zh?: string[]
  value_en?: string[]
  evidence?: string
  evidence_zh?: string
  evidence_en?: string
  limitations?: string[]
  limitations_zh?: string[]
  limitations_en?: string[]
  recommended_for?: string[]
  recommended_for_zh?: string[]
  recommended_for_en?: string[]
}

export type Paper = {
  id: number
  title_en: string
  title_zh?: string | null
  abstract_en: string
  abstract_zh?: string | null
  authors: string[]
  published_at?: string | null
  venue_name?: string | null
  venue_tier: string
  publication_status: string
  arxiv_id?: string | null
  doi?: string | null
  primary_url: string
  pdf_url?: string | null
  summary?: Summary | null
  analysis_scope?: 'abstract'|'full_text'|'author_statement'|null
  analysis_evidence?: {id:number;field_name:string;claim:string;page_number?:number|null;section?:string|null;evidence_excerpt:string;source_scope:string;conclusion_type:string}[]
  work_version?: {work_id:number;version_label:string;confidence:number;confirmed:boolean}|null
  ai_status: string
  repository_url?: string | null
  repository_status: string
  tags: Tag[]
  in_library: boolean
  library_added_at?: string | null
  library_tags: LibraryTag[]
  library_folders: Pick<LibraryFolder,'id'|'name'|'relative_path'>[]
  local_files: LocalPaperFile[]
  zotero?: {
    library_type: 'user'|'group'
    library_id: string
    item_key: string
    item_version: number
    item_url?: string | null
    sync_status: string
    error?: string | null
    synced_at?: string | null
  } | null
  learned: boolean
  completed_at?: string | null
  note: string
  score: number
  recommended_at?: string | null
  recommendation_assessment?: {
    taste_score: number
    novelty_score: number
    value_score: number
    confidence: number
    reason: string
    caution?: string | null
    model?: string | null
  } | null
  direction_match?: {
    relevance_score: number
    confidence: number
    matched_concepts: string[]
    reason: string
    lane: 'focused' | 'adjacent' | 'explore' | 'broad'
  } | null
}

export type Batch = {
  id: number
  requested_count: number
  delivered_count: number
  status: string
  message?: string
  created_at: string
  papers: Paper[]
  mode?: 'broad' | 'focus' | 'mixed'
  profile?: { id: number; name: string; description?: string } | null
}

export type ResearchProfile = {
  id: number
  name: string
  domain: string
  domain_pack_id?: number | null
  domain_pack?: Pick<DomainPack,'id'|'slug'|'name_zh'|'name_en'> | null
  description: string
  positive_keywords: string[]
  negative_keywords: string[]
  seed_papers: string[]
  relevance_weight: number
  recency_weight: number
  exploration_ratio: number
  enabled: boolean
  created_at: string
  updated_at: string
}

export type DomainPack = {
  id:number; slug:string; name_zh:string; name_en:string; description:string; is_builtin:boolean; version:number; enabled:boolean
  source_adapters:{adapter:string;enabled?:boolean;[key:string]:unknown}[]; search_templates:string[]; keywords:string[]; exclusions:string[]; category_codes:string[]
  venue_rules:any[]; paper_types:string[]; scoring_weights:Record<string,number>; evidence_rules:Record<string,any>; analysis_prompt:string; review_prompt:string
  citation_config:Record<string,any>; impact_config:Record<string,any>; metrics:{id?:number;name:string;value:number;year:number;source_url:string}[]; created_at:string; updated_at:string
}

export type ResearchProject = {
  id:number; title:string; research_question:string; research_direction:string; domain_pack_id?:number|null; research_profile_id?:number|null
  repository_url?:string|null; deepwiki_job_id?:number|null; current_conclusion:string; unresolved_questions:string[]; next_reading_suggestion:string
  created_at:string; updated_at:string; study_ids?:number[]; notes?:{id:number;title:string;content:string;updated_at:string}[]
  papers?:{link_id:number;paper_id:number;title:string;title_zh?:string|null;role:'core'|'support'|'conflict'|'background'|'to_verify';reading_status:'to_screen'|'to_read'|'reading'|'read_to_organize'|'completed'|'shelved';queue_order:number;venue?:string|null}[]
}

export type DeepWikiJob = {
  id: number
  paper_id: number
  paper_title?: string
  repository_url: string
  status: string
  progress: number
  message: string
  error?: string | null
  wiki_available: boolean
  wiki_mode?: 'full' | 'legacy' | null
  needs_regeneration?: boolean
  created_at: string
}

export type AppSettings = {
  default_abstract_language: 'zh' | 'en'
  font_size: number
  daily_enabled: boolean
  daily_time: string
  timezone: string
  daily_count: number
  daily_tag_ids: number[]
  daily_profile_ids: number[]
  daily_profile_mode: 'focus'|'mixed'
  top_venue_ratio: number
  only_verified_top_venues: boolean
  llm_provider: 'openai' | 'claude' | 'glm' | 'deepseek' | 'zhizengzeng'
  llm_model: string
  llm_base_url: string
  has_llm_api_key: boolean
  has_github_token: boolean
  timezone_options: { value: string; label: string }[]
  llm_rerank_enabled: boolean
  zotero_library_type: 'user'|'group'
  zotero_library_id: string
  zotero_collection_key: string
  zotero_sync_tags: boolean
  has_zotero_api_key: boolean
  llm_rerank_weight: number
  active_llm_profile?: LLMProfile | null
  library_root: string
}

export type ResearchStudyPaper = {
  rank: number
  final_score: number
  relevance_score: number
  value_score: number
  novelty_score: number
  confidence: number
  matched_concepts: string[]
  reason: string
  caution?: string | null
  paper: {
    id: number
    title_en: string
    abstract_en: string
    authors: string[]
    published_at?: string | null
    venue_name?: string | null
    venue_tier: string
    arxiv_id?: string | null
    doi?: string | null
    primary_url: string
    pdf_url?: string | null
    in_library: boolean
  }
}

export type ResearchStudy = {
  id: number
  domain: string
  prompt: string
  title: string
  status: string
  search_terms: string[]
  core_concepts: string[]
  review_markdown?: string | null
  model?: string | null
  error?: string | null
  paper_count: number
  papers?: ResearchStudyPaper[]
  artifacts?: {taxonomy:any[];comparison:any[];research_routes:any[];representative_works:any[];controversies:any[];gaps:any[];cited_review_markdown:string;generated_at:string}|null
  created_at: string
  updated_at: string
}

export type KnowledgeGraphData = {
  nodes: { id:string; type:string; label:string; paper_id?:number; color?:string; metadata?:Record<string,any> }[]
  edges: { source:string; target:string; type:string; evidence?:string;confidence?:number;confirmed?:boolean;source_type?:string;source_id?:string }[]
}

export type LLMProfile = {
  id: string
  name: string
  provider: 'openai' | 'claude' | 'glm' | 'deepseek' | 'custom'
  base_url: string
  model: string
  is_active: boolean
  has_api_key: boolean
  created_at?: string | null
}

export type UsageTotals = {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  requests: number
  estimated_requests: number
}

export type TokenUsageStats = {
  timezone: string
  today: UsageTotals
  total: UsageTotals
  daily: ({ date: string } & UsageTotals)[]
  by_profile: ({ profile_id?: string | null; name: string } & UsageTotals)[]
  by_purpose: ({ purpose: string; label: string } & UsageTotals)[]
}

export type ChatMessage = {
  id?: number
  role: 'user' | 'assistant'
  content: string
  created_at?: string
}

export type ChatSession = {
  id: string
  paper_id: number
  title: string
  created_at: string
  updated_at?: string
}

export type NoteFormat = 'markdown' | 'latex'
export type NoteEditorMode = 'standard' | 'professional'

export type UnifiedNote = {
  id: number
  title: string
  content: string
  document_format: NoteFormat
  editor_mode: NoteEditorMode
  origin: 'standalone' | 'reader'
  paper_ids: number[]
  papers?: { id: number; title: string; title_zh?: string | null }[]
  project_id?: number | null
  created_at: string
  updated_at: string
}

export type NoteArtifact = {
  type: 'flowchart' | 'mindmap' | 'presentation'
  status: string
  content?: string | null
  download_url?: string | null
  message?: string | null
  error?: string | null
}
