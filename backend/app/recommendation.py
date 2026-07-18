from __future__ import annotations

import asyncio
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .catalog import detect_venue, domain_categories, tag_domain
from .llm import LLMClient
from .models import Paper, PaperStudyState, Recommendation, RecommendationAssessment, RecommendationBatch, RecommendationContext, RecommendationMatch, ResearchProfile, Tag
from .paper_sources import ArxivSource, PaperCandidate, SemanticScholarSource
from .recommendation_pipeline import (
    ArxivCandidateSource,
    CallbackReranker,
    DefaultFeatureProvider,
    DefaultSelector,
    PermanentCandidateFilter,
    RecommendationContext as PipelineContext,
    RecommendationRequest,
    RuleRanker,
    RankedCandidate,
    identity_hash,
    normalize_title,
)
from .settings_service import get_settings


STOP_WORDS = {"the", "and", "for", "with", "from", "that", "this", "into", "using", "based", "study", "research", "model", "models", "paper", "method"}


class RecommendationService:
    def __init__(self, db: Session):
        self.db = db
        self.arxiv = ArxivSource()
        self.s2 = SemanticScholarSource()
        self._last_relation_assessments: dict[int, dict[str, Any]] = {}

    async def generate(self, tag_ids: list[int], count: int, triggered_by: str = "manual", profile_id: int | None = None, mode: str = "broad") -> RecommendationBatch:
        profile = self.db.get(ResearchProfile, profile_id) if profile_id else None
        if profile_id and (not profile or not profile.enabled):
            raise ValueError("研究方向不存在或已停用")
        if mode != "broad" and not profile:
            raise ValueError("聚焦推荐需要选择一个研究方向")
        tags = list(self.db.scalars(select(Tag).where(Tag.id.in_(tag_ids), Tag.enabled.is_(True))))
        if profile and not tags:
            domain_tags = list(self.db.scalars(select(Tag).where(Tag.enabled.is_(True))))
            tags = [tag for tag in domain_tags if tag_domain(tag.slug) == profile.domain]
        batch = RecommendationBatch(
            requested_count=count,
            tag_ids_json=json.dumps([tag.id for tag in tags]),
            triggered_by=triggered_by,
            status="running",
        )
        self.db.add(batch)
        batch.context = RecommendationContext(
            mode=mode,
            profile_id=profile.id if profile else None,
            profile_name=profile.name if profile else None,
            profile_description=profile.description if profile else None,
        )
        self.db.commit()
        if not tags:
            batch.status = "failed"
            batch.message = "没有可用的 Tag"
            self.db.commit()
            return batch

        categories = [category for tag in tags for category in json.loads(tag.arxiv_categories_json)]
        if profile:
            categories = sorted(set(categories + domain_categories(profile.domain)))
        keywords = [term.strip() for tag in tags for term in re.split(r"\s+OR\s+", tag.query, flags=re.I)]
        profile_keywords: list[str] = []
        exclusions: list[str] = []
        seed_papers: list[str] = []
        if profile:
            profile_keywords = json.loads(profile.positive_keywords_json or "[]")
            exclusions = json.loads(profile.negative_keywords_json or "[]")
            seed_papers = json.loads(profile.seed_papers_json or "[]")
            llm = LLMClient(self.db)
            if llm.configured:
                try:
                    expansion = await llm.expand_research_profile(
                        profile.name,
                        profile.description,
                        profile_keywords,
                        exclusions,
                        seed_papers,
                    )
                    profile_keywords = list(dict.fromkeys([*profile_keywords, *expansion.get("search_terms", [])]))[:20]
                    exclusions = list(dict.fromkeys([*exclusions, *expansion.get("exclusions", [])]))[:20]
                except Exception:
                    pass
        source = ArxivCandidateSource(self.arxiv)
        try:
            candidates = await source.collect(RecommendationRequest(
                categories=categories,
                keywords=keywords,
                count=count,
                mode=mode,
                profile_name=profile.name if profile else None,
                focused_keywords=profile_keywords,
            ))
        except Exception as exc:
            batch.status = "failed"
            batch.message = f"论文源暂时不可用：{exc}"
            self.db.commit()
            return batch

        # Enrich the strongest fresh candidates with a second scholarly source before
        # venue scoring. Failures and public-API rate limits degrade gracefully.
        await self._enrich_candidate_metadata(candidates[: min(24, count * 5)])

        settings = get_settings(self.db)
        preferences = None
        if profile:
            preferences = "\n".join(filter(None, [
                f"研究方向：{profile.name}",
                f"自然语言描述：{profile.description}",
                f"核心检索概念：{', '.join(profile_keywords)}" if profile_keywords else None,
                f"种子论文：{', '.join(seed_papers)}" if seed_papers else None,
            ]))
        pipeline_context = PipelineContext(tags=tags, count=count, mode=mode, settings=settings, profile=profile, exclusions=exclusions, preferences=preferences)
        candidates = PermanentCandidateFilter(self.db, self._find_existing).apply(candidates, pipeline_context)
        relation_provider = (lambda candidate: self._profile_relevance(candidate, profile, profile_keywords)) if profile else None
        feature_provider = DefaultFeatureProvider(self._upsert, self._score, relation_provider)
        ranked_items = [feature_provider.provide(candidate, pipeline_context) for candidate in candidates]
        self.db.commit()
        ranked_items = RuleRanker().rank(ranked_items, pipeline_context)

        async def llm_rerank(items: list[RankedCandidate], context: PipelineContext) -> bool:
            ranked_pairs = [(item.paper, item.final_score) for item in items]
            used = await self._apply_llm_rerank(ranked_pairs, context.tags, context.count, context.settings, context.preferences)
            score_by_id = {paper.id: score for paper, score in ranked_pairs}
            for item in items:
                item.final_score = score_by_id.get(item.paper.id, item.final_score)
                if item.paper.id in self._last_relation_assessments:
                    item.relation = self._last_relation_assessments[item.paper.id]
            return used

        llm_used = await CallbackReranker(llm_rerank).rerank(ranked_items, pipeline_context)
        result = DefaultSelector().select(ranked_items, pipeline_context, llm_used)
        chosen = result.items

        for item in chosen:
            paper, score = item.paper, item.final_score
            recommendation = Recommendation(batch_id=batch.id, paper_id=paper.id, score=score)
            self.db.add(recommendation)
            self.db.flush()
            if profile:
                relation = item.relation
                relevance = float(relation.get("relevance_score", 0))
                recommendation.match = RecommendationMatch(
                    profile_id=profile.id,
                    relevance_score=relevance,
                    confidence=float(relation.get("confidence", 55)),
                    matched_concepts_json=json.dumps(relation.get("matched_concepts", []), ensure_ascii=False),
                    reason=str(relation.get("reason") or "根据研究方向描述、关键词与摘要的概念覆盖度计算"),
                    lane=item.lane,
                )
        batch.delivered_count = len(chosen)
        batch.status = "completed"
        if len(chosen) != count:
            batch.message = f"符合条件且未推荐过的论文仅有 {len(chosen)} 篇"
        elif llm_used and profile:
            batch.message = f"推荐完成：已结合“{profile.name}”关联度、时效、学术价值与探索配额"
        elif llm_used:
            batch.message = "推荐完成：已结合规则筛选与 LLM 学术价值复排"
        else:
            batch.message = "推荐完成：当前未配置 LLM，已使用规则排序"
        self.db.commit()
        await self._enrich_selected([item.paper for item in chosen])
        self.db.refresh(batch)
        return batch

    def _profile_relevance(self, candidate: PaperCandidate, profile: ResearchProfile, keywords: list[str]) -> dict[str, Any]:
        haystack = f"{candidate.title} {candidate.abstract}".lower()
        phrases = [item.strip() for item in [profile.name, *keywords] if item and item.strip()]
        phrase_hits = [item for item in phrases if item.lower() in haystack]
        profile_tokens = {token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", f"{profile.name} {profile.description} {' '.join(keywords)}".lower()) if token not in STOP_WORDS}
        title_tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", candidate.title.lower()))
        abstract_tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", candidate.abstract.lower()))
        title_overlap = len(profile_tokens & title_tokens) / max(1, min(8, len(profile_tokens)))
        abstract_overlap = len(profile_tokens & abstract_tokens) / max(1, min(15, len(profile_tokens)))
        phrase_score = min(1.0, len(phrase_hits) / max(1, min(4, len(phrases))))
        score = min(100.0, 100 * (0.45 * phrase_score + 0.35 * title_overlap + 0.20 * abstract_overlap))
        concepts = phrase_hits[:4] or list(profile_tokens & (title_tokens | abstract_tokens))[:4]
        return {"relevance_score": round(score, 1), "confidence": 55, "matched_concepts": concepts, "reason": "标题与摘要覆盖了研究方向中的关键概念" if concepts else "作为相邻或探索性候选保留"}

    def _upsert(self, candidate: PaperCandidate, tags: list[Tag]) -> Paper:
        digest = identity_hash(candidate)
        paper = self._find_existing(candidate)
        venue_name, venue_tier, status = detect_venue(candidate.venue_hint)
        if paper is None:
            paper = Paper(
                title_en=candidate.title,
                abstract_en=candidate.abstract,
                authors_json=json.dumps(candidate.authors, ensure_ascii=False),
                published_at=candidate.published_at,
                updated_at=candidate.updated_at,
                venue_name=venue_name,
                venue_tier=venue_tier,
                publication_status=status,
                arxiv_id=candidate.arxiv_id,
                doi=candidate.doi,
                semantic_scholar_id=candidate.semantic_scholar_id,
                primary_url=candidate.primary_url,
                pdf_url=candidate.pdf_url,
                identity_hash=digest,
            )
            paper.study_state = PaperStudyState(learned=False)
            self.db.add(paper)
            self.db.flush()
        else:
            paper.title_en = candidate.title
            paper.abstract_en = candidate.abstract
            paper.updated_at = candidate.updated_at
            if venue_name:
                paper.venue_name, paper.venue_tier, paper.publication_status = venue_name, venue_tier, status
            if candidate.semantic_scholar_id:
                paper.semantic_scholar_id = candidate.semantic_scholar_id
            if candidate.doi and not paper.doi:
                paper.doi = candidate.doi
        existing = {tag.id for tag in paper.tags}
        paper.tags.extend(tag for tag in tags if tag.id not in existing)
        return paper

    def _find_existing(self, candidate: PaperCandidate) -> Paper | None:
        identities = [Paper.identity_hash == identity_hash(candidate)]
        if candidate.arxiv_id:
            identities.append(Paper.arxiv_id == candidate.arxiv_id)
        if candidate.doi:
            identities.append(Paper.doi == candidate.doi)
        if candidate.semantic_scholar_id:
            identities.append(Paper.semantic_scholar_id == candidate.semantic_scholar_id)
        return self.db.scalar(select(Paper).where(or_(*identities)))

    def _score(self, candidate: PaperCandidate, paper: Paper, tags: list[Tag]) -> float:
        age_days = max(0, (datetime.now(timezone.utc) - candidate.published_at).days)
        recency = 40 * math.exp(-age_days / 120)
        venue = 35 if paper.venue_tier in {"CCF-A/top", "field-top"} else 5 if paper.venue_tier == "other" else 0
        haystack = f"{candidate.title} {candidate.abstract}".lower()
        matched = 0
        total = 0
        for tag in tags:
            terms = [term.strip().lower() for term in re.split(r"\s+OR\s+", tag.query, flags=re.I)]
            total += 1
            if any(term in haystack for term in terms):
                matched += 1
        relevance = 20 * matched / max(total, 1)
        reproducibility = 5 if "github.com" in (candidate.comment or "").lower() else 0
        return round(recency + venue + relevance + reproducibility, 3)

    async def _enrich_selected(self, papers: list[Paper]) -> None:
        llm = LLMClient(self.db)
        if not llm.configured:
            for paper in papers:
                paper.ai_status = "pending_configuration"
            self.db.commit()
            return

        async def analyze(paper: Paper) -> tuple[int, dict[str, Any] | Exception]:
            try:
                return paper.id, await llm.analyze_paper(paper.title_en, paper.abstract_en)
            except Exception as exc:
                return paper.id, exc

        results = await asyncio.gather(*(analyze(paper) for paper in papers))
        for paper_id, result in results:
            paper = self.db.get(Paper, paper_id)
            if isinstance(result, Exception):
                paper.ai_status = "failed"
                continue
            paper.title_zh = result.get("title_zh")
            paper.abstract_zh = result.get("abstract_zh")
            paper.summary_json = json.dumps(result, ensure_ascii=False)
            paper.ai_status = "completed"
        self.db.commit()

    async def _enrich_candidate_metadata(self, candidates: list[PaperCandidate]) -> None:
        semaphore = asyncio.Semaphore(4)

        async def enrich(candidate: PaperCandidate) -> None:
            async with semaphore:
                try:
                    metadata = await self.s2.enrich(candidate)
                except Exception:
                    return
            if not metadata:
                return
            candidate.semantic_scholar_id = metadata.get("paperId")
            external_ids = metadata.get("externalIds") or {}
            candidate.doi = candidate.doi or external_ids.get("DOI")
            publication_venue = metadata.get("publicationVenue") or {}
            candidate.venue_hint = publication_venue.get("name") or metadata.get("venue") or candidate.venue_hint

        await asyncio.gather(*(enrich(candidate) for candidate in candidates))

    async def _apply_llm_rerank(self, ranked: list[tuple[Paper, float]], tags: list[Tag], count: int, settings: dict[str, Any], profile_description: str | None = None) -> bool:
        self._last_relation_assessments = {}
        llm = LLMClient(self.db)
        if not settings.get("llm_rerank_enabled", True) or not llm.configured or not ranked:
            return False
        pool = sorted(ranked, key=lambda item: item[1], reverse=True)[: min(30, max(12, count * 4))]
        payload = [{
            "paper_id": paper.id,
            "title": paper.title_en,
            "abstract": paper.abstract_en,
            "published_at": paper.published_at.isoformat() if paper.published_at else None,
            "venue": paper.venue_name or "arXiv preprint",
            "rule_score": rule_score,
        } for paper, rule_score in pool]
        try:
            preferences = profile_description or ", ".join(f"{tag.name_en} / {tag.name_zh}" for tag in tags)
            assessments = await llm.rank_papers(payload, preferences)
        except Exception:
            return False
        assessment_by_id = {int(item["paper_id"]): item for item in assessments if str(item.get("paper_id", "")).isdigit()}
        weight = float(settings.get("llm_rerank_weight", 0.45))
        for index, (paper, rule_score) in enumerate(ranked):
            item = assessment_by_id.get(paper.id)
            if not item:
                continue
            taste = _bounded_score(item.get("taste_score"))
            novelty = _bounded_score(item.get("novelty_score"))
            value = _bounded_score(item.get("value_score"))
            confidence = _bounded_score(item.get("confidence"))
            llm_quality = taste * 0.45 + value * 0.35 + novelty * 0.20
            confidence_factor = 0.75 + confidence / 400
            final_score = rule_score * (1 - weight) + llm_quality * confidence_factor * weight
            ranked[index] = (paper, round(final_score, 3))
            assessment = paper.recommendation_assessment or RecommendationAssessment(paper_id=paper.id)
            assessment.taste_score = taste
            assessment.novelty_score = novelty
            assessment.value_score = value
            assessment.confidence = confidence
            assessment.reason = str(item.get("reason") or "")[:2000]
            assessment.caution = str(item.get("caution") or "")[:1000] or None
            assessment.model = llm.model
            self.db.add(assessment)
            if profile_description:
                self._last_relation_assessments[paper.id] = {
                    "relevance_score": _bounded_score(item.get("relevance_score")),
                    "confidence": confidence,
                    "matched_concepts": [str(value)[:160] for value in (item.get("matched_concepts") or [])[:8]],
                    "reason": str(item.get("relation_reason") or item.get("reason") or "")[:2000],
                }
        self.db.commit()
        return bool(assessment_by_id)


    async def retry_ai(self, paper: Paper) -> Paper:
        llm = LLMClient(self.db)
        result = await llm.analyze_paper(paper.title_en, paper.abstract_en)
        paper.title_zh = result.get("title_zh")
        paper.abstract_zh = result.get("abstract_zh")
        paper.summary_json = json.dumps(result, ensure_ascii=False)
        paper.ai_status = "completed"
        self.db.commit()
        return paper


def _bounded_score(value: Any) -> float:
    try:
        return min(100.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
