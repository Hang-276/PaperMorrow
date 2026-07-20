from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import ROOT_DIR
from .cowork_models import SkillManifest


SKILL_ROOT = ROOT_DIR / "backend" / "cowork_skills"


def load_builtin_catalog() -> list[dict]:
    catalog = json.loads((SKILL_ROOT / "catalog.json").read_text(encoding="utf-8"))
    if not isinstance(catalog, list):
        raise ValueError("Cowork Skill 目录格式无效")
    return catalog


def seed_builtin_skills(db: Session) -> None:
    for item in load_builtin_catalog():
        entry = (SKILL_ROOT / item["entrypoint"]).resolve(strict=True)
        if SKILL_ROOT.resolve() not in entry.parents:
            raise ValueError("Skill 入口越过内置目录")
        checksum = hashlib.sha256(entry.read_bytes()).hexdigest()
        existing = db.scalar(select(SkillManifest).where(SkillManifest.name == item["name"], SkillManifest.version == item["version"]))
        values = {
            "description": item["description"], "entrypoint": str(entry),
            "allowed_tools_json": json.dumps(item["allowed_tools"], ensure_ascii=False),
            "source": item["source"], "license": item["license"], "enabled": True,
            "checksum": checksum, "reviewed_at": datetime.now(timezone.utc),
        }
        if existing:
            for key, value in values.items(): setattr(existing, key, value)
        else:
            db.add(SkillManifest(id=str(uuid.uuid4()), name=item["name"], version=item["version"], **values))
    db.commit()


def skill_dict(item: SkillManifest) -> dict:
    return {
        "id": item.id, "name": item.name, "description": item.description, "version": item.version,
        "allowed_tools": json.loads(item.allowed_tools_json or "[]"), "source": item.source,
        "license": item.license, "enabled": item.enabled, "checksum": item.checksum,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }


def load_skill_instruction(item: SkillManifest) -> str:
    path = Path(item.entrypoint).resolve(strict=True)
    if SKILL_ROOT.resolve() not in path.parents:
        raise PermissionError("Skill 入口不在受信任内置目录")
    if hashlib.sha256(path.read_bytes()).hexdigest() != item.checksum:
        raise PermissionError("Skill 校验失败，已拒绝加载")
    return path.read_text(encoding="utf-8")[:20_000]
