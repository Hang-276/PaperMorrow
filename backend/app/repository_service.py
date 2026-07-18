from __future__ import annotations

import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .models import Paper
from .settings_service import get_secret


GITHUB_URL_RE = re.compile(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", re.I)


class RepositoryService:
    def __init__(self, db: Session):
        self.db = db

    async def discover(self, paper: Paper) -> dict[str, Any]:
        explicit = GITHUB_URL_RE.findall(f"{paper.abstract_en} {paper.primary_url}")
        if explicit:
            paper.repository_url = explicit[0].rstrip(".,)")
            paper.repository_status = "verified"
            self.db.commit()
            return {"status": paper.repository_status, "repository_url": paper.repository_url, "candidates": []}

        token = get_secret("github_token")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        queries = [f'"{paper.title_en}"', paper.arxiv_id or ""]
        candidates: dict[str, dict[str, Any]] = {}
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for query in queries:
                if not query:
                    continue
                response = await client.get("https://api.github.com/search/repositories", params={"q": query, "per_page": 5}, headers=headers)
                if response.status_code in {403, 429}:
                    break
                response.raise_for_status()
                for item in response.json().get("items", []):
                    url = item["html_url"]
                    description = item.get("description") or ""
                    text = f"{item['name']} {description}".lower()
                    score = 0
                    if paper.arxiv_id and paper.arxiv_id.lower() in text:
                        score += 70
                    title_tokens = {token for token in re.findall(r"[a-z0-9]+", paper.title_en.lower()) if len(token) > 3}
                    score += min(30, len(title_tokens & set(re.findall(r"[a-z0-9]+", text))) * 4)
                    candidates[url] = {
                        "url": url,
                        "name": item["full_name"],
                        "description": description,
                        "stars": item.get("stargazers_count", 0),
                        "score": score,
                    }
        ranked = sorted(candidates.values(), key=lambda item: (item["score"], item["stars"]), reverse=True)
        if ranked and ranked[0]["score"] >= 70:
            paper.repository_url = ranked[0]["url"]
            paper.repository_status = "verified"
        elif ranked and ranked[0]["score"] >= 20:
            paper.repository_url = ranked[0]["url"]
            paper.repository_status = "candidate"
        else:
            paper.repository_status = "not_found"
        self.db.commit()
        return {"status": paper.repository_status, "repository_url": paper.repository_url, "candidates": ranked}

