from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


paper_tags = Table(
    "paper_tags",
    Base.metadata,
    Column("paper_id", ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

paper_library_tags = Table(
    "paper_library_tags",
    Base.metadata,
    Column("paper_id", ForeignKey("library_entries.paper_id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("library_tags.id", ondelete="CASCADE"), primary_key=True),
)

paper_library_folders = Table(
    "paper_library_folders",
    Base.metadata,
    Column("paper_id", ForeignKey("library_entries.paper_id", ondelete="CASCADE"), primary_key=True),
    Column("folder_id", ForeignKey("library_folders.id", ondelete="CASCADE"), primary_key=True),
)


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_en: Mapped[str] = mapped_column(Text)
    title_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract_en: Mapped[str] = mapped_column(Text, default="")
    abstract_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors_json: Mapped[str] = mapped_column(Text, default="[]")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    venue_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    venue_tier: Mapped[str] = mapped_column(String(32), default="preprint")
    publication_status: Mapped[str] = mapped_column(String(32), default="preprint")
    arxiv_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    semantic_scholar_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    primary_url: Mapped[str] = mapped_column(Text)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="arxiv")
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_status: Mapped[str] = mapped_column(String(32), default="pending")
    repository_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    repository_status: Mapped[str] = mapped_column(String(32), default="unknown")
    identity_hash: Mapped[str] = mapped_column(String(64), unique=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tags: Mapped[list["Tag"]] = relationship(secondary=paper_tags, back_populates="papers")
    study_state: Mapped["PaperStudyState | None"] = relationship(back_populates="paper", uselist=False, cascade="all, delete-orphan")
    note: Mapped["PaperNote | None"] = relationship(back_populates="paper", uselist=False, cascade="all, delete-orphan")
    recommendation_assessment: Mapped["RecommendationAssessment | None"] = relationship(back_populates="paper", uselist=False, cascade="all, delete-orphan")
    document: Mapped["PaperDocument | None"] = relationship(back_populates="paper", uselist=False, cascade="all, delete-orphan")
    library_entry: Mapped["LibraryEntry | None"] = relationship(back_populates="paper", uselist=False, cascade="all, delete-orphan")
    local_files: Mapped[list["LocalPaperFile"]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    research_results: Mapped[list["ResearchStudyPaper"]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    zotero_link: Mapped["ZoteroLink | None"] = relationship(back_populates="paper", uselist=False, cascade="all, delete-orphan")
    work_version: Mapped["PaperVersion | None"] = relationship(back_populates="paper", uselist=False, cascade="all, delete-orphan")
    analysis_evidence: Mapped[list["PaperAnalysisEvidence"]] = relationship(back_populates="paper", cascade="all, delete-orphan")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name_zh: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str] = mapped_column(String(120))
    query: Mapped[str] = mapped_column(Text)
    arxiv_categories_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    papers: Mapped[list[Paper]] = relationship(secondary=paper_tags, back_populates="tags")


class RecommendationBatch(Base):
    __tablename__ = "recommendation_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    requested_count: Mapped[int] = mapped_column(Integer)
    delivered_count: Mapped[int] = mapped_column(Integer, default=0)
    tag_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    triggered_by: Mapped[str] = mapped_column(String(32), default="manual")
    status: Mapped[str] = mapped_column(String(32), default="running")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="batch", cascade="all, delete-orphan")
    context: Mapped["RecommendationContext | None"] = relationship(back_populates="batch", uselist=False, cascade="all, delete-orphan")


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("paper_id", name="uq_recommendation_paper"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("recommendation_batches.id", ondelete="CASCADE"))
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float, default=0)
    recommended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    batch: Mapped[RecommendationBatch] = relationship(back_populates="recommendations")
    paper: Mapped[Paper] = relationship()
    match: Mapped["RecommendationMatch | None"] = relationship(back_populates="recommendation", uselist=False, cascade="all, delete-orphan")


class DomainPack(Base):
    __tablename__ = "domain_packs"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name_zh: Mapped[str] = mapped_column(String(160))
    name_en: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source_adapters_json: Mapped[str] = mapped_column(Text, default="[]")
    search_templates_json: Mapped[str] = mapped_column(Text, default="[]")
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    exclusions_json: Mapped[str] = mapped_column(Text, default="[]")
    category_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    venue_rules_json: Mapped[str] = mapped_column(Text, default="[]")
    paper_types_json: Mapped[str] = mapped_column(Text, default="[]")
    scoring_weights_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_rules_json: Mapped[str] = mapped_column(Text, default="{}")
    analysis_prompt: Mapped[str] = mapped_column(Text, default="")
    review_prompt: Mapped[str] = mapped_column(Text, default="")
    citation_config_json: Mapped[str] = mapped_column(Text, default="{}")
    impact_config_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    metrics: Mapped[list["DomainMetric"]] = relationship(back_populates="domain_pack", cascade="all, delete-orphan")
    research_profiles: Mapped[list["ResearchProfile"]] = relationship(back_populates="domain_pack")


class DomainMetric(Base):
    __tablename__ = "domain_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_pack_id: Mapped[int] = mapped_column(ForeignKey("domain_packs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    value: Mapped[float] = mapped_column(Float)
    year: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    domain_pack: Mapped[DomainPack] = relationship(back_populates="metrics")


class ResearchProfile(Base):
    __tablename__ = "research_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_pack_id: Mapped[int | None] = mapped_column(ForeignKey("domain_packs.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    domain: Mapped[str] = mapped_column(String(32), default="ai", index=True)
    description: Mapped[str] = mapped_column(Text)
    positive_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    negative_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    seed_papers_json: Mapped[str] = mapped_column(Text, default="[]")
    relevance_weight: Mapped[float] = mapped_column(Float, default=0.55)
    recency_weight: Mapped[float] = mapped_column(Float, default=0.25)
    exploration_ratio: Mapped[float] = mapped_column(Float, default=0.2)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    domain_pack: Mapped["DomainPack | None"] = relationship(back_populates="research_profiles")


class RecommendationContext(Base):
    __tablename__ = "recommendation_contexts"

    batch_id: Mapped[int] = mapped_column(ForeignKey("recommendation_batches.id", ondelete="CASCADE"), primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("research_profiles.id", ondelete="SET NULL"), nullable=True)
    mode: Mapped[str] = mapped_column(String(24), default="broad")
    profile_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    profile_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    batch: Mapped[RecommendationBatch] = relationship(back_populates="context")
    profile: Mapped[ResearchProfile | None] = relationship()


class RecommendationMatch(Base):
    __tablename__ = "recommendation_matches"

    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"), primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("research_profiles.id", ondelete="SET NULL"), nullable=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    matched_concepts_json: Mapped[str] = mapped_column(Text, default="[]")
    reason: Mapped[str] = mapped_column(Text, default="")
    lane: Mapped[str] = mapped_column(String(24), default="broad")

    recommendation: Mapped[Recommendation] = relationship(back_populates="match")
    profile: Mapped[ResearchProfile | None] = relationship()


class PaperStudyState(Base):
    __tablename__ = "paper_study_states"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True)
    learned: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    paper: Mapped[Paper] = relationship(back_populates="study_state")


class PaperNote(Base):
    __tablename__ = "paper_notes"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    paper: Mapped[Paper] = relationship(back_populates="note")


class LibraryEntry(Base):
    __tablename__ = "library_entries"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    paper: Mapped[Paper] = relationship(back_populates="library_entry")
    tags: Mapped[list["LibraryTag"]] = relationship(secondary=paper_library_tags, back_populates="entries")
    folders: Mapped[list["LibraryFolder"]] = relationship(secondary=paper_library_folders, back_populates="entries")


class LibraryTag(Base):
    __tablename__ = "library_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    normalized_name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    color: Mapped[str] = mapped_column(String(16), default="#0a84ff")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entries: Mapped[list[LibraryEntry]] = relationship(secondary=paper_library_tags, back_populates="tags")


class LibraryFolder(Base):
    __tablename__ = "library_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    normalized_name: Mapped[str] = mapped_column(String(160), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("library_folders.id", ondelete="CASCADE"), nullable=True, index=True)
    relative_path: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    parent: Mapped["LibraryFolder | None"] = relationship(remote_side="LibraryFolder.id", back_populates="children")
    children: Mapped[list["LibraryFolder"]] = relationship(back_populates="parent", cascade="all, delete-orphan")
    entries: Mapped[list[LibraryEntry]] = relationship(secondary=paper_library_folders, back_populates="folders")
    files: Mapped[list["LocalPaperFile"]] = relationship(back_populates="folder")


class LocalPaperFile(Base):
    __tablename__ = "local_paper_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("library_folders.id", ondelete="CASCADE"), index=True)
    relative_path: Mapped[str] = mapped_column(Text, unique=True)
    file_name: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    modified_ns: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="ready")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    paper: Mapped[Paper] = relationship(back_populates="local_files")
    folder: Mapped[LibraryFolder] = relationship(back_populates="files")


class ResearchStudy(Base):
    __tablename__ = "research_studies"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(32), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(500), default="专题调研")
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    search_terms_json: Mapped[str] = mapped_column(Text, default="[]")
    core_concepts_json: Mapped[str] = mapped_column(Text, default="[]")
    review_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    papers: Mapped[list["ResearchStudyPaper"]] = relationship(back_populates="study", cascade="all, delete-orphan", order_by="ResearchStudyPaper.rank")
    artifacts: Mapped["ResearchStudyArtifact | None"] = relationship(back_populates="study", uselist=False, cascade="all, delete-orphan")


