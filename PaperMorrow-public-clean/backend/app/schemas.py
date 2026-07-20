from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, HttpUrl, field_validator


class GenerateRequest(BaseModel):
    tag_ids: list[int] = Field(default_factory=list)
    count: int = Field(default=5, ge=1, le=30)
    triggered_by: Literal["manual", "schedule", "startup"] = "manual"
    profile_id: int | None = None
    mode: Literal["broad", "focus", "mixed"] = "broad"


class StudyStateRequest(BaseModel):
    learned: bool


class NoteRequest(BaseModel):
    content: str = Field(max_length=500_000)


class LibraryTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#0a84ff", pattern=r"^#[0-9a-fA-F]{6}$")


class LibraryTagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class LibraryPaperTagsRequest(BaseModel):
    tag_ids: list[int] = Field(default_factory=list, max_length=100)


class LibraryFolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    parent_id: int | None = None


class LibraryPaperFoldersRequest(BaseModel):
    folder_ids: list[int] = Field(default_factory=list, max_length=100)


class LibraryScanRequest(BaseModel):
    root_path: str | None = Field(default=None, max_length=4000)


class ResearchStudyCreate(BaseModel):
    domain: str = Field(default="ai", pattern=r"^[a-z0-9-]{1,80}$")
    prompt: str = Field(min_length=8, max_length=20_000)
    count: int = Field(default=12, ge=3, le=30)


class LibraryImportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=5000)
    abstract: str = Field(default="", max_length=100_000)
    authors: list[str] = Field(default_factory=list, max_length=500)
    published_at: datetime | None = None
    updated_at: datetime | None = None
    arxiv_id: str | None = Field(default=None, max_length=64)
    doi: str | None = Field(default=None, max_length=255)
    semantic_scholar_id: str | None = Field(default=None, max_length=64)
    primary_url: HttpUrl
    pdf_url: HttpUrl | None = None
    venue: str | None = Field(default=None, max_length=1000)
    source: Literal["arxiv", "semantic_scholar", "local"] = "arxiv"


class ResearchProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    domain: str = Field(default="ai", pattern=r"^[a-z0-9-]{1,80}$")
    domain_pack_id: int | None = None
    description: str = Field(min_length=8, max_length=10_000)
    positive_keywords: list[str] = Field(default_factory=list, max_length=80)
    negative_keywords: list[str] = Field(default_factory=list, max_length=80)
    seed_papers: list[str] = Field(default_factory=list, max_length=20)
    relevance_weight: float = Field(default=0.55, ge=0.1, le=0.85)
    recency_weight: float = Field(default=0.25, ge=0.05, le=0.7)
    exploration_ratio: float = Field(default=0.2, ge=0, le=0.6)

    @field_validator("recency_weight")
    @classmethod
    def validate_weights(cls, value: float, info) -> float:
        relevance = info.data.get("relevance_weight", 0.55)
        if relevance + value > 0.95:
            raise ValueError("关联度与发布时间权重之和不能超过 95%")
        return value


class ResearchProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    domain: str | None = Field(default=None, pattern=r"^[a-z0-9-]{1,80}$")
    domain_pack_id: int | None = None
    description: str | None = Field(default=None, min_length=8, max_length=10_000)
    positive_keywords: list[str] | None = Field(default=None, max_length=80)
    negative_keywords: list[str] | None = Field(default=None, max_length=80)
    seed_papers: list[str] | None = Field(default=None, max_length=20)
    relevance_weight: float | None = Field(default=None, ge=0.1, le=0.85)
    recency_weight: float | None = Field(default=None, ge=0.05, le=0.7)
    exploration_ratio: float | None = Field(default=None, ge=0, le=0.6)
    enabled: bool | None = None


class DomainMetricInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    value: float
    year: int = Field(ge=1900, le=2200)
    source_url: HttpUrl


class DomainPackCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    name_zh: str = Field(min_length=1, max_length=160)
    name_en: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=20_000)
    enabled: bool = True
    source_adapters: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    search_templates: list[str] = Field(default_factory=list, max_length=30)
    keywords: list[str] = Field(default_factory=list, max_length=200)
    exclusions: list[str] = Field(default_factory=list, max_length=200)
    category_codes: list[str] = Field(default_factory=list, max_length=200)
    venue_rules: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    paper_types: list[str] = Field(default_factory=list, max_length=100)
    scoring_weights: dict[str, float] = Field(default_factory=dict)
    evidence_rules: dict[str, Any] = Field(default_factory=dict)
    analysis_prompt: str = Field(default="", max_length=50_000)
    review_prompt: str = Field(default="", max_length=50_000)
    citation_config: dict[str, Any] = Field(default_factory=dict)
    impact_config: dict[str, Any] = Field(default_factory=dict)
    metrics: list[DomainMetricInput] = Field(default_factory=list, max_length=100)


class DomainPackUpdate(BaseModel):
    name_zh: str | None = Field(default=None, min_length=1, max_length=160)
    name_en: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=20_000)
    enabled: bool | None = None
    source_adapters: list[dict[str, Any]] | None = Field(default=None, max_length=20)
    search_templates: list[str] | None = Field(default=None, max_length=30)
    keywords: list[str] | None = Field(default=None, max_length=200)
    exclusions: list[str] | None = Field(default=None, max_length=200)
    category_codes: list[str] | None = Field(default=None, max_length=200)
    venue_rules: list[dict[str, Any]] | None = Field(default=None, max_length=500)
    paper_types: list[str] | None = Field(default=None, max_length=100)
    scoring_weights: dict[str, float] | None = None
    evidence_rules: dict[str, Any] | None = None
    analysis_prompt: str | None = Field(default=None, max_length=50_000)
    review_prompt: str | None = Field(default=None, max_length=50_000)
    citation_config: dict[str, Any] | None = None
    impact_config: dict[str, Any] | None = None
    metrics: list[DomainMetricInput] | None = Field(default=None, max_length=100)


class DomainSourceTestRequest(BaseModel):
    config: dict[str, Any]


class DomainSearchPreviewRequest(BaseModel):
    query: str = Field(default="", max_length=5000)


class ResearchProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    research_question: str = Field(default="", max_length=20_000)
    research_direction: str = Field(default="", max_length=10_000)
    domain_pack_id: int | None = None
    research_profile_id: int | None = None
    repository_url: str | None = Field(default=None, max_length=4000)
    deepwiki_job_id: int | None = None
    current_conclusion: str = Field(default="", max_length=50_000)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=200)
    next_reading_suggestion: str = Field(default="", max_length=20_000)


class ResearchProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    research_question: str | None = Field(default=None, max_length=20_000)
    research_direction: str | None = Field(default=None, max_length=10_000)
    domain_pack_id: int | None = None
    research_profile_id: int | None = None
    repository_url: str | None = Field(default=None, max_length=4000)
    deepwiki_job_id: int | None = None
    current_conclusion: str | None = Field(default=None, max_length=50_000)
    unresolved_questions: list[str] | None = Field(default=None, max_length=200)
    next_reading_suggestion: str | None = Field(default=None, max_length=20_000)


class ResearchProjectPaperRequest(BaseModel):
    paper_id: int
    role: Literal["core", "support", "conflict", "background", "to_verify"] = "to_verify"
    reading_status: Literal["to_screen", "to_read", "reading", "read_to_organize", "completed", "shelved"] = "to_screen"


class ResearchProjectPaperUpdate(BaseModel):
    role: Literal["core", "support", "conflict", "background", "to_verify"] | None = None
    reading_status: Literal["to_screen", "to_read", "reading", "read_to_organize", "completed", "shelved"] | None = None
    queue_order: int | None = Field(default=None, ge=0)


class ResearchProjectNoteCreate(BaseModel):
    title: str = Field(default="项目笔记", min_length=1, max_length=300)
    content: str = Field(default="", max_length=200_000)


class ResearchProjectSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=20)


class ResearchProjectChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)


class ExperimentMetricInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    value: float
    step: int | None = Field(default=None, ge=0)
    split: str = Field(default="", max_length=80)
    unit: str = Field(default="", max_length=40)
    is_primary: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime | None = None


