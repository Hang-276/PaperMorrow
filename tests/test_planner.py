import os
import tempfile
from pathlib import Path

_TEST_ROOT = tempfile.mkdtemp(prefix="papermorrow-planner-")
os.environ.setdefault("PAPERMORROW_DATA_DIR", _TEST_ROOT)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_ROOT}/fixture.db")
os.environ["LLM_API_KEY"] = ""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app.database import init_db
from backend.app.main import app
from backend.app.migrations import run_migrations


def test_planner_migration_preserves_existing_data_and_creates_backup(tmp_path: Path):
    database = tmp_path / "legacy-planner.db"
    migration_engine = create_engine(f"sqlite:///{database}")
    with migration_engine.begin() as connection:
        connection.execute(text("CREATE TABLE user_history (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO user_history VALUES (1, 'must-stay')"))
    completed = run_migrations(migration_engine)
    assert "009_planner_deadlines" in completed
    with migration_engine.begin() as connection:
        assert connection.execute(text("SELECT value FROM user_history WHERE id=1")).scalar_one() == "must-stay"
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert {"planner_tasks", "submission_deadlines"} <= tables
    assert list((tmp_path / "backups").glob("legacy-planner-pre-*.db"))


def test_planner_task_and_submission_deadline_crud():
    init_db()
    with TestClient(app) as client:
        task = client.post("/api/planner/tasks", json={
            "title": "整理消融实验", "details": "汇总三个随机种子", "priority": "high",
            "due_at": "2030-03-01T10:00:00Z",
        })
        assert task.status_code == 201, task.text
        task_id = task.json()["id"]
        assert task.json()["status"] == "pending"
        assert any(item["id"] == task_id for item in client.get("/api/planner/tasks").json())

        completed = client.put(f"/api/planner/tasks/{task_id}", json={"status": "completed"})
        assert completed.status_code == 200
        assert completed.json()["completed_at"]
        assert all(item["id"] != task_id for item in client.get("/api/planner/tasks").json())
        assert any(item["id"] == task_id for item in client.get("/api/planner/tasks?include_completed=true").json())

        deadline = client.post("/api/planner/deadlines", json={
            "venue_name": "Fixture Research Conference", "venue_type": "conference", "round_name": "Main Track",
            "deadline_at": "2030-04-15T23:59:00Z", "timezone_name": "AoE (UTC-12)",
            "domain": "人工智能", "website_url": "https://example.com/cfp", "remind_days_before": 21,
        })
        assert deadline.status_code == 201, deadline.text
        deadline_id = deadline.json()["id"]
        assert deadline.json()["source"] == "user"
        assert deadline.json()["website_url"] == "https://example.com/cfp"

        updated = client.put(f"/api/planner/deadlines/{deadline_id}", json={"venue_type": "journal", "enabled": False})
        assert updated.status_code == 200 and updated.json()["venue_type"] == "journal"
        assert all(item["id"] != deadline_id for item in client.get("/api/planner/deadlines").json())
        assert any(item["id"] == deadline_id for item in client.get("/api/planner/deadlines?include_disabled=true").json())

        assert client.delete(f"/api/planner/tasks/{task_id}").status_code == 204
        assert client.delete(f"/api/planner/deadlines/{deadline_id}").status_code == 204


def test_timezone_settings_accept_iana_and_share_deadline_timezone():
    init_db()
    with TestClient(app) as client:
        response = client.put("/api/settings", json={
            "timezone": "Europe/London", "timezone_auto": False, "daylight_saving_enabled": True,
        })
        assert response.status_code == 200
        settings = response.json()
        assert settings["timezone"] == "Europe/London"
        assert settings["timezone_auto"] is False
        assert settings["daylight_saving_enabled"] is True

        deadline = client.post("/api/planner/deadlines", json={
            "venue_name": "Timezone Fixture", "deadline_at": "2035-06-01T12:00:00Z",
            "timezone_name": settings["timezone"],
        })
        assert deadline.status_code == 201
        assert deadline.json()["timezone_name"] == settings["timezone"]
        assert client.delete(f"/api/planner/deadlines/{deadline.json()['id']}").status_code == 204

        assert client.put("/api/settings", json={"timezone": "Mars/Olympus"}).status_code == 422
