from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .cowork_models import CoworkArtifact, CoworkMessage, CoworkSession, CoworkStep, CoworkTask, PermissionGrant, SkillManifest, ToolCall
from .cowork_runtime import add_message, cancel_session, create_plan, create_session, pause_session, resume_session, retry_step, run_next_step
from .cowork_security import create_grant, revoke_grant
from .cowork_tools import DEFAULT_REGISTRY
from .database import get_db
from .settings_service import get_active_llm_profile
from .cowork_skills import skill_dict


router = APIRouter(prefix="/api/cowork", tags=["cowork"])


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(StrictPayload):
    goal: str = Field(min_length=1, max_length=20_000)
    title: str = Field(default="", max_length=500)
    response_detail: Literal["concise", "rich"] = "rich"
    thinking_effort: Literal["low", "medium", "high"] = "medium"


class SessionUpdate(StrictPayload):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    goal: str | None = Field(default=None, min_length=1, max_length=20_000)
    response_detail: Literal["concise", "rich"] | None = None
    thinking_effort: Literal["low", "medium", "high"] | None = None


class MessageCreate(StrictPayload):
    content: str = Field(min_length=1, max_length=100_000)
    attachments: list[dict] = Field(default_factory=list, max_length=20)


class GrantCreate(StrictPayload):
    resource_type: Literal["file", "folder", "paper", "note", "project", "experiment", "study", "deepwiki", "reading_history"]
    resource_scope: str = Field(min_length=1, max_length=4000)
    can_read: bool = True
    can_write: bool = False
    duration: Literal["session", "permanent"] = "session"


class PlanUpdate(StrictPayload):
    steps: list[dict] = Field(min_length=3, max_length=8)


def _session(db: Session, session_id: str) -> CoworkSession:
    item = db.get(CoworkSession, session_id)
    if not item:
        raise HTTPException(404, "Cowork 会话不存在")
    return item


def _loads(value: str, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def session_dict(db: Session, item: CoworkSession, *, detail: bool = False) -> dict:
    result = {
        "id": item.id, "title": item.title, "goal": item.goal, "status": item.status,
        "model_profile_id": item.model_profile_id, "model_name": item.model_name,
        "response_detail": item.response_detail, "thinking_effort": item.thinking_effort,
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
    }
    if not detail:
        return result
    messages = db.scalars(select(CoworkMessage).where(CoworkMessage.session_id == item.id).order_by(CoworkMessage.id)).all()
    tasks = db.scalars(select(CoworkTask).where(CoworkTask.session_id == item.id).order_by(CoworkTask.id)).all()
    grants = db.scalars(select(PermissionGrant).where(PermissionGrant.session_id == item.id, PermissionGrant.revoked_at.is_(None))).all()
    calls = db.scalars(select(ToolCall).where(ToolCall.session_id == item.id).order_by(ToolCall.created_at)).all()
    artifacts = db.scalars(select(CoworkArtifact).where(CoworkArtifact.session_id == item.id).order_by(CoworkArtifact.created_at)).all()
    result.update({
        "messages": [{"id": row.id, "role": row.role, "blocks": _loads(row.content_blocks_json, []), "sources": _loads(row.sources_json, []), "attachments": _loads(row.attachments_json, []), "created_at": row.created_at.isoformat()} for row in messages],
        "tasks": [{"id": task.id, "title": task.title, "status": task.status, "result_summary": task.result_summary, "steps": [{"id": step.id, "position": step.position, "title": step.title, "description": step.description, "status": step.status, "retry_count": step.retry_count, "result_summary": step.result_summary, "error": step.error} for step in db.scalars(select(CoworkStep).where(CoworkStep.task_id == task.id).order_by(CoworkStep.position)).all()]} for task in tasks],
        "grants": [{"id": row.id, "resource_type": row.resource_type, "resource_scope": row.resource_scope, "normalized_path": row.normalized_path, "can_read": row.can_read, "can_write": row.can_write, "duration": row.duration, "granted_at": row.granted_at.isoformat()} for row in grants],
        "tool_calls": [{"id": row.id, "tool_name": row.tool_name, "risk_level": row.risk_level, "approval_status": row.approval_status, "status": row.status, "arguments": _loads(row.arguments_summary_json, {}), "summary": row.user_summary, "error": row.error} for row in calls],
        "artifacts": [{"id": row.id, "type": row.artifact_type, "title": row.title, "local_path": row.local_path, "sources": _loads(row.sources_json, [])} for row in artifacts],
    })
    return result


@router.get("/capabilities")
def capabilities(db: Session = Depends(get_db)) -> dict:
    profile = get_active_llm_profile(db)
    provider = profile.provider if profile else "none"
    return {"configured": bool(profile), "provider": provider, "thinking_efforts": ["low", "medium", "high"] if provider in {"openai", "claude"} else ["low", "medium"], "tools": DEFAULT_REGISTRY.list_tools()}


@router.get("/skills")
def list_skills(db: Session = Depends(get_db)) -> list[dict]:
    return [skill_dict(item) for item in db.scalars(select(SkillManifest).where(SkillManifest.enabled.is_(True)).order_by(SkillManifest.name)).all()]


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db)) -> list[dict]:
    return [session_dict(db, item) for item in db.scalars(select(CoworkSession).order_by(CoworkSession.updated_at.desc())).all()]


