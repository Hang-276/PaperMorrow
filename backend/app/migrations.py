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


MIGRATIONS = [("001_domain_packs", _migration_001_domain_packs)]


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