class ExperimentArtifactInput(BaseModel):
    artifact_type: Literal["file", "log", "checkpoint", "figure", "table", "dataset", "link"] = "file"
    name: str = Field(min_length=1, max_length=300)
    uri: str = Field(min_length=1, max_length=8000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    objective: str = Field(default="", max_length=50_000)
    hypothesis: str = Field(default="", max_length=50_000)
    experiment_type: Literal["run", "baseline", "ablation", "reproduction", "evaluation", "exploration"] = "run"
    status: Literal["planned", "queued", "running", "completed", "failed", "cancelled"] = "planned"
    parent_experiment_id: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    dataset_version: str = Field(default="", max_length=4000)
    code_reference: str = Field(default="", max_length=4000)
    command: str = Field(default="", max_length=20_000)
    observations: str = Field(default="", max_length=100_000)
    conclusion: str = Field(default="", max_length=100_000)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    metrics: list[ExperimentMetricInput] = Field(default_factory=list, max_length=10_000)
    artifacts: list[ExperimentArtifactInput] = Field(default_factory=list, max_length=500)


class ExperimentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    objective: str | None = Field(default=None, max_length=50_000)
    hypothesis: str | None = Field(default=None, max_length=50_000)
    experiment_type: Literal["run", "baseline", "ablation", "reproduction", "evaluation", "exploration"] | None = None
    status: Literal["planned", "queued", "running", "completed", "failed", "cancelled"] | None = None
    parent_experiment_id: int | None = None
    config: dict[str, Any] | None = None
    environment: dict[str, Any] | None = None
    dataset_version: str | None = Field(default=None, max_length=4000)
    code_reference: str | None = Field(default=None, max_length=4000)
    command: str | None = Field(default=None, max_length=20_000)
    observations: str | None = Field(default=None, max_length=100_000)
    conclusion: str | None = Field(default=None, max_length=100_000)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class ExperimentMetricsAppend(BaseModel):
    metrics: list[ExperimentMetricInput] = Field(min_length=1, max_length=10_000)


class ExperimentArtifactsAppend(BaseModel):
    artifacts: list[ExperimentArtifactInput] = Field(min_length=1, max_length=500)


class ExperimentAnalysisRequest(BaseModel):
    question: str = Field(default="请总结实验进展、主要结果、异常与下一步建议。", min_length=1, max_length=20_000)


class PaperEvidenceItem(BaseModel):
    field_name: Literal["research_problem", "method", "innovation", "experiment_conclusion", "limitation"]
    claim: str = Field(min_length=1, max_length=20_000)
    page_number: int | None = Field(default=None, ge=1, le=100_000)
    section: str | None = Field(default=None, max_length=500)
    evidence_excerpt: str = Field(default="", max_length=1000)
    conclusion_type: Literal["paper_fact", "author_claim", "ai_judgment"] = "paper_fact"


class PaperEvidenceUpdate(BaseModel):
    source_scope: Literal["full_text", "abstract", "author_statement"]
    items: list[PaperEvidenceItem] = Field(default_factory=list, max_length=200)

    @field_validator("items")
    @classmethod
    def abstract_has_no_pages(cls, value: list[PaperEvidenceItem], info):
        if info.data.get("source_scope") == "abstract" and any(item.page_number for item in value):
            raise ValueError("仅摘要分析不能填写页码")
        return value


class PaperVersionLinkRequest(BaseModel):
    target_paper_id: int
    crossref_related: bool = False
    user_confirmed: bool = False


class KnowledgeNodeCreate(BaseModel):
    node_type: Literal["paper", "method", "task", "dataset", "benchmark", "model", "experiment_conclusion", "limitation", "repository", "weight", "project"]
    label: str = Field(min_length=1, max_length=1000)
    external_key: str = Field(min_length=1, max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeEdgeCreate(BaseModel):
    source_node_id: int
    target_node_id: int
    relation_type: Literal["proposes", "uses", "improves", "evaluated_on", "supports", "refutes", "implements", "reproduces", "extends"]
    source_type: str = Field(min_length=1, max_length=40)
    source_id: str = Field(min_length=1, max_length=300)
    evidence: str = Field(min_length=1, max_length=5000)
    confidence: float = Field(ge=0, le=1)
    confirmed: bool = False


class PaperResourceCreate(BaseModel):
    resource_type: Literal["official_repository", "third_party_reproduction", "model_weights", "dataset", "project_page"]
    url: HttpUrl
    label: str = Field(default="", max_length=300)
    source: str = Field(default="user", max_length=40)
    verified: bool = False


class ReaderTranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    page: int | None = Field(default=None, ge=1, le=1000)
    target_language: Literal["zh", "en"] = "zh"


class ReaderFigureRequest(BaseModel):
    data_url: str = Field(min_length=32, max_length=9_000_000)
    page: int = Field(ge=1, le=1000)
    caption: str | None = Field(default=None, max_length=500)


class RepositoryBindRequest(BaseModel):
    repository_url: HttpUrl

    @field_validator("repository_url")
    @classmethod
    def github_only(cls, value: HttpUrl) -> HttpUrl:
        if value.host not in {"github.com", "www.github.com"}:
            raise ValueError("当前仅支持 GitHub 仓库")
        return value


class SettingsUpdate(BaseModel):
    default_abstract_language: Literal["zh", "en"] | None = None
    font_size: int | None = Field(default=None, ge=13, le=20)
    daily_enabled: bool | None = None
    daily_time: str | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    timezone_auto: bool | None = None
    daylight_saving_enabled: bool | None = None
    daily_count: int | None = Field(default=None, ge=1, le=30)
    daily_tag_ids: list[int] | None = None
    daily_profile_ids: list[int] | None = None
    daily_profile_mode: Literal["focus", "mixed"] | None = None
    top_venue_ratio: float | None = Field(default=None, ge=0, le=1)
    only_verified_top_venues: bool | None = None
    llm_provider: Literal["openai", "claude", "glm", "deepseek", "zhizengzeng"] | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    github_token: str | None = None
    llm_rerank_enabled: bool | None = None
    llm_rerank_weight: float | None = Field(default=None, ge=0, le=1)
    zotero_library_type: Literal["user", "group"] | None = None
    zotero_library_id: str | None = Field(default=None, max_length=64)
    zotero_collection_key: str | None = Field(default=None, max_length=64)
    zotero_sync_tags: bool | None = None
    zotero_api_key: str | None = Field(default=None, max_length=2000)
    library_root: str | None = Field(default=None, max_length=4000)

    @field_validator("daily_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            hour, minute = map(int, value.split(":"))
        except ValueError as exc:
            raise ValueError("时间格式必须为 HH:MM") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("无效时间")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("请选择有效的 IANA 时区") from exc
        return value


class LLMProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: Literal["openai", "claude", "glm", "deepseek", "custom"] = "custom"
    base_url: str = Field(min_length=4, max_length=1000)
    model: str = Field(min_length=1, max_length=160)
    api_key: str | None = Field(default=None, max_length=2000)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("https://", "http://")):
            raise ValueError("API 地址必须以 http:// 或 https:// 开头")
        return value


class LLMProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    provider: Literal["openai", "claude", "glm", "deepseek", "custom"] | None = None
    base_url: str | None = Field(default=None, min_length=4, max_length=1000)
    model: str | None = Field(default=None, min_length=1, max_length=160)
    api_key: str | None = Field(default=None, max_length=2000)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip().rstrip("/")
        if not value.startswith(("https://", "http://")):
            raise ValueError("API 地址必须以 http:// 或 https:// 开头")
        return value


class PaperChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    session_id: str | None = None


class WorkspaceChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class WorkspaceChatRequest(BaseModel):
    page_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")
    page_title: str = Field(min_length=1, max_length=200)
    context: str = Field(default="", max_length=60_000)
    message: str = Field(min_length=1, max_length=20_000)
    history: list[WorkspaceChatMessage] = Field(default_factory=list, max_length=20)
    response_detail: Literal["concise", "rich"] = "rich"


class PaperChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class RelatedPaper(BaseModel):
    paper_id: str | None = None
    title: str
    url: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    relation: str = "similar"
