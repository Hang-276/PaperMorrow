from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from backend.app.cowork_models import CoworkSession
from backend.app.cowork_security import create_grant, has_object_permission, redact_sensitive, revoke_grant, write_audit
from backend.app.migrations import run_migrations


def test_cowork_migration_preserves_existing_data_and_creates_backup(tmp_path: Path):
    database = tmp_path / "existing.db"
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE legacy_user_data (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO legacy_user_data(value) VALUES ('keep me')"))
    completed = run_migrations(engine)
    assert "010_cowork_foundation" in completed
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT value FROM legacy_user_data")) == "keep me"
    assert "cowork_sessions" in inspect(engine).get_table_names()
    assert list((tmp_path / "backups").glob("existing-pre-001_domain_packs-*.db"))


def test_permissions_are_default_deny_and_revocable(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    with Session(engine) as db:
        session = CoworkSession(id="s1", title="test")
        db.add(session)
        db.flush()
        assert not has_object_permission(db, "s1", "note", "42")
        grant = create_grant(db, "s1", "note", "42", can_read=True, can_write=False)
        db.flush()
        assert has_object_permission(db, "s1", "note", "42")
        assert not has_object_permission(db, "s1", "note", "42", write=True)
        revoke_grant(db, grant)
        db.flush()
        assert not has_object_permission(db, "s1", "note", "42")


def test_secret_files_and_audit_values_are_redacted(tmp_path: Path):
    secret = tmp_path / ".env"
    secret.write_text("OPENAI_API_KEY=sk-do-not-read")
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    with Session(engine) as db:
        db.add(CoworkSession(id="s1", title="test"))
        db.flush()
        with pytest.raises(PermissionError):
            create_grant(db, "s1", "file", str(secret), can_read=True, can_write=False)
        audit = write_audit(db, "test", "Bearer private-token", session_id="s1", details={"api_key": "sk-private-value", "content": "paper body"})
        assert "private-token" not in audit.summary
        parsed = json.loads(audit.details_json)
        assert parsed["api_key"] == "[REDACTED]"
        assert parsed["content"].startswith("[CONTENT OMITTED")
    assert redact_sensitive({"password": "x"}) == {"password": "[REDACTED]"}
