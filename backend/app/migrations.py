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


def _migration_003_paper_evidence_versions(connection) -> None:
    connection.execute(text("CREATE TABLE IF NOT EXISTS paper_works (id INTEGER PRIMARY KEY, canonical_title TEXT NOT NULL, created_at DATETIME NOT NULL)"))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS paper_versions (
        id INTEGER PRIMARY KEY, work_id INTEGER NOT NULL REFERENCES paper_works(id) ON DELETE CASCADE,
        paper_id INTEGER NOT NULL UNIQUE REFERENCES papers(id) ON DELETE CASCADE, version_label VARCHAR(160) NOT NULL DEFAULT '原始版本',
        relation_type VARCHAR(32) NOT NULL DEFAULT 'same_work', confidence FLOAT NOT NULL DEFAULT 1,
        confirmed BOOLEAN NOT NULL DEFAULT 1, match_reason TEXT NOT NULL DEFAULT '', important_changes TEXT NOT NULL DEFAULT '',
        version_date DATETIME, created_at DATETIME NOT NULL)"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS paper_merge_audits (
        id INTEGER PRIMARY KEY, paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        from_work_id INTEGER, to_work_id INTEGER, action VARCHAR(24) NOT NULL, snapshot_json TEXT NOT NULL DEFAULT '{}', created_at DATETIME NOT NULL)"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS paper_analysis_evidence (
        id INTEGER PRIMARY KEY, paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        field_name VARCHAR(80) NOT NULL, claim TEXT NOT NULL, page_number INTEGER, section VARCHAR(500),
        evidence_excerpt TEXT NOT NULL DEFAULT '', source_scope VARCHAR(24) NOT NULL DEFAULT 'abstract',
        conclusion_type VARCHAR(24) NOT NULL DEFAULT 'paper_fact', created_at DATETIME NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_paper_versions_work ON paper_versions(work_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_paper_analysis_evidence_paper ON paper_analysis_evidence(paper_id)"))


def _migration_004_research_artifacts(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS research_study_artifacts (
        study_id INTEGER PRIMARY KEY REFERENCES research_studies(id) ON DELETE CASCADE,
        taxonomy_json TEXT NOT NULL DEFAULT '[]', comparison_json TEXT NOT NULL DEFAULT '[]',
        research_routes_json TEXT NOT NULL DEFAULT '[]', representative_works_json TEXT NOT NULL DEFAULT '[]',
        controversies_json TEXT NOT NULL DEFAULT '[]', gaps_json TEXT NOT NULL DEFAULT '[]',
        cited_review_markdown TEXT NOT NULL DEFAULT '', generated_at DATETIME NOT NULL)"""))


def _migration_005_grounded_knowledge_graph(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS knowledge_nodes (
        id INTEGER PRIMARY KEY, node_type VARCHAR(40) NOT NULL, label TEXT NOT NULL,
        external_key VARCHAR(300) NOT NULL UNIQUE, metadata_json TEXT NOT NULL DEFAULT '{}', created_at DATETIME NOT NULL)"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS knowledge_edges (
        id INTEGER PRIMARY KEY, source_node_id INTEGER NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
        target_node_id INTEGER NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE, relation_type VARCHAR(40) NOT NULL,
        source_type VARCHAR(40) NOT NULL, source_id VARCHAR(300) NOT NULL, evidence TEXT NOT NULL,
        confidence FLOAT NOT NULL, confirmed BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME NOT NULL)"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS paper_resources (
        id INTEGER PRIMARY KEY, paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        resource_type VARCHAR(32) NOT NULL, url TEXT NOT NULL, label VARCHAR(300) NOT NULL DEFAULT '',
        source VARCHAR(40) NOT NULL DEFAULT 'user', verified BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME NOT NULL,
        UNIQUE(paper_id, resource_type, url))"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS reproduction_checks (
        id INTEGER PRIMARY KEY, paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        deepwiki_job_id INTEGER REFERENCES deepwiki_jobs(id) ON DELETE SET NULL, check_key VARCHAR(80) NOT NULL,
        title VARCHAR(300) NOT NULL, status VARCHAR(32) NOT NULL, evidence TEXT NOT NULL DEFAULT '',
        details TEXT NOT NULL DEFAULT '', created_at DATETIME NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_edges_source ON knowledge_edges(source_node_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_edges_target ON knowledge_edges(target_node_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_paper_resources_paper ON paper_resources(paper_id)"))


def _migration_006_unified_notes(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY, title VARCHAR(500) NOT NULL DEFAULT '未命名笔记', content TEXT NOT NULL DEFAULT '',
        document_format VARCHAR(16) NOT NULL DEFAULT 'markdown', editor_mode VARCHAR(16) NOT NULL DEFAULT 'standard',
        origin VARCHAR(16) NOT NULL DEFAULT 'standalone', project_id INTEGER REFERENCES research_projects(id) ON DELETE SET NULL,
        legacy_paper_id INTEGER UNIQUE REFERENCES papers(id) ON DELETE SET NULL,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    )"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS note_paper_links (
        id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
        paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE, citation_key VARCHAR(120) NOT NULL DEFAULT '',
        locator VARCHAR(120) NOT NULL DEFAULT '', created_at DATETIME NOT NULL, UNIQUE(note_id, paper_id)
    )"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS note_artifacts (
        id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
        artifact_type VARCHAR(32) NOT NULL, status VARCHAR(24) NOT NULL DEFAULT 'completed', content TEXT NOT NULL DEFAULT '',
        output_path TEXT, error TEXT, created_at DATETIME NOT NULL
    )"""))
    if inspect(connection).has_table("paper_notes") and inspect(connection).has_table("papers"):
        connection.execute(text("""INSERT OR IGNORE INTO notes
            (title, content, document_format, editor_mode, origin, legacy_paper_id, created_at, updated_at)
            SELECT COALESCE(NULLIF(p.title_zh, ''), p.title_en), pn.content, 'markdown', 'professional', 'reader',
                   pn.paper_id, pn.updated_at, pn.updated_at
            FROM paper_notes pn JOIN papers p ON p.id = pn.paper_id
        """))
        connection.execute(text("""INSERT OR IGNORE INTO note_paper_links (note_id, paper_id, citation_key, locator, created_at)
            SELECT n.id, n.legacy_paper_id, '', '', n.created_at FROM notes n WHERE n.legacy_paper_id IS NOT NULL
        """))
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_notes_updated ON notes(updated_at)",
        "CREATE INDEX IF NOT EXISTS ix_notes_project ON notes(project_id)",
        "CREATE INDEX IF NOT EXISTS ix_note_paper_links_note ON note_paper_links(note_id)",
        "CREATE INDEX IF NOT EXISTS ix_note_paper_links_paper ON note_paper_links(paper_id)",
        "CREATE INDEX IF NOT EXISTS ix_note_artifacts_note ON note_artifacts(note_id)",
    ):
        connection.execute(text(statement))


