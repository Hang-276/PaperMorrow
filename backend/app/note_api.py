from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .database import get_db
from .note_models import Note
from .note_service import create_diagram_artifact, note_dict, note_query, set_note_papers, sync_legacy_from_note


router = APIRouter(prefix="/api/notes", tags=["notes"])


class NoteCreate(BaseModel):
    title: str = Field(default="未命名笔记", max_length=500)
    content: str = ""
    document_format: Literal["markdown", "latex"] = "markdown"
    editor_mode: Literal["standard", "professional"] = "standard"
    origin: Literal["standalone", "reader"] = "standalone"
    project_id: int | None = None
    paper_ids: list[int] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    content: str | None = None
    document_format: Literal["markdown", "latex"] | None = None
    editor_mode: Literal["standard", "professional"] | None = None
    project_id: int | None = None
    paper_ids: list[int] | None = None


class NoteAppend(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    source_label: str = Field(default="AI 助手", max_length=200)


class ArtifactRequest(BaseModel):
    type: Literal["flowchart", "mindmap", "presentation"]
    instructions: str = ""
    presentation_mode: Literal["paper_report", "progress_report", "lab_meeting"] = "lab_meeting"
    language: Literal["zh", "en"] = "zh"
    slide_count: int = Field(default=10, ge=4, le=30)


def _note_or_404(db: Session, note_id: int) -> Note:
    note = db.scalar(note_query().where(Note.id == note_id))
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return note


@router.get("")
def list_notes(
    q: str = "",
    paper_id: int | None = None,
    project_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    query = note_query().order_by(Note.updated_at.desc())
    if q.strip():
        pattern = f"%{q.strip()}%"
        query = query.where(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))
    if project_id is not None:
        query = query.where(Note.project_id == project_id)
    notes = db.scalars(query).unique().all()
    if paper_id is not None:
        notes = [note for note in notes if any(link.paper_id == paper_id for link in note.paper_links)]
    return [note_dict(note, db) for note in notes]


@router.post("", status_code=201)
def create_note(payload: NoteCreate, db: Session = Depends(get_db)) -> dict:
    note = Note(**payload.model_dump(exclude={"paper_ids"}))
    db.add(note)
    try:
        set_note_papers(db, note, payload.paper_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return note_dict(_note_or_404(db, note.id), db)


@router.get("/{note_id}")
def get_note(note_id: int, db: Session = Depends(get_db)) -> dict:
    return note_dict(_note_or_404(db, note_id), db)


@router.put("/{note_id}")
def update_note(note_id: int, payload: NoteUpdate, db: Session = Depends(get_db)) -> dict:
    note = _note_or_404(db, note_id)
    values = payload.model_dump(exclude_unset=True, exclude={"paper_ids"})
    for key, value in values.items():
        setattr(note, key, value)
    if payload.paper_ids is not None:
        try:
            set_note_papers(db, note, payload.paper_ids)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    sync_legacy_from_note(db, note)
    db.commit()
    return note_dict(_note_or_404(db, note.id), db)


@router.post("/{note_id}/append")
def append_to_note(note_id: int, payload: NoteAppend, db: Session = Depends(get_db)) -> dict:
    note = _note_or_404(db, note_id)
    if note.document_format != "markdown":
        raise HTTPException(status_code=422, detail="只能将 AI 回复写入 Markdown 笔记")
    source = payload.source_label.strip() or "AI 助手"
    source = " ".join(source.splitlines())
    addition = f"## {source}\n\n{payload.content.strip()}\n"
    note.content = f"{note.content.rstrip()}\n\n{addition}" if note.content.strip() else addition
    sync_legacy_from_note(db, note)
    db.commit()
    return note_dict(_note_or_404(db, note.id), db)


@router.post("/{note_id}/artifacts", status_code=201)
def create_artifact(note_id: int, payload: ArtifactRequest, db: Session = Depends(get_db)) -> dict:
    note = _note_or_404(db, note_id)
    if note.document_format != "markdown" and payload.type != "presentation":
        raise HTTPException(status_code=422, detail="流程图和思维导图当前从 Markdown 标题结构生成")
    if payload.type == "presentation":
        # The presentation engine registers its handler here during integration.
        from .presentation_service import create_note_presentation
        artifact = create_note_presentation(db, note, payload.model_dump())
    else:
        artifact = create_diagram_artifact(db, note, payload.type)
    db.commit()
    artifacts = note_dict(_note_or_404(db, note.id), db)["artifacts"]
    return next(item for item in artifacts if item["id"] == artifact.id)
