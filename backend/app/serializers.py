from __future__ import annotations

import json
from typing import Any

from .catalog import tag_domain
from .models import DeepWikiJob, LibraryTag, Paper, Recommendation, RecommendationBatch, ResearchProfile, Tag
from .zotero_service import zotero_link_dict
from .evidence_service import evidence_dict


def tag_dict(tag: Tag) -> dict[str, Any]:
    return {
        "id": tag.id,
        "slug": tag.slug,
        "name_zh": tag.name_zh,
        "name_en": tag.name_en,
        "query": tag.query,
        "arxiv_categories": json.loads(tag.arxiv_categories_json),
        "domain": tag_domain(tag.slug),
    }


def library_tag_dict(tag: LibraryTag) -> dict[str, Any]:
    return {"id": tag.id, "name": tag.name, "color": tag.color, "created_at": tag.created_at.isoformat()}


def paper_dict(paper: Paper, score: float | None = None, recommended_at: Any = None, recommendation: Recommendation | None = None) -> dict[str, Any]:
    summary = None
    if paper.summary_json:
        try:
            summary = json.loads(paper.summary_json)
        except json.JSONDecodeError:
            summary = None
    assessment = paper.recommendation_assessment
    match = recommendation.match if recommendation else None
    return {
        "id": paper.id,
        "title_en": paper.title_en,
        "title_zh": paper.title_zh,
        "abstract_en": paper.abstract_en,
        "abstract_zh": paper.abstract_zh,
        "authors": json.loads(paper.authors_json or "[]"),
        "published_at": paper.published_at.isoformat() if paper.published_at else None,
        "updated_at": paper.updated_at.isoformat() if paper.updated_at else None,
        "venue_name": paper.venue_name,
        "venue_tier": paper.venue_tier,
        "publication_status": paper.publication_status,
        "arxiv_id": paper.arxiv_id,
        "doi": paper.doi,
        "semantic_scholar_id": paper.semantic_scholar_id,
        "primary_url": paper.primary_url,
        "pdf_url": paper.pdf_url,
        "source": paper.source,
        "summary": summary,
        "analysis_scope": paper.analysis_evidence[0].source_scope if paper.analysis_evidence else ("abstract" if summary else None),
        "analysis_evidence": [evidence_dict(item) for item in paper.analysis_evidence],
        "work_version": {"work_id": paper.work_version.work_id, "version_label": paper.work_version.version_label, "confidence": paper.work_version.confidence, "confirmed": paper.work_version.confirmed} if paper.work_version else None,
        "ai_status": paper.ai_status,
        "repository_url": paper.repository_url,
        "repository_status": paper.repository_status,
        "tags": [tag_dict(tag) for tag in paper.tags],
        "in_library": paper.library_entry is not None,
        "library_added_at": paper.library_entry.added_at.isoformat() if paper.library_entry else None,
        "library_tags": [library_tag_dict(tag) for tag in paper.library_entry.tags] if paper.library_entry else [],
        "library_folders": [{"id": folder.id, "name": folder.name, "relative_path": folder.relative_path} for folder in paper.library_entry.folders] if paper.library_entry else [],
        "local_files": [{
            "id": item.id, "file_name": item.file_name, "relative_path": item.relative_path,
            "folder_id": item.folder_id, "size_bytes": item.size_bytes,
            "page_count": item.page_count, "status": item.status,
            "pdf_url": f"/api/library/files/{item.id}/pdf",
        } for item in paper.local_files],
        "zotero": zotero_link_dict(paper.zotero_link),
        "learned": bool(paper.study_state and paper.study_state.learned),
        "completed_at": paper.study_state.completed_at.isoformat() if paper.study_state and paper.study_state.completed_at else None,
        "note": paper.note.content if paper.note else "",
        "note_updated_at": paper.note.updated_at.isoformat() if paper.note else None,
        "score": score if score is not None else paper.relevance_score,
        "recommended_at": recommended_at.isoformat() if recommended_at else None,
        "recommendation_assessment": {
            "taste_score": assessment.taste_score,
            "novelty_score": assessment.novelty_score,
            "value_score": assessment.value_score,
            "confidence": assessment.confidence,
            "reason": assessment.reason,
            "caution": assessment.caution,
            "model": assessment.model,
        } if assessment else None,
        "direction_match": {
            "relevance_score": match.relevance_score,
            "confidence": match.confidence,
            "matched_concepts": json.loads(match.matched_concepts_json or "[]"),
            "reason": match.reason,
            "lane": match.lane,
        } if match else None,
    }


def batch_dict(batch: RecommendationBatch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "requested_count": batch.requested_count,
        "delivered_count": batch.delivered_count,
        "tag_ids": json.loads(batch.tag_ids_json),
        "triggered_by": batch.triggered_by,
        "status": batch.status,
        "message": batch.message,
        "created_at": batch.created_at.isoformat(),
        "mode": batch.context.mode if batch.context else "broad",
        "profile": {"id": batch.context.profile_id, "name": batch.context.profile_name, "description": batch.context.profile_description} if batch.context and batch.context.profile_id else None,
        "papers": [paper_dict(item.paper, item.score, item.recommended_at, item) for item in batch.recommendations],
    }


def research_profile_dict(profile: ResearchProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "domain": profile.domain,
        "domain_pack_id": profile.domain_pack_id,
        "domain_pack": {"id": profile.domain_pack.id, "slug": profile.domain_pack.slug, "name_zh": profile.domain_pack.name_zh, "name_en": profile.domain_pack.name_en} if profile.domain_pack else None,
        "description": profile.description,
        "positive_keywords": json.loads(profile.positive_keywords_json or "[]"),
        "negative_keywords": json.loads(profile.negative_keywords_json or "[]"),
        "seed_papers": json.loads(profile.seed_papers_json or "[]"),
        "relevance_weight": profile.relevance_weight,
        "recency_weight": profile.recency_weight,
        "exploration_ratio": profile.exploration_ratio,
        "enabled": profile.enabled,
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
    }


def job_dict(job: DeepWikiJob) -> dict[str, Any]:
    from .deepwiki_service import wiki_is_complete, wiki_is_full_deepwiki
    wiki_available = job.status == "completed" and wiki_is_complete(job.output_dir)
    full_deepwiki = wiki_available and wiki_is_full_deepwiki(job.output_dir)
    legacy_message = "这是旧版简化 Wiki；请重新生成完整原版知识库" if wiki_available and not full_deepwiki else None
    return {
        "id": job.id,
        "paper_id": job.paper_id,
        "paper_title": job.paper.title_en if job.paper else None,
        "repository_url": job.repository_url,
        "status": job.status,
        "progress": job.progress,
        "message": legacy_message or job.message,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "wiki_available": wiki_available,
        "wiki_mode": "full" if full_deepwiki else ("legacy" if wiki_available else None),
        "needs_regeneration": bool(wiki_available and not full_deepwiki),
    }
