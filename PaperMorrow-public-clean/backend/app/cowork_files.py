from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .cowork_models import PermissionGrant
from .cowork_security import BLOCKED_FILE_NAMES, BLOCKED_SUFFIXES


class FileAccessDenied(PermissionError):
    pass


def resolve_authorized_path(db: Session, session_id: str, requested_path: str, *, write: bool = False) -> Path:
    requested = Path(requested_path).expanduser()
    if not requested.is_absolute():
        raise FileAccessDenied("文件路径必须为绝对路径")
    try:
        resolved = requested.resolve(strict=not write)
    except (FileNotFoundError, RuntimeError) as exc:
        raise FileAccessDenied("目标不存在或路径无效") from exc
    if resolved.name.lower() in BLOCKED_FILE_NAMES or resolved.suffix.lower() in BLOCKED_SUFFIXES:
        raise FileAccessDenied("密钥或凭据文件禁止读取")
    if any(part.startswith(".") for part in resolved.parts if part not in {".", ".."}):
        raise FileAccessDenied("默认禁止读取隐藏文件或目录")
    grants = db.scalars(select(PermissionGrant).where(
        PermissionGrant.session_id == session_id,
        PermissionGrant.resource_type.in_(["file", "folder"]),
        PermissionGrant.revoked_at.is_(None),
    )).all()
    for grant in grants:
        if write and not grant.can_write:
            continue
        if not write and not grant.can_read:
            continue
        root = Path(grant.normalized_path or "").resolve(strict=True)
        if grant.resource_type == "file" and resolved == root:
            return resolved
        if grant.resource_type == "folder" and (resolved == root or root in resolved.parents):
            return resolved
    raise FileAccessDenied("目标不在本会话授权范围内")


def read_authorized_text(db: Session, session_id: str, path: str, *, max_bytes: int = 1_000_000) -> str:
    resolved = resolve_authorized_path(db, session_id, path)
    if not resolved.is_file():
        raise FileAccessDenied("目标不是普通文件")
    if resolved.stat().st_size > max_bytes:
        raise FileAccessDenied("文件过大，请缩小资料范围")
    return resolved.read_text(encoding="utf-8", errors="replace")
