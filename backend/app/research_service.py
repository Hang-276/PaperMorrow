from __future__ import annotations

import asyncio
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .catalog import detect_venue
from .llm import LLMClient, LLMNotConfigured
from .models import Paper, PaperStudyState, ResearchStudy, ResearchStudyPaper
from .paper_sources import ArxivSource, PaperCandidate, SemanticScholarSource
from .recommendation import identity_hash, normalize_title


DOMAIN_LABELS = {"ai": "人工智能", "computer": "计算机", "physics": "物理", "math": "数学"}


class ResearchService:
    def __init__(self, db: Session):
        self.db = db
        self.llm = LLMClient(db)
        self.arxiv = ArxivSource()
        self.s2 = SemanticScholarSource()

    async def run(self, domain: str, prompt: str, count: int = 12) -> ResearchStudy:
        study = ResearchStudy(domain=domain, prompt=prompt.strip(), title=prompt.strip()[:160], status="running", model=self.llm.model or None)
        self.db.add(study); self.db.commit(); self.db.refresh(study)
        try:
            if not self.llm.configured:
                raise LLMNotConfigured("调研功能需要先在设置中选择一个可用的 LLM API")
            plan = await self.llm.expand_research_profile(
                f"{DOMAIN_LABELS.get(domain, domain)}专题调研",
                prompt,
                [],
                [],
                [],
            )
            terms = [str(item).strip() for item in plan.get("search_terms", []) if str(item).strip()]
            if not terms:
                terms = [prompt]
            terms = list(dict.fromkeys(terms))[:5]
            study.search_terms_json = json.dumps(terms, ensure_ascii=False)
            study.core_concepts_json = json.dumps(plan.get("core_concepts", []), ensure_ascii=False)
            self.db.commit()

            candidates = await self._search(terms, max(8, min(15, count)))
            if not candidates:
                raise RuntimeError("arXiv 与 Semantic Scholar 暂未返回可用文献")
            papers = [self._upsert(candidate) for candidate in candidates[: max(20, count * 3)]]
            self.db.commit()
            payload = [{
                "paper_id": paper.id,
                "title": paper.title_en,
                "abstract": paper.abstract_en,
                "published_at": paper.published_at.isoformat() if paper.published_at else None,
                "venue": paper.venue_name or "arXiv preprint",
                "rule_score": _base_score(paper),
            } for paper in papers]
            assessments = await self.llm.rank_papers(payload, f"{DOMAIN_LABELS.get(domain, domain)}领域调研：{prompt}")
            by_id = {int(item["paper_id"]): item for item in assessments if str(item.get("paper_id", "")).isdigit()}
            ranked: list[tuple[Paper, dict[str, Any], float]] = []
            for paper in papers:
                item = by_id.get(paper.id, {})
                relevance = _score(item.get("relevance_score"), _lexical_relevance(prompt, paper))
                value = _score(item.get("value_score"), _base_score(paper))
                novelty = _score(item.get("novelty_score"), 45)
                confidence = _score(item.get("confidence"), 45)
                final = relevance * .46 + value * .29 + novelty * .14 + confidence * .06 + _base_score(paper) * .05
                ranked.append((paper, item, round(final, 2)))
            ranked.sort(key=lambda row: row[2], reverse=True)
            for rank, (paper, item, final) in enumerate(ranked[:count], 1):
                study.papers.append(ResearchStudyPaper(
                    paper_id=paper.id, rank=rank, final_score=final,
                    relevance_score=_score(item.get("relevance_score"), _lexical_relevance(prompt, paper)),
                    value_score=_score(item.get("value_score"), _base_score(paper)),
                    novelty_score=_score(item.get("novelty_score"), 45),
                    confidence=_score(item.get("confidence"), 45),
                    matched_concepts_json=json.dumps(item.get("matched_concepts", []), ensure_ascii=False),
                    reason=str(item.get("relation_reason") or item.get("reason") or "根据标题、摘要与调研问题的概念覆盖度排序")[:3000],
                    caution=str(item.get("caution") or "")[:1500] or None,
                ))
            study.status = "completed"
            self.db.commit(); self.db.refresh(study)
            return study
        except Exception as exc:
            study.status = "failed"; study.error = str(exc)[:3000]
            self.db.commit(); self.db.refresh(study)
            return study

    async def generate_review(self, study: ResearchStudy) -> ResearchStudy:
        if study.status != "completed" or not study.papers:
            raise ValueError("调研尚未完成，不能生成综述")
        if not self.llm.configured:
            raise LLMNotConfigured("生成综述需要可用的 LLM API")
        papers = [{
            "title": item.paper.title_en,
            "authors": json.loads(item.paper.authors_json or "[]"),
            "published_at": item.paper.published_at.isoformat() if item.paper.published_at else None,
            "venue": item.paper.venue_name,
            "abstract": item.paper.abstract_en,
            "primary_url": item.paper.primary_url,
            "relevance_score": item.relevance_score,
            "value_score": item.value_score,
        } for item in study.papers]
        study.review_markdown = await self.llm.generate_literature_review(study.prompt, DOMAIN_LABELS.get(study.domain, study.domain), papers)
        self.db.commit(); self.db.refresh(study)
        return study

    async def _search(self, terms: list[str], per_query: int) -> list[PaperCandidate]:
        tasks = []
        for term in terms:
            tasks.extend((self.arxiv.search(term, per_query), self.s2.search(term, per_query)))
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        candidates: list[PaperCandidate] = []
        seen: set[str] = set()
        for response in responses:
            if not isinstance(response, list):
                continue
            for candidate in response:
                key = (candidate.doi or candidate.arxiv_id or candidate.semantic_scholar_id or normalize_title(candidate.title)).casefold()
                if not key or key in seen:
                    continue
                seen.add(key); candidates.append(candidate)
        candidates.sort(key=lambda item: item.published_at, reverse=True)
        return candidates

    def _upsert(self, candidate: PaperCandidate) -> Paper:
        digest = identity_hash(candidate)
        clauses = [Paper.identity_hash == digest]
        if candidate.arxiv_id: clauses.append(Paper.arxiv_id == candidate.arxiv_id)
        if candidate.doi: clauses.append(Paper.doi == candidate.doi)
        if candidate.semantic_scholar_id: clauses.append(Paper.semantic_scholar_id == candidate.semantic_scholar_id)
        paper = self.db.scalar(select(Paper).where(or_(*clauses)))
        venue_name, venue_tier, publication_status = detect_venue(candidate.venue_hint)
        if not paper:
            paper = Paper(
                title_en=candidate.title, abstract_en=candidate.abstract,
                authors_json=json.dumps(candidate.authors, ensure_ascii=False),
                published_at=candidate.published_at, updated_at=candidate.updated_at,
                venue_name=venue_name, venue_tier=venue_tier, publication_status=publication_status,
                arxiv_id=candidate.arxiv_id or None, doi=candidate.doi,
                semantic_scholar_id=candidate.semantic_scholar_id,
                primary_url=candidate.primary_url, pdf_url=candidate.pdf_url,
                source="research", identity_hash=digest,
            )
            paper.study_state = PaperStudyState(learned=False)
            self.db.add(paper); self.db.flush()
        else:
            paper.abstract_en = paper.abstract_en or candidate.abstract
            paper.pdf_url = paper.pdf_url or candidate.pdf_url
            paper.semantic_scholar_id = paper.semantic_scholar_id or candidate.semantic_scholar_id
            if venue_name and not paper.venue_name:
                paper.venue_name, paper.venue_tier, paper.publication_status = venue_name, venue_tier, publication_status
        return paper


