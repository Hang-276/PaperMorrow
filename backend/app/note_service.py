from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Paper, PaperNote
from .note_models import Note, NoteArtifact, NotePaperLink


def note_query():
    return select(Note).options(selectinload(Note.paper_links), selectinload(Note.artifacts))


def note_dict(note: Note, db: Session | None = None) -> dict[str, Any]:
    paper_ids = [item.paper_id for item in note.paper_links]
    papers: list[dict[str, Any]] = []
    if db and paper_ids:
        rows = {item.id: item for item in db.scalars(select(Paper).where(Paper.id.in_(paper_ids))).all()}
        papers = [{"id": paper_id, "title": rows[paper_id].title_en, "title_zh": rows[paper_id].title_zh} for paper_id in paper_ids if paper_id in rows]
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content,
        "document_format": note.document_format,
        "editor_mode": note.editor_mode,
        "origin": note.origin,
        "project_id": note.project_id,
        "legacy_paper_id": note.legacy_paper_id,
        "paper_ids": paper_ids,
        "papers": papers,
        "artifacts": [{
            "id": item.id, "type": item.artifact_type, "status": item.status,
            "content": item.content, "download_url": f"/api/presentations/{item.id}/download" if item.output_path else None,
            "error": item.error, "created_at": item.created_at.isoformat(),
        } for item in note.artifacts],
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
    }


def set_note_papers(db: Session, note: Note, paper_ids: list[int]) -> None:
    unique_ids = list(dict.fromkeys(paper_ids))
    if unique_ids:
        existing = set(db.scalars(select(Paper.id).where(Paper.id.in_(unique_ids))).all())
        missing = [paper_id for paper_id in unique_ids if paper_id not in existing]
        if missing:
            raise ValueError(f"论文不存在：{', '.join(map(str, missing))}")
    current = {link.paper_id: link for link in note.paper_links}
    requested = set(unique_ids)
    for paper_id, link in current.items():
        if paper_id not in requested:
            note.paper_links.remove(link)
    for paper_id in unique_ids:
        if paper_id not in current:
            note.paper_links.append(NotePaperLink(paper_id=paper_id))


def sync_reader_note(db: Session, paper: Paper, content: str) -> Note:
    """Preserve the legacy reader note while exposing the same content in Notes."""
    legacy = paper.note or PaperNote(paper_id=paper.id)
    legacy.content = content
    db.add(legacy)
    note = db.scalar(note_query().where(Note.legacy_paper_id == paper.id))
    if not note:
        note = Note(
            title=paper.title_zh or paper.title_en,
            content=content,
            document_format="markdown",
            editor_mode="professional",
            origin="reader",
            legacy_paper_id=paper.id,
        )
        note.paper_links.append(NotePaperLink(paper_id=paper.id))
        db.add(note)
    else:
        note.content = content
        if not any(link.paper_id == paper.id for link in note.paper_links):
            note.paper_links.append(NotePaperLink(paper_id=paper.id))
    return note


def sync_legacy_from_note(db: Session, note: Note) -> None:
    if note.legacy_paper_id is None:
        return
    legacy = db.get(PaperNote, note.legacy_paper_id) or PaperNote(paper_id=note.legacy_paper_id)
    legacy.content = note.content
    db.add(legacy)


def derive_mermaid(content: str, artifact_type: str) -> str:
    headings = [match.group(1).strip() for match in re.finditer(r"^#{1,4}\s+(.+)$", content, re.MULTILINE)]
    headings = headings[:18] or [line.strip(" -*\t") for line in content.splitlines() if line.strip()][:8]
    if artifact_type == "flowchart":
        nodes = [f'  N{index}["{label.replace(chr(34), chr(39))}"]' for index, label in enumerate(headings)]
        edges = [f"  N{index} --> N{index + 1}" for index in range(max(0, len(headings) - 1))]
        return "flowchart TD\n" + "\n".join(nodes + edges)
    root = headings[0] if headings else "研究笔记"
    children = headings[1:] or ["核心观点", "证据", "下一步"]
    return "mindmap\n  root((%s))\n%s" % (root, "\n".join(f"    {item}" for item in children))


def create_diagram_artifact(db: Session, note: Note, artifact_type: str) -> NoteArtifact:
    artifact = NoteArtifact(note=note, artifact_type=artifact_type, content=derive_mermaid(note.content, artifact_type))
    db.add(artifact)
    return artifact
