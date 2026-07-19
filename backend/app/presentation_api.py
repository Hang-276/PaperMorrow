from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .presentation_models import PresentationDraft
from .presentation_service import create_outline, draft_dict, render_presentation, validate_outline


router = APIRouter(prefix="/api/presentations", tags=["presentations"])


class OutlineCreate(BaseModel):
    title: str = ""
    kind: Literal["lab-meeting", "paper-report", "research-progress", "literature-review", "experiment-report"] = "lab-meeting"
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    note_id: int | None = None
    project_id: int | None = None
    paper_id: int | None = None
    instructions: str = ""
    slide_count: int = Field(default=10, ge=4, le=30)
    use_ai: bool = True
    blank: bool = False


class OutlineUpdate(BaseModel):
    outline: dict
    title: str | None = None
    instructions: str | None = None


def _draft_or_404(db: Session, draft_id: int) -> PresentationDraft:
    draft = db.get(PresentationDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="演示文稿不存在")
    return draft


@router.get("")
def list_presentations(db: Session = Depends(get_db)) -> list[dict]:
    return [draft_dict(item) for item in db.scalars(select(PresentationDraft).order_by(PresentationDraft.updated_at.desc())).all()]


@router.post("/outlines", status_code=201)
async def generate_outline(payload: OutlineCreate, db: Session = Depends(get_db)) -> dict:
    if not any((payload.note_id, payload.project_id, payload.paper_id)) and not payload.blank:
        raise HTTPException(status_code=422, detail="请选择笔记、论文或研究项目作为汇报上下文，或从空白大纲开始")
    try:
        return draft_dict(await create_outline(db, payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{draft_id}")
def get_presentation(draft_id: int, db: Session = Depends(get_db)) -> dict:
    return draft_dict(_draft_or_404(db, draft_id))


@router.put("/{draft_id}/outline")
def update_outline(draft_id: int, payload: OutlineUpdate, db: Session = Depends(get_db)) -> dict:
    draft = _draft_or_404(db, draft_id)
    sources = json.loads(draft.source_catalog_json or "[]")
    try:
        outline = validate_outline(payload.outline, sources)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    draft.outline_json = json.dumps(outline, ensure_ascii=False)
    if payload.title is not None:
        draft.title = payload.title.strip() or draft.title
    if payload.instructions is not None:
        draft.instructions = payload.instructions
    draft.status = "outline"; draft.error = None
    db.commit(); db.refresh(draft)
    return draft_dict(draft)


@router.post("/{draft_id}/generate")
def generate_presentation(draft_id: int, db: Session = Depends(get_db)) -> dict:
    draft = render_presentation(db, _draft_or_404(db, draft_id))
    if draft.status == "failed":
        raise HTTPException(status_code=500, detail=draft.error or "PPTX 生成失败")
    return draft_dict(draft)


@router.get("/{draft_id}/download")
def download_presentation(draft_id: int, db: Session = Depends(get_db)) -> FileResponse:
    draft = _draft_or_404(db, draft_id)
    path = Path(draft.output_path or "").resolve()
    if draft.status != "completed" or not path.is_file():
        raise HTTPException(status_code=404, detail="演示文稿尚未生成")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation", filename=f"{draft.title}.pptx")
