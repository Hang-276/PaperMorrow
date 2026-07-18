from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .catalog import detect_venue
from .models import LibraryEntry, Paper, PaperNote, PaperStudyState
from .paper_sources import ArxivSource, PaperCandidate, SemanticScholarSource
from .recommendation import identity_hash, normalize_title


class LibraryService:
    def __init__(self, db: Session):
        self.db = db
        self.arxiv = ArxivSource()
        self.semantic_scholar = SemanticScholarSource()

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        query = query.strip()
        if len(query) < 2:
            return []
        local = self._local_search(query, limit)
        external_limit = min(20, max(6, limit))
        arxiv_result, semantic_result = await asyncio.gather(
            self.arxiv.search(query, external_limit),
            self.semantic_scholar.search(query, external_limit),
            return_exceptions=True,
        )
        candidates = [
            *(arxiv_result if isinstance(arxiv_result, list) else []),
            *(semantic_result if isinstance(semantic_result, list) else []),
        ]
        results = list(local)
        seen = {key for item in results for key in _result_keys(item)}
        seen_paper_ids = {item["paper_id"] for item in results if item.get("paper_id")}
        for candidate in candidates:
            existing = self._find_existing(candidate)
            keys = _candidate_keys(candidate)
            if keys & seen or (existing and existing.id in seen_paper_ids):
                continue
            result = candidate_dict(candidate, existing)
            results.append(result)
            seen.update(keys)
            if existing:
                seen_paper_ids.add(existing.id)
            if len(results) >= limit:
                break
        return results[:limit]

    def import_candidate(self, values: dict[str, Any]) -> Paper:
        arxiv_id = _clean_arxiv_id(values.get("arxiv_id"))
        candidate = PaperCandidate(
            title=str(values["title"]).strip(),
            abstract=str(values.get("abstract") or "").strip(),
            authors=[str(item).strip() for item in values.get("authors") or [] if str(item).strip()],
            published_at=values.get("published_at") or datetime.now(timezone.utc),
            updated_at=values.get("updated_at") or values.get("published_at") or datetime.now(timezone.utc),
            arxiv_id=arxiv_id or "",
            primary_url=str(values["primary_url"]),
            pdf_url=str(values["pdf_url"]) if values.get("pdf_url") else None,
            doi=_clean_identifier(values.get("doi")),
            venue_hint=values.get("venue"),
            semantic_scholar_id=_clean_identifier(values.get("semantic_scholar_id")),
        )
        paper = self._find_existing(candidate)
        if paper is None:
            venue_name, venue_tier, publication_status = detect_venue(candidate.venue_hint)
            paper = Paper(
                title_en=candidate.title,
                abstract_en=candidate.abstract,
                authors_json=_json_list(candidate.authors),
                published_at=candidate.published_at,
                updated_at=candidate.updated_at,
                venue_name=venue_name,
                venue_tier=venue_tier,
                publication_status=publication_status,
                arxiv_id=arxiv_id,
                doi=candidate.doi,
                semantic_scholar_id=candidate.semantic_scholar_id,
                primary_url=candidate.primary_url,
                pdf_url=candidate.pdf_url,
                source=str(values.get("source") or "arxiv"),
                identity_hash=identity_hash(candidate),
            )
            paper.study_state = PaperStudyState(learned=False)
            self.db.add(paper)
            self.db.flush()
        else:
            if not paper.abstract_en and candidate.abstract:
                paper.abstract_en = candidate.abstract
            paper.pdf_url = paper.pdf_url or candidate.pdf_url
            paper.doi = paper.doi or candidate.doi
            paper.semantic_scholar_id = paper.semantic_scholar_id or candidate.semantic_scholar_id
        self.add_paper(paper, str(values.get("source") or "search"))
        self.db.commit()
        self.db.refresh(paper)
        return paper

    def add_paper(self, paper: Paper, source: str = "manual") -> LibraryEntry:
        entry = paper.library_entry or LibraryEntry(paper_id=paper.id, source=source[:32])
        self.db.add(entry)
        self.db.flush()
        return entry

    def _find_existing(self, candidate: PaperCandidate) -> Paper | None:
        clauses = [Paper.identity_hash == identity_hash(candidate)]
        if candidate.arxiv_id:
            clauses.append(Paper.arxiv_id == _clean_arxiv_id(candidate.arxiv_id))
        if candidate.doi:
            clauses.append(Paper.doi == candidate.doi)
        if candidate.semantic_scholar_id:
            clauses.append(Paper.semantic_scholar_id == candidate.semantic_scholar_id)
        return self.db.scalar(select(Paper).where(or_(*clauses)))

    def _local_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        pattern = f"%{query}%"
        rows = self.db.scalars(
            select(Paper).where(or_(
                Paper.title_en.ilike(pattern),
                Paper.title_zh.ilike(pattern),
                Paper.abstract_en.ilike(pattern),
                Paper.arxiv_id.ilike(pattern),
                Paper.doi.ilike(pattern),
            )).order_by(Paper.published_at.desc()).limit(limit)
        ).all()
        return [local_paper_result(row) for row in rows]


