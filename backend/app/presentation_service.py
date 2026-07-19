from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import DATA_DIR, ROOT_DIR
from .llm import LLMClient, LLMNotConfigured
from .models import Paper, ResearchProject
from .note_models import Note, NoteArtifact
from .presentation_models import PresentationDraft


PRESENTATION_DIR = DATA_DIR / "presentations"
ENGINE_DIR = ROOT_DIR / "presentation-studio"
VALID_KINDS = {"lab-meeting", "paper-report", "research-progress", "literature-review", "experiment-report"}


def _safe_json(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return fallback


def _paper_source(paper: Paper) -> dict[str, Any]:
    summary = _safe_json(paper.summary_json, {})
    evidence = {
        "title_en": paper.title_en, "title_zh": paper.title_zh,
        "abstract": paper.abstract_en[:5000], "analysis": summary,
        "analysis_scope": paper.analysis_evidence[0].source_scope if paper.analysis_evidence else ("abstract" if paper.abstract_en else "metadata"),
    }
    return {
        "id": f"PAPER-{paper.id}", "type": "paper", "title": paper.title_en,
        "authors": _safe_json(paper.authors_json, [])[:8],
        "year": paper.published_at.year if paper.published_at else None,
        "url": paper.primary_url if str(paper.primary_url).startswith(("http://", "https://")) else None,
        "doi": paper.doi, "locator": "Abstract" if paper.abstract_en else "Metadata only",
        "evidence": evidence, "confidence": 0.8 if paper.abstract_en else 0.55,
    }


def build_source_catalog(db: Session, note_id: int | None = None, project_id: int | None = None, paper_id: int | None = None) -> tuple[list[dict[str, Any]], str]:
    sources: list[dict[str, Any]] = []
    seen_papers: set[int] = set()
    primary_text = ""
    if note_id:
        note = db.get(Note, note_id)
        if not note:
            raise ValueError("笔记不存在")
        primary_text = note.content
        sources.append({"id": f"NOTE-{note.id}", "type": "note", "title": note.title, "evidence": note.content[:16000], "confidence": 1})
        for link in note.paper_links:
            paper = db.get(Paper, link.paper_id)
            if paper:
                sources.append(_paper_source(paper)); seen_papers.add(paper.id)
    if paper_id and paper_id not in seen_papers:
        paper = db.get(Paper, paper_id)
        if not paper:
            raise ValueError("论文不存在")
        sources.append(_paper_source(paper)); seen_papers.add(paper.id)
        primary_text = primary_text or paper.abstract_en
    if project_id:
        project = db.get(ResearchProject, project_id)
        if not project:
            raise ValueError("研究项目不存在")
        project_text = "\n".join(filter(None, [project.research_question, project.research_direction, project.current_conclusion, project.next_reading_suggestion]))
        primary_text = primary_text or project_text
        sources.append({"id": f"PROJECT-{project.id}", "type": "project", "title": project.title, "evidence": project_text[:12000], "confidence": 1})
        for link in project.papers:
            if link.paper_id not in seen_papers:
                sources.append(_paper_source(link.paper)); seen_papers.add(link.paper_id)
        for experiment in project.experiments:
            metrics = [{"name": item.name, "value": item.value, "unit": item.unit, "split": item.split} for item in experiment.metrics]
            evidence = {"objective": experiment.objective, "hypothesis": experiment.hypothesis, "config": _safe_json(experiment.config_json, {}), "metrics": metrics, "observations": experiment.observations, "conclusion": experiment.conclusion}
            sources.append({"id": f"EXP-{experiment.id}", "type": "experiment", "title": experiment.title, "evidence": evidence, "confidence": 1})
    return sources, primary_text


def _headings(text: str) -> list[str]:
    items = [match.group(1).strip() for match in re.finditer(r"^#{1,4}\s+(.+)$", text, re.MULTILINE)]
    return list(dict.fromkeys(items))[:18]


def default_outline(title: str, kind: str, language: str, sources: list[dict[str, Any]], primary_text: str, slide_count: int = 10, blank: bool = False) -> dict[str, Any]:
    refs = [item["id"] for item in sources]
    if blank:
        return {"schemaVersion": "1.0", "title": title, "kind": kind, "language": language, "slides": [{"id": "outline-1", "title": "汇报主题", "purpose": "开场", "key_message": "", "points": [], "source_refs": []}]}
    if kind == "paper-report":
        topics = ["论文与研究背景", "研究问题", "核心方法", "实验设计", "主要结果", "创新与贡献", "局限与风险", "可复现性", "讨论问题", "总结"]
    elif kind in {"research-progress", "lab-meeting", "experiment-report"}:
        topics = ["研究问题与本阶段目标", "背景与已有证据", "本阶段工作", "实验时间线", "关键结果变化", "消融与对比", "失败实验与经验", "当前结论", "待解决问题", "下一步计划"]
    else:
        topics = ["问题范围", "研究分类", "代表性工作", "方法路线", "证据对比", "争议观点", "研究空白", "阅读建议", "总结"]
    headings = _headings(primary_text)
    if headings:
        topics[2:2 + min(len(headings), max(0, len(topics) - 4))] = headings[:max(0, len(topics) - 4)]
    topics = topics[:max(4, min(30, slide_count))]
    slides = []
    for index, topic in enumerate(topics):
        slide_refs = refs if index in {0, len(topics) - 1} else refs[:min(4, len(refs))]
        slides.append({"id": f"outline-{index + 1}", "title": topic, "purpose": "结论" if index == len(topics) - 1 else "论证", "key_message": "", "points": [], "source_refs": slide_refs})
    return {"schemaVersion": "1.0", "title": title, "kind": kind, "language": language, "slides": slides}


def validate_outline(outline: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    source_ids = {item["id"] for item in sources}
    if not isinstance(outline, dict) or not str(outline.get("title", "")).strip():
        raise ValueError("大纲需要标题")
    slides = outline.get("slides")
    if not isinstance(slides, list) or not 1 <= len(slides) <= 60:
        raise ValueError("大纲需要包含 1–60 页")
    normalized = []
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict) or not str(slide.get("title", "")).strip():
            raise ValueError(f"第 {index + 1} 页缺少标题")
        refs = list(dict.fromkeys(str(item) for item in slide.get("source_refs", [])))
        unknown = [item for item in refs if item not in source_ids]
        if unknown:
            raise ValueError(f"第 {index + 1} 页引用了未知来源：{', '.join(unknown)}")
        normalized.append({
            "id": str(slide.get("id") or f"outline-{index + 1}"), "title": str(slide["title"]).strip(),
            "purpose": str(slide.get("purpose") or "论证"), "key_message": str(slide.get("key_message") or ""),
            "points": [str(item).strip() for item in slide.get("points", []) if str(item).strip()][:6], "source_refs": refs,
        })
    return {"schemaVersion": "1.0", "title": str(outline["title"]).strip(), "kind": str(outline.get("kind") or "lab-meeting"), "language": str(outline.get("language") or "zh-CN"), "slides": normalized}


async def create_outline(db: Session, values: dict[str, Any]) -> PresentationDraft:
    kind = values.get("kind", "lab-meeting")
    if kind not in VALID_KINDS:
        raise ValueError("不支持的汇报类型")
    sources, primary_text = build_source_catalog(db, values.get("note_id"), values.get("project_id"), values.get("paper_id"))
    title = values.get("title") or (db.get(Note, values.get("note_id")).title if values.get("note_id") else "科研组会汇报")
    outline = default_outline(title, kind, values.get("language", "zh-CN"), sources, primary_text, values.get("slide_count", 10), values.get("blank", False))
    if values.get("use_ai", True) and not values.get("blank", False):
        client = LLMClient(db)
        try:
            generated = await client.generate_presentation_outline({"sources": sources, "primary_text": primary_text[:20000]}, values)
            generated.setdefault("schemaVersion", "1.0"); generated.setdefault("title", title); generated.setdefault("kind", kind); generated.setdefault("language", values.get("language", "zh-CN"))
            outline = validate_outline(generated, sources)
        except (LLMNotConfigured, ValueError, KeyError, TypeError, json.JSONDecodeError):
            pass
        except Exception:
            # A model/network failure should not block the editable outline workflow.
            pass
    draft = PresentationDraft(title=title, kind=kind, language=values.get("language", "zh-CN"), note_id=values.get("note_id"), project_id=values.get("project_id"), paper_id=values.get("paper_id"), instructions=values.get("instructions", ""), outline_json=json.dumps(outline, ensure_ascii=False), source_catalog_json=json.dumps(sources, ensure_ascii=False), status="outline")
    db.add(draft); db.commit(); db.refresh(draft)
    return draft


def draft_dict(draft: PresentationDraft) -> dict[str, Any]:
    return {"id": draft.id, "title": draft.title, "kind": draft.kind, "language": draft.language, "note_id": draft.note_id, "project_id": draft.project_id, "paper_id": draft.paper_id, "instructions": draft.instructions, "outline": _safe_json(draft.outline_json, {}), "sources": _safe_json(draft.source_catalog_json, []), "status": draft.status, "download_url": f"/api/presentations/{draft.id}/download" if draft.output_path and draft.status == "completed" else None, "error": draft.error, "created_at": draft.created_at.isoformat(), "updated_at": draft.updated_at.isoformat()}


def compile_deck_spec(draft: PresentationDraft) -> dict[str, Any]:
    outline = validate_outline(_safe_json(draft.outline_json, {}), _safe_json(draft.source_catalog_json, []))
    sources = _safe_json(draft.source_catalog_json, [])
    deck_kind = "research-progress" if draft.kind == "lab-meeting" else draft.kind
    slides: list[dict[str, Any]] = []
    for index, item in enumerate(outline["slides"]):
        layout = "title" if index == 0 else "content"
        points = item["points"] or ([item["key_message"]] if item["key_message"] else ["在大纲中补充本页要点，或让 AI 基于已引用来源继续完善。"])
        slide = {"id": f"slide-{index + 1}", "layout": layout, "title": item["title"], "blocks": [] if layout == "title" else [{"type": "bullets", "items": points}], "citations": item["source_refs"]}
        if item["key_message"]:
            slide["subtitle"] = item["key_message"]
            slide["keyMessage"] = item["key_message"]
        if item["source_refs"]:
            slide["speakerNotes"] = "证据来源：" + ", ".join(item["source_refs"])
        slides.append(slide)
    if sources:
        slides.append({"id": "slide-references", "layout": "bibliography", "title": "参考文献与证据来源", "blocks": [], "citations": []})
    clean_sources = []
    for item in sources:
        clean_sources.append({key: value for key, value in item.items() if key in {"id", "type", "title", "authors", "year", "locator", "url", "doi", "confidence"} and value is not None})
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"schemaVersion": "1.0", "metadata": {"title": draft.title, "language": draft.language, "kind": deck_kind, "generatedAt": generated_at}, "theme": {"accentColor": "1677FF", "fontFamily": "Arial", "monoFontFamily": "Menlo"}, "sources": clean_sources, "slides": slides}


