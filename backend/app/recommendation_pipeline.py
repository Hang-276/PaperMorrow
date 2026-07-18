from __future__ import annotations

import asyncio
import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import LibraryEntry, LocalPaperFile, Paper, Recommendation, ResearchStudyPaper, Tag
from .paper_sources import ArxivSource, PaperCandidate


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def candidate_identity(candidate: PaperCandidate) -> str:
    identity = candidate.doi or candidate.arxiv_id or normalize_title(candidate.title)
    return identity.lower().strip()


def identity_hash(candidate: PaperCandidate) -> str:
    return hashlib.sha256(candidate_identity(candidate).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RecommendationRequest:
    categories: list[str]
    keywords: list[str]
    count: int
    mode: str = "broad"
    profile_name: str | None = None
    focused_keywords: list[str] = field(default_factory=list)


@dataclass
class RecommendationContext:
    tags: list[Tag]
    count: int
    mode: str
    settings: dict[str, Any]
    profile: Any | None = None
    exclusions: list[str] = field(default_factory=list)
    preferences: str | None = None


@dataclass
class CandidateFeatures:
    values: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class RankedCandidate:
    candidate: PaperCandidate
    paper: Paper
    features: CandidateFeatures
    rule_score: float
    final_score: float
    relation: dict[str, Any] = field(default_factory=dict)
    lane: str = "broad"


@dataclass
class RecommendationResult:
    items: list[RankedCandidate]
    reranker_used: bool = False
    degraded: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CandidateSource(Protocol):
    async def collect(self, request: RecommendationRequest) -> list[PaperCandidate]: ...


@runtime_checkable
class CandidateFilter(Protocol):
    def apply(self, candidates: list[PaperCandidate], context: RecommendationContext) -> list[PaperCandidate]: ...


@runtime_checkable
class FeatureProvider(Protocol):
    def provide(self, candidate: PaperCandidate, context: RecommendationContext) -> RankedCandidate: ...


@runtime_checkable
class Ranker(Protocol):
    def rank(self, candidates: list[RankedCandidate], context: RecommendationContext) -> list[RankedCandidate]: ...


@runtime_checkable
class Reranker(Protocol):
    async def rerank(self, candidates: list[RankedCandidate], context: RecommendationContext) -> bool: ...


@runtime_checkable
class Selector(Protocol):
    def select(self, candidates: list[RankedCandidate], context: RecommendationContext, reranker_used: bool) -> RecommendationResult: ...


class ArxivCandidateSource:
    def __init__(self, source: ArxivSource):
        self.source = source

    async def collect(self, request: RecommendationRequest) -> list[PaperCandidate]:
        if request.profile_name and request.mode != "broad":
            focused, broad = await asyncio.gather(
                self.source.fetch(request.categories, request.focused_keywords or [request.profile_name], max(60, request.count * 15)),
                self.source.fetch(request.categories, [], max(40, request.count * 8)),
            )
            combined = [*focused, *broad]
        else:
            combined = await self.source.fetch(request.categories, request.keywords, max(60, request.count * 15))
        unique: dict[str, PaperCandidate] = {}
        for candidate in combined:
            unique.setdefault(candidate_identity(candidate), candidate)
        return list(unique.values())


class PermanentCandidateFilter:
    """Excludes every paper already surfaced anywhere in the local-first workspace."""

    def __init__(self, db: Session, resolve_existing: Callable[[PaperCandidate], Paper | None]):
        self.db = db
        self.resolve_existing = resolve_existing

    def apply(self, candidates: list[PaperCandidate], context: RecommendationContext) -> list[PaperCandidate]:
        seen_paper_ids = set(self.db.scalars(select(Recommendation.paper_id)))
        seen_paper_ids.update(self.db.scalars(select(LibraryEntry.paper_id)))
        seen_paper_ids.update(self.db.scalars(select(ResearchStudyPaper.paper_id)))
        seen_paper_ids.update(self.db.scalars(select(LocalPaperFile.paper_id)))
        unique_identities: set[str] = set()
        accepted: list[PaperCandidate] = []
        exclusions = [term.lower().strip() for term in context.exclusions if term.strip()]
        for candidate in candidates:
            haystack = f"{candidate.title} {candidate.abstract}".lower()
            if exclusions and any(term in haystack for term in exclusions):
                continue
            identity = candidate_identity(candidate)
            if not identity or identity in unique_identities:
                continue
            unique_identities.add(identity)
            existing = self.resolve_existing(candidate)
            if existing is not None and existing.id in seen_paper_ids:
                continue
            accepted.append(candidate)
        return accepted


class DefaultFeatureProvider:
    def __init__(
        self,
        upsert: Callable[[PaperCandidate, list[Tag]], Paper],
        score: Callable[[PaperCandidate, Paper, list[Tag]], float],
        relation: Callable[[PaperCandidate], dict[str, Any]] | None = None,
    ):
        self.upsert = upsert
        self.score = score
        self.relation = relation

    def provide(self, candidate: PaperCandidate, context: RecommendationContext) -> RankedCandidate:
        paper = self.upsert(candidate, context.tags)
        rule_score = self.score(candidate, paper, context.tags)
        paper.relevance_score = rule_score
        return RankedCandidate(
            candidate=candidate,
            paper=paper,
            features=CandidateFeatures(values={"rule_score": rule_score}),
            rule_score=rule_score,
            final_score=rule_score,
            relation=self.relation(candidate) if self.relation else {},
        )


class RuleRanker:
    def rank(self, candidates: list[RankedCandidate], context: RecommendationContext) -> list[RankedCandidate]:
        return sorted(candidates, key=lambda item: item.rule_score, reverse=True)


class CallbackReranker:
    def __init__(self, callback: Callable[[list[RankedCandidate], RecommendationContext], Awaitable[bool]]):
        self.callback = callback

    async def rerank(self, candidates: list[RankedCandidate], context: RecommendationContext) -> bool:
        return await self.callback(candidates, context)


class DefaultSelector:
    def select(self, candidates: list[RankedCandidate], context: RecommendationContext, reranker_used: bool) -> RecommendationResult:
        profile = context.profile
        broad_scores = {item.paper.id: item.final_score for item in candidates}
        if profile and context.mode != "broad":
            relevance_weight = profile.relevance_weight
            recency_weight = profile.recency_weight
            quality_weight = max(0.05, 1 - relevance_weight - recency_weight)
            for item in candidates:
                relevance = float(item.relation.get("relevance_score", 0))
                published = item.paper.published_at or datetime.now(timezone.utc)
                age_days = max(0, (datetime.now(timezone.utc) - published).days)
                recency = 100 * math.exp(-age_days / 120)
                item.final_score = round(relevance * relevance_weight + recency * recency_weight + min(100, item.final_score) * quality_weight, 3)
        ranked = sorted(candidates, key=lambda item: item.final_score, reverse=True)
        top_tiers = {"CCF-A/top", "field-top"}
        top = [item for item in ranked if item.paper.venue_tier in top_tiers]
        frontier = [item for item in ranked if item.paper.venue_tier not in top_tiers]
        if profile and context.mode in {"focus", "mixed"}:
            if context.mode == "mixed":
                explore_count = min(context.count, round(context.count * profile.exploration_ratio))
                chosen = ranked[: context.count - explore_count]
                chosen_ids = {item.paper.id for item in chosen}
                explore_pool = sorted((item for item in ranked if item.paper.id not in chosen_ids), key=lambda item: broad_scores.get(item.paper.id, 0), reverse=True)
                explored = explore_pool[:explore_count]
                chosen.extend(explored)
                explored_ids = {item.paper.id for item in explored}
            else:
                chosen = ranked[: context.count]
                explored_ids = set()
            for item in chosen:
                relevance = float(item.relation.get("relevance_score", 0))
                item.lane = "explore" if item.paper.id in explored_ids else "focused" if relevance >= 70 else "adjacent"
        elif context.settings.get("only_verified_top_venues"):
            chosen = top[: context.count]
        else:
            top_target = round(context.count * float(context.settings.get("top_venue_ratio", 0.7)))
            chosen = [*top[:top_target], *frontier[: context.count - min(top_target, len(top))]]
            if len(chosen) < context.count:
                selected_ids = {item.paper.id for item in chosen}
                chosen.extend(item for item in ranked if item.paper.id not in selected_ids)
                chosen = chosen[: context.count]
        return RecommendationResult(
            items=chosen,
            reranker_used=reranker_used,
            degraded=not reranker_used,
            diagnostics={"candidate_count": len(candidates), "selected_count": len(chosen)},
        )
