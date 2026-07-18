from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import TokenUsage


PURPOSE_LABELS = {
    "recommendation": "推荐复排",
    "analysis": "论文摘要与分析",
    "chat": "论文对话",
    "translation": "论文翻译",
    "deepwiki": "DeepWiki",
    "other": "其他",
}


def estimate_tokens(value: Any) -> int:
    text = value if isinstance(value, str) else str(value)
    return max(1, math.ceil(len(text) / 4))


def record_token_usage(
    *, profile_id: str | None, profile_name: str, provider: str, model: str,
    purpose: str, prompt_tokens: int, completion_tokens: int, estimated: bool,
) -> None:
    db = SessionLocal()
    try:
        db.add(TokenUsage(
            profile_id=profile_id,
            profile_name=profile_name,
            provider=provider,
            model=model,
            purpose=purpose,
            prompt_tokens=max(0, int(prompt_tokens)),
            completion_tokens=max(0, int(completion_tokens)),
            total_tokens=max(0, int(prompt_tokens)) + max(0, int(completion_tokens)),
            estimated=estimated,
        ))
        db.commit()
    finally:
        db.close()


def token_usage_stats(db: Session, timezone_name: str, days: int = 14) -> dict[str, Any]:
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    rows = db.query(TokenUsage).order_by(TokenUsage.created_at).all()
    now_local = datetime.now(timezone.utc).astimezone(tz)
    today_key = now_local.date().isoformat()
    by_day: dict[str, dict[str, int]] = defaultdict(lambda: _empty_totals())
    by_profile: dict[str, dict[str, Any]] = {}
    by_purpose: dict[str, dict[str, Any]] = {}
    total = _empty_totals()
    today = _empty_totals()

    for row in rows:
        created = row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
        day = created.astimezone(tz).date().isoformat()
        _add(total, row)
        _add(by_day[day], row)
        if day == today_key:
            _add(today, row)
        profile_key = row.profile_id or row.profile_name
        profile = by_profile.setdefault(profile_key, {"profile_id": row.profile_id, "name": row.profile_name, **_empty_totals()})
        _add(profile, row)
        purpose = by_purpose.setdefault(row.purpose, {"purpose": row.purpose, "label": PURPOSE_LABELS.get(row.purpose, row.purpose), **_empty_totals()})
        _add(purpose, row)

    day_items = [{"date": key, **value} for key, value in sorted(by_day.items())[-days:]]
    return {
        "timezone": timezone_name,
        "today": today,
        "total": total,
        "daily": day_items,
        "by_profile": sorted(by_profile.values(), key=lambda item: item["total_tokens"], reverse=True),
        "by_purpose": sorted(by_purpose.values(), key=lambda item: item["total_tokens"], reverse=True),
    }


def _empty_totals() -> dict[str, int]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0, "estimated_requests": 0}


def _add(target: dict[str, Any], row: TokenUsage) -> None:
    target["prompt_tokens"] += row.prompt_tokens
    target["completion_tokens"] += row.completion_tokens
    target["total_tokens"] += row.total_tokens
    target["requests"] += 1
    target["estimated_requests"] += int(row.estimated)
