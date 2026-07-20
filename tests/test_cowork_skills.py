from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.cowork_models import SkillManifest
from backend.app.cowork_skills import load_skill_instruction, seed_builtin_skills
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
