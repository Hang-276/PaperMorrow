import os
import tempfile
import uuid
import zipfile
from pathlib import Path

_TEST_ROOT = tempfile.mkdtemp(prefix="papermorrow-presentations-")
os.environ.setdefault("PAPERMORROW_DATA_DIR", _TEST_ROOT)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_ROOT}/fixture.db")
os.environ["LLM_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal, init_db
from backend.app.main import app
from backend.app.models import LibraryEntry, Paper


def test_editable_outline_supports_manual_paper_and_note_references():
    init_db()
    marker = uuid.uuid4().hex
    db = SessionLocal()
    paper = Paper(
        title_en=f"Outline fixture {marker}", abstract_en="A grounded method and one measured result.",
        authors_json='["Researcher A"]', primary_url="https://example.com/outline-paper", identity_hash=marker,
    )
    paper.library_entry = LibraryEntry(source="fixture")
    db.add(paper); db.commit(); paper_id = paper.id; db.close()
    with TestClient(app) as client:
        reader = client.put(f"/api/papers/{paper_id}/note", json={"content": "# 组会主题\n\n## 方法\n\n## 实验结果\n\n## 下一步"})
        note_id = reader.json()["note_id"]
        created = client.post("/api/presentations/outlines", json={
            "note_id": note_id, "kind": "paper-report", "slide_count": 8, "use_ai": True,
            "instructions": "用于无真实 API Key 的组会 fixture",
        })
        assert created.status_code == 201, created.text
        draft = created.json()
        assert draft["status"] == "outline" and draft["outline"]["slides"]
        source_ids = {item["id"] for item in draft["sources"]}
        assert {f"NOTE-{note_id}", f"PAPER-{paper_id}"} <= source_ids

        outline = draft["outline"]
        outline["slides"][0]["title"] = "用户编辑后的汇报标题"
        outline["slides"][0]["key_message"] = "这是一份可检查、可修改的大纲"
        outline["slides"][0]["points"] = ["先确认叙事结构", "再生成可编辑 PPTX"]
        outline["slides"][0]["source_refs"] = [f"NOTE-{note_id}", f"PAPER-{paper_id}"]
        saved = client.put(f"/api/presentations/{draft['id']}/outline", json={"outline": outline})
        assert saved.status_code == 200
        assert saved.json()["outline"]["slides"][0]["title"] == "用户编辑后的汇报标题"

        invalid = dict(outline)
        invalid["slides"] = [dict(item) for item in outline["slides"]]
        invalid["slides"][0]["source_refs"] = ["PAPER-DOES-NOT-EXIST"]
        rejected = client.put(f"/api/presentations/{draft['id']}/outline", json={"outline": invalid})
        assert rejected.status_code == 422


@pytest.mark.skipif(not Path("presentation-studio/node_modules/pptxgenjs").exists(), reason="独立 PPT 引擎依赖尚未安装")
def test_outline_compiles_to_editable_pptx_fixture():
    init_db()
    with TestClient(app) as client:
        note = client.post("/api/notes", json={"title": "PPT fixture", "content": "# 研究问题\n\n## 方法\n\n## 结果", "paper_ids": []}).json()
        draft = client.post("/api/presentations/outlines", json={"note_id": note["id"], "kind": "lab-meeting", "use_ai": False, "slide_count": 6}).json()
        generated = client.post(f"/api/presentations/{draft['id']}/generate")
        assert generated.status_code == 200, generated.text
        download = client.get(generated.json()["download_url"])
        assert download.status_code == 200
        output = Path(_TEST_ROOT) / "fixture.pptx"
        output.write_bytes(download.content)
        assert zipfile.is_zipfile(output)
        with zipfile.ZipFile(output) as archive:
            assert "ppt/presentation.xml" in archive.namelist()
            assert any(name.startswith("ppt/slides/slide") for name in archive.namelist())
