from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .config import DATA_DIR
from .models import LibraryEntry, LibraryFolder, LibraryTag, LocalPaperFile, Paper, PaperStudyState
from .recommendation import normalize_title
from .settings_service import get_settings, update_settings


INVALID_FOLDER_CHARS = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
ARXIV_PATTERN = re.compile(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b", re.I)
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


class LibraryFolderService:
    def __init__(self, db: Session):
        self.db = db

    def root_path(self) -> Path:
        configured = str(get_settings(self.db).get("library_root") or "").strip()
        root = Path(configured).expanduser() if configured else DATA_DIR / "library_vault"
        root = root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def set_root(self, value: str) -> Path:
        root = Path(value).expanduser().resolve() if value.strip() else (DATA_DIR / "library_vault").resolve()
        root.mkdir(parents=True, exist_ok=True)
        update_settings(self.db, {"library_root": str(root)})
        return root

    def sync_folder_tree(self) -> list[LibraryFolder]:
        root = self.root_path()
        root_row = self._ensure_folder(root, root, None)
        rows_by_path = {".": root_row}
        directories = sorted(
            (path for path in root.rglob("*") if path.is_dir() and not any(part.startswith(".") for part in path.relative_to(root).parts)),
            key=lambda path: len(path.relative_to(root).parts),
        )
        for directory in directories:
            relative = directory.relative_to(root).as_posix()
            parent_relative = directory.parent.relative_to(root).as_posix() or "."
            parent = rows_by_path.get(parent_relative) or root_row
            rows_by_path[relative] = self._ensure_folder(root, directory, parent.id)
        self.db.commit()
        return list(self.db.scalars(select(LibraryFolder).order_by(LibraryFolder.relative_path)).all())

    def create_folder(self, name: str, parent_id: int | None = None) -> LibraryFolder:
        clean_name = INVALID_FOLDER_CHARS.sub("-", name).strip().strip(".")
        if not clean_name or clean_name in {".", ".."}:
            raise ValueError("文件夹名称无效")
        self.sync_folder_tree()
        root = self.root_path()
        parent = self.db.get(LibraryFolder, parent_id) if parent_id else self.db.scalar(select(LibraryFolder).where(LibraryFolder.relative_path == "."))
        if not parent:
            raise ValueError("父文件夹不存在")
        parent_path = root if parent.relative_path == "." else self._resolve_relative(parent.relative_path)
        target = (parent_path / clean_name).resolve()
        self._assert_inside_root(target)
        target.mkdir(parents=False, exist_ok=True)
        row = self._ensure_folder(root, target, parent.id)
        self.db.commit(); self.db.refresh(row)
        return row

    def scan(self, root_path: str | None = None) -> dict[str, Any]:
        if root_path is not None:
            self.set_root(root_path)
        root = self.root_path()
        folders = self.sync_folder_tree()
        folder_by_path = {row.relative_path: row for row in folders}
        imported = updated = skipped = failed = 0
        errors: list[str] = []
        pdfs = sorted(path for path in root.rglob("*.pdf") if path.is_file() and not any(part.startswith(".") for part in path.relative_to(root).parts))
        seen_paths: set[str] = set()
        for path in pdfs:
            relative = path.relative_to(root).as_posix()
            seen_paths.add(relative)
            folder_relative = path.parent.relative_to(root).as_posix() or "."
            folder = folder_by_path.get(folder_relative)
            if not folder:
                failed += 1; errors.append(f"{relative}: 无法识别所属文件夹"); continue
            try:
                outcome = self._import_pdf(path, relative, folder)
                if outcome == "imported": imported += 1
                elif outcome == "updated": updated += 1
                else: skipped += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{relative}: {str(exc)[:240]}")
        for row in self.db.scalars(select(LocalPaperFile)).all():
            if row.relative_path not in seen_paths:
                row.status = "missing"
        self.db.commit()
        return {
            "root_path": str(root), "folders": len(folders), "pdf_files": len(pdfs),
            "imported": imported, "updated": updated, "skipped": skipped,
            "failed": failed, "errors": errors[:30],
        }

    def set_paper_folders(self, paper: Paper, folder_ids: list[int]) -> None:
        entry = paper.library_entry or LibraryEntry(paper_id=paper.id, source="folder")
        self.db.add(entry); self.db.flush()
        folders = list(self.db.scalars(select(LibraryFolder).where(LibraryFolder.id.in_(folder_ids))).all()) if folder_ids else []
        if len(folders) != len(set(folder_ids)):
            raise ValueError("包含不存在的文件夹")
        entry.folders = folders
        self.db.commit()

    def folder_dicts(self) -> list[dict[str, Any]]:
        rows = self.sync_folder_tree()
        return [{
            "id": row.id, "name": row.name, "parent_id": row.parent_id,
            "relative_path": row.relative_path,
            "paper_count": len({entry.paper_id for entry in row.entries} | {item.paper_id for item in row.files if item.status != "missing"}),
            "file_count": sum(item.status != "missing" for item in row.files),
        } for row in rows]

    def knowledge_graph(self) -> dict[str, Any]:
        papers = list(self.db.scalars(select(Paper).join(LibraryEntry).order_by(LibraryEntry.added_at.desc()).limit(250)).unique())
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for paper in papers:
            nodes.append({"id": f"paper:{paper.id}", "type": "paper", "label": paper.title_en, "paper_id": paper.id})
        folder_ids: set[int] = set()
        tag_ids: set[int] = set()
        for paper in papers:
            entry = paper.library_entry
            if not entry:
                continue
            for folder in entry.folders:
                folder_ids.add(folder.id); edges.append({"source": f"folder:{folder.id}", "target": f"paper:{paper.id}", "type": "contains"})
            for local_file in paper.local_files:
                folder_ids.add(local_file.folder_id); edges.append({"source": f"folder:{local_file.folder_id}", "target": f"paper:{paper.id}", "type": "file"})
            for tag in entry.tags:
                tag_ids.add(tag.id); edges.append({"source": f"tag:{tag.id}", "target": f"paper:{paper.id}", "type": "tag"})
        folders = {row.id: row for row in self.db.scalars(select(LibraryFolder).where(LibraryFolder.id.in_(folder_ids))).all()} if folder_ids else {}
        tags = {row.id: row for row in self.db.scalars(select(LibraryTag).where(LibraryTag.id.in_(tag_ids))).all()} if tag_ids else {}
        nodes.extend({"id": f"folder:{row.id}", "type": "folder", "label": row.name} for row in folders.values())
        nodes.extend({"id": f"tag:{row.id}", "type": "tag", "label": row.name, "color": row.color} for row in tags.values())
        title_map: dict[str, Paper] = {}
        for paper in papers:
            for title in (paper.title_en, paper.title_zh or ""):
                if title.strip(): title_map[normalize_title(title)] = paper
        concepts: dict[str, str] = {}
        for paper in papers:
            if not paper.note:
                continue
            for raw_target in WIKI_LINK_PATTERN.findall(paper.note.content or ""):
                target = raw_target.strip()
                linked = title_map.get(normalize_title(target))
                if linked and linked.id != paper.id:
                    edges.append({"source": f"paper:{paper.id}", "target": f"paper:{linked.id}", "type": "wikilink"})
                elif target:
                    concept_id = hashlib.sha256(target.casefold().encode()).hexdigest()[:16]
                    concepts[concept_id] = target
                    edges.append({"source": f"paper:{paper.id}", "target": f"concept:{concept_id}", "type": "concept"})
        nodes.extend({"id": f"concept:{key}", "type": "concept", "label": label} for key, label in list(concepts.items())[:80])
        dedup_edges = list({(edge["source"], edge["target"], edge["type"]): edge for edge in edges}.values())
        return {"nodes": nodes, "edges": dedup_edges}

    def resolve_file(self, file_id: int) -> tuple[LocalPaperFile, Path]:
        row = self.db.get(LocalPaperFile, file_id)
        if not row:
            raise FileNotFoundError("本地 PDF 记录不存在")
        path = self._resolve_relative(row.relative_path)
        if not path.is_file():
            row.status = "missing"; self.db.commit()
            raise FileNotFoundError("本地 PDF 已被移动或删除，请重新扫描")
        return row, path

    def _import_pdf(self, path: Path, relative: str, folder: LibraryFolder) -> str:
        stat = path.stat()
        existing_path = self.db.scalar(select(LocalPaperFile).where(LocalPaperFile.relative_path == relative))
        if existing_path and existing_path.size_bytes == stat.st_size and existing_path.modified_ns == stat.st_mtime_ns:
            existing_path.status = "ready"
            return "skipped"
        digest = _file_sha256(path)
        duplicate = self.db.scalar(select(LocalPaperFile).where(LocalPaperFile.sha256 == digest))
        if duplicate and duplicate.relative_path != relative:
            entry = duplicate.paper.library_entry
            if not entry:
                entry = LibraryEntry(source="local_pdf")
                duplicate.paper.library_entry = entry
            if folder not in entry.folders:
                entry.folders.append(folder)
            old_path = self._resolve_relative(duplicate.relative_path)
            if old_path.is_file():
                return "skipped"
            duplicate.relative_path = relative; duplicate.file_name = path.name; duplicate.folder_id = folder.id
            duplicate.size_bytes = stat.st_size; duplicate.modified_ns = stat.st_mtime_ns; duplicate.status = "ready"
            return "updated"
        metadata = _read_pdf_metadata(path)
        paper = self._find_paper(metadata, digest)
        is_new_paper = paper is None
        if not paper:
            identity_value = metadata["doi"] or metadata["arxiv_id"] or normalize_title(metadata["title"]) or digest
            paper = Paper(
                title_en=metadata["title"], abstract_en=metadata["abstract"],
                authors_json=json.dumps(metadata["authors"], ensure_ascii=False),
                arxiv_id=metadata["arxiv_id"], doi=metadata["doi"],
                primary_url=f"local-file://{relative}", pdf_url=None, source="local_pdf",
                identity_hash=hashlib.sha256(identity_value.casefold().encode()).hexdigest(),
            )
            paper.study_state = PaperStudyState(learned=False)
            self.db.add(paper); self.db.flush()
        entry = paper.library_entry
        if not entry:
            entry = LibraryEntry(source="local_pdf")
            paper.library_entry = entry
        self.db.add(entry); self.db.flush()
        if folder not in entry.folders:
            entry.folders.append(folder)
        row = existing_path or LocalPaperFile(paper=paper, folder=folder, relative_path=relative, file_name=path.name, sha256=digest)
        row.paper_id = paper.id; row.folder_id = folder.id; row.file_name = path.name; row.sha256 = digest
        row.size_bytes = stat.st_size; row.modified_ns = stat.st_mtime_ns; row.page_count = metadata["page_count"]; row.status = "ready"; row.error = None
        self.db.add(row); self.db.flush()
        if is_new_paper:
            paper.primary_url = f"/api/library/files/{row.id}/pdf"
        paper.pdf_url = f"/api/library/files/{row.id}/pdf"
        return "updated" if existing_path else "imported"

    def _find_paper(self, metadata: dict[str, Any], digest: str) -> Paper | None:
        clauses = []
        if metadata["arxiv_id"]: clauses.append(Paper.arxiv_id == metadata["arxiv_id"])
        if metadata["doi"]: clauses.append(Paper.doi == metadata["doi"])
        title_hash = hashlib.sha256((normalize_title(metadata["title"]) or digest).encode()).hexdigest()
        clauses.append(Paper.identity_hash == title_hash)
        return self.db.scalar(select(Paper).where(or_(*clauses)))

    def _ensure_folder(self, root: Path, path: Path, parent_id: int | None) -> LibraryFolder:
        relative = path.relative_to(root).as_posix() or "."
        row = self.db.scalar(select(LibraryFolder).where(LibraryFolder.relative_path == relative))
        name = root.name if relative == "." else path.name
        if row:
            row.name = name; row.normalized_name = name.casefold(); row.parent_id = parent_id
            return row
        row = LibraryFolder(name=name, normalized_name=name.casefold(), parent_id=parent_id, relative_path=relative)
        self.db.add(row); self.db.flush()
        return row

    def _resolve_relative(self, relative: str) -> Path:
        target = (self.root_path() / relative).resolve()
        self._assert_inside_root(target)
        return target

    def _assert_inside_root(self, path: Path) -> None:
        root = self.root_path()
        if path != root and root not in path.parents:
            raise ValueError("路径超出知识库根目录")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_pdf_metadata(path: Path) -> dict[str, Any]:
    reader = PdfReader(str(path))
    meta = reader.metadata or {}
    pages_text: list[str] = []
    for page in reader.pages[:3]:
        try: pages_text.append(page.extract_text() or "")
        except Exception: continue
    text = "\n".join(pages_text)
    title = str(getattr(meta, "title", "") or "").strip()
    if not title:
        candidates = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()[:30]]
        title = next((line for line in candidates if 12 <= len(line) <= 300 and not line.lower().startswith(("arxiv:", "abstract", "http"))), path.stem)
    author_value = str(getattr(meta, "author", "") or "").strip()
    authors = [item.strip() for item in re.split(r"[,;]", author_value) if item.strip()]
    arxiv_match = ARXIV_PATTERN.search(f"{path.name}\n{text[:12000]}")
    doi_match = DOI_PATTERN.search(text[:20000])
    abstract_match = re.search(r"(?is)\babstract\b\s*[:—-]?\s*(.{80,3000}?)(?:\n\s*(?:1\.?\s+)?introduction\b|\n\s*keywords?\b)", text)
    return {
        "title": title[:5000], "authors": authors, "arxiv_id": arxiv_match.group(1) if arxiv_match else None,
        "doi": doi_match.group(0).rstrip(".,;)") if doi_match else None,
        "abstract": re.sub(r"\s+", " ", abstract_match.group(1)).strip() if abstract_match else "",
        "page_count": len(reader.pages),
    }
