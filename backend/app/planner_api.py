from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import PlannerTask, SubmissionDeadline


router = APIRouter(prefix="/api/planner", tags=["planner"])


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    details: str = Field(default="", max_length=20_000)
    due_at: datetime | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    project_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    details: str | None = Field(default=None, max_length=20_000)
    due_at: datetime | None = None
    priority: Literal["low", "medium", "high"] | None = None
    status: Literal["pending", "completed"] | None = None
    project_id: int | None = None


class DeadlineCreate(BaseModel):
    venue_name: str = Field(min_length=1, max_length=300)
    venue_type: Literal["conference", "journal"] = "conference"
    round_name: str = Field(default="", max_length=160)
    deadline_at: datetime
    timezone_name: str = Field(default="AoE (UTC-12)", max_length=80)
    domain: str = Field(default="", max_length=120)
    website_url: HttpUrl | None = None
    notes: str = Field(default="", max_length=20_000)
    remind_days_before: int = Field(default=14, ge=0, le=365)
    enabled: bool = True


class DeadlineUpdate(BaseModel):
    venue_name: str | None = Field(default=None, min_length=1, max_length=300)
    venue_type: Literal["conference", "journal"] | None = None
    round_name: str | None = Field(default=None, max_length=160)
    deadline_at: datetime | None = None
    timezone_name: str | None = Field(default=None, max_length=80)
    domain: str | None = Field(default=None, max_length=120)
    website_url: HttpUrl | None = None
    notes: str | None = Field(default=None, max_length=20_000)
    remind_days_before: int | None = Field(default=None, ge=0, le=365)
    enabled: bool | None = None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def task_dict(item: PlannerTask) -> dict:
    return {
        "id": item.id, "title": item.title, "details": item.details, "due_at": _iso(item.due_at),
        "priority": item.priority, "status": item.status, "project_id": item.project_id,
        "completed_at": _iso(item.completed_at), "created_at": _iso(item.created_at), "updated_at": _iso(item.updated_at),
    }


def deadline_dict(item: SubmissionDeadline) -> dict:
    return {
        "id": item.id, "venue_name": item.venue_name, "venue_type": item.venue_type,
        "round_name": item.round_name, "deadline_at": _iso(item.deadline_at), "timezone_name": item.timezone_name,
        "domain": item.domain, "website_url": item.website_url, "notes": item.notes,
        "remind_days_before": item.remind_days_before, "enabled": item.enabled, "source": item.source,
        "created_at": _iso(item.created_at), "updated_at": _iso(item.updated_at),
    }


def _task(db: Session, item_id: int) -> PlannerTask:
    item = db.get(PlannerTask, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="待办不存在")
    return item


def _deadline(db: Session, item_id: int) -> SubmissionDeadline:
    item = db.get(SubmissionDeadline, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="截稿提醒不存在")
    return item


@router.get("/tasks")
def list_tasks(include_completed: bool = Query(False), db: Session = Depends(get_db)) -> list[dict]:
    statement = select(PlannerTask)
    if not include_completed:
        statement = statement.where(PlannerTask.status == "pending")
    items = db.scalars(statement.order_by(PlannerTask.due_at.is_(None), PlannerTask.due_at, PlannerTask.created_at.desc())).all()
    return [task_dict(item) for item in items]


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> dict:
    item = PlannerTask(**payload.model_dump())
    db.add(item); db.commit(); db.refresh(item)
    return task_dict(item)


@router.put("/tasks/{item_id}")
def update_task(item_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> dict:
    item = _task(db, item_id)
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(item, key, value)
    if "status" in values:
        item.completed_at = datetime.now(timezone.utc) if item.status == "completed" else None
    db.commit(); db.refresh(item)
    return task_dict(item)


@router.delete("/tasks/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(item_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_task(db, item_id)); db.commit()


@router.get("/deadlines")
def list_deadlines(include_disabled: bool = Query(False), db: Session = Depends(get_db)) -> list[dict]:
    statement = select(SubmissionDeadline)
    if not include_disabled:
        statement = statement.where(SubmissionDeadline.enabled.is_(True))
    items = db.scalars(statement.order_by(SubmissionDeadline.deadline_at)).all()
    return [deadline_dict(item) for item in items]


@router.post("/deadlines", status_code=status.HTTP_201_CREATED)
def create_deadline(payload: DeadlineCreate, db: Session = Depends(get_db)) -> dict:
    values = payload.model_dump()
    values["website_url"] = str(values["website_url"]) if values["website_url"] else ""
    item = SubmissionDeadline(**values, source="user")
    db.add(item); db.commit(); db.refresh(item)
    return deadline_dict(item)


@router.put("/deadlines/{item_id}")
def update_deadline(item_id: int, payload: DeadlineUpdate, db: Session = Depends(get_db)) -> dict:
    item = _deadline(db, item_id)
    values = payload.model_dump(exclude_unset=True)
    if "website_url" in values:
        values["website_url"] = str(values["website_url"]) if values["website_url"] else ""
    for key, value in values.items():
        setattr(item, key, value)
    db.commit(); db.refresh(item)
    return deadline_dict(item)


@router.delete("/deadlines/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deadline(item_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_deadline(db, item_id)); db.commit()
