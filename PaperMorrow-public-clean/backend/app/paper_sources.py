from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from .config import runtime_settings


ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


@dataclass
class PaperCandidate:
    title: str
    abstract: str
    authors: list[str]
    published_at: datetime
    updated_at: datetime
    arxiv_id: str
    primary_url: str
    pdf_url: str | None
    categories: list[str] = field(default_factory=list)
    doi: str | None = None
    venue_hint: str | None = None
    comment: str | None = None
    semantic_scholar_id: str | None = None


class ArxivSource:
    endpoint = "https://export.arxiv.org/api/query"

    async def fetch(self, categories: list[str], keywords: list[str], limit: int) -> list[PaperCandidate]:
        categories = sorted(set(categories))
        cat_query = " OR ".join(f"cat:{item}" for item in categories)
        keyword_query = " OR ".join(f'all:"{word}"' for word in keywords[:8] if word)
        query = f"({cat_query})" if cat_query else "cat:cs.AI"
        if keyword_query:
            query = f"{query} AND ({keyword_query})"
        params = {
            "search_query": query,
            "start": 0,
            "max_results": min(max(limit, 10), 200),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        headers = {"User-Agent": "PaperMorrow/0.3 (local research assistant)"}
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.get(self.endpoint, params=params, headers=headers)
            response.raise_for_status()
        return self._parse(response.text)

    async def search(self, query: str, limit: int = 20) -> list[PaperCandidate]:
        query = query.strip()
        if not query:
            return []
        arxiv_id = _extract_arxiv_id(query)
        search_query = f"id:{arxiv_id}" if arxiv_id else f'all:"{query[:300]}"'
        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": min(max(limit, 1), 50),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        headers = {"User-Agent": "PaperMorrow/0.4 (local research assistant)"}
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.get(self.endpoint, params=params, headers=headers)
            response.raise_for_status()
        return self._parse(response.text)

    def _parse(self, content: str) -> list[PaperCandidate]:
        root = ET.fromstring(content)
        results: list[PaperCandidate] = []
        for entry in root.findall("atom:entry", ARXIV_NS):
            url = _text(entry, "atom:id")
            arxiv_id = re.sub(r"v\d+$", "", url.rsplit("/", 1)[-1])
            links = {link.attrib.get("type", ""): link.attrib.get("href", "") for link in entry.findall("atom:link", ARXIV_NS)}
            authors = [_text(author, "atom:name") for author in entry.findall("atom:author", ARXIV_NS)]
            comment = _optional_text(entry, "arxiv:comment")
            journal_ref = _optional_text(entry, "arxiv:journal_ref")
            venue_hint = journal_ref
            if not venue_hint and comment and re.search(r"\b(accepted|to appear|published)\b", comment, re.I):
                venue_hint = comment
            results.append(
                PaperCandidate(
                    title=" ".join(_text(entry, "atom:title").split()),
                    abstract=" ".join(_text(entry, "atom:summary").split()),
                    authors=authors,
                    published_at=datetime.fromisoformat(_text(entry, "atom:published").replace("Z", "+00:00")),
                    updated_at=datetime.fromisoformat(_text(entry, "atom:updated").replace("Z", "+00:00")),
                    arxiv_id=arxiv_id,
                    primary_url=url,
                    pdf_url=links.get("application/pdf") or f"https://arxiv.org/pdf/{arxiv_id}",
                    categories=[item.attrib.get("term", "") for item in entry.findall("atom:category", ARXIV_NS)],
                    doi=_optional_text(entry, "arxiv:doi"),
                    venue_hint=venue_hint,
                    comment=comment,
                )
            )
        return results


class SemanticScholarSource:
    graph_url = "https://api.semanticscholar.org/graph/v1"
    recommendation_url = "https://api.semanticscholar.org/recommendations/v1"

    def _headers(self) -> dict[str, str]:
        key = runtime_settings.semantic_scholar_api_key
        return {"x-api-key": key} if key else {}

    async def enrich(self, candidate: PaperCandidate) -> dict[str, Any]:
        fields = "paperId,title,abstract,venue,publicationVenue,publicationDate,externalIds,url"
        url = f"{self.graph_url}/paper/ARXIV:{candidate.arxiv_id}"
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get(url, params={"fields": fields}, headers=self._headers())
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()

    async def search(self, query: str, limit: int = 20) -> list[PaperCandidate]:
        fields = "paperId,title,abstract,authors,year,publicationDate,venue,publicationVenue,externalIds,url,openAccessPdf"
        url = f"{self.graph_url}/paper/search"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params={"query": query[:500], "limit": min(max(limit, 1), 50), "fields": fields}, headers=self._headers())
        if response.status_code in {400, 404, 429}:
            return []
        response.raise_for_status()
        results: list[PaperCandidate] = []
        for item in response.json().get("data", []):
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            external = item.get("externalIds") or {}
            arxiv_id = str(external.get("ArXiv") or "").strip()
            paper_id = str(item.get("paperId") or "")
            published = item.get("publicationDate") or (f"{item['year']}-01-01" if item.get("year") else None)
            try:
                published_at = datetime.fromisoformat(published).astimezone() if published else datetime.now().astimezone()
            except ValueError:
                published_at = datetime.now().astimezone()
            primary_url = str(item.get("url") or (f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else ""))
            if not primary_url:
                continue
            venue = (item.get("publicationVenue") or {}).get("name") or item.get("venue")
            pdf_url = (item.get("openAccessPdf") or {}).get("url")
            results.append(PaperCandidate(
                title=title,
                abstract=str(item.get("abstract") or ""),
                authors=[str(author.get("name") or "") for author in item.get("authors") or [] if author.get("name")],
                published_at=published_at,
                updated_at=published_at,
                arxiv_id=arxiv_id,
                primary_url=primary_url,
                pdf_url=pdf_url,
                doi=external.get("DOI"),
                venue_hint=venue,
                semantic_scholar_id=paper_id or None,
            ))
        return results

    async def related(self, paper_identifier: str, limit: int = 12) -> list[dict[str, Any]]:
        fields = "paperId,title,url,authors,year,venue,externalIds"
        similar_url = f"{self.recommendation_url}/papers/forpaper/{paper_identifier}"
        references_url = f"{self.graph_url}/paper/{paper_identifier}/references"
        citations_url = f"{self.graph_url}/paper/{paper_identifier}/citations"
        async with httpx.AsyncClient(timeout=30) as client:
            responses = await asyncio.gather(
                client.get(similar_url, params={"limit": limit, "fields": fields}, headers=self._headers()),
                client.get(references_url, params={"limit": 6, "fields": fields}, headers=self._headers()),
                client.get(citations_url, params={"limit": 6, "fields": fields}, headers=self._headers()),
                return_exceptions=True,
            )
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, response in enumerate(responses):
            if isinstance(response, Exception) or response.status_code in {400, 404, 429}:
                continue
            response.raise_for_status()
            payload = response.json()
            if index == 0:
                papers = payload.get("recommendedPapers", [])
                relation = "similar"
            elif index == 1:
                papers = [row.get("citedPaper", {}) for row in payload.get("data", [])]
                relation = "reference"
            else:
                papers = [row.get("citingPaper", {}) for row in payload.get("data", [])]
                relation = "citation"
            for paper in papers:
                identifier = paper.get("paperId") or paper.get("title")
                if not identifier or identifier in seen:
                    continue
                seen.add(identifier)
                paper["relation"] = relation
                items.append(paper)
        return items


def _text(node: ET.Element, path: str) -> str:
    item = node.find(path, ARXIV_NS)
    return item.text.strip() if item is not None and item.text else ""


def _optional_text(node: ET.Element, path: str) -> str | None:
    value = _text(node, path)
    return value or None


def _extract_arxiv_id(value: str) -> str | None:
    match = re.search(r"(?:arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5})(?:v\d+)?", value, re.I)
    return match.group(1) if match else None
