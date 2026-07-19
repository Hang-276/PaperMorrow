from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .llm import LLMClient, LLMNotConfigured
from .models import ExperimentAnalysis, ExperimentArtifact, ExperimentMetric, ProjectExperiment, ResearchProject


EXPERIMENT_STATUSES = {"planned", "queued", "running", "completed", "failed", "cancelled"}
EXPERIMENT_TYPES = {"run", "baseline", "ablation", "reproduction", "evaluation", "exploration"}


def _json_load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_experiment(db: Session, experiment_id: int) -> ProjectExperiment | None:
    return db.scalar(
        select(ProjectExperiment)
        .where(ProjectExperiment.id == experiment_id)
        .options(selectinload(ProjectExperiment.metrics), selectinload(ProjectExperiment.artifacts))
    )


def list_experiments(db: Session, project_id: int) -> list[ProjectExperiment]:
    return list(
        db.scalars(
            select(ProjectExperiment)
            .where(ProjectExperiment.project_id == project_id)
            .options(selectinload(ProjectExperiment.metrics), selectinload(ProjectExperiment.artifacts))
            .order_by(ProjectExperiment.started_at, ProjectExperiment.created_at, ProjectExperiment.id)
        ).all()
    )


def metric_dict(metric: ExperimentMetric) -> dict[str, Any]:
    return {
        "id": metric.id,
        "name": metric.name,
        "value": metric.value,
        "step": metric.step,
        "split": metric.split,
        "unit": metric.unit,
        "is_primary": metric.is_primary,
        "metadata": _json_load(metric.metadata_json, {}),
        "recorded_at": metric.recorded_at,
    }


def artifact_dict(artifact: ExperimentArtifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "name": artifact.name,
        "uri": artifact.uri,
        "metadata": _json_load(artifact.metadata_json, {}),
        "created_at": artifact.created_at,
    }


def experiment_dict(experiment: ProjectExperiment, detail: bool = True) -> dict[str, Any]:
    result = {
        "id": experiment.id,
        "project_id": experiment.project_id,
        "parent_experiment_id": experiment.parent_experiment_id,
        "title": experiment.title,
        "objective": experiment.objective,
        "hypothesis": experiment.hypothesis,
        "experiment_type": experiment.experiment_type,
        "status": experiment.status,
        "config": _json_load(experiment.config_json, {}),
        "environment": _json_load(experiment.environment_json, {}),
        "dataset_version": experiment.dataset_version,
        "code_reference": experiment.code_reference,
        "command": experiment.command,
        "observations": experiment.observations,
        "conclusion": experiment.conclusion,
        "started_at": experiment.started_at,
        "ended_at": experiment.ended_at,
        "created_at": experiment.created_at,
        "updated_at": experiment.updated_at,
    }
    if detail:
        result["metrics"] = [metric_dict(item) for item in experiment.metrics]
        result["artifacts"] = [artifact_dict(item) for item in experiment.artifacts]
    return result


def _metric_from_input(experiment: ProjectExperiment, item: dict[str, Any]) -> ExperimentMetric:
    return ExperimentMetric(
        experiment=experiment,
        name=item["name"],
        value=item["value"],
        step=item.get("step"),
        split=item.get("split", ""),
        unit=item.get("unit", ""),
        is_primary=item.get("is_primary", False),
        metadata_json=json.dumps(item.get("metadata") or {}, ensure_ascii=False),
        recorded_at=item.get("recorded_at") or _utcnow(),
    )


def _artifact_from_input(experiment: ProjectExperiment, item: dict[str, Any]) -> ExperimentArtifact:
    return ExperimentArtifact(
        experiment=experiment,
        artifact_type=item.get("artifact_type", "file"),
        name=item["name"],
        uri=item["uri"],
        metadata_json=json.dumps(item.get("metadata") or {}, ensure_ascii=False),
    )


