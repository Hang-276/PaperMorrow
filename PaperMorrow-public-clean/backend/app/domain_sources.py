from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

import httpx


@runtime_checkable
class DomainSourceAdapter(Protocol):
    slug: str
    label: str
    async def test_connection(self, config: dict[str, Any], client: httpx.AsyncClient | None = None) -> dict[str, Any]: ...


@dataclass(frozen=True)
class HttpSourceAdapter:
    slug: str
    label: str
    probe_url: str
    params: dict[str, str]

    async def test_connection(self, config: dict[str, Any], client: httpx.AsyncClient | None = None) -> dict[str, Any]:
        if config.get("enabled", True) is False:
            return {"ok": True, "adapter": self.slug, "message": "适配器已配置但当前停用"}
        owns_client = client is None
        client = client or httpx.AsyncClient(timeout=8, follow_redirects=True)
        try:
            response = await client.get(str(config.get("base_url") or self.probe_url), params=self.params)
            response.raise_for_status()
            return {"ok": True, "adapter": self.slug, "status_code": response.status_code, "message": f"{self.label} 连接正常"}
        except Exception as exc:
            return {"ok": False, "adapter": self.slug, "message": f"{self.label} 连接失败：{exc}"}
        finally:
            if owns_client:
                await client.aclose()


class FeedSourceAdapter:
    slug = "rss_atom"
    label = "RSS / Atom"

    async def test_connection(self, config: dict[str, Any], client: httpx.AsyncClient | None = None) -> dict[str, Any]:
        url = str(config.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return {"ok": False, "adapter": self.slug, "message": "RSS/Atom 必须提供有效的 http(s) Feed URL"}
        owns_client = client is None
        client = client or httpx.AsyncClient(timeout=8, follow_redirects=True)
        try:
            response = await client.get(url, headers={"Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml"})
            response.raise_for_status()
            sample = response.text[:1000].lower()
            ok = "<rss" in sample or "<feed" in sample
            return {"ok": ok, "adapter": self.slug, "status_code": response.status_code, "message": "Feed 连接正常" if ok else "URL 可访问，但内容不是 RSS/Atom"}
        except Exception as exc:
            return {"ok": False, "adapter": self.slug, "message": f"Feed 连接失败：{exc}"}
        finally:
            if owns_client:
                await client.aclose()


SOURCE_ADAPTERS: dict[str, DomainSourceAdapter] = {
    item.slug: item for item in [
        HttpSourceAdapter("arxiv", "arXiv", "https://export.arxiv.org/api/query", {"search_query": "all:test", "max_results": "1"}),
        HttpSourceAdapter("semantic_scholar", "Semantic Scholar", "https://api.semanticscholar.org/graph/v1/paper/search", {"query": "test", "limit": "1"}),
        HttpSourceAdapter("openalex", "OpenAlex", "https://api.openalex.org/works", {"search": "test", "per-page": "1"}),
        HttpSourceAdapter("crossref", "Crossref", "https://api.crossref.org/works", {"query": "test", "rows": "1"}),
        HttpSourceAdapter("pubmed", "PubMed", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", {"db": "pubmed", "term": "test", "retmax": "1"}),
        HttpSourceAdapter("europe_pmc", "Europe PMC", "https://www.ebi.ac.uk/europepmc/webservices/rest/search", {"query": "test", "pageSize": "1", "format": "json"}),
        FeedSourceAdapter(),
    ]
}


def validate_source_configs(configs: list[dict[str, Any]]) -> None:
    for config in configs:
        adapter = str(config.get("adapter") or "")
        if adapter not in SOURCE_ADAPTERS:
            raise ValueError(f"不支持数据源适配器：{adapter or '未指定'}；普通网页只能作为参考 URL，不能启用自动检索")


async def test_source_config(config: dict[str, Any], client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    validate_source_configs([config])
    return await SOURCE_ADAPTERS[str(config["adapter"])].test_connection(config, client)
