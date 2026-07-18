from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path

from .config import DATA_DIR
from .models import Paper
from .paper_document_service import _download_pdf, _trusted_pdf_url


PDF_CACHE_DIR = DATA_DIR / "pdf_cache"
READER_ASSET_DIR = DATA_DIR / "reader_assets"
PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
READER_ASSET_DIR.mkdir(parents=True, exist_ok=True)


async def cached_pdf_path(paper: Paper) -> Path:
    if not paper.pdf_url or not _trusted_pdf_url(paper.pdf_url):
        raise ValueError("该论文没有可安全读取的公开 PDF")
    path = PDF_CACHE_DIR / f"paper-{paper.id}.pdf"
    if path.exists() and path.stat().st_size > 100:
        return path
    content = await _download_pdf(paper.pdf_url)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    return path


def save_reader_figure(paper_id: int, data_url: str) -> tuple[str, Path]:
    match = re.fullmatch(r"data:image/png;base64,([A-Za-z0-9+/=\s]+)", data_url)
    if not match:
        raise ValueError("插图必须是 PNG 图像")
    try:
        content = base64.b64decode(match.group(1), validate=True)
    except ValueError as exc:
        raise ValueError("插图数据无效") from exc
    if len(content) > 6 * 1024 * 1024:
        raise ValueError("插图不能超过 6MB")
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("插图格式无效")
    folder = READER_ASSET_DIR / str(paper_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"figure-{uuid.uuid4().hex}.png"
    path = folder / name
    path.write_bytes(content)
    return name, path


def reader_figure_path(paper_id: int, name: str) -> Path | None:
    if not re.fullmatch(r"figure-[a-f0-9]{32}\.png", name):
        return None
    path = READER_ASSET_DIR / str(paper_id) / name
    return path if path.is_file() else None
