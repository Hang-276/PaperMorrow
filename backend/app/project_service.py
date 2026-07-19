from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, selectinload

from .models import (
    DeepWikiJob, Paper, ProjectChatMessage, ProjectExperiment, ResearchProject, ResearchProjectNote,
    ResearchProjectPaper, ResearchProjectStudy, ResearchStudy,
)


PAPER_ROLES = {"core", "support", "conflict", "background", "to_verify"}
READING_STATUSES = {"to_screen", "to_read", "reading", "read_to_organize", "completed", "shelved"}
SOURCE_LABELS = {"paper": "论文", "note": "笔记", "study": "专题调研", "wiki": "Wiki", "analysis": "证据化分析", "experiment": "实验记录"}


def project_dict(project: ResearchProject, detail: bool = True) -> dict[str, Any]:
    result = {
        "id": project.id, "title": project.title, "research_question": project.research_question,
        "research_direction": project.research_direction, "domain_pack_id": project.domain_pack_id,
        "research_profile_id": project.research_profile_id, "repository_url": project.repository_url,
        "deepwiki_job_id": project.deepwiki_job_id, "current_conclusion": project.current_conclusion,
        "unresolved_questions": json.loads(project.unresolved_questions_json or "[]"),
        "next_reading_suggestion": project.next_reading_suggestion,
        "created_at": project.created_at, "updated_at": project.updated_at,
    }
    if detail:
        result["papers"] = [{
            "link_id": link.id, "paper_id": link.paper_id, "title": link.paper.title_en,
            "title_zh": link.paper.title_zh, "role": link.role, "reading_status": link.reading_status,
            "queue_order": link.queue_order, "venue": link.paper.venue_name,
        } for link in project.papers]
        result["notes"] = [{"id": note.id, "title": note.title, "content": note.content, "updated_at": note.updated_at} for note in project.notes]
        result["study_ids"] = [link.study_id for link in project.studies]
    return result


def load_project(db: Session, project_id: int) -> ResearchProject | None:
    return db.scalar(select(ResearchProject).where(ResearchProject.id == project_id).options(
        selectinload(ResearchProject.papers).selectinload(ResearchProjectPaper.paper),
        selectinload(ResearchProject.notes), selectinload(ResearchProject.studies), selectinload(ResearchProject.experiments).selectinload(ProjectExperiment.metrics),
    ))


def reindex_project(db: Session, project_id: int) -> int:
    project = load_project(db, project_id)
    if not project:
        return 0
    db.execute(text("DELETE FROM project_search_fts WHERE project_id=:project_id"), {"project_id": project_id})
    rows: list[dict[str, Any]] = []
    for link in project.papers:
        paper = link.paper
        paper_text = "\n".join(filter(None, [paper.abstract_en, paper.abstract_zh or ""]))
        if paper.document and paper.document.full_text:
            paper_text += "\n" + paper.document.full_text
        rows.append({"project_id": project_id, "source_type": "paper", "source_id": str(paper.id), "title": paper.title_en, "content": paper_text})
        if paper.summary_json:
            rows.append({"project_id": project_id, "source_type": "analysis", "source_id": str(paper.id), "title": f"{paper.title_en} · AI 分析", "content": paper.summary_json})
        if paper.note and paper.note.content:
            rows.append({"project_id": project_id, "source_type": "note", "source_id": f"paper:{paper.id}", "title": f"{paper.title_en} · 论文笔记", "content": paper.note.content})
    for note in project.notes:
        rows.append({"project_id": project_id, "source_type": "note", "source_id": str(note.id), "title": note.title, "content": note.content})
    for link in project.studies:
        study = db.get(ResearchStudy, link.study_id)
        if study and study.review_markdown:
            rows.append({"project_id": project_id, "source_type": "study", "source_id": str(study.id), "title": study.title, "content": study.review_markdown})
    for experiment in project.experiments:
        metric_text = "\n".join(
            f"{metric.name}={metric.value}{metric.unit} step={metric.step if metric.step is not None else '-'} split={metric.split or '-'}"
            for metric in experiment.metrics
        )
        content = "\n".join(filter(None, [
            f"状态：{experiment.status}；类型：{experiment.experiment_type}",
            f"目标：{experiment.objective}" if experiment.objective else "",
            f"假设：{experiment.hypothesis}" if experiment.hypothesis else "",
            f"数据版本：{experiment.dataset_version}" if experiment.dataset_version else "",
            f"代码版本：{experiment.code_reference}" if experiment.code_reference else "",
            f"观察：{experiment.observations}" if experiment.observations else "",
            f"结论：{experiment.conclusion}" if experiment.conclusion else "",
            metric_text,
        ]))
        rows.append({"project_id": project_id, "source_type": "experiment", "source_id": str(experiment.id), "title": experiment.title, "content": content})
    if project.deepwiki_job_id:
        job = db.get(DeepWikiJob, project.deepwiki_job_id)
        if job and job.output_dir:
            root = Path(job.output_dir)
            for path in list(root.glob("*.md"))[:40] if root.is_dir() else []:
                try:
                    rows.append({"project_id": project_id, "source_type": "wiki", "source_id": path.name, "title": path.stem, "content": path.read_text("utf-8")[:200_000]})
                except OSError:
                    continue
    if rows:
        db.execute(text("INSERT INTO project_search_fts(project_id,source_type,source_id,title,content) VALUES(:project_id,:source_type,:source_id,:title,:content)"), rows)
    return len(rows)


def search_project(db: Session, project_id: int, query: str, limit: int = 8) -> list[dict[str, Any]]:
    reindex_project(db, project_id)
    tokens = re.findall(r"[\w\-]+", query, flags=re.UNICODE)[:12]
    if not tokens:
        return []
    match = " OR ".join(f'"{token}"' for token in tokens)
    result = db.execute(text("""
        SELECT source_type, source_id, title, snippet(project_search_fts, 4, '‹', '›', '…', 28) AS excerpt,
               bm25(project_search_fts, 2.0, 1.0) AS rank
        FROM project_search_fts WHERE project_search_fts MATCH :match AND project_id=:project_id
        ORDER BY rank LIMIT :limit
    """), {"match": match, "project_id": project_id, "limit": limit})
    return [{"source_type": row.source_type, "source_label": SOURCE_LABELS.get(row.source_type, row.source_type),
             "source_id": row.source_id, "title": row.title, "excerpt": row.excerpt, "rank": row.rank} for row in result]


def add_project_paper(db: Session, project: ResearchProject, paper: Paper, role: str, reading_status: str) -> ResearchProjectPaper:
    if role not in PAPER_ROLES or reading_status not in READING_STATUSES:
        raise ValueError("无效的论文角色或阅读状态")
    existing = db.scalar(select(ResearchProjectPaper).where(ResearchProjectPaper.project_id == project.id, ResearchProjectPaper.paper_id == paper.id))
    if existing:
        existing.role, existing.reading_status = role, reading_status
        return existing
    order = max((item.queue_order for item in project.papers), default=-1) + 1
    link = ResearchProjectPaper(project=project, paper=paper, role=role, reading_status=reading_status, queue_order=order)
    db.add(link)
    return link


def save_chat(db: Session, project_id: int, question: str, answer: str, sources: list[dict[str, Any]]) -> None:
    now = datetime.now(timezone.utc)
    db.add_all([
        ProjectChatMessage(project_id=project_id, role="user", content=question, sources_json="[]", created_at=now),
        ProjectChatMessage(project_id=project_id, role="assistant", content=answer, sources_json=json.dumps(sources, ensure_ascii=False), created_at=now),
    ])