def render_presentation(db: Session, draft: PresentationDraft) -> PresentationDraft:
    PRESENTATION_DIR.mkdir(parents=True, exist_ok=True)
    spec = compile_deck_spec(draft)
    spec_path = PRESENTATION_DIR / f"presentation-{draft.id}.json"
    output_path = PRESENTATION_DIR / f"presentation-{draft.id}.pptx"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    cli = ENGINE_DIR / "dist" / "src" / "cli.js"
    if not cli.exists():
        subprocess.run(["npm", "run", "build"], cwd=ENGINE_DIR, check=True, capture_output=True, text=True, timeout=120)
    draft.status = "generating"; draft.error = None; db.commit()
    try:
        result = subprocess.run(["node", str(cli), str(spec_path), str(output_path)], cwd=ENGINE_DIR, check=False, capture_output=True, text=True, timeout=180)
        if result.returncode != 0 or not output_path.exists():
            raise RuntimeError((result.stderr or result.stdout or "PPTX 生成失败")[-3000:])
        draft.deck_spec_json = json.dumps(spec, ensure_ascii=False)
        draft.output_path = str(output_path)
        draft.status = "completed"
    except Exception as exc:
        draft.status = "failed"; draft.error = str(exc)
    db.commit(); db.refresh(draft)
    return draft


def create_note_presentation(db: Session, note: Note, values: dict[str, Any]) -> NoteArtifact:
    outline = default_outline(note.title, values.get("presentation_mode", "lab-meeting"), "zh-CN" if values.get("language", "zh") == "zh" else "en-US", [{"id": f"NOTE-{note.id}", "type": "note", "title": note.title}], note.content, values.get("slide_count", 10))
    artifact = NoteArtifact(note=note, artifact_type="presentation", status="outline", content=json.dumps(outline, ensure_ascii=False))
    db.add(artifact)
    return artifact