@router.post("/sessions", status_code=201)
def new_session(payload: SessionCreate, db: Session = Depends(get_db)) -> dict:
    item = create_session(db, payload.goal, title=payload.title, response_detail=payload.response_detail, thinking_effort=payload.thinking_effort)
    db.commit(); db.refresh(item)
    return session_dict(db, item, detail=True)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)) -> dict:
    return session_dict(db, _session(db, session_id), detail=True)


@router.put("/sessions/{session_id}")
def update_session(session_id: str, payload: SessionUpdate, db: Session = Depends(get_db)) -> dict:
    item = _session(db, session_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit(); db.refresh(item)
    return session_dict(db, item, detail=True)


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, payload: MessageCreate, db: Session = Depends(get_db)) -> dict:
    item = _session(db, session_id)
    message = add_message(db, item.id, "user", payload.content)
    message.attachments_json = json.dumps(payload.attachments, ensure_ascii=False)
    if not db.scalar(select(CoworkTask).where(CoworkTask.session_id == item.id)):
        item.goal = item.goal or payload.content; create_plan(db, item)
    if item.status in {"draft", "planned", "paused"}:
        try:
            if item.status == "paused": resume_session(db, item)
            await run_next_step(db, item)
        except RuntimeError:
            pass
    db.commit(); db.refresh(item)
    return session_dict(db, item, detail=True)


@router.post("/sessions/{session_id}/run-next")
async def run_next(session_id: str, db: Session = Depends(get_db)) -> dict:
    item = _session(db, session_id)
    try:
        await run_next_step(db, item)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit(); db.refresh(item)
    return session_dict(db, item, detail=True)


@router.post("/sessions/{session_id}/pause")
def pause(session_id: str, db: Session = Depends(get_db)) -> dict:
    item = _session(db, session_id); pause_session(db, item); db.commit(); return session_dict(db, item, detail=True)


@router.post("/sessions/{session_id}/resume")
def resume(session_id: str, db: Session = Depends(get_db)) -> dict:
    item = _session(db, session_id)
    try: resume_session(db, item)
    except RuntimeError as exc: raise HTTPException(409, str(exc)) from exc
    db.commit(); return session_dict(db, item, detail=True)


@router.post("/sessions/{session_id}/cancel")
def cancel(session_id: str, db: Session = Depends(get_db)) -> dict:
    item = _session(db, session_id); cancel_session(db, item); db.commit(); return session_dict(db, item, detail=True)


@router.post("/sessions/{session_id}/steps/{step_id}/retry")
def retry(session_id: str, step_id: int, db: Session = Depends(get_db)) -> dict:
    item = _session(db, session_id); step = db.get(CoworkStep, step_id)
    if not step or step.task.session_id != session_id: raise HTTPException(404, "步骤不存在")
    try: retry_step(db, item, step)
    except RuntimeError as exc: raise HTTPException(409, str(exc)) from exc
    db.commit(); return session_dict(db, item, detail=True)


@router.post("/sessions/{session_id}/grants", status_code=201)
def grant(session_id: str, payload: GrantCreate, db: Session = Depends(get_db)) -> dict:
    _session(db, session_id)
    try:
        create_grant(db, session_id, **payload.model_dump())
    except (ValueError, PermissionError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit(); return session_dict(db, _session(db, session_id), detail=True)


@router.delete("/sessions/{session_id}/grants/{grant_id}")
def revoke(session_id: str, grant_id: str, db: Session = Depends(get_db)) -> dict:
    item = _session(db, session_id); grant_item = db.get(PermissionGrant, grant_id)
    if not grant_item or grant_item.session_id != session_id: raise HTTPException(404, "授权不存在")
    revoke_grant(db, grant_item); db.commit(); return session_dict(db, item, detail=True)


@router.delete("/sessions/{session_id}/context")
def clear_context(session_id: str, db: Session = Depends(get_db)) -> dict:
    item = _session(db, session_id)
    for message in db.scalars(select(CoworkMessage).where(CoworkMessage.session_id == session_id)).all(): db.delete(message)
    item.context_summary = ""; item.stop_requested = True; item.status = "paused"
    db.commit(); return session_dict(db, item, detail=True)
