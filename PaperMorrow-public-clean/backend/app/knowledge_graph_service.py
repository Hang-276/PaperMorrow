from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .deepwiki_service import wiki_is_complete, wiki_is_full_deepwiki
from .models import DeepWikiJob, KnowledgeEdge, KnowledgeNode, Paper, PaperResource, ReproductionCheck, ResearchProject


NODE_TYPES = {"paper", "method", "task", "dataset", "benchmark", "model", "experiment_conclusion", "limitation", "repository", "weight", "project"}
RELATION_TYPES = {"proposes", "uses", "improves", "evaluated_on", "supports", "refutes", "implements", "reproduces", "extends"}
RESOURCE_TYPES = {"official_repository", "third_party_reproduction", "model_weights", "dataset", "project_page"}
CHECK_STATUSES = {"confirmed", "possibly_consistent", "missing", "unable_to_confirm"}


def upsert_node(db: Session, node_type: str, label: str, external_key: str, metadata: dict[str, Any] | None = None) -> KnowledgeNode:
    if node_type not in NODE_TYPES:
        raise ValueError("不支持的知识节点类型")
    node = db.scalar(select(KnowledgeNode).where(KnowledgeNode.external_key == external_key))
    if not node:
        node = KnowledgeNode(node_type=node_type, label=label, external_key=external_key, metadata_json=json.dumps(metadata or {}, ensure_ascii=False)); db.add(node); db.flush()
    return node


def create_grounded_edge(db: Session, source_node_id: int, target_node_id: int, relation_type: str, source_type: str, source_id: str, evidence: str, confidence: float, confirmed: bool = False) -> KnowledgeEdge:
    if relation_type not in RELATION_TYPES or relation_type in {"semantic_similarity", "similar"}:
        raise ValueError("只允许有研究语义和证据的关系")
    if not evidence.strip() or not source_type.strip() or not source_id.strip():
        raise ValueError("关系必须保存来源与证据")
    if not 0 <= confidence <= 1:
        raise ValueError("置信度必须在 0 到 1 之间")
    if not db.get(KnowledgeNode, source_node_id) or not db.get(KnowledgeNode, target_node_id):
        raise ValueError("关系节点不存在")
    edge = KnowledgeEdge(source_node_id=source_node_id, target_node_id=target_node_id, relation_type=relation_type,
                         source_type=source_type, source_id=source_id, evidence=evidence[:5000], confidence=confidence, confirmed=confirmed)
    db.add(edge); db.flush(); return edge


