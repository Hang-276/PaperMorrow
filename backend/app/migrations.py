from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, inspect, text


def _backup_sqlite(engine: Engine, label: str) -> Path | None:
    url = engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    source = Path(url.database).resolve()
    if not source.exists() or source.stat().st_size == 0:
        return None
    backup_dir = source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"{source.stem}-pre-{label}-{stamp}{source.suffix}"
    shutil.copy2(source, target)
    return target


def _migration_001_domain_packs(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS domain_packs (
            id INTEGER PRIMARY KEY,
            slug VARCHAR(80) NOT NULL UNIQUE,
            name_zh VARCHAR(160) NOT NULL,
            name_en VARCHAR(160) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_builtin BOOLEAN NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 1,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            source_adapters_json TEXT NOT NULL DEFAULT '[]',
            search_templates_json TEXT NOT NULL DEFAULT '[]',
            keywords_json TEXT NOT NULL DEFAULT '[]',
            exclusions_json TEXT NOT NULL DEFAULT '[]',
            category_codes_json TEXT NOT NULL DEFAULT '[]',
            venue_rules_json TEXT NOT NULL DEFAULT '[]',
            paper_types_json TEXT NOT NULL DEFAULT '[]',
            scoring_weights_json TEXT NOT NULL DEFAULT '{}',
            evidence_rules_json TEXT NOT NULL DEFAULT '{}',
            analysis_prompt TEXT NOT NULL DEFAULT '',
            review_prompt TEXT NOT NULL DEFAULT '',
            citation_config_json TEXT NOT NULL DEFAULT '{}',
            impact_config_json TEXT NOT NULL DEFAULT '{}',
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
    """))
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS domain_metrics (
            id INTEGER PRIMARY KEY,
            domain_pack_id INTEGER NOT NULL REFERENCES domain_packs(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            value FLOAT NOT NULL,
            year INTEGER NOT NULL,
            source_url TEXT NOT NULL,
            created_at DATETIME NOT NULL
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_domain_metrics_pack ON domain_metrics(domain_pack_id)"))
    inspector = inspect(connection)
    if "research_profiles" in inspector.get_table_names():
        columns = {item["name"] for item in inspector.get_columns("research_profiles")}
        if "domain_pack_id" not in columns:
            connection.execute(text("ALTER TABLE research_profiles ADD COLUMN domain_pack_id INTEGER"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_research_profiles_domain_pack_id ON research_profiles(domain_pack_id)"))


def _migration_002_research_projects(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS research_projects (
            id INTEGER PRIMARY KEY, title VARCHAR(500) NOT NULL,
            research_question TEXT NOT NULL DEFAULT '', research_direction TEXT NOT NULL DEFAULT '',
            domain_pack_id INTEGER REFERENCES domain_packs(id) ON DELETE SET NULL,
            research_profile_id INTEGER REFERENCES research_profiles(id) ON DELETE SET NULL,
            repository_url TEXT, deepwiki_job_id INTEGER REFERENCES deepwiki_jobs(id) ON DELETE SET NULL,
            current_conclusion TEXT NOT NULL DEFAULT '', unresolved_questions_json TEXT NOT NULL DEFAULT '[]',
            next_reading_suggestion TEXT NOT NULL DEFAULT '', created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        )
    """))
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS research_project_papers (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
            paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE, role VARCHAR(24) NOT NULL DEFAULT 'to_verify',
            reading_status VARCHAR(32) NOT NULL DEFAULT 'to_screen', queue_order INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, UNIQUE(project_id, paper_id)
        )
    """))
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS research_project_notes (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
            title VARCHAR(300) NOT NULL DEFAULT '项目笔记', content TEXT NOT NULL DEFAULT '',
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        )
    """))
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS research_project_studies (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
            study_id INTEGER NOT NULL REFERENCES research_studies(id) ON DELETE CASCADE, UNIQUE(project_id, study_id)
        )
    """))
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS project_chat_messages (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
            role VARCHAR(16) NOT NULL, content TEXT NOT NULL, sources_json TEXT NOT NULL DEFAULT '[]', created_at DATETIME NOT NULL
        )
    """))
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_research_project_papers_project ON research_project_papers(project_id)",
        "CREATE INDEX IF NOT EXISTS ix_research_project_notes_project ON research_project_notes(project_id)",
        "CREATE INDEX IF NOT EXISTS ix_project_chat_messages_project ON project_chat_messages(project_id)",
    ):
        connection.execute(text(statement))
    connection.execute(text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS project_search_fts USING fts5(
            project_id UNINDEXED, source_type UNINDEXED, source_id UNINDEXED, title, content,
            tokenize='unicode61 remove_diacritics 2'
        )
    """))


MIGRATIONS = [
    ("001_domain_packs", _migration_001_domain_packs),
    ("002_research_projects", _migration_002_research_projects),
]


def run_migrations(engine: Engine) -> list[str]:
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(120) PRIMARY KEY, applied_at DATETIME NOT NULL)"))
        applied = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
    pending = [(version, migration) for version, migration in MIGRATIONS if version not in applied]
    if pending:
        _backup_sqlite(engine, pending[0][0])
    completed: list[str] = []
    for version, migration in pending:
        with engine.begin() as connection:
            migration(connection)
            connection.execute(text("INSERT INTO schema_migrations(version, applied_at) VALUES (:version, :applied_at)"), {"version": version, "applied_at": datetime.now(timezone.utc)})
        completed.append(version)
    return completed
