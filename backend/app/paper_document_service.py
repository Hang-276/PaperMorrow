from __future__ import annotations

import asyncio
from io import BytesIO
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader
from sqlalchemy.orm import Session

from .models import Paper, PaperDocument


MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PAGES = 100
MAX_TEXT_CHARS = 180_000
TRUSTED_PDF_HOSTS = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}


async def get_or_extract_paper_text(db: Session, paper: Paper) -> str | None:
    existing = db.get(PaperDocument, paper.id)
    if existing and existing.status == "completed":
        return existing.full_text
    if existing and existing.status == "failed":
        return None
    if not paper.pdf_url or not _trusted_pdf_url(paper.pdf_url):
        return None
    document = existing or PaperDocument(paper_id=paper.id, source_url=paper.pdf_url, status="processing")
    document.status = "processing"
    db.add(document)
    db.commit()
    try:
        pdf_bytes = await _download_pdf(paper.pdf_url)
        text, page_count = await asyncio.to_thread(_extract_text, pdf_bytes)
        document.full_text = text
        document.page_count = page_count
        document.status = "completed"
        document.error = None
        db.commit()
        return text
    except Exception as exc:
        document.status = "failed"
        document.error = str(exc)[:1000]
        db.commit()
        return None


def _trusted_pdf_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in TRUSTED_PDF_HOSTS


async def _download_pdf(url: str) -> bytes:
    headers = {"User-Agent": "PaperMorrow/0.3 (local research assistant)"}
    chunks: list[bytes] = []
    total = 0
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        async with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                raise ValueError("目标不是 PDF")
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_PDF_BYTES:
                    raise ValueError("PDF 超过 25MB 安全限制")
                chunks.append(chunk)
    return b"".join(chunks)


def _extract_text(content: bytes) -> tuple[str, int]:
    reader = PdfReader(BytesIO(content), strict=False)
    parts: list[str] = []
    size = 0
    pages = min(len(reader.pages), MAX_PAGES)
    for index in range(pages):
        text = reader.pages[index].extract_text() or ""
        if not text.strip():
            continue
        remaining = MAX_TEXT_CHARS - size
        if remaining <= 0:
            break
        excerpt = text[:remaining]
        parts.append(f"\n--- Page {index + 1} ---\n{excerpt}")
        size += len(excerpt)
    if not parts:
        raise ValueError("PDF 未能提取到文本")
    return "".join(parts), pages