class ResearchStudyPaper(Base):
    __tablename__ = "research_study_papers"
    __table_args__ = (UniqueConstraint("study_id", "paper_id", name="uq_research_study_paper"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("research_studies.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    final_score: Mapped[float] = mapped_column(Float, default=0)
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    value_score: Mapped[float] = mapped_column(Float, default=0)
    novelty_score: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    matched_concepts_json: Mapped[str] = mapped_column(Text, default="[]")
    reason: Mapped[str] = mapped_column(Text, default="")
    caution: Mapped[str | None] = mapped_column(Text, nullable=True)

    study: Mapped[ResearchStudy] = relationship(back_populates="papers")
    paper: Mapped[Paper] = relationship(back_populates="research_results")


class ResearchStudyArtifact(Base):
    __tablename__ = "research_study_artifacts"

    study_id: Mapped[int] = mapped_column(ForeignKey("research_studies.id", ondelete="CASCADE"), primary_key=True)
    taxonomy_json: Mapped[str] = mapped_column(Text, default="[]")
    comparison_json: Mapped[str] = mapped_column(Text, default="[]")
    research_routes_json: Mapped[str] = mapped_column(Text, default="[]")
    representative_works_json: Mapped[str] = mapped_column(Text, default="[]")
    controversies_json: Mapped[str] = mapped_column(Text, default="[]")
    gaps_json: Mapped[str] = mapped_column(Text, default="[]")
    cited_review_markdown: Mapped[str] = mapped_column(Text, default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    study: Mapped[ResearchStudy] = relationship(back_populates="artifacts")


class ZoteroLink(Base):
    __tablename__ = "zotero_links"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True)
    library_type: Mapped[str] = mapped_column(String(16), default="user")
    library_id: Mapped[str] = mapped_column(String(64))
    item_key: Mapped[str] = mapped_column(String(16))
    item_version: Mapped[int] = mapped_column(Integer, default=0)
    item_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(24), default="synced")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    paper: Mapped[Paper] = relationship(back_populates="zotero_link")


class RecommendationAssessment(Base):
    __tablename__ = "recommendation_assessments"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True)
    taste_score: Mapped[float] = mapped_column(Float, default=0)
    novelty_score: Mapped[float] = mapped_column(Float, default=0)
    value_score: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    caution: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    paper: Mapped[Paper] = relationship(back_populates="recommendation_assessment")


class PaperDocument(Base):
    __tablename__ = "paper_documents"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True)
    source_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    paper: Mapped[Paper] = relationship(back_populates="document")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="论文对话")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    paper: Mapped[Paper] = relationship()
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LLMProfile(Base):
    __tablename__ = "llm_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(32), default="custom")
    base_url: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TokenUsage(Base):
    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    profile_name: Mapped[str] = mapped_column(String(120), default="Unknown API")
    provider: Mapped[str] = mapped_column(String(32), default="custom")
    model: Mapped[str] = mapped_column(String(160), default="")
    purpose: Mapped[str] = mapped_column(String(32), default="other", index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class DeepWikiJob(Base):
    __tablename__ = "deepwiki_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    repository_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="等待开始")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    paper: Mapped[Paper] = relationship()


class ResearchProject(Base):
    __tablename__ = "research_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    research_question: Mapped[str] = mapped_column(Text, default="")
    research_direction: Mapped[str] = mapped_column(Text, default="")
    domain_pack_id: Mapped[int | None] = mapped_column(ForeignKey("domain_packs.id", ondelete="SET NULL"), nullable=True, index=True)
    research_profile_id: Mapped[int | None] = mapped_column(ForeignKey("research_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    repository_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deepwiki_job_id: Mapped[int | None] = mapped_column(ForeignKey("deepwiki_jobs.id", ondelete="SET NULL"), nullable=True)
    current_conclusion: Mapped[str] = mapped_column(Text, default="")
    unresolved_questions_json: Mapped[str] = mapped_column(Text, default="[]")
    next_reading_suggestion: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    papers: Mapped[list["ResearchProjectPaper"]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="ResearchProjectPaper.queue_order")
    notes: Mapped[list["ResearchProjectNote"]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="ResearchProjectNote.updated_at")
    studies: Mapped[list["ResearchProjectStudy"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ResearchProjectPaper(Base):
    __tablename__ = "research_project_papers"
    __table_args__ = (UniqueConstraint("project_id", "paper_id", name="uq_research_project_paper"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(24), default="to_verify")
    reading_status: Mapped[str] = mapped_column(String(32), default="to_screen")
    queue_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped[ResearchProject] = relationship(back_populates="papers")
    paper: Mapped[Paper] = relationship()


class ResearchProjectNote(Base):
    __tablename__ = "research_project_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="项目笔记")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped[ResearchProject] = relationship(back_populates="notes")


class ResearchProjectStudy(Base):
    __tablename__ = "research_project_studies"
    __table_args__ = (UniqueConstraint("project_id", "study_id", name="uq_research_project_study"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("research_studies.id", ondelete="CASCADE"), index=True)
    project: Mapped[ResearchProject] = relationship(back_populates="studies")
    study: Mapped[ResearchStudy] = relationship()


class ProjectChatMessage(Base):
    __tablename__ = "project_chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaperWork(Base):
    __tablename__ = "paper_works"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    versions: Mapped[list["PaperVersion"]] = relationship(back_populates="work", cascade="all, delete-orphan", order_by="PaperVersion.version_date")


class PaperVersion(Base):
    __tablename__ = "paper_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("paper_works.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), unique=True, index=True)
    version_label: Mapped[str] = mapped_column(String(160), default="原始版本")
    relation_type: Mapped[str] = mapped_column(String(32), default="same_work")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    match_reason: Mapped[str] = mapped_column(Text, default="")
    important_changes: Mapped[str] = mapped_column(Text, default="")
    version_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    work: Mapped[PaperWork] = relationship(back_populates="versions")
    paper: Mapped[Paper] = relationship(back_populates="work_version")


class PaperMergeAudit(Base):
    __tablename__ = "paper_merge_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    from_work_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_work_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(24))
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaperAnalysisEvidence(Base):
    __tablename__ = "paper_analysis_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    field_name: Mapped[str] = mapped_column(String(80))
    claim: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_excerpt: Mapped[str] = mapped_column(Text, default="")
    source_scope: Mapped[str] = mapped_column(String(24), default="abstract")
    conclusion_type: Mapped[str] = mapped_column(String(24), default="paper_fact")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paper: Mapped[Paper] = relationship(back_populates="analysis_evidence")


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    node_type: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str] = mapped_column(Text)
    external_key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_node_id: Mapped[int] = mapped_column(ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True)
    target_node_id: Mapped[int] = mapped_column(ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True)
    relation_type: Mapped[str] = mapped_column(String(40), index=True)
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(300))
    evidence: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaperResource(Base):
    __tablename__ = "paper_resources"
    __table_args__ = (UniqueConstraint("paper_id", "resource_type", "url", name="uq_paper_resource"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    resource_type: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(40), default="user")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReproductionCheck(Base):
    __tablename__ = "reproduction_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    deepwiki_job_id: Mapped[int | None] = mapped_column(ForeignKey("deepwiki_jobs.id", ondelete="SET NULL"), nullable=True)
    check_key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
