from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from .deepwiki_service import run_deepwiki_job, validate_repository_url, wiki_is_complete
from .domain_pack_service import adapter_catalog, apply_domain_pack, create_domain_pack, domain_pack_dict, search_preview
from .domain_sources import test_source_config
from .library_service import LibraryService, normalize_library_tag
from .library_folder_service import LibraryFolderService
from .llm import LLMClient, LLMNotConfigured
from .models import ChatMessage, ChatSession, DeepWikiJob, DomainPack, ExperimentAnalysis, LibraryEntry, LibraryTag, LLMProfile, Paper, PaperNote, PaperStudyState, Recommendation, RecommendationBatch, ResearchProfile, ResearchProject, ResearchProjectNote, ResearchProjectPaper, ResearchProjectStudy, ResearchStudy, Tag, ZoteroLink
from .paper_sources import SemanticScholarSource
from .paper_document_service import get_or_extract_paper_text
from .recommendation import RecommendationService
from .repository_service import RepositoryService
from .scheduler import sync_scheduler
from .reader_service import cached_pdf_path, reader_figure_path, save_reader_figure
from .schemas import ChatSessionCreate, DomainPackCreate, DomainPackUpdate, DomainSearchPreviewRequest, DomainSourceTestRequest, ExperimentAnalysisRequest, ExperimentArtifactsAppend, ExperimentCreate, ExperimentMetricsAppend, ExperimentUpdate, GenerateRequest, KnowledgeEdgeCreate, KnowledgeNodeCreate, LibraryFolderCreate, LibraryImportRequest, LibraryPaperFoldersRequest, LibraryPaperTagsRequest, LibraryScanRequest, LibraryTagCreate, LibraryTagUpdate, LLMProfileCreate, LLMProfileUpdate, NoteRequest, PaperChatRequest, PaperEvidenceUpdate, PaperResourceCreate, PaperVersionLinkRequest, ReaderFigureRequest, ReaderTranslateRequest, RepositoryBindRequest, ResearchProfileCreate, ResearchProfileUpdate, ResearchProjectChatRequest, ResearchProjectCreate, ResearchProjectNoteCreate, ResearchProjectPaperRequest, ResearchProjectPaperUpdate, ResearchProjectSearchRequest, ResearchProjectUpdate, ResearchStudyCreate, SettingsUpdate, StudyStateRequest, WorkspaceChatRequest
from .serializers import batch_dict, job_dict, library_tag_dict, paper_dict, research_profile_dict, tag_dict
from .settings_service import delete_llm_profile_key, get_active_llm_profile, get_settings, list_llm_profiles, llm_profile_dict, save_llm_profile_key, save_secrets, update_settings
from .usage_service import token_usage_stats
from .database import get_db
from .zotero_service import ZoteroError, ZoteroService
from .research_service import ResearchService, research_study_dict
from .project_service import PAPER_ROLES, READING_STATUSES, add_project_paper, load_project, project_dict, reindex_project, save_chat, search_project
from .evidence_service import evidence_dict, link_versions, replace_analysis_evidence, split_version, undo_last_version_action, work_timeline
from .knowledge_graph_service import add_resource, check_dict, create_grounded_edge, generate_reproduction_checklist, resource_dict, unified_graph, upsert_node
from .experiment_service import analyze_experiments, append_artifacts, append_metrics, artifact_dict, create_experiment, experiment_dict, experiment_summary, list_experiments, load_experiment, metric_dict, update_experiment
from .note_service import sync_reader_note


router = APIRouter(prefix="/api")


