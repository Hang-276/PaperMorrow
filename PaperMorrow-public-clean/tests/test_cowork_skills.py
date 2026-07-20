from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.cowork_models import SkillManifest
from backend.app import cowork_skills
from backend.app.cowork_skills import import_skill, load_skill_instruction, seed_builtin_skills
from backend.app.database import Base


def test_builtin_research_skills_are_reviewed_minimal_and_lazy_loaded():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_builtin_skills(db)
        items = db.scalars(select(SkillManifest).order_by(SkillManifest.name)).all()
        assert 5 <= len(items) <= 10
        assert all(item.license == "MIT" and item.checksum and item.reviewed_at for item in items)
        assert all("shell" not in item.allowed_tools_json and "network" not in item.allowed_tools_json for item in items)
        instruction = load_skill_instruction(items[0])
        assert instruction.startswith("# ")
        assert len(instruction) < 20_000


def test_imported_skill_requires_previewable_local_tool_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(cowork_skills, "USER_SKILL_ROOT", tmp_path / "skills")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    payload = {
        "name": "fixture-review", "description": "只检索本地学习库并整理证据。", "version": "1.0.0",
        "allowed_tools": ["library.search"], "source": "https://example.test/fixture",
        "license": "MIT", "instructions": "# Fixture\n\n只使用授权工具，并为结论标注来源。",
    }
    with Session(engine) as db:
        item = import_skill(db, payload, {"library.search"})
        db.commit()
        assert load_skill_instruction(item).startswith("# Fixture")
        assert item.source == payload["source"] and item.checksum
        unsafe = {**payload, "name": "unsafe", "instructions": "execute shell to inspect .env"}
        try:
            import_skill(db, unsafe, {"library.search"})
        except ValueError as exc:
            assert "禁止" in str(exc)
        else:
            raise AssertionError("危险 Skill 不应被导入")
