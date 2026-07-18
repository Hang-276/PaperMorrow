from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Paper, PaperAnalysisEvidence, PaperMergeAudit, PaperVersion, PaperWork


def normalize_doi(value: str | None) -> str:
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", (value or "").strip().lower())


def arxiv_work_id(value: str | None) -> str:
    return re.sub(r"v\d+$", "", (value or "").strip().lower())


def match_paper_versions(left: Paper, right: Paper, crossref_related: bool = False) -> tuple[float, str]:
    if left.id == right.id:
        return 1.0, "同一数据库论文"
    if normalize_doi(left.doi) and normalize_doi(left.doi) == normalize_doi(right.doi):
        return 1.0, "DOI 完全一致"
    if arxiv_work_id(left.arxiv_id) and arxiv_work_id(left.arxiv_id) == arxiv_work_id(right.arxiv_id):
        return .99, "arXiv 主标识一致"
    if crossref_related:
        return .96, "Crossref 版本关系"
    title_ratio = SequenceMatcher(None, _norm_title(left.title_en), _norm_title(right.title_en)).ratio()
    left_authors, right_authors = set(json.loads(left.authors_json or "[]")), set(json.loads(right.authors_json or "[]"))
    author_overlap = len(left_authors & right_authors) / max(1, min(len(left_authors), len(right_authors)))
    confidence = .65 * title_ratio + .35 * author_overlap
    return round(confidence, 3), "标题与作者保守匹配"


def ensure_work(db: Session, paper: Paper) -> PaperVersion:
    existing = db.scalar(select(PaperVersion).where(PaperVersion.paper_id == paper.id))
    if existing:
        return existing
    work = PaperWork(canonical_title=paper.title_en)
    version = PaperVersion(work=work, paper=paper, version_label=_version_label(paper), version_date=paper.published_at, confidence=1, confirmed=True, match_reason="初始版本")
    db.add(version); db.flush()
    return version


def link_versions(db: Session, source: Paper, target: Paper, crossref_related: bool = False, user_confirmed: bool = False) -> PaperVersion:
    source_version, target_version = ensure_work(db, source), ensure_work(db, target)
    confidence, reason = match_paper_versions(source, target, crossref_related)
    if confidence < .75:
        raise ValueError("匹配置信度过低，未建立版本关系")
    old_work = target_version.work_id
    db.add(PaperMergeAudit(paper_id=target.id, from_work_id=old_work, to_work_id=source_version.work_id, action="merge", snapshot_json=json.dumps({"confirmed": target_version.confirmed, "confidence": target_version.confidence})))
    target_version.work_id = source_version.work_id
    target_version.confidence = confidence
    target_version.confirmed = bool(user_confirmed or confidence >= .95)
    target_version.match_reason = reason
    db.flush()
    return target_version


def split_version(db: Session, paper: Paper) -> PaperVersion:
    version = ensure_work(db, paper)
    old_work = version.work_id
    work = PaperWork(canonical_title=paper.title_en)
    db.add(work); db.flush()
    db.add(PaperMergeAudit(paper_id=paper.id, from_work_id=old_work, to_work_id=work.id, action="split", snapshot_json="{}"))
    version.work_id = work.id; version.confirmed = True; version.confidence = 1; version.match_reason = "用户拆分"
    db.flush()
    return version


def undo_last_version_action(db: Session, paper: Paper) -> PaperVersion:
    version = ensure_work(db, paper)
    audit = db.scalar(select(PaperMergeAudit).where(PaperMergeAudit.paper_id == paper.id).order_by(PaperMergeAudit.id.desc()))
    if not audit:
        raise ValueError("没有可撤销的版本操作")
    version.work_id = audit.from_work_id or version.work_id
    snapshot = json.loads(audit.snapshot_json or "{}")
    version.confirmed = snapshot.get("confirmed", True); version.confidence = snapshot.get("confidence", 1)
    version.match_reason = "已撤销上一操作"
    db.delete(audit); db.flush()
    return version


def work_timeline(db: Session, paper: Paper) -> dict[str, Any]:
    version = ensure_work(db, paper)
    work = db.get(PaperWork, version.work_id)
    versions = list(db.scalars(select(PaperVersion).where(PaperVersion.work_id == work.id).order_by(PaperVersion.version_date, PaperVersion.id)).all())
    return {"work_id": work.id, "canonical_title": work.canonical_title, "versions": [{
        "paper_id": item.paper_id, "title": item.paper.title_en, "version_label": item.version_label,
        "relation_type": item.relation_type, "confidence": item.confidence, "confirmed": item.confirmed,
        "match_reason": item.match_reason, "important_changes": item.important_changes,
        "version_date": item.version_date,
    } for item in versions]}


def replace_analysis_evidence(db: Session, paper: Paper, items: list[dict[str, Any]], scope: str) -> list[PaperAnalysisEvidence]:
    for existing in list(paper.analysis_evidence):
        db.delete(existing)
    created = []
    for item in items:
        page = item.get("page_number")
        if scope == "abstract":
            page = None
        row = PaperAnalysisEvidence(paper=paper, field_name=item["field_name"], claim=item["claim"], page_number=page,
            section=item.get("section"), evidence_excerpt=item.get("evidence_excerpt", "")[:1000], source_scope=scope,
            conclusion_type=item.get("conclusion_type", "paper_fact"))
        db.add(row); created.append(row)
    return created


def evidence_dict(item: PaperAnalysisEvidence) -> dict[str, Any]:
    return {"id": item.id, "field_name": item.field_name, "claim": item.claim, "page_number": item.page_number,
            "section": item.section, "evidence_excerpt": item.evidence_excerpt, "source_scope": item.source_scope,
            "conclusion_type": item.conclusion_type}


def _norm_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _version_label(paper: Paper) -> str:
    if paper.doi and paper.arxiv_id:
        return "出版版本"
    if paper.doi:
        return "期刊/会议版本"
    if paper.arxiv_id:
        match = re.search(r"v\d+$", paper.arxiv_id)
        return f"arXiv {match.group(0) if match else '预印本'}"
    return "收录版本"