def create_experiment(db: Session, project_id: int, values: dict[str, Any]) -> ProjectExperiment:
    if not db.get(ResearchProject, project_id):
        raise LookupError("研究项目不存在")
    parent_id = values.get("parent_experiment_id")
    if parent_id:
        parent = db.get(ProjectExperiment, parent_id)
        if not parent or parent.project_id != project_id:
            raise ValueError("父实验必须属于当前研究项目")
    metrics = values.pop("metrics", [])
    artifacts = values.pop("artifacts", [])
    config = values.pop("config", {})
    environment = values.pop("environment", {})
    experiment = ProjectExperiment(
        project_id=project_id,
        config_json=json.dumps(config, ensure_ascii=False),
        environment_json=json.dumps(environment, ensure_ascii=False),
        **values,
    )
    db.add(experiment)
    for item in metrics:
        db.add(_metric_from_input(experiment, item))
    for item in artifacts:
        db.add(_artifact_from_input(experiment, item))
    db.flush()
    return experiment


def update_experiment(db: Session, experiment: ProjectExperiment, values: dict[str, Any]) -> ProjectExperiment:
    if "parent_experiment_id" in values and values["parent_experiment_id"] is not None:
        parent_id = values["parent_experiment_id"]
        if parent_id == experiment.id:
            raise ValueError("实验不能把自身设为父实验")
        parent = db.get(ProjectExperiment, parent_id)
        if not parent or parent.project_id != experiment.project_id:
            raise ValueError("父实验必须属于当前研究项目")
    if "config" in values:
        experiment.config_json = json.dumps(values.pop("config") or {}, ensure_ascii=False)
    if "environment" in values:
        experiment.environment_json = json.dumps(values.pop("environment") or {}, ensure_ascii=False)
    for key, value in values.items():
        setattr(experiment, key, value)
    experiment.updated_at = _utcnow()
    db.flush()
    return experiment


def append_metrics(db: Session, experiment: ProjectExperiment, items: list[dict[str, Any]]) -> list[ExperimentMetric]:
    metrics = [_metric_from_input(experiment, item) for item in items]
    db.add_all(metrics)
    experiment.updated_at = _utcnow()
    db.flush()
    return metrics


def append_artifacts(db: Session, experiment: ProjectExperiment, items: list[dict[str, Any]]) -> list[ExperimentArtifact]:
    artifacts = [_artifact_from_input(experiment, item) for item in items]
    db.add_all(artifacts)
    experiment.updated_at = _utcnow()
    db.flush()
    return artifacts


def experiment_summary(db: Session, project_id: int) -> dict[str, Any]:
    experiments = list_experiments(db, project_id)
    statuses = Counter(item.status for item in experiments)
    timeline = []
    series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for experiment in experiments:
        timeline.append({
            "experiment_id": experiment.id,
            "parent_experiment_id": experiment.parent_experiment_id,
            "title": experiment.title,
            "experiment_type": experiment.experiment_type,
            "status": experiment.status,
            "started_at": experiment.started_at,
            "ended_at": experiment.ended_at,
            "created_at": experiment.created_at,
        })
        grouped: dict[tuple[str, str], list[ExperimentMetric]] = defaultdict(list)
        for metric in experiment.metrics:
            grouped[(metric.name, metric.split)].append(metric)
        for (name, split), metrics in grouped.items():
            latest = max(metrics, key=lambda item: (item.recorded_at, item.id or 0))
            key = f"{name}:{split}" if split else name
            series[key].append({
                "experiment_id": experiment.id,
                "title": experiment.title,
                "value": latest.value,
                "unit": latest.unit,
                "recorded_at": latest.recorded_at,
                "is_primary": any(item.is_primary for item in metrics),
            })
    for points in series.values():
        previous = None
        for point in points:
            point["delta_previous"] = None if previous is None else round(point["value"] - previous, 12)
            previous = point["value"]
    return {
        "project_id": project_id,
        "experiment_count": len(experiments),
        "status_counts": dict(statuses),
        "timeline": timeline,
        "metric_series": dict(series),
    }