def unified_graph(db: Session, base: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {"nodes": list((base or {}).get("nodes", [])), "edges": list((base or {}).get("edges", []))}
    known = {node["id"] for node in data["nodes"]}
    for node in db.scalars(select(KnowledgeNode).order_by(KnowledgeNode.id)).all():
        node_id = f"entity:{node.id}"
        if node_id not in known:
            data["nodes"].append({"id": node_id, "type": node.node_type, "label": node.label, "metadata": json.loads(node.metadata_json or "{}")}); known.add(node_id)
    for edge in db.scalars(select(KnowledgeEdge).order_by(KnowledgeEdge.id)).all():
        data["edges"].append({"id": edge.id, "source": f"entity:{edge.source_node_id}", "target": f"entity:{edge.target_node_id}",
                              "type": edge.relation_type, "source_type": edge.source_type, "source_id": edge.source_id,
                              "evidence": edge.evidence, "confidence": edge.confidence, "confirmed": edge.confirmed})
    return data


def project_knowledge_graph(db: Session, project: ResearchProject) -> dict[str, Any]:
    """Build a graph strictly from objects already linked to one research project."""
    project_id = f"project:{project.id}"
    nodes: list[dict[str, Any]] = [{
        "id": project_id, "type": "project", "label": project.title,
        "metadata": {"project_id": project.id, "research_question": project.research_question},
    }]
    edges: list[dict[str, Any]] = []
    paper_ids: set[int] = set()

    for link in project.papers:
        paper_ids.add(link.paper_id)
        node_id = f"paper:{link.paper_id}"
        nodes.append({
            "id": node_id, "type": "paper", "label": link.paper.title_zh or link.paper.title_en,
            "paper_id": link.paper_id,
            "metadata": {"project_id": project.id, "role": link.role, "reading_status": link.reading_status},
        })
        edges.append({
            "source": project_id, "target": node_id, "type": "uses",
            "source_type": "project_paper", "source_id": str(link.id),
            "evidence": f"论文由用户关联到项目，角色为 {link.role}。", "confidence": 1.0, "confirmed": True,
        })

    for note in project.notes:
        node_id = f"project-note:{note.id}"
        nodes.append({"id": node_id, "type": "note", "label": note.title, "metadata": {"project_id": project.id}})
        edges.append({
            "source": node_id, "target": project_id, "type": "supports",
            "source_type": "project_note", "source_id": str(note.id),
            "evidence": "该笔记由用户创建在当前项目中。", "confidence": 1.0, "confirmed": True,
        })

    for link in project.studies:
        node_id = f"study:{link.study_id}"
        nodes.append({"id": node_id, "type": "study", "label": link.study.title, "metadata": {"project_id": project.id}})
        edges.append({
            "source": node_id, "target": project_id, "type": "supports",
            "source_type": "project_study", "source_id": str(link.id),
            "evidence": "该专题调研由用户关联到当前项目。", "confidence": 1.0, "confirmed": True,
        })

    for experiment in project.experiments:
        node_id = f"experiment:{experiment.id}"
        nodes.append({
            "id": node_id, "type": "experiment", "label": experiment.title,
            "metadata": {"project_id": project.id, "status": experiment.status},
        })
        edges.append({
            "source": node_id, "target": project_id, "type": "supports",
            "source_type": "project_experiment", "source_id": str(experiment.id),
            "evidence": "该实验记录属于当前项目；关系不代表实验结论已得到验证。", "confidence": 1.0, "confirmed": True,
        })

    entity_ids: set[int] = set()
    for entity in db.scalars(select(KnowledgeNode).order_by(KnowledgeNode.id)).all():
        metadata = json.loads(entity.metadata_json or "{}")
        belongs = metadata.get("project_id") == project.id or metadata.get("paper_id") in paper_ids
        if not belongs:
            continue
        entity_ids.add(entity.id)
        nodes.append({"id": f"entity:{entity.id}", "type": entity.node_type, "label": entity.label, "metadata": metadata})
    for edge in db.scalars(select(KnowledgeEdge).order_by(KnowledgeEdge.id)).all():
        if edge.source_node_id in entity_ids and edge.target_node_id in entity_ids:
            edges.append({
                "id": edge.id, "source": f"entity:{edge.source_node_id}", "target": f"entity:{edge.target_node_id}",
                "type": edge.relation_type, "source_type": edge.source_type, "source_id": edge.source_id,
                "evidence": edge.evidence, "confidence": edge.confidence, "confirmed": edge.confirmed,
            })
    return {"scope": {"type": "project", "id": project.id, "title": project.title}, "nodes": nodes, "edges": edges}


def add_resource(db: Session, paper: Paper, resource_type: str, url: str, label: str, source: str, verified: bool) -> PaperResource:
    if resource_type not in RESOURCE_TYPES:
        raise ValueError("不支持的论文资源类型")
    existing = db.scalar(select(PaperResource).where(PaperResource.paper_id == paper.id, PaperResource.resource_type == resource_type, PaperResource.url == url))
    if existing:
        existing.label, existing.source, existing.verified = label, source, verified
        return existing
    row = PaperResource(paper_id=paper.id, resource_type=resource_type, url=url, label=label, source=source, verified=verified); db.add(row); return row


def generate_reproduction_checklist(db: Session, paper: Paper, job: DeepWikiJob | None = None) -> list[ReproductionCheck]:
    db.flush()
    resources = list(db.scalars(select(PaperResource).where(PaperResource.paper_id == paper.id)).all())
    by_type = {item.resource_type: item for item in resources}
    if paper.repository_url and "official_repository" not in by_type:
        by_type["official_repository"] = PaperResource(paper_id=paper.id, resource_type="official_repository", url=paper.repository_url, label="论文关联仓库", source="paper_metadata", verified=paper.repository_status == "verified")
    wiki_ready = bool(job and job.status == "completed" and wiki_is_complete(job.output_dir))
    wiki_full = bool(wiki_ready and wiki_is_full_deepwiki(job.output_dir))
    specifications = [
        ("repository", "代码仓库可用性", "confirmed" if by_type.get("official_repository") and by_type["official_repository"].verified else ("possibly_consistent" if by_type.get("official_repository") else "missing"), "来自经验证元数据" if by_type.get("official_repository") and by_type["official_repository"].verified else "仓库存在但尚未核验官方关系"),
        ("method_alignment", "论文方法与实现一致性", "possibly_consistent" if wiki_full else "unable_to_confirm", "完整 DeepWiki 已生成，可进行人工逐项核对" if wiki_full else "缺少完整代码 Wiki 或全文方法证据"),
        ("experiment_config", "实验配置一致性", "unable_to_confirm", "不得仅凭文件名确认超参数、数据划分或训练流程"),
        ("weights", "模型权重", "confirmed" if by_type.get("model_weights") and by_type["model_weights"].verified else "missing", "已验证权重链接" if by_type.get("model_weights") and by_type["model_weights"].verified else "未找到可核验权重"),
        ("dataset", "数据集与处理说明", "confirmed" if by_type.get("dataset") and by_type["dataset"].verified else ("possibly_consistent" if by_type.get("dataset") else "missing"), "依据已登记数据集资源" if by_type.get("dataset") else "未登记数据集资源"),
    ]
    rows = []
    for key, title, status, evidence in specifications:
        row = db.scalar(select(ReproductionCheck).where(ReproductionCheck.paper_id == paper.id, ReproductionCheck.check_key == key).order_by(ReproductionCheck.id.desc()))
        if not row:
            row = ReproductionCheck(paper_id=paper.id, check_key=key, title=title, status=status); db.add(row)
        row.deepwiki_job_id = job.id if job else None; row.status = status; row.evidence = evidence; row.details = "状态仅表示当前可核验证据，不替代实际复现实验。"
        rows.append(row)
    db.flush(); return rows


def resource_dict(item: PaperResource) -> dict[str, Any]:
    return {"id": item.id, "paper_id": item.paper_id, "resource_type": item.resource_type, "url": item.url, "label": item.label, "source": item.source, "verified": item.verified}


def check_dict(item: ReproductionCheck) -> dict[str, Any]:
    return {"id": item.id, "check_key": item.check_key, "title": item.title, "status": item.status, "evidence": item.evidence, "details": item.details}
