from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from .database import SessionLocal
from .models import RecommendationBatch
from .library_folder_service import LibraryFolderService
from .recommendation import RecommendationService
from .settings_service import get_settings


scheduler = BackgroundScheduler()
JOB_ID = "daily-paper-recommendation"
LIBRARY_SYNC_JOB_ID = "local-library-folder-sync"


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
    sync_scheduler()
    _schedule_library_sync()
    _schedule_startup_catchup()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def sync_scheduler() -> None:
    db = SessionLocal()
    try:
        settings = get_settings(db)
    finally:
        db.close()
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)
    if not settings.get("daily_enabled"):
        return
    hour, minute = map(int, settings["daily_time"].split(":"))
    trigger = CronTrigger(hour=hour, minute=minute, timezone=ZoneInfo(settings["timezone"]))
    scheduler.add_job(run_daily_recommendation, trigger=trigger, id=JOB_ID, replace_existing=True, kwargs={"triggered_by": "schedule"}, max_instances=1, coalesce=True)


def run_daily_recommendation(triggered_by: str = "schedule") -> None:
    db = SessionLocal()
    try:
        settings = get_settings(db)
        if not settings.get("daily_enabled"):
            return
        tag_ids = settings.get("daily_tag_ids") or []
        if not tag_ids or _already_ran_today(db, settings["timezone"]):
            return
        asyncio.run(RecommendationService(db).generate(tag_ids, int(settings.get("daily_count", 5)), triggered_by))
    finally:
        db.close()


def run_local_library_sync() -> None:
    """Import PDFs dropped into the configured vault without touching source files."""
    db = SessionLocal()
    try:
        LibraryFolderService(db).scan()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _schedule_library_sync() -> None:
    scheduler.add_job(
        run_local_library_sync,
        trigger="interval",
        minutes=2,
        id=LIBRARY_SYNC_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def _schedule_startup_catchup() -> None:
    db = SessionLocal()
    try:
        settings = get_settings(db)
        if not settings.get("daily_enabled") or not settings.get("daily_tag_ids"):
            return
        now = datetime.now(ZoneInfo(settings["timezone"]))
        scheduled_hour, scheduled_minute = map(int, settings["daily_time"].split(":"))
        if (now.hour, now.minute) >= (scheduled_hour, scheduled_minute) and not _already_ran_today(db, settings["timezone"]):
            scheduler.add_job(run_daily_recommendation, kwargs={"triggered_by": "startup"})
    finally:
        db.close()


def _already_ran_today(db, timezone_name: str) -> bool:
    tz = ZoneInfo(timezone_name)
    batches = db.scalars(select(RecommendationBatch).where(RecommendationBatch.triggered_by.in_(["schedule", "startup"]))).all()
    today = datetime.now(tz).date()
    for batch in batches:
        value = batch.created_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("UTC"))
        if value.astimezone(tz).date() == today:
            return True
    return False