def build_experiment_context(db: Session, project_id: int, max_chars: int = 55_000) -> tuple[str, list[dict[str, Any]]]:
    """Represent every experiment in a compact ledger, then add bounded details.

    The ledger is never truncated per-record, so the agent remains aware of the full
    experiment history. Long free-form observations are added newest-first until the
    context budget is reached.
    """
    experiments = list_experiments(db, project_id)
    sources: list[dict[str, Any]] = []
    ledger: list[str] = ["# 完整实验账本"]
    details: list[str] = []
    for experiment in experiments:
        citation = f"EXP-{experiment.id}"
        metrics = defaultdict(list)
        for metric in experiment.metrics:
            metrics[metric.name].append(metric.value)
        compact_metrics = ", ".join(f"{name}={values[-1]:g}" for name, values in metrics.items()) or "无指标"
        ledger.append(
            f"[{citation}] {experiment.title} | {experiment.experiment_type}/{experiment.status} | "
            f"开始={experiment.started_at or '未记录'} | 数据={experiment.dataset_version or '未记录'} | {compact_metrics}"
        )
        sources.append({"source_id": citation, "source_type": "experiment", "experiment_id": experiment.id, "title": experiment.title})
        detail = (
            f"\n## [{citation}] {experiment.title}\n目标：{experiment.objective or '未记录'}\n"
            f"假设：{experiment.hypothesis or '未记录'}\n配置：{experiment.config_json}\n环境：{experiment.environment_json}\n"
            f"代码：{experiment.code_reference or '未记录'}\n观察：{experiment.observations or '未记录'}\n"
            f"结论：{experiment.conclusion or '未记录'}\n指标："
            + json.dumps([metric_dict(item) for item in experiment.metrics], ensure_ascii=False, default=str)
        )
        details.append(detail)
    context = "\n".join(ledger)
    for detail in reversed(details):
        remaining = max_chars - len(context)
        if remaining <= 300:
            break
        context += detail[:remaining]
    return context, sources


def fallback_analysis(summary: dict[str, Any], question: str) -> str:
    counts = summary["status_counts"]
    completed = counts.get("completed", 0)
    failed = counts.get("failed", 0)
    lines = [
        "当前未配置 LLM，以下为基于结构化实验记录生成的统计摘要。",
        f"项目共记录 {summary['experiment_count']} 次实验，其中已完成 {completed} 次、失败 {failed} 次。",
    ]
    for name, points in summary["metric_series"].items():
        if not points:
            continue
        last = points[-1]
        delta = last.get("delta_previous")
        change = "首次记录" if delta is None else f"较上一条变化 {delta:+g}"
        lines.append(f"- {name}：最新值 {last['value']:g}{last.get('unit') or ''}，{change}。[EXP-{last['experiment_id']}]")
    if summary["experiment_count"] == 0:
        lines.append("尚无实验记录，建议先记录目标、配置、数据版本和主要指标，再进行结果分析。")
    else:
        lines.append("建议优先补齐缺失的代码版本、数据版本和结论，并在相同评估设置下比较关键指标。")
    lines.append(f"分析问题：{question}")
    return "\n".join(lines)


async def analyze_experiments(db: Session, project_id: int, question: str) -> dict[str, Any]:
    context, sources = build_experiment_context(db, project_id)
    summary = experiment_summary(db, project_id)
    client = LLMClient(db)
    used_llm = False
    try:
        answer = await client.analyze_project_experiments(context, question)
        used_llm = True
    except (LLMNotConfigured, httpx.HTTPError):
        answer = fallback_analysis(summary, question)
    analysis = ExperimentAnalysis(
        project_id=project_id,
        question=question,
        answer=answer,
        sources_json=json.dumps(sources, ensure_ascii=False),
        used_llm=used_llm,
    )
    db.add(analysis)
    db.flush()
    return {
        "id": analysis.id,
        "project_id": project_id,
        "question": question,
        "answer": answer,
        "sources": sources,
        "used_llm": used_llm,
        "created_at": analysis.created_at,
    }
