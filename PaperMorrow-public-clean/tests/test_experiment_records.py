import os
import tempfile
from pathlib import Path

_TEST_ROOT = tempfile.mkdtemp(prefix="papermorrow-experiments-")
os.environ.setdefault("PAPERMORROW_DATA_DIR", _TEST_ROOT)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_ROOT}/fixture.db")
os.environ["LLM_API_KEY"] = ""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app.database import init_db
from backend.app.main import app
from backend.app.migrations import run_migrations


def test_experiment_migration_is_incremental_and_preserves_existing_rows(tmp_path: Path):
    database = tmp_path / "legacy.db"
    migration_engine = create_engine(f"sqlite:///{database}")
    with migration_engine.begin() as connection:
        connection.execute(text("CREATE TABLE user_fixture (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO user_fixture(id, value) VALUES (1, 'keep-me')"))
    completed = run_migrations(migration_engine)
    assert "007_experiment_records" in completed
    with migration_engine.begin() as connection:
        assert connection.execute(text("SELECT value FROM user_fixture WHERE id=1")).scalar_one() == "keep-me"
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert {"project_experiments", "experiment_metrics", "experiment_artifacts", "experiment_analyses"} <= tables
    backups = list((tmp_path / "backups").glob("legacy-pre-*.db"))
    assert backups, "增量迁移前应自动创建 SQLite 备份"


def test_experiment_api_summary_timeline_and_no_llm_fallback():
    init_db()
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "实验 fixture 项目"})
        assert project.status_code == 200
        project_id = project.json()["id"]

        baseline = client.post(f"/api/projects/{project_id}/experiments", json={
            "title": "Baseline",
            "objective": "建立可比较基线",
            "experiment_type": "baseline",
            "status": "completed",
            "config": {"learning_rate": 0.001, "seed": 7},
            "dataset_version": "fixture-v1",
            "code_reference": "fixture-commit-a",
            "metrics": [{"name": "accuracy", "value": 0.71, "split": "test", "is_primary": True}],
        })
        assert baseline.status_code == 200, baseline.text
        baseline_id = baseline.json()["id"]

        ablation = client.post(f"/api/projects/{project_id}/experiments", json={
            "title": "Ablation without memory",
            "objective": "验证记忆模块贡献",
            "hypothesis": "移除记忆后准确率下降",
            "experiment_type": "ablation",
            "status": "completed",
            "parent_experiment_id": baseline_id,
            "config": {"learning_rate": 0.001, "seed": 7, "memory": False},
            "metrics": [{"name": "accuracy", "value": 0.64, "split": "test", "is_primary": True}],
            "artifacts": [{"artifact_type": "log", "name": "run.log", "uri": "fixture://run.log"}],
        })
        assert ablation.status_code == 200, ablation.text

        appended = client.post(
            f"/api/projects/{project_id}/experiments/{baseline_id}/metrics",
            json={"metrics": [{"name": "loss", "value": 0.42, "step": 100, "split": "validation"}]},
        )
        assert appended.status_code == 200

        summary = client.get(f"/api/projects/{project_id}/experiments/summary")
        assert summary.status_code == 200
        payload = summary.json()
        assert payload["experiment_count"] == 2
        assert payload["status_counts"]["completed"] == 2
        assert len(payload["timeline"]) == 2
        assert payload["metric_series"]["accuracy:test"][1]["delta_previous"] == -0.07

        other = client.post("/api/projects", json={"title": "隔离项目"}).json()
        graph = client.get(f"/api/projects/{project_id}/knowledge-graph")
        assert graph.status_code == 200
        graph_payload = graph.json()
        assert graph_payload["scope"] == {"type": "project", "id": project_id, "title": "实验 fixture 项目"}
        assert {node["id"] for node in graph_payload["nodes"]} >= {f"project:{project_id}", f"experiment:{baseline_id}"}
        assert f"project:{other['id']}" not in {node["id"] for node in graph_payload["nodes"]}

        analysis = client.post(
            f"/api/projects/{project_id}/experiments/analyze",
            json={"question": "准确率发生了什么变化？"},
        )
        assert analysis.status_code == 200, analysis.text
        result = analysis.json()
        assert result["used_llm"] is False
        assert "EXP-" in result["answer"]
        assert {item["experiment_id"] for item in result["sources"]} == {baseline_id, ablation.json()["id"]}

        search = client.post(f"/api/projects/{project_id}/search", json={"query": "accuracy", "limit": 10})
        assert search.status_code == 200
        assert any(item["source_type"] == "experiment" for item in search.json()["items"])