def ensure_library_membership_migration(db: Session) -> None:
    papers = db.scalars(
        select(Paper)
        .outerjoin(LibraryEntry, LibraryEntry.paper_id == Paper.id)
        .outerjoin(PaperStudyState, PaperStudyState.paper_id == Paper.id)
        .outerjoin(PaperNote, PaperNote.paper_id == Paper.id)
        .where(
            LibraryEntry.paper_id.is_(None),
            or_(PaperStudyState.learned.is_(True), PaperNote.content.is_not(None) & (PaperNote.content != "")),
        )
    ).all()
    for paper in papers:
        db.add(LibraryEntry(paper_id=paper.id, source="migration"))
    if papers:
        db.commit()


def local_paper_result(paper: Paper) -> dict[str, Any]:
    return {
        "identity": f"paper:{paper.id}",
        "paper_id": paper.id,
        "title": paper.title_en,
        "abstract": paper.abstract_en,
        "authors": json.loads(paper.authors_json or "[]"),
        "published_at": paper.published_at.isoformat() if paper.published_at else None,
        "updated_at": paper.updated_at.isoformat() if paper.updated_at else None,
        "arxiv_id": paper.arxiv_id,
        "doi": paper.doi,
        "semantic_scholar_id": paper.semantic_scholar_id,
        "primary_url": paper.primary_url,
        "pdf_url": paper.pdf_url,
        "venue": paper.venue_name,
        "source": "local",
        "in_library": paper.library_entry is not None,
    }


def candidate_dict(candidate: PaperCandidate, existing: Paper | None = None) -> dict[str, Any]:
    return {
        "identity": _candidate_identity(candidate),
        "paper_id": existing.id if existing else None,
        "title": candidate.title,
        "abstract": candidate.abstract,
        "authors": candidate.authors,
        "published_at": candidate.published_at.isoformat(),
        "updated_at": candidate.updated_at.isoformat(),
        "arxiv_id": _clean_arxiv_id(candidate.arxiv_id),
        "doi": candidate.doi,
        "semantic_scholar_id": candidate.semantic_scholar_id,
        "primary_url": candidate.primary_url,
        "pdf_url": candidate.pdf_url,
        "venue": candidate.venue_hint,
        "source": "arxiv" if candidate.arxiv_id else "semantic_scholar",
        "in_library": bool(existing and existing.library_entry),
    }


def normalize_library_tag(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _candidate_identity(candidate: PaperCandidate) -> str:
    value = candidate.doi or _clean_arxiv_id(candidate.arxiv_id) or candidate.semantic_scholar_id or normalize_title(candidate.title)
    return hashlib.sha256(str(value).casefold().encode()).hexdigest()


def _candidate_keys(candidate: PaperCandidate) -> set[str]:
    values = {
        _clean_identifier(candidate.doi),
        _clean_arxiv_id(candidate.arxiv_id),
        _clean_identifier(candidate.semantic_scholar_id),
        normalize_title(candidate.title),
    }
    return {str(value).casefold() for value in values if value}


def _result_keys(item: dict[str, Any]) -> set[str]:
    values = {
        _clean_identifier(item.get("doi")),
        _clean_arxiv_id(item.get("arxiv_id")),
        _clean_identifier(item.get("semantic_scholar_id")),
        normalize_title(str(item.get("title") or "")),
    }
    return {str(value).casefold() for value in values if value}


def _clean_arxiv_id(value: Any) -> str | None:
    if not value:
        return None
    match = re.search(r"(\d{4}\.\d{4,5})(?:v\d+)?", str(value))
    return match.group(1) if match else None


def _clean_identifier(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _json_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)
