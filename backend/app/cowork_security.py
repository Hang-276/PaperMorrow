from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .cowork_models import CoworkAuditLog, PermissionGrant


SECRET_KEY_PATTERN = re.compile(r"(api[_-]?key|authorization|password|secret|token|cookie)", re.IGNORECASE)
SECRET_VALUE_PATTERN = re.compile(r"(?i)(bearer\s+\S+|sk-[a-z0-9_-]{12,}|gh[opusr]_[a-z0-9]{12,})")
BLOCKED_FILE_NAMES = {".env", ".npmrc", ".pypirc", "credentials", "credentials.json", "secrets.json"}
BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def redact_sensitive(value: Any) -> Any:
    """Return an audit-safe copy without credentials or full file bodies."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_KEY_PATTERN.search(str(key)):
                cleaned[str(key)] = "[REDACTED]"
            elif str(key).lower() in {"content", "file_content", "body", "raw_text"} and isinstance(item, str):
                cleaned[str(key)] = f"[CONTENT OMITTED: {len(item)} chars]"
            else:
                cleaned[str(key)] = redact_sensitive(item)
        return cleaned
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return SECRET_VALUE_PATTERN.sub("[REDACTED]", value)
    return value


def write_audit(db: Session, event_type: str, summary: str, *, session_id: str | None = None, actor: str = "system", details: dict[str, Any] | None = None) -> CoworkAuditLog:
    item = CoworkAuditLog(
        session_id=session_id,
        event_type=event_type,
        actor=actor,
        summary=SECRET_VALUE_PATTERN.sub("[REDACTED]", summary),
        details_json=json.dumps(redact_sensitive(details or {}), ensure_ascii=False),
    )
    db.add(item)
    db.flush()
    return item


def normalize_selected_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise ValueError("必须选择绝对路径")
    resolved = path.resolve(strict=True)
    if resolved.name.lower() in BLOCKED_FILE_NAMES or resolved.suffix.lower() in BLOCKED_SUFFIXES:
        raise PermissionError("密钥或凭据文件不能授权给 Agent")
    return resolved


def create_grant(db: Session, session_id: str, resource_type: str, resource_scope: str, *, can_read: bool, can_write: bool, duration: str = "session") -> PermissionGrant:
    if not can_read and not can_write:
        raise ValueError("授权必须至少包含读取或写入权限")
    if duration not in {"session", "permanent"}:
        raise ValueError("不支持的授权期限")
    normalized_path = None
    if resource_type in {"file", "folder"}:
        normalized_path = str(normalize_selected_path(resource_scope))
    grant = PermissionGrant(
        id=str(uuid.uuid4()), session_id=session_id, resource_type=resource_type,
        resource_scope=resource_scope, normalized_path=normalized_path,
        can_read=can_read, can_write=can_write, duration=duration,
    )
    db.add(grant)
    write_audit(db, "permission.granted", "用户授予受限资源权限", session_id=session_id, actor="user", details={
        "grant_id": grant.id, "resource_type": resource_type, "scope": resource_scope,
        "can_read": can_read, "can_write": can_write, "duration": duration,
    })
    return grant


def revoke_grant(db: Session, grant: PermissionGrant) -> None:
    grant.revoked_at = utcnow()
    write_audit(db, "permission.revoked", "用户撤销资源权限", session_id=grant.session_id, actor="user", details={"grant_id": grant.id})


def has_object_permission(db: Session, session_id: str, resource_type: str, resource_scope: str, *, write: bool = False) -> bool:
    grants = db.scalars(select(PermissionGrant).where(
        PermissionGrant.session_id == session_id,
        PermissionGrant.resource_type == resource_type,
        PermissionGrant.revoked_at.is_(None),
    )).all()
    for grant in grants:
        if grant.resource_scope == resource_scope and (grant.can_write if write else grant.can_read):
            return True
    return False