def _migration_007_experiment_records(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS project_experiments (
        id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
        parent_experiment_id INTEGER REFERENCES project_experiments(id) ON DELETE SET NULL,
        title VARCHAR(500) NOT NULL, objective TEXT NOT NULL DEFAULT '', hypothesis TEXT NOT NULL DEFAULT '',
        experiment_type VARCHAR(32) NOT NULL DEFAULT 'run', status VARCHAR(32) NOT NULL DEFAULT 'planned',
        config_json TEXT NOT NULL DEFAULT '{}', environment_json TEXT NOT NULL DEFAULT '{}',
        dataset_version TEXT NOT NULL DEFAULT '', code_reference TEXT NOT NULL DEFAULT '', command TEXT NOT NULL DEFAULT '',
        observations TEXT NOT NULL DEFAULT '', conclusion TEXT NOT NULL DEFAULT '', started_at DATETIME, ended_at DATETIME,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    )"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS experiment_metrics (
        id INTEGER PRIMARY KEY, experiment_id INTEGER NOT NULL REFERENCES project_experiments(id) ON DELETE CASCADE,
        name VARCHAR(160) NOT NULL, value FLOAT NOT NULL, step INTEGER, split VARCHAR(80) NOT NULL DEFAULT '',
        unit VARCHAR(40) NOT NULL DEFAULT '', is_primary BOOLEAN NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}', recorded_at DATETIME NOT NULL
    )"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS experiment_artifacts (
        id INTEGER PRIMARY KEY, experiment_id INTEGER NOT NULL REFERENCES project_experiments(id) ON DELETE CASCADE,
        artifact_type VARCHAR(40) NOT NULL DEFAULT 'file', name VARCHAR(300) NOT NULL, uri TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}', created_at DATETIME NOT NULL
    )"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS experiment_analyses (
        id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
        question TEXT NOT NULL, answer TEXT NOT NULL, sources_json TEXT NOT NULL DEFAULT '[]',
        used_llm BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME NOT NULL
    )"""))
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_project_experiments_project ON project_experiments(project_id)",
        "CREATE INDEX IF NOT EXISTS ix_project_experiments_parent ON project_experiments(parent_experiment_id)",
        "CREATE INDEX IF NOT EXISTS ix_project_experiments_status ON project_experiments(status)",
        "CREATE INDEX IF NOT EXISTS ix_experiment_metrics_experiment ON experiment_metrics(experiment_id)",
        "CREATE INDEX IF NOT EXISTS ix_experiment_metrics_name ON experiment_metrics(name)",
        "CREATE INDEX IF NOT EXISTS ix_experiment_metrics_recorded_at ON experiment_metrics(recorded_at)",
        "CREATE INDEX IF NOT EXISTS ix_experiment_artifacts_experiment ON experiment_artifacts(experiment_id)",
        "CREATE INDEX IF NOT EXISTS ix_experiment_analyses_project ON experiment_analyses(project_id)",
    ):
        connection.execute(text(statement))


def _migration_008_presentation_drafts(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS presentation_drafts (
        id INTEGER PRIMARY KEY, title VARCHAR(500) NOT NULL, kind VARCHAR(40) NOT NULL DEFAULT 'lab-meeting',
        language VARCHAR(16) NOT NULL DEFAULT 'zh-CN', note_id INTEGER REFERENCES notes(id) ON DELETE SET NULL,
        project_id INTEGER REFERENCES research_projects(id) ON DELETE SET NULL,
        paper_id INTEGER REFERENCES papers(id) ON DELETE SET NULL, instructions TEXT NOT NULL DEFAULT '',
        outline_json TEXT NOT NULL DEFAULT '{}', source_catalog_json TEXT NOT NULL DEFAULT '[]',
        deck_spec_json TEXT, status VARCHAR(24) NOT NULL DEFAULT 'outline', output_path TEXT, error TEXT,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    )"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_presentation_drafts_note ON presentation_drafts(note_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_presentation_drafts_project ON presentation_drafts(project_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_presentation_drafts_status ON presentation_drafts(status)"))


def _migration_009_planner_deadlines(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS planner_tasks (
        id INTEGER PRIMARY KEY, title VARCHAR(500) NOT NULL, details TEXT NOT NULL DEFAULT '',
        due_at DATETIME, priority VARCHAR(16) NOT NULL DEFAULT 'medium', status VARCHAR(16) NOT NULL DEFAULT 'pending',
        project_id INTEGER REFERENCES research_projects(id) ON DELETE SET NULL, completed_at DATETIME,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    )"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS submission_deadlines (
        id INTEGER PRIMARY KEY, venue_name VARCHAR(300) NOT NULL, venue_type VARCHAR(24) NOT NULL DEFAULT 'conference',
        round_name VARCHAR(160) NOT NULL DEFAULT '', deadline_at DATETIME NOT NULL,
        timezone_name VARCHAR(80) NOT NULL DEFAULT 'AoE (UTC-12)', domain VARCHAR(120) NOT NULL DEFAULT '',
        website_url TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', remind_days_before INTEGER NOT NULL DEFAULT 14,
        enabled BOOLEAN NOT NULL DEFAULT 1, source VARCHAR(32) NOT NULL DEFAULT 'user',
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    )"""))
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_planner_tasks_due_at ON planner_tasks(due_at)",
        "CREATE INDEX IF NOT EXISTS ix_planner_tasks_status ON planner_tasks(status)",
        "CREATE INDEX IF NOT EXISTS ix_planner_tasks_project ON planner_tasks(project_id)",
        "CREATE INDEX IF NOT EXISTS ix_submission_deadlines_at ON submission_deadlines(deadline_at)",
        "CREATE INDEX IF NOT EXISTS ix_submission_deadlines_type ON submission_deadlines(venue_type)",
        "CREATE INDEX IF NOT EXISTS ix_submission_deadlines_enabled ON submission_deadlines(enabled)",
    ):
        connection.execute(text(statement))


MIGRATIONS = [
    ("001_domain_packs", _migration_001_domain_packs),
    ("002_research_projects", _migration_002_research_projects),
    ("003_paper_evidence_versions", _migration_003_paper_evidence_versions),
    ("004_research_artifacts", _migration_004_research_artifacts),
    ("005_grounded_knowledge_graph", _migration_005_grounded_knowledge_graph),
    ("006_unified_notes", _migration_006_unified_notes),
    ("007_experiment_records", _migration_007_experiment_records),
    ("008_presentation_drafts", _migration_008_presentation_drafts),
    ("009_planner_deadlines", _migration_009_planner_deadlines),
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
