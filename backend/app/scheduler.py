from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from .database import SessionLocal
from .catalog import tag_domain
from .models import RecommendationBatch, ResearchProfile, Tag
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
        if _already_ran_today(db, settings["timezone"]):
            return
        for lane in daily_recommendation_lanes(db, settings):
            asyncio.run(RecommendationService(db).generate(
                lane["tag_ids"], lane["count"], triggered_by,
                profile_id=lane["profile_id"], mode=lane["mode"],
            ))
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
        if not settings.get("daily_enabled") or not (settings.get("daily_tag_ids") or settings.get("daily_profile_ids")):
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


def daily_recommendation_lanes(db, settings: dict) -> list[dict]:
    """Build an exact-size daily plan from broad tags and custom profiles.

    Profiles are rotated by day so a small daily quota does not permanently hide
    later selections. AI profiles remain first-class and are considered before
    other domains. Disabled/deleted profiles and unusable domains are skipped.
    """
    total = max(1, min(30, int(settings.get("daily_count", 5))))
    selected_tag_ids = list(dict.fromkeys(int(item) for item in (settings.get("daily_tag_ids") or [])))
    selected_profile_ids = list(dict.fromkeys(int(item) for item in (settings.get("daily_profile_ids") or [])))
    enabled_tags = list(db.scalars(select(Tag).where(Tag.enabled.is_(True))).all())
    selected_tags = [tag for tag in enabled_tags if tag.id in selected_tag_ids]
    tags_by_domain: dict[str, list[int]] = {}
    for tag in enabled_tags:
        tags_by_domain.setdefault(tag_domain(tag.slug), []).append(tag.id)

    profiles = list(db.scalars(select(ResearchProfile).where(
        ResearchProfile.id.in_(selected_profile_ids), ResearchProfile.enabled.is_(True)
    )).all()) if selected_profile_ids else []
    position = {profile_id: index for index, profile_id in enumerate(selected_profile_ids)}
    profiles.sort(key=lambda item: position.get(item.id, 10_000))
    ai_profiles = [item for item in profiles if item.domain == "ai"]
    other_profiles = [item for item in profiles if item.domain != "ai"]
    if other_profiles:
        day = datetime.now(ZoneInfo(settings.get("timezone", "Asia/Shanghai"))).date().toordinal()
        offset = day % len(other_profiles)
        other_profiles = other_profiles[offset:] + other_profiles[:offset]

    lanes: list[dict] = []
    for profile in [*ai_profiles, *other_profiles]:
        profile_tags = [tag.id for tag in selected_tags if tag_domain(tag.slug) == profile.domain]
        profile_tags = profile_tags or tags_by_domain.get(profile.domain, [])
        if profile_tags:
            lanes.append({"profile_id": profile.id, "tag_ids": profile_tags, "mode": settings.get("daily_profile_mode", "mixed")})
    if selected_tags:
        lanes.append({"profile_id": None, "tag_ids": [tag.id for tag in selected_tags], "mode": "broad"})
    lanes = lanes[:total]
    if not lanes:
        return []
    quotient, remainder = divmod(total, len(lanes))
    for index, lane in enumerate(lanes):
        lane["count"] = quotient + (1 if index < remainder else 0)
    return lanes
