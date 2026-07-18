from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .catalog import DEFAULT_SETTINGS, TIMEZONE_OPTIONS
from .config import DATA_DIR, runtime_settings
from .models import AppSetting, LLMProfile


SECRET_FILE = DATA_DIR / "secrets.json"


def get_settings(db: Session) -> dict[str, Any]:
    result = dict(DEFAULT_SETTINGS)
    for item in db.query(AppSetting).all():
        try:
            result[item.key] = json.loads(item.value)
        except json.JSONDecodeError:
            result[item.key] = item.value
    profile = ensure_llm_profile(db, result)
    secrets = _load_secrets()
    result["has_llm_api_key"] = bool(profile and get_llm_profile_key(profile.id))
    result["active_llm_profile"] = llm_profile_dict(profile) if profile else None
    result["has_github_token"] = bool(os.getenv("GITHUB_TOKEN") or secrets.get("github_token") or runtime_settings.github_token)
    result["has_zotero_api_key"] = bool(secrets.get("zotero_api_key"))
    result["timezone_options"] = TIMEZONE_OPTIONS
    return result


def update_settings(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    allowed = set(DEFAULT_SETTINGS)
    for key, value in values.items():
        if key not in allowed:
            continue
        row = db.get(AppSetting, key)
        encoded = json.dumps(value, ensure_ascii=False)
        if row:
            row.value = encoded
        else:
            db.add(AppSetting(key=key, value=encoded))
    db.commit()
    return get_settings(db)


def save_secrets(llm_api_key: str | None = None, github_token: str | None = None, zotero_api_key: str | None = None) -> None:
    values = _load_secrets()
    if llm_api_key is not None and llm_api_key.strip():
        values["llm_api_key"] = llm_api_key.strip()
    if github_token is not None and github_token.strip():
        values["github_token"] = github_token.strip()
    if zotero_api_key is not None and zotero_api_key.strip():
        values["zotero_api_key"] = zotero_api_key.strip()
    SECRET_FILE.write_text(json.dumps(values), encoding="utf-8")
    SECRET_FILE.chmod(0o600)


def get_secret(name: str) -> str:
    env_names = {"llm_api_key": "LLM_API_KEY", "github_token": "GITHUB_TOKEN", "zotero_api_key": "ZOTERO_API_KEY"}
    return os.getenv(env_names.get(name, ""), "") or str(_load_secrets().get(name, ""))


def ensure_llm_profile(db: Session, settings: dict[str, Any] | None = None) -> LLMProfile | None:
    profiles = db.query(LLMProfile).order_by(LLMProfile.created_at).all()
    if profiles:
        active = next((profile for profile in profiles if profile.is_active), None)
        if active:
            return active
        profiles[0].is_active = True
        db.commit()
        return profiles[0]
    values = settings or dict(DEFAULT_SETTINGS)
    provider = str(values.get("llm_provider") or runtime_settings.llm_provider or "openai")
    profile = LLMProfile(
        id=str(uuid.uuid4()),
        name={"openai": "OpenAI", "claude": "Claude", "glm": "GLM", "deepseek": "DeepSeek", "zhizengzeng": "智增增"}.get(provider, "自定义 API"),
        provider="custom" if provider == "zhizengzeng" else provider,
        base_url=str(values.get("llm_base_url") or runtime_settings.llm_base_url),
        model=str(values.get("llm_model") or runtime_settings.llm_model),
        is_active=True,
    )
    db.add(profile)
    db.commit()
    secrets = _load_secrets()
    legacy_file_key = str(secrets.get("llm_api_key", ""))
    if legacy_file_key:
        save_llm_profile_key(profile.id, legacy_file_key)
        migrated = _load_secrets()
        migrated.pop("llm_api_key", None)
        _write_secrets(migrated)
    elif os.getenv("LLM_API_KEY") or runtime_settings.llm_api_key:
        secrets["llm_env_profile_id"] = profile.id
        _write_secrets(secrets)
    return profile


def get_active_llm_profile(db: Session) -> LLMProfile | None:
    return ensure_llm_profile(db)


def list_llm_profiles(db: Session) -> list[dict[str, Any]]:
    ensure_llm_profile(db)
    return [llm_profile_dict(item) for item in db.query(LLMProfile).order_by(LLMProfile.created_at).all()]


def llm_profile_dict(profile: LLMProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "provider": profile.provider,
        "base_url": profile.base_url,
        "model": profile.model,
        "is_active": profile.is_active,
        "has_api_key": bool(get_llm_profile_key(profile.id)),
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }


def get_llm_profile_key(profile_id: str) -> str:
    secrets = _load_secrets()
    stored = str((secrets.get("llm_api_keys") or {}).get(profile_id, ""))
    if stored:
        return stored
    if secrets.get("llm_env_profile_id") == profile_id:
        return os.getenv("LLM_API_KEY", "") or runtime_settings.llm_api_key
    return ""


def save_llm_profile_key(profile_id: str, api_key: str) -> None:
    if not api_key.strip():
        return
    values = _load_secrets()
    keys = dict(values.get("llm_api_keys") or {})
    keys[profile_id] = api_key.strip()
    values["llm_api_keys"] = keys
    _write_secrets(values)


def delete_llm_profile_key(profile_id: str) -> None:
    values = _load_secrets()
    keys = dict(values.get("llm_api_keys") or {})
    keys.pop(profile_id, None)
    values["llm_api_keys"] = keys
    if values.get("llm_env_profile_id") == profile_id:
        values.pop("llm_env_profile_id", None)
    _write_secrets(values)


def _load_secrets() -> dict[str, Any]:
    if not SECRET_FILE.exists():
        return {}
    try:
        return json.loads(SECRET_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_secrets(values: dict[str, Any]) -> None:
    SECRET_FILE.write_text(json.dumps(values), encoding="utf-8")
    SECRET_FILE.chmod(0o600)
