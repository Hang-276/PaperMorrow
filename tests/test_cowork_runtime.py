from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.cowork_files import FileAccessDenied, read_authorized_text, resolve_authorized_path
from backend.app.cowork_models import CoworkSession, CoworkStep, CoworkTask
from backend.app.cowork_runtime import cancel_session, create_session, repair_interrupted_sessions, resume_session, run_next_step
from backend.app.cowork_security import create_grant
from backend.app.database import Base


def _engine(path: Path | None = None):
    engine = create_engine(f"sqlite:///{path}" if path else "sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_plan_is_bounded_editable_shape_and_cancel_stops_all_steps():
    engine = _engine()
    with Session(engine) as db:
        item = create_session(db, "整理本周实验并形成组会报告")
        db.commit()
        task = db.scalar(select(CoworkTask).where(CoworkTask.session_id == item.id))
        steps = db.scalars(select(CoworkStep).where(CoworkStep.task_id == task.id)).all()
        assert 3 <= len(steps) <= 8
        cancel_session(db, item); db.commit()
        assert item.stop_requested and item.status == "cancelled"
        assert all(step.status == "cancelled" for step in steps)
        with pytest.raises(RuntimeError):
            asyncio.run(run_next_step(db, item))


def test_restart_can_resume_from_persisted_checkpoint(tmp_path: Path):
    database = tmp_path / "cowork.db"
    engine = _engine(database)
    with Session(engine) as db:
        item = create_session(db, "比较两篇论文")
        db.commit(); session_id = item.id
        asyncio.run(run_next_step(db, item)); db.commit()
        assert item.status == "planned"
    engine.dispose()
    with Session(_engine(database)) as db:
        item = db.get(CoworkSession, session_id)
        assert item is not None
        resume_session(db, item)
        asyncio.run(run_next_step(db, item)); db.commit()
        completed = db.scalars(select(CoworkStep).join(CoworkTask).where(CoworkTask.session_id == session_id, CoworkStep.status == "completed")).all()
        assert len(completed) == 2


def test_folder_grant_blocks_traversal_symlink_and_hidden_secrets(tmp_path: Path):
    root = tmp_path / "allowed"; root.mkdir()
    allowed = root / "paper.md"; allowed.write_text("evidence")
    outside = tmp_path / "outside.md"; outside.write_text("private")
    link = root / "escape.md"; link.symlink_to(outside)
    hidden = root / ".hidden"; hidden.write_text("secret")
    engine = _engine()
    with Session(engine) as db:
        db.add(CoworkSession(id="s1", title="files")); db.flush()
        create_grant(db, "s1", "folder", str(root), can_read=True, can_write=False); db.flush()
        assert read_authorized_text(db, "s1", str(allowed)) == "evidence"
        with pytest.raises(FileAccessDenied): resolve_authorized_path(db, "s1", str(root / ".." / "outside.md"))
        with pytest.raises(FileAccessDenied): resolve_authorized_path(db, "s1", str(link))
        with pytest.raises(FileAccessDenied): resolve_authorized_path(db, "s1", str(hidden))


def test_write_requires_explicit_write_grant(tmp_path: Path):
    root = tmp_path / "allowed"; root.mkdir()
    engine = _engine()
    with Session(engine) as db:
        db.add(CoworkSession(id="s1", title="files")); db.flush()
        create_grant(db, "s1", "folder", str(root), can_read=True, can_write=False); db.flush()
        with pytest.raises(FileAccessDenied): resolve_authorized_path(db, "s1", str(root / "draft.md"), write=True)


def test_interrupted_running_session_recovers_as_paused():
    engine = _engine()
    with Session(engine) as db:
        item = create_session(db, "recover me")
        task = db.scalar(select(CoworkTask).where(CoworkTask.session_id == item.id))
        step = db.scalar(select(CoworkStep).where(CoworkStep.task_id == task.id).order_by(CoworkStep.position))
        item.status = task.status = step.status = "running"; db.commit()
        assert repair_interrupted_sessions(db) == 1
        assert item.status == "paused" and step.status == "paused"
