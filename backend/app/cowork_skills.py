from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import DATA_DIR, ROOT_DIR
from .cowork_models import SkillManifest


SKILL_ROOT = ROOT_DIR / "backend" / "cowork_skills"
USER_SKILL_ROOT = DATA_DIR / "cowork_skills"


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


def validate_imported_skill(payload: dict, available_tools: set[str]) -> dict:
    allowed_keys = {"name", "description", "version", "allowed_tools", "source", "license", "instructions"}
    extra = set(payload) - allowed_keys
    if extra:
        raise ValueError(f"Skill 清单包含不支持的字段：{', '.join(sorted(extra))}")
    name = str(payload.get("name", "")).strip()
    description = str(payload.get("description", "")).strip()
    version = str(payload.get("version", "")).strip()
    source = str(payload.get("source", "")).strip()
    license_name = str(payload.get("license", "")).strip()
    instructions = str(payload.get("instructions", "")).strip()
    tools = payload.get("allowed_tools", [])
    if not name or len(name) > 160 or not all(char.isalnum() or char in "-_." for char in name):
        raise ValueError("Skill 名称只能包含字母、数字、短横线、下划线和点")
    if not description or len(description) > 2000:
        raise ValueError("Skill 说明不能为空且不能超过 2000 字")
    if not version or len(version) > 40 or not source or len(source) > 1000 or not license_name or len(license_name) > 120:
        raise ValueError("版本、来源和许可证必须填写")
    if not isinstance(tools, list) or len(tools) > 20 or any(not isinstance(item, str) for item in tools):
        raise ValueError("allowed_tools 必须是最多 20 项的工具名称列表")
    unknown = sorted(set(tools) - available_tools)
    if unknown:
        raise ValueError(f"Skill 声明了未开放的工具：{', '.join(unknown)}")
    if not instructions or len(instructions) > 20_000:
        raise ValueError("Skill 说明必须在 1–20000 字之间")
    unsafe_markers = ("execute shell", "执行 shell", "subprocess", "os.system", "curl ", "wget ", "读取 .env", "api key")
    lowered = instructions.lower()
    if any(marker in lowered for marker in unsafe_markers):
        raise ValueError("Skill 说明包含被禁止的脚本、密钥或外部执行要求")
    return {
        "name": name, "description": description, "version": version, "allowed_tools": list(dict.fromkeys(tools)),
        "source": source, "license": license_name, "instructions": instructions,
    }


def import_skill(db: Session, payload: dict, available_tools: set[str]) -> SkillManifest:
    values = validate_imported_skill(payload, available_tools)
    existing = db.scalar(select(SkillManifest).where(SkillManifest.name == values["name"], SkillManifest.version == values["version"]))
    if existing:
        raise ValueError("相同名称和版本的 Skill 已存在")
    content = values.pop("instructions")
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    folder = USER_SKILL_ROOT / checksum[:16]
    folder.mkdir(parents=True, exist_ok=False)
    entry = folder / "SKILL.md"
    entry.write_text(content, encoding="utf-8")
    item = SkillManifest(
        id=str(uuid.uuid4()), entrypoint=str(entry), checksum=checksum, enabled=True,
        reviewed_at=datetime.now(timezone.utc), allowed_tools_json=json.dumps(values.pop("allowed_tools"), ensure_ascii=False),
        **values,
    )
    db.add(item); db.flush()
    return item


def load_skill_instruction(item: SkillManifest) -> str:
    path = Path(item.entrypoint).resolve(strict=True)
    trusted_roots = (SKILL_ROOT.resolve(), USER_SKILL_ROOT.resolve())
    if not any(root in path.parents for root in trusted_roots):
        raise PermissionError("Skill 入口不在受控目录")
    if hashlib.sha256(path.read_bytes()).hexdigest() != item.checksum:
        raise PermissionError("Skill 校验失败，已拒绝加载")
    return path.read_text(encoding="utf-8")[:20_000]
