from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .models import Paper, ZoteroLink
from .settings_service import get_secret, get_settings


class ZoteroError(RuntimeError):
    pass


class ZoteroService:
    api_url = "https://api.zotero.org"

    def __init__(self, db: Session):
        self.db = db
        settings = get_settings(db)
        self.library_type = str(settings.get("zotero_library_type") or "user")
        self.library_id = str(settings.get("zotero_library_id") or "").strip()
        self.collection_key = str(settings.get("zotero_collection_key") or "").strip()
        self.sync_tags = bool(settings.get("zotero_sync_tags", True))
        self.api_key = get_secret("zotero_api_key")

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.library_id and self.library_type in {"user", "group"})

    @property
    def prefix(self) -> str:
        plural = "users" if self.library_type == "user" else "groups"
        return f"/{plural}/{self.library_id}"

    def _headers(self) -> dict[str, str]:
        return {
            "Zotero-API-Key": self.api_key,
            "Zotero-API-Version": "3",
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> dict[str, Any]:
        if not self.configured:
            raise ZoteroError("请先填写 Zotero Library ID 和具有写权限的 API Key")
        async with httpx.AsyncClient(timeout=25) as client:
            key_response = await client.get(f"{self.api_url}/keys/current", headers=self._headers())
            if key_response.status_code == 403:
                raise ZoteroError("Zotero API Key 无效或没有访问权限")
            key_response.raise_for_status()
            library_response = await client.get(f"{self.api_url}{self.prefix}/items/top", params={"limit": 1}, headers=self._headers())
            if library_response.status_code == 403:
                raise ZoteroError("API Key 没有访问该 Zotero Library 的权限")
            library_response.raise_for_status()
        return {"connected": True, "library_type": self.library_type, "library_id": self.library_id}

    async def sync_paper(self, paper: Paper) -> ZoteroLink:
        if not self.configured:
            raise ZoteroError("请先在设置中连接 Zotero")
        async with httpx.AsyncClient(timeout=45) as client:
            link = paper.zotero_link
            remote = None
            if link and link.library_id == self.library_id and link.library_type == self.library_type:
                remote = await self._get_item(client, link.item_key)
            if remote is None:
                remote = await self._find_existing(client, paper)
            payload = await self._item_payload(client, paper)
            if remote:
                item_key = str(remote["key"])
                version = int(remote.get("version") or 0)
                response = await client.patch(
                    f"{self.api_url}{self.prefix}/items/{item_key}",
                    headers={**self._headers(), "If-Unmodified-Since-Version": str(version)},
                    json=payload,
                )
                if response.status_code == 412:
                    remote = await self._get_item(client, item_key)
                    version = int((remote or {}).get("version") or 0)
                    response = await client.patch(
                        f"{self.api_url}{self.prefix}/items/{item_key}",
                        headers={**self._headers(), "If-Unmodified-Since-Version": str(version)},
                        json=payload,
                    )
                self._raise_write_error(response)
            else:
                response = await client.post(
                    f"{self.api_url}{self.prefix}/items",
                    headers={**self._headers(), "Zotero-Write-Token": uuid.uuid4().hex},
                    json=[payload],
                )
                self._raise_write_error(response)
                result = response.json()
                successful = result.get("successful") or result.get("success") or {}
                created = successful.get("0")
                if isinstance(created, dict):
                    item_key = str(created.get("key") or (created.get("data") or {}).get("key") or "")
                else:
                    item_key = str(created or "")
                if not item_key:
                    failed = (result.get("failed") or {}).get("0")
                    raise ZoteroError(f"Zotero 未返回新条目编号：{failed or '未知错误'}")
            remote = await self._get_item(client, item_key)
        data = (remote or {}).get("data") or remote or {}
        links = (remote or {}).get("links") or {}
        alternate = links.get("alternate") or {}
        link = paper.zotero_link or ZoteroLink(paper_id=paper.id, library_type=self.library_type, library_id=self.library_id, item_key=item_key)
        link.library_type = self.library_type
        link.library_id = self.library_id
        link.item_key = item_key
        link.item_version = int(data.get("version") or (remote or {}).get("version") or 0)
        link.item_url = alternate.get("href") or f"http://zotero.org/{'users' if self.library_type == 'user' else 'groups'}/{self.library_id}/items/{item_key}"
        link.sync_status = "synced"
        link.error = None
        link.synced_at = datetime.now(timezone.utc)
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link

    async def _get_item(self, client: httpx.AsyncClient, item_key: str) -> dict[str, Any] | None:
        response = await client.get(f"{self.api_url}{self.prefix}/items/{item_key}", headers=self._headers())
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def _find_existing(self, client: httpx.AsyncClient, paper: Paper) -> dict[str, Any] | None:
        identifier = paper.doi or paper.arxiv_id
        if not identifier:
            return None
        response = await client.get(
            f"{self.api_url}{self.prefix}/items/top",
            params={"q": identifier, "qmode": "everything", "limit": 10},
            headers=self._headers(),
        )
        response.raise_for_status()
        target = identifier.casefold()
        for item in response.json():
            data = item.get("data") or {}
            values = [str(data.get("DOI") or ""), str(data.get("extra") or ""), str(data.get("archiveLocation") or "")]
            if any(target in value.casefold() for value in values):
                return item
        return None

    async def _item_payload(self, client: httpx.AsyncClient, paper: Paper) -> dict[str, Any]:
        item_type = _item_type(paper)
        template_response = await client.get(f"{self.api_url}/items/new", params={"itemType": item_type}, headers={"Zotero-API-Version": "3"})
        if template_response.status_code >= 400 and item_type == "preprint":
            item_type = "journalArticle"
            template_response = await client.get(f"{self.api_url}/items/new", params={"itemType": item_type}, headers={"Zotero-API-Version": "3"})
        template_response.raise_for_status()
        payload = template_response.json()
        payload["itemType"] = item_type
        _set_if_supported(payload, "title", paper.title_en)
        _set_if_supported(payload, "abstractNote", paper.abstract_en)
        _set_if_supported(payload, "url", paper.primary_url)
        _set_if_supported(payload, "date", paper.published_at.date().isoformat() if paper.published_at else "")
        _set_if_supported(payload, "DOI", paper.doi or "")
        _set_if_supported(payload, "publicationTitle", paper.venue_name or "")
        _set_if_supported(payload, "proceedingsTitle", paper.venue_name or "")
        _set_if_supported(payload, "conferenceName", paper.venue_name or "")
        _set_if_supported(payload, "archive", "arXiv" if paper.arxiv_id else "")
        _set_if_supported(payload, "archiveLocation", paper.arxiv_id or "")
        extra = f"arXiv: {paper.arxiv_id}" if paper.arxiv_id else "Imported from PaperMorrow"
        _set_if_supported(payload, "extra", extra)
        payload["creators"] = [{"creatorType": "author", "name": name} for name in _authors(paper)]
        if self.sync_tags:
            user_tags = [tag.name for tag in paper.library_entry.tags] if paper.library_entry else []
            payload["tags"] = [{"tag": name} for name in ["PaperMorrow", *user_tags]]
        if self.collection_key:
            payload["collections"] = [self.collection_key]
        return payload

    @staticmethod
    def _raise_write_error(response: httpx.Response) -> None:
        if response.status_code in {200, 204}:
            return
        if response.status_code == 403:
            raise ZoteroError("Zotero API Key 没有写入该文献库的权限")
        if response.status_code == 409:
            raise ZoteroError("Zotero 文献库暂时被锁定，请稍后重试")
        response.raise_for_status()


def zotero_link_dict(link: ZoteroLink | None) -> dict[str, Any] | None:
    if not link:
        return None
    return {
        "library_type": link.library_type,
        "library_id": link.library_id,
        "item_key": link.item_key,
        "item_version": link.item_version,
        "item_url": link.item_url,
        "sync_status": link.sync_status,
        "error": link.error,
        "synced_at": link.synced_at.isoformat() if link.synced_at else None,
    }


def _set_if_supported(payload: dict[str, Any], key: str, value: Any) -> None:
    if key in payload:
        payload[key] = value


def _authors(paper: Paper) -> list[str]:
    import json
    return [str(item) for item in json.loads(paper.authors_json or "[]") if str(item).strip()]


def _item_type(paper: Paper) -> str:
    if paper.publication_status == "preprint" or not paper.venue_name:
        return "preprint"
    journal_markers = ("JOURNAL", "TRANSACTIONS", "NATURE", "PHYSICAL REVIEW", "ANNALS", "ACTA", "INVENTIONES")
    return "journalArticle" if any(marker in paper.venue_name.upper() for marker in journal_markers) else "conferencePaper"