def research_study_dict(study: ResearchStudy, include_papers: bool = True) -> dict[str, Any]:
    result = {
        "id": study.id, "domain": study.domain, "prompt": study.prompt, "title": study.title,
        "status": study.status, "search_terms": json.loads(study.search_terms_json or "[]"),
        "core_concepts": json.loads(study.core_concepts_json or "[]"),
        "review_markdown": study.review_markdown, "model": study.model, "error": study.error,
        "created_at": study.created_at.isoformat(), "updated_at": study.updated_at.isoformat(),
        "paper_count": len(study.papers),
    }
    if include_papers:
        result["papers"] = [{
            "rank": item.rank, "final_score": item.final_score,
            "relevance_score": item.relevance_score, "value_score": item.value_score,
            "novelty_score": item.novelty_score, "confidence": item.confidence,
            "matched_concepts": json.loads(item.matched_concepts_json or "[]"),
            "reason": item.reason, "caution": item.caution,
            "paper": {
                "id": item.paper.id, "title_en": item.paper.title_en,
                "abstract_en": item.paper.abstract_en,
                "authors": json.loads(item.paper.authors_json or "[]"),
                "published_at": item.paper.published_at.isoformat() if item.paper.published_at else None,
                "venue_name": item.paper.venue_name, "venue_tier": item.paper.venue_tier,
                "arxiv_id": item.paper.arxiv_id, "doi": item.paper.doi,
                "primary_url": item.paper.primary_url, "pdf_url": item.paper.pdf_url,
                "in_library": item.paper.library_entry is not None,
            },
        } for item in study.papers]
    return result


def _score(value: Any, fallback: float) -> float:
    try: return min(100.0, max(0.0, float(value)))
    except (TypeError, ValueError): return fallback


def _base_score(paper: Paper) -> float:
    venue = 95 if paper.venue_tier in {"CCF-A/top", "field-top"} else 62 if paper.venue_name else 50
    if not paper.published_at: return venue
    date = paper.published_at
    if date.tzinfo is None: date = date.replace(tzinfo=timezone.utc)
    age_days = max(0, (datetime.now(timezone.utc) - date).days)
    recency = 100 * math.exp(-age_days / 730)
    return venue * .65 + recency * .35


def _lexical_relevance(prompt: str, paper: Paper) -> float:
    tokens = {token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", prompt.lower()) if len(token) > 2}
    haystack = f"{paper.title_en} {paper.abstract_en}".lower()
    if not tokens: return 45
    hits = sum(token in haystack for token in tokens)
    return min(85, 25 + hits / max(1, len(tokens)) * 75)