@router.get("/system/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "PaperMorrow"}


@router.post("/assistant/chat")
async def workspace_chat(payload: WorkspaceChatRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Discuss only the user-visible context supplied by the current product page."""
    messages = [item.model_dump() for item in payload.history]
    messages.append({"role": "user", "content": payload.message})
    try:
        answer = await LLMClient(db).chat_about_workspace(payload.page_title, payload.context, messages, payload.response_detail)
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="模型接口暂时不可用，请稍后重试") from exc
    return {
        "answer": answer,
        "context": {"page_id": payload.page_id, "page_title": payload.page_title, "characters": len(payload.context)},
    }


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [tag_dict(tag) for tag in db.scalars(select(Tag).where(Tag.enabled.is_(True)).order_by(Tag.id))]


@router.get("/library/papers")
def list_library_papers(
    search: str = "",
    tag_ids: list[int] = Query(default=[]),
    learned: bool | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = select(Paper).join(LibraryEntry).order_by(desc(LibraryEntry.added_at)).limit(limit)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Paper.title_en.ilike(pattern), Paper.title_zh.ilike(pattern), Paper.abstract_en.ilike(pattern)))
    papers = list(db.scalars(query).unique())
    if tag_ids:
        required = set(tag_ids)
        papers = [paper for paper in papers if required.issubset({tag.id for tag in paper.library_entry.tags})]
    if learned is not None:
        papers = [paper for paper in papers if bool(paper.study_state and paper.study_state.learned) == learned]
    return [paper_dict(paper) for paper in papers]


@router.get("/library/search")
async def search_library_papers(q: str = Query(min_length=2, max_length=500), limit: int = Query(default=20, ge=1, le=50), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"query": q, "items": await LibraryService(db).search(q, limit)}


@router.post("/library/papers/{paper_id}")
def add_existing_paper_to_library(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    LibraryService(db).add_paper(paper, "manual")
    db.commit(); db.refresh(paper)
    return paper_dict(paper)


@router.post("/library/import")
def import_paper_to_library(payload: LibraryImportRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = LibraryService(db).import_candidate(payload.model_dump())
    return paper_dict(paper)


@router.delete("/library/papers/{paper_id}")
def remove_paper_from_library(paper_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    entry = db.get(LibraryEntry, paper_id)
    if not entry:
        raise HTTPException(status_code=404, detail="论文不在学习库中")
    db.delete(entry); db.commit()
    return {"removed": True}


@router.get("/library/tags")
def list_library_tags(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [library_tag_dict(tag) for tag in db.scalars(select(LibraryTag).order_by(LibraryTag.name)).all()]


@router.post("/library/tags")
def create_library_tag(payload: LibraryTagCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    normalized = normalize_library_tag(payload.name)
    if db.scalar(select(LibraryTag).where(LibraryTag.normalized_name == normalized)):
        raise HTTPException(status_code=409, detail="同名标签已经存在")
    tag = LibraryTag(name=payload.name.strip(), normalized_name=normalized, color=payload.color.lower())
    db.add(tag); db.commit(); db.refresh(tag)
    return library_tag_dict(tag)


@router.put("/library/tags/{tag_id}")
def update_library_tag(tag_id: int, payload: LibraryTagUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    tag = db.get(LibraryTag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    if payload.name is not None:
        normalized = normalize_library_tag(payload.name)
        duplicate = db.scalar(select(LibraryTag).where(LibraryTag.normalized_name == normalized, LibraryTag.id != tag_id))
        if duplicate:
            raise HTTPException(status_code=409, detail="同名标签已经存在")
        tag.name, tag.normalized_name = payload.name.strip(), normalized
    if payload.color is not None:
        tag.color = payload.color.lower()
    db.commit(); db.refresh(tag)
    return library_tag_dict(tag)


@router.delete("/library/tags/{tag_id}")
def delete_library_tag(tag_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    tag = db.get(LibraryTag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.delete(tag); db.commit()
    return {"deleted": True}


@router.put("/library/papers/{paper_id}/tags")
def set_library_paper_tags(paper_id: int, payload: LibraryPaperTagsRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    entry = paper.library_entry or LibraryService(db).add_paper(paper, "tagged")
    tags = list(db.scalars(select(LibraryTag).where(LibraryTag.id.in_(payload.tag_ids))).all()) if payload.tag_ids else []
    if len(tags) != len(set(payload.tag_ids)):
        raise HTTPException(status_code=400, detail="包含不存在的学习标签")
    entry.tags = tags
    db.commit(); db.refresh(paper)
    return paper_dict(paper)


@router.get("/library/folders")
def list_library_folders(db: Session = Depends(get_db)) -> dict[str, Any]:
    service = LibraryFolderService(db)
    return {"root_path": str(service.root_path()), "folders": service.folder_dicts()}


@router.post("/library/folders")
def create_library_folder(payload: LibraryFolderCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    service = LibraryFolderService(db)
    try:
        folder = service.create_folder(payload.name, payload.parent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return next(item for item in service.folder_dicts() if item["id"] == folder.id)


@router.post("/library/folders/scan")
def scan_library_folders(payload: LibraryScanRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return LibraryFolderService(db).scan(payload.root_path)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/library/papers/{paper_id}/folders")
def set_library_paper_folders(paper_id: int, payload: LibraryPaperFoldersRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    try:
        LibraryFolderService(db).set_paper_folders(paper, payload.folder_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(paper)
    return paper_dict(paper)


@router.get("/library/knowledge-graph")
def library_knowledge_graph(db: Session = Depends(get_db)) -> dict[str, Any]:
    return unified_graph(db, LibraryFolderService(db).knowledge_graph())


@router.post("/knowledge-graph/nodes")
def create_knowledge_node(payload: KnowledgeNodeCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        node = upsert_node(db, payload.node_type, payload.label, payload.external_key, payload.metadata); db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": node.id, "node_type": node.node_type, "label": node.label, "external_key": node.external_key}


@router.post("/knowledge-graph/edges")
def create_knowledge_edge(payload: KnowledgeEdgeCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        edge = create_grounded_edge(db, **payload.model_dump()); db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": edge.id, "relation_type": edge.relation_type, "evidence": edge.evidence, "confidence": edge.confidence, "confirmed": edge.confirmed}


@router.get("/papers/{paper_id}/resources")
def list_paper_resources(paper_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    from .models import PaperResource
    _paper_or_404(db, paper_id)
    return [resource_dict(item) for item in db.scalars(select(PaperResource).where(PaperResource.paper_id == paper_id).order_by(PaperResource.id)).all()]


@router.post("/papers/{paper_id}/resources")
def create_paper_resource(paper_id: int, payload: PaperResourceCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        row = add_resource(db, _paper_or_404(db, paper_id), payload.resource_type, str(payload.url), payload.label, payload.source, payload.verified); db.commit(); db.refresh(row)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return resource_dict(row)


@router.post("/papers/{paper_id}/reproduction-checklist")
def build_reproduction_checklist(paper_id: int, deepwiki_job_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    job = db.get(DeepWikiJob, deepwiki_job_id) if deepwiki_job_id else db.scalar(select(DeepWikiJob).where(DeepWikiJob.paper_id == paper_id).order_by(DeepWikiJob.id.desc()))
    if deepwiki_job_id and (not job or job.paper_id != paper_id):
        raise HTTPException(status_code=404, detail="DeepWiki 任务与论文不匹配")
    items = generate_reproduction_checklist(db, paper, job); db.commit()
    return {"paper_id": paper.id, "deepwiki_job_id": job.id if job else None, "items": [check_dict(item) for item in items],
            "allowed_statuses": ["confirmed", "possibly_consistent", "missing", "unable_to_confirm"]}


@router.get("/library/files/{file_id}/pdf")
def local_library_pdf(file_id: int, db: Session = Depends(get_db)) -> FileResponse:
    try:
        row, path = LibraryFolderService(db).resolve_file(file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/pdf", filename=row.file_name)


@router.get("/research/studies")
def list_research_studies(limit: int = Query(default=30, ge=1, le=100), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    studies = db.scalars(select(ResearchStudy).order_by(desc(ResearchStudy.created_at)).limit(limit)).unique().all()
    return [research_study_dict(study, include_papers=False) for study in studies]


@router.post("/research/studies")
async def create_research_study(payload: ResearchStudyCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    study = await ResearchService(db).run(payload.domain, payload.prompt, payload.count)
    if study.status == "failed":
        raise HTTPException(status_code=503, detail=study.error or "调研失败")
    return research_study_dict(study)


@router.get("/research/studies/{study_id}")
def get_research_study(study_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    study = db.get(ResearchStudy, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="调研记录不存在")
    return research_study_dict(study)


@router.post("/research/studies/{study_id}/review")
async def generate_research_review(study_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    study = db.get(ResearchStudy, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="调研记录不存在")
    try:
        study = await ResearchService(db).generate_review(study)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return research_study_dict(study)


@router.post("/research/studies/{study_id}/artifacts")
def generate_research_artifacts(study_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    study = db.get(ResearchStudy, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="调研记录不存在")
    try:
        ResearchService(db).build_artifacts(study); db.commit(); db.refresh(study)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return research_study_dict(study)


@router.post("/zotero/test")
async def test_zotero_connection(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return await ZoteroService(db).test_connection()
    except (ZoteroError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/papers/{paper_id}/zotero/sync")
async def sync_paper_to_zotero(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    try:
        await ZoteroService(db).sync_paper(paper)
    except (ZoteroError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.refresh(paper)
    return paper_dict(paper)


@router.delete("/papers/{paper_id}/zotero/link")
def unlink_paper_from_zotero(paper_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    _paper_or_404(db, paper_id)
    link = db.get(ZoteroLink, paper_id)
    if link:
        db.delete(link); db.commit()
    return {"unlinked": True}


@router.post("/recommendations/generate")
async def generate_recommendations(payload: GenerateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        batch = await RecommendationService(db).generate(payload.tag_ids, payload.count, payload.triggered_by, payload.profile_id, payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return batch_dict(batch)


@router.get("/research-profiles")
def list_research_profiles(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [research_profile_dict(item) for item in db.scalars(select(ResearchProfile).order_by(ResearchProfile.created_at)).all()]


@router.get("/domain-packs/adapters")
def list_domain_source_adapters() -> list[dict[str, str]]:
    return adapter_catalog()


@router.post("/domain-packs/test-source")
async def test_domain_source(payload: DomainSourceTestRequest) -> dict[str, Any]:
    try:
        return await test_source_config(payload.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/domain-packs")
def list_domain_packs(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [domain_pack_dict(item) for item in db.scalars(select(DomainPack).order_by(DomainPack.is_builtin.desc(), DomainPack.id)).all()]


@router.post("/domain-packs")
def create_domain_pack_api(payload: DomainPackCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return domain_pack_dict(create_domain_pack(db, payload.model_dump(mode="json")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/domain-packs/import")
def import_domain_pack(payload: DomainPackCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    return create_domain_pack_api(payload, db)


@router.get("/domain-packs/{pack_id}")
def read_domain_pack(pack_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    pack = db.get(DomainPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="专业包不存在")
    return domain_pack_dict(pack)


@router.get("/domain-packs/{pack_id}/export")
def export_domain_pack(pack_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    data = read_domain_pack(pack_id, db)
    for key in ("id", "is_builtin", "created_at", "updated_at", "version"):
        data.pop(key, None)
    return data


@router.put("/domain-packs/{pack_id}")
def update_domain_pack(pack_id: int, payload: DomainPackUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    pack = db.get(DomainPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="专业包不存在")
    try:
        apply_domain_pack(pack, payload.model_dump(exclude_none=True, mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit(); db.refresh(pack)
    return domain_pack_dict(pack)


@router.delete("/domain-packs/{pack_id}")
def delete_domain_pack(pack_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    pack = db.get(DomainPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="专业包不存在")
    if pack.is_builtin:
        pack.enabled = False
    else:
        db.delete(pack)
    db.commit()
    return {"deleted": not pack.is_builtin, "disabled": pack.is_builtin}


@router.post("/domain-packs/{pack_id}/search-preview")
def preview_domain_search(pack_id: int, payload: DomainSearchPreviewRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    pack = db.get(DomainPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="专业包不存在")
    return search_preview(pack, payload.query)


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [project_dict(item, detail=False) for item in db.scalars(select(ResearchProject).order_by(desc(ResearchProject.updated_at))).all()]


@router.post("/projects")
def create_project(payload: ResearchProjectCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    values = payload.model_dump()
    project = ResearchProject(**{key: value for key, value in values.items() if key != "unresolved_questions"}, unresolved_questions_json=json.dumps(values["unresolved_questions"], ensure_ascii=False))
    db.add(project); db.commit()
    return project_dict(load_project(db, project.id))


@router.get("/projects/{project_id}")
def read_project(project_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = load_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return project_dict(project)


@router.put("/projects/{project_id}")
def update_project(project_id: int, payload: ResearchProjectUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = db.get(ResearchProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    values = payload.model_dump(exclude_unset=True)
    if "unresolved_questions" in values:
        project.unresolved_questions_json = json.dumps(values.pop("unresolved_questions") or [], ensure_ascii=False)
    for key, value in values.items():
        setattr(project, key, value)
    db.commit()
    return project_dict(load_project(db, project.id))


@router.post("/projects/{project_id}/papers")
def add_paper_to_project(project_id: int, payload: ResearchProjectPaperRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    project, paper = db.get(ResearchProject, project_id), db.get(Paper, payload.paper_id)
    if not project or not paper:
        raise HTTPException(status_code=404, detail="研究项目或论文不存在")
    try:
        add_project_paper(db, project, paper, payload.role, payload.reading_status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit(); reindex_project(db, project_id); db.commit()
    return project_dict(load_project(db, project_id))


@router.put("/projects/{project_id}/papers/{paper_id}")
def update_project_paper(project_id: int, paper_id: int, payload: ResearchProjectPaperUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    link = db.scalar(select(ResearchProjectPaper).where(ResearchProjectPaper.project_id == project_id, ResearchProjectPaper.paper_id == paper_id))
    if not link:
        raise HTTPException(status_code=404, detail="项目论文不存在")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(link, key, value)
    db.commit()
    return read_project(project_id, db)


@router.delete("/projects/{project_id}/papers/{paper_id}")
def unlink_project_paper(project_id: int, paper_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    link = db.scalar(select(ResearchProjectPaper).where(ResearchProjectPaper.project_id == project_id, ResearchProjectPaper.paper_id == paper_id))
    if link:
        db.delete(link); db.commit(); reindex_project(db, project_id); db.commit()
    return {"unlinked": bool(link)}


@router.post("/projects/{project_id}/notes")
def create_project_note(project_id: int, payload: ResearchProjectNoteCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(ResearchProject, project_id):
        raise HTTPException(status_code=404, detail="研究项目不存在")
    note = ResearchProjectNote(project_id=project_id, **payload.model_dump())
    db.add(note); db.commit(); reindex_project(db, project_id); db.commit()
    return {"id": note.id, "title": note.title, "content": note.content, "updated_at": note.updated_at}


@router.post("/projects/{project_id}/studies/{study_id}")
def link_project_study(project_id: int, study_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(ResearchProject, project_id) or not db.get(ResearchStudy, study_id):
        raise HTTPException(status_code=404, detail="研究项目或专题调研不存在")
    existing = db.scalar(select(ResearchProjectStudy).where(ResearchProjectStudy.project_id == project_id, ResearchProjectStudy.study_id == study_id))
    if not existing:
        db.add(ResearchProjectStudy(project_id=project_id, study_id=study_id)); db.commit()
    return read_project(project_id, db)


@router.post("/projects/{project_id}/search")
def search_within_project(project_id: int, payload: ResearchProjectSearchRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(ResearchProject, project_id):
        raise HTTPException(status_code=404, detail="研究项目不存在")
    items = search_project(db, project_id, payload.query, payload.limit); db.commit()
    return {"query": payload.query, "items": items}


@router.post("/projects/{project_id}/chat")
async def chat_with_project(project_id: int, payload: ResearchProjectChatRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(ResearchProject, project_id):
        raise HTTPException(status_code=404, detail="研究项目不存在")
    sources = search_project(db, project_id, payload.message, 8)
    if not sources:
        answer = "当前项目中没有检索到足够证据。请先加入相关论文、笔记、专题调研或 DeepWiki。"
        inferred = False
    else:
        context = "\n\n".join(f"[S{i + 1}] 类型={item['source_label']} 标题={item['title']}\n{item['excerpt']}" for i, item in enumerate(sources))
        try:
            answer = await LLMClient(db).chat_about_project(context, payload.message)
            inferred = True
        except (LLMNotConfigured, httpx.HTTPError):
            answer = "未配置 LLM，已可靠降级为项目内检索结果。下面片段均来自当前项目，不包含外部内容。\n\n" + "\n\n".join(f"[S{i + 1} · {item['source_label']}] {item['title']}：{item['excerpt']}" for i, item in enumerate(sources))
            inferred = False
    save_chat(db, project_id, payload.message, answer, sources); db.commit()
    return {"answer": answer, "sources": sources, "contains_ai_inference": inferred}


@router.get("/projects/{project_id}/experiments")
def list_project_experiments(project_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if not db.get(ResearchProject, project_id):
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return [experiment_dict(item) for item in list_experiments(db, project_id)]


@router.post("/projects/{project_id}/experiments")
def create_project_experiment(project_id: int, payload: ExperimentCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        experiment = create_experiment(db, project_id, payload.model_dump())
        db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return experiment_dict(load_experiment(db, experiment.id))


@router.get("/projects/{project_id}/experiments/summary")
def summarize_project_experiments(project_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(ResearchProject, project_id):
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return experiment_summary(db, project_id)


@router.post("/projects/{project_id}/experiments/analyze")
async def analyze_project_experiment_history(project_id: int, payload: ExperimentAnalysisRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(ResearchProject, project_id):
        raise HTTPException(status_code=404, detail="研究项目不存在")
    result = await analyze_experiments(db, project_id, payload.question)
    db.commit()
    return result


@router.get("/projects/{project_id}/experiments/analyses")
def list_project_experiment_analyses(project_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if not db.get(ResearchProject, project_id):
        raise HTTPException(status_code=404, detail="研究项目不存在")
    rows = db.scalars(
        select(ExperimentAnalysis)
        .where(ExperimentAnalysis.project_id == project_id)
        .order_by(desc(ExperimentAnalysis.created_at), desc(ExperimentAnalysis.id))
        .limit(100)
    ).all()
    return [{
        "id": item.id, "project_id": item.project_id, "question": item.question, "answer": item.answer,
        "sources": json.loads(item.sources_json or "[]"), "used_llm": item.used_llm, "created_at": item.created_at,
    } for item in rows]


@router.get("/projects/{project_id}/experiments/{experiment_id}")
def read_project_experiment(project_id: int, experiment_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    experiment = load_experiment(db, experiment_id)
    if not experiment or experiment.project_id != project_id:
        raise HTTPException(status_code=404, detail="实验记录不存在")
    return experiment_dict(experiment)


@router.put("/projects/{project_id}/experiments/{experiment_id}")
def update_project_experiment(project_id: int, experiment_id: int, payload: ExperimentUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    experiment = load_experiment(db, experiment_id)
    if not experiment or experiment.project_id != project_id:
        raise HTTPException(status_code=404, detail="实验记录不存在")
    try:
        update_experiment(db, experiment, payload.model_dump(exclude_unset=True))
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return experiment_dict(load_experiment(db, experiment_id))


@router.post("/projects/{project_id}/experiments/{experiment_id}/metrics")
def add_project_experiment_metrics(project_id: int, experiment_id: int, payload: ExperimentMetricsAppend, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    experiment = load_experiment(db, experiment_id)
    if not experiment or experiment.project_id != project_id:
        raise HTTPException(status_code=404, detail="实验记录不存在")
    metrics = append_metrics(db, experiment, [item.model_dump() for item in payload.metrics])
    db.commit()
    return [metric_dict(item) for item in metrics]


@router.post("/projects/{project_id}/experiments/{experiment_id}/artifacts")
def add_project_experiment_artifacts(project_id: int, experiment_id: int, payload: ExperimentArtifactsAppend, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    experiment = load_experiment(db, experiment_id)
    if not experiment or experiment.project_id != project_id:
        raise HTTPException(status_code=404, detail="实验记录不存在")
    artifacts = append_artifacts(db, experiment, [item.model_dump() for item in payload.artifacts])
    db.commit()
    return [artifact_dict(item) for item in artifacts]


@router.post("/research-profiles")
def create_research_profile(payload: ResearchProfileCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    values = payload.model_dump()
    profile = ResearchProfile(
        name=values["name"], domain=values["domain"], domain_pack_id=values.get("domain_pack_id"), description=values["description"],
        positive_keywords_json=json.dumps(values["positive_keywords"], ensure_ascii=False),
        negative_keywords_json=json.dumps(values["negative_keywords"], ensure_ascii=False),
        seed_papers_json=json.dumps(values["seed_papers"], ensure_ascii=False),
        relevance_weight=values["relevance_weight"], recency_weight=values["recency_weight"], exploration_ratio=values["exploration_ratio"],
    )
    db.add(profile); db.commit(); db.refresh(profile)
    return research_profile_dict(profile)


@router.put("/research-profiles/{profile_id}")
def update_research_profile(profile_id: int, payload: ResearchProfileUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    profile = db.get(ResearchProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="研究方向不存在")
    values = payload.model_dump(exclude_none=True)
    relevance = float(values.get("relevance_weight", profile.relevance_weight))
    recency = float(values.get("recency_weight", profile.recency_weight))
    if relevance + recency > 0.95:
        raise HTTPException(status_code=400, detail="关联度与发布时间权重之和不能超过 95%")
    for key in ("positive_keywords", "negative_keywords", "seed_papers"):
        if key in values:
            setattr(profile, f"{key}_json", json.dumps(values.pop(key), ensure_ascii=False))
    for key, value in values.items():
        setattr(profile, key, value)
    db.commit(); db.refresh(profile)
    return research_profile_dict(profile)


@router.delete("/research-profiles/{profile_id}")
def delete_research_profile(profile_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    profile = db.get(ResearchProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="研究方向不存在")
    db.delete(profile); db.commit()
    return {"deleted": True}


@router.get("/recommendations/today")
def recommendations_today(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    batches = db.scalars(select(RecommendationBatch).order_by(desc(RecommendationBatch.created_at))).all()
    result = []
    for batch in batches:
        created = batch.created_at.replace(tzinfo=timezone.utc) if batch.created_at.tzinfo is None else batch.created_at
        if created.date() == now.date():
            result.append(batch_dict(batch))
    return result


@router.get("/recommendations/history")
def recommendation_history(
    search: str = "",
    learned: bool | None = None,
    tag_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = select(Recommendation).join(Recommendation.paper).order_by(desc(Recommendation.recommended_at)).limit(limit)
    if search:
        query = query.where(or_(Paper.title_en.ilike(f"%{search}%"), Paper.title_zh.ilike(f"%{search}%")))
    recommendations = list(db.scalars(query).unique())
    result = []
    for item in recommendations:
        if learned is not None and bool(item.paper.study_state and item.paper.study_state.learned) != learned:
            continue
        if tag_id is not None and tag_id not in {tag.id for tag in item.paper.tags}:
            continue
        result.append(paper_dict(item.paper, item.score, item.recommended_at, item))
    return result


@router.get("/papers/{paper_id}")
def get_paper(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return paper_dict(_paper_or_404(db, paper_id))


@router.patch("/papers/{paper_id}/study-state")
def update_study_state(paper_id: int, payload: StudyStateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    state_row = paper.study_state or PaperStudyState(paper_id=paper.id)
    state_row.learned = payload.learned
    state_row.completed_at = datetime.now(timezone.utc) if payload.learned else None
    db.add(state_row)
    if payload.learned and not paper.library_entry:
        LibraryService(db).add_paper(paper, "completed")
    db.commit()
    db.refresh(paper)
    return paper_dict(paper)


@router.put("/papers/{paper_id}/note")
def save_note(paper_id: int, payload: NoteRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    unified_note = sync_reader_note(db, paper, payload.content)
    if payload.content.strip() and not paper.library_entry:
        LibraryService(db).add_paper(paper, "note")
    db.commit()
    return {"paper_id": paper.id, "note_id": unified_note.id, "content": payload.content, "updated_at": unified_note.updated_at.isoformat()}


@router.get("/papers/{paper_id}/reader/pdf")
async def reader_pdf(paper_id: int, db: Session = Depends(get_db)) -> FileResponse:
    paper = _paper_or_404(db, paper_id)
    try:
        path = await cached_pdf_path(paper)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/pdf", filename=f"paper-{paper.id}.pdf", content_disposition_type="inline")


@router.post("/papers/{paper_id}/reader/translate")
async def translate_reader_selection(paper_id: int, payload: ReaderTranslateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    _paper_or_404(db, paper_id)
    try:
        translation = await LLMClient(db).translate_selection(payload.text, payload.target_language, payload.page)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"translation": translation, "page": payload.page, "target_language": payload.target_language}


@router.post("/papers/{paper_id}/reader/figures")
def save_reader_selection_figure(paper_id: int, payload: ReaderFigureRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    _paper_or_404(db, paper_id)
    try:
        name, _ = save_reader_figure(paper_id, payload.data_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    url = f"/api/papers/{paper_id}/reader/figures/{name}"
    return {"url": url, "page": payload.page, "markdown": f"![{payload.caption or f'论文插图 Page {payload.page}'}]({url})"}


@router.get("/papers/{paper_id}/reader/figures/{name}")
def get_reader_figure(paper_id: int, name: str, db: Session = Depends(get_db)) -> FileResponse:
    _paper_or_404(db, paper_id)
    path = reader_figure_path(paper_id, name)
    if not path:
        raise HTTPException(status_code=404, detail="插图不存在")
    return FileResponse(path, media_type="image/png")


@router.post("/papers/{paper_id}/ai/retry")
async def retry_ai(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    try:
        paper = await RecommendationService(db).retry_ai(paper)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return paper_dict(paper)


@router.get("/papers/{paper_id}/evidence")
def get_paper_evidence(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    items = [evidence_dict(item) for item in paper.analysis_evidence]
    scope = items[0]["source_scope"] if items else ("full_text" if paper.document and paper.document.full_text else "abstract")
    return {"paper_id": paper.id, "analysis_scope": scope, "scope_label": "全文分析" if scope == "full_text" else "仅摘要分析", "items": items}


@router.put("/papers/{paper_id}/evidence")
def update_paper_evidence(paper_id: int, payload: PaperEvidenceUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    if payload.source_scope == "abstract" and any(item.page_number for item in payload.items):
        raise HTTPException(status_code=400, detail="仅摘要分析不能伪造页码")
    replace_analysis_evidence(db, paper, [item.model_dump() for item in payload.items], payload.source_scope)
    db.commit()
    return get_paper_evidence(paper_id, db)


@router.get("/papers/{paper_id}/versions")
def get_paper_versions(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    timeline = work_timeline(db, _paper_or_404(db, paper_id)); db.commit()
    return timeline


@router.post("/papers/{paper_id}/versions/link")
def link_paper_version(paper_id: int, payload: PaperVersionLinkRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    source, target = _paper_or_404(db, paper_id), _paper_or_404(db, payload.target_paper_id)
    try:
        link_versions(db, source, target, payload.crossref_related, payload.user_confirmed); db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return work_timeline(db, source)


@router.post("/papers/{paper_id}/versions/confirm")
def confirm_paper_version(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    version = work_timeline(db, paper)
    paper.work_version.confirmed = True; db.commit()
    return work_timeline(db, paper)


@router.post("/papers/{paper_id}/versions/split")
def split_paper_work(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id); split_version(db, paper); db.commit()
    return work_timeline(db, paper)


@router.post("/papers/{paper_id}/versions/undo")
def undo_paper_work_action(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    try:
        undo_last_version_action(db, paper); db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return work_timeline(db, paper)


@router.get("/papers/{paper_id}/related")
async def related_papers(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    identifier = paper.semantic_scholar_id or (f"ARXIV:{paper.arxiv_id}" if paper.arxiv_id else None)
    if not identifier:
        return {"paper_id": paper.id, "items": [], "message": "缺少可查询的论文标识"}
    try:
        items = await SemanticScholarSource().related(identifier)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"相关研究服务暂时不可用：{exc}") from exc
    return {
        "paper_id": paper.id,
        "items": [{
            "paper_id": item.get("paperId"),
            "title": item.get("title"),
            "url": item.get("url"),
            "authors": [author.get("name") for author in item.get("authors", [])],
            "year": item.get("year"),
            "venue": item.get("venue"),
            "relation": item.get("relation", "similar"),
        } for item in items],
    }


@router.post("/papers/{paper_id}/repository/discover")
async def discover_repository(paper_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return await RepositoryService(db).discover(_paper_or_404(db, paper_id))


@router.post("/papers/{paper_id}/repository/bind")
def bind_repository(paper_id: int, payload: RepositoryBindRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    paper.repository_url = validate_repository_url(str(payload.repository_url))
    paper.repository_status = "manual"
    db.commit()
    return paper_dict(paper)


@router.post("/deepwiki/jobs")
def create_deepwiki_job(paper_id: int, background: BackgroundTasks, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    if not paper.repository_url:
        raise HTTPException(status_code=400, detail="该论文尚未绑定代码仓库")
    active = db.scalar(select(DeepWikiJob).where(DeepWikiJob.paper_id == paper.id, DeepWikiJob.status.in_(["queued", "running"])))
    if active:
        return job_dict(active)
    if not LLMClient(db).configured:
        raise HTTPException(status_code=409, detail="完整 DeepWiki 需要可用的模型 API；请先在设置中为当前接口填写 API Key")
    job = DeepWikiJob(paper_id=paper.id, repository_url=validate_repository_url(paper.repository_url))
    db.add(job)
    db.commit()
    db.refresh(job)
    background.add_task(run_deepwiki_job, job.id)
    return job_dict(job)


@router.get("/deepwiki/jobs")
def list_deepwiki_jobs(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    jobs = db.scalars(select(DeepWikiJob).order_by(desc(DeepWikiJob.created_at))).all()
    return [job_dict(job) for job in jobs]


@router.get("/deepwiki/jobs/{job_id}")
def get_deepwiki_job(job_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = db.get(DeepWikiJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job_dict(job)


@router.post("/deepwiki/jobs/{job_id}/retry")
def retry_deepwiki_job(job_id: int, background: BackgroundTasks, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = db.get(DeepWikiJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="任务正在运行")
    if not LLMClient(db).configured:
        raise HTTPException(status_code=409, detail="完整 DeepWiki 需要可用的模型 API；请先在设置中为当前接口填写 API Key")
    job.status, job.progress, job.message, job.error = "queued", 0, "等待重新生成", None
    db.commit(); db.refresh(job)
    background.add_task(run_deepwiki_job, job.id)
    return job_dict(job)


@router.get("/deepwiki/jobs/{job_id}/wiki")
def get_wiki(job_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = db.get(DeepWikiJob, job_id)
    if not job or job.status != "completed" or not wiki_is_complete(job.output_dir):
        raise HTTPException(status_code=404, detail="Wiki 尚未生成或正文不完整")
    path = Path(job.output_dir) / "wiki_structure.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/deepwiki/jobs/{job_id}/wiki/pages/{page_id}")
def get_wiki_page(job_id: int, page_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = db.get(DeepWikiJob, job_id)
    if not job or not job.output_dir or not page_id.replace("-", "").isalnum():
        raise HTTPException(status_code=404, detail="页面不存在")
    path = Path(job.output_dir) / "pages" / f"{page_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="页面不存在")
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise HTTPException(status_code=409, detail="Wiki 页面正文为空，请重新生成")
    return {"id": page_id, "content": content}


@router.get("/settings")
def read_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_settings(db)


@router.put("/settings")
def write_settings(payload: SettingsUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    values = payload.model_dump(exclude_none=True)
    llm_api_key = values.pop("llm_api_key", None)
    github_token = values.pop("github_token", None)
    zotero_api_key = values.pop("zotero_api_key", None)
    if llm_api_key:
        active_profile = get_active_llm_profile(db)
        if active_profile:
            save_llm_profile_key(active_profile.id, llm_api_key)
    save_secrets(github_token=github_token, zotero_api_key=zotero_api_key)
    result = update_settings(db, values)
    sync_scheduler()
    return result


@router.get("/llm/profiles")
def read_llm_profiles(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_llm_profiles(db)


@router.post("/llm/profiles")
def create_llm_profile(payload: LLMProfileCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    profile = LLMProfile(id=str(uuid.uuid4()), **payload.model_dump(exclude={"api_key"}), is_active=False)
    if db.query(LLMProfile).count() == 0:
        profile.is_active = True
    db.add(profile)
    db.commit()
    if payload.api_key:
        save_llm_profile_key(profile.id, payload.api_key)
    db.refresh(profile)
    return llm_profile_dict(profile)


@router.put("/llm/profiles/{profile_id}")
def update_llm_profile(profile_id: str, payload: LLMProfileUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    profile = db.get(LLMProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="API 配置不存在")
    values = payload.model_dump(exclude_none=True)
    api_key = values.pop("api_key", None)
    for key, value in values.items():
        setattr(profile, key, value)
    if api_key:
        save_llm_profile_key(profile.id, api_key)
    db.commit()
    db.refresh(profile)
    return llm_profile_dict(profile)


@router.post("/llm/profiles/{profile_id}/activate")
def activate_llm_profile(profile_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    profile = db.get(LLMProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="API 配置不存在")
    for item in db.query(LLMProfile).all():
        item.is_active = item.id == profile.id
    db.commit()
    db.refresh(profile)
    return llm_profile_dict(profile)


@router.delete("/llm/profiles/{profile_id}")
def delete_llm_profile(profile_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    profile = db.get(LLMProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="API 配置不存在")
    was_active = profile.is_active
    db.delete(profile)
    db.commit()
    delete_llm_profile_key(profile_id)
    if was_active:
        fallback = db.query(LLMProfile).order_by(LLMProfile.created_at).first()
        if fallback:
            fallback.is_active = True
            db.commit()
    return {"deleted": True}


@router.get("/llm/usage")
def read_token_usage(days: int = Query(default=14, ge=1, le=90), db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = get_settings(db)
    return token_usage_stats(db, settings.get("timezone", "Asia/Shanghai"), days)


@router.post("/papers/{paper_id}/chat/sessions")
def create_chat_session(paper_id: int, payload: ChatSessionCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    session = ChatSession(id=str(uuid.uuid4()), paper_id=paper.id, title=payload.title or "论文对话")
    db.add(session)
    db.commit()
    return {"id": session.id, "paper_id": session.paper_id, "title": session.title, "created_at": session.created_at.isoformat(), "messages": []}


@router.get("/papers/{paper_id}/chat/sessions")
def list_chat_sessions(paper_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    _paper_or_404(db, paper_id)
    sessions = db.scalars(select(ChatSession).where(ChatSession.paper_id == paper_id).order_by(desc(ChatSession.updated_at))).all()
    return [{"id": item.id, "paper_id": item.paper_id, "title": item.title, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()} for item in sessions]


@router.get("/papers/{paper_id}/chat/sessions/{session_id}/messages")
def list_chat_messages(paper_id: int, session_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    session = db.get(ChatSession, session_id)
    if not session or session.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="对话不存在")
    return [{"id": item.id, "role": item.role, "content": item.content, "created_at": item.created_at.isoformat()} for item in session.messages]


@router.post("/papers/{paper_id}/chat")
async def paper_chat(paper_id: int, payload: PaperChatRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    paper = _paper_or_404(db, paper_id)
    session = db.get(ChatSession, payload.session_id) if payload.session_id else None
    if session and session.paper_id != paper.id:
        raise HTTPException(status_code=404, detail="对话不存在")
    if session is None:
        session = ChatSession(id=str(uuid.uuid4()), paper_id=paper.id, title=payload.message[:48])
        db.add(session)
        db.flush()
    db.add(ChatMessage(session_id=session.id, role="user", content=payload.message))
    db.commit()
    recent = list(db.scalars(select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(desc(ChatMessage.created_at)).limit(20)))
    recent.reverse()
    full_text = await get_or_extract_paper_text(db, paper)
    context = _paper_chat_context(paper, full_text)
    try:
        answer = await LLMClient(db).chat_about_paper(context, [{"role": item.role, "content": item.content} for item in recent])
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    assistant_message = ChatMessage(session_id=session.id, role="assistant", content=answer)
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    citations = [{"label": "论文页面", "url": paper.primary_url}]
    if paper.pdf_url:
        citations.append({"label": "PDF", "url": paper.pdf_url})
    return {"session_id": session.id, "answer": answer, "citations": citations}


def _paper_or_404(db: Session, paper_id: int) -> Paper:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    return paper


def _paper_chat_context(paper: Paper, full_text: str | None = None) -> str:
    parts = [
        f"English title: {paper.title_en}",
        f"Chinese title: {paper.title_zh or 'not available'}",
        f"Authors: {', '.join(json.loads(paper.authors_json or '[]'))}",
        f"Venue: {paper.venue_name or 'arXiv preprint'} ({paper.venue_tier})",
        f"English abstract:\n{paper.abstract_en}",
        f"Chinese abstract:\n{paper.abstract_zh or 'not available'}",
    ]
    if paper.summary_json:
        parts.append(f"Existing AI analysis:\n{paper.summary_json}")
    if paper.note and paper.note.content:
        parts.append(f"User learning notes:\n{paper.note.content[:12000]}")
    if full_text:
        parts.append(f"Extracted paper full text (up to 100 pages / 180k characters):\n{full_text}")
    else:
        parts.append("Full PDF text is not available. Base paper-specific claims on the abstracts and metadata above.")
    return "\n\n".join(parts)
