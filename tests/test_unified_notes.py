import os
import tempfile
import uuid
from pathlib import Path

_TEST_ROOT = tempfile.mkdtemp(prefix="papermorrow-notes-")
os.environ.setdefault("PAPERMORROW_DATA_DIR", _TEST_ROOT)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_ROOT}/fixture.db")
os.environ["LLM_API_KEY"] = ""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app.database import SessionLocal, init_db
from backend.app.main import app
from backend.app.migrations import run_migrations
from backend.app.models import LibraryEntry, Paper


def test_unified_note_migration_keeps_legacy_reader_note_and_creates_backup(tmp_path: Path):
    database = tmp_path / "legacy-notes.db"
    migration_engine = create_engine(f"sqlite:///{database}")
    with migration_engine.begin() as connection:
        connection.execute(text("CREATE TABLE papers (id INTEGER PRIMARY KEY, title_en TEXT NOT NULL, title_zh TEXT)"))
        connection.execute(text("CREATE TABLE paper_notes (paper_id INTEGER PRIMARY KEY, content TEXT NOT NULL, updated_at DATETIME NOT NULL)"))
        connection.execute(text("INSERT INTO papers VALUES (8, 'Legacy Paper', '历史论文')"))
        connection.execute(text("INSERT INTO paper_notes VALUES (8, '# 不可丢失的笔记', '2026-01-02 03:04:05')"))
    completed = run_migrations(migration_engine)
    assert "006_unified_notes" in completed
    with migration_engine.begin() as connection:
        row = connection.execute(text("SELECT title, content, legacy_paper_id FROM notes")).one()
        assert row == ("历史论文", "# 不可丢失的笔记", 8)
        assert connection.execute(text("SELECT content FROM paper_notes WHERE paper_id=8")).scalar_one() == "# 不可丢失的笔记"
    assert list((tmp_path / "backups").glob("legacy-notes-pre-*.db"))


def test_note_api_unifies_reader_and_standalone_notes_with_citations():
    init_db()
    marker = uuid.uuid4().hex
    db = SessionLocal()
    paper = Paper(
        title_en=f"Fixture paper {marker}", abstract_en="fixture", authors_json="[]",
        primary_url="https://example.com/paper", identity_hash=marker,
    )
    paper.library_entry = LibraryEntry(source="fixture")
    db.add(paper); db.commit(); paper_id = paper.id; db.close()
    with TestClient(app) as client:
        reader = client.put(f"/api/papers/{paper_id}/note", json={"content": "# 阅读记录\n\n实验值得复现。"})
        assert reader.status_code == 200 and reader.json()["note_id"]
        notes = client.get(f"/api/notes?paper_id={paper_id}").json()
        assert len(notes) == 1 and notes[0]["origin"] == "reader"
        note_id = notes[0]["id"]
        updated = client.put(f"/api/notes/{note_id}", json={"content": "# 已在完整编辑器更新", "paper_ids": [paper_id]})
        assert updated.status_code == 200
        assert client.get("/api/library/papers").json()[0]["note"] == "# 已在完整编辑器更新"

        standalone = client.post("/api/notes", json={
            "title": "独立研究笔记", "document_format": "markdown", "editor_mode": "standard",
            "content": "# 研究问题\n\n## 方法\n\n## 结果", "paper_ids": [paper_id],
        })
        assert standalone.status_code == 201
        artifact = client.post(f"/api/notes/{standalone.json()['id']}/artifacts", json={"type": "flowchart"})
        assert artifact.status_code == 201
        assert artifact.json()["content"].startswith("flowchart TD")
