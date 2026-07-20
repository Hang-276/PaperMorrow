from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .cowork_files import resolve_authorized_path
from .cowork_models import CoworkAgentInstance, CoworkArtifact, CoworkDelegation, CoworkMessage, CoworkSession, CoworkStep, CoworkTask
from .cowork_security import has_object_permission, redact_sensitive, write_audit
from .llm import LLMClient, LLMNotConfigured
from .usage_service import estimate_tokens


AGENT_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
AGENT_ACTIVE_STATUSES = {"queued", "running", "paused"}


class StrictAgentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextReference(StrictAgentPayload):
    resource_type: Literal["paper", "note", "project", "experiment", "study", "deepwiki", "file", "artifact", "message"]
    resource_id: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=160)
    label: str = Field(default="", max_length=500)
    excerpt: str = Field(default="", max_length=4000)
    evidence_scope: Literal["metadata", "abstract", "full_text", "user_record", "generated"] = "metadata"


class AgentFinding(StrictAgentPayload):
    kind: Literal["paper_fact", "author_claim", "user_record", "ai_inference"]
    statement: str = Field(min_length=1, max_length=8000)
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    confidence: Literal["low", "medium", "high"] = "medium"

    @model_validator(mode="after")
    def sourced_fact(self):
        if self.kind != "ai_inference" and not self.source_ids:
            raise ValueError("论文事实、作者主张和用户记录必须提供来源编号")
        return self


class AgentArtifactReference(StrictAgentPayload):
    artifact_type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=500)
    artifact_id: str | None = Field(default=None, max_length=160)


class AgentResult(StrictAgentPayload):
    summary: str = Field(min_length=1, max_length=20_000)
    findings: list[AgentFinding] = Field(default_factory=list, max_length=50)
    artifacts: list[AgentArtifactReference] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    next_actions: list[str] = Field(default_factory=list, max_length=20)


@dataclass(frozen=True)
class ExpertRole:
    role: str
    display_name: str
    description: str
    instructions: str
    allowed_tools: tuple[str, ...]
    default_token_budget: int = 20_000
    max_iterations: int = 6

    def public_dict(self) -> dict:
        return {
            "role": self.role,
            "display_name": self.display_name,
            "description": self.description,
            "allowed_tools": list(self.allowed_tools),
            "default_token_budget": self.default_token_budget,
            "max_iterations": self.max_iterations,
        }


EXPERT_ROLES = {
    item.role: item
    for item in (
        ExpertRole("literature_evidence", "文献检索与证据核验", "检索候选论文、核对证据范围并保守综合。", "只基于分配的资料和工具工作；摘要证据必须标明仅摘要。", ("library.search", "library.read_paper")),
        ExpertRole("experiment_analysis", "实验分析", "比较授权实验记录并识别异常、混杂因素和缺失证据。", "实验事实引用实验编号，不把相关性写成因果。", ("projects.search",)),
        ExpertRole("research_synthesis", "笔记与综述", "把已核验材料组织成可追溯综述或研究笔记。", "区分论文事实、作者主张、用户记录与 AI 推断。", ("library.read_paper", "notes.read")),
        ExpertRole("document_presentation", "PPT 与文档", "基于证据包设计科研汇报和文档产物。", "只返回结构化产物建议；不得直接写入，不得补造页码、数值、引文或工具执行结果。", ("library.read_paper", "notes.read")),
        ExpertRole("project_planning", "项目规划", "拆分研究目标、依赖、风险和可验证下一步。", "只返回结构化规划，不执行写操作。", ("projects.search",)),
    )
}


def _loads(value: str, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def ensure_supervisor(db: Session, session: CoworkSession) -> CoworkAgentInstance:
    supervisor = db.scalar(select(CoworkAgentInstance).where(CoworkAgentInstance.session_id == session.id, CoworkAgentInstance.role == "supervisor", CoworkAgentInstance.parent_agent_id.is_(None)))
    if supervisor:
        return supervisor
    task = db.scalar(select(CoworkTask).where(CoworkTask.session_id == session.id).order_by(CoworkTask.id.desc()))
    from .cowork_tools import DEFAULT_REGISTRY

    supervisor = CoworkAgentInstance(
        id=str(uuid.uuid4()), session_id=session.id, task_id=task.id if task else None,
        role="supervisor", display_name="主协调 Agent", status="idle", objective=session.goal,
        instructions="分配最小上下文给专家，验证结构化结果；不得替专家扩大权限。",
        allowed_tools_json=json.dumps([item["name"] for item in DEFAULT_REGISTRY.list_tools()], ensure_ascii=False), token_budget=session.agent_token_budget,
        max_iterations=max(8, session.delegation_budget),
    )
    db.add(supervisor); db.flush()
    write_audit(db, "agent.supervisor_created", "创建主协调 Agent", session_id=session.id, details={"agent_id": supervisor.id})
    return supervisor


def create_delegation(
    db: Session,
    session: CoworkSession,
    *,
    role: str,
    objective: str,
    context_refs: list[ContextReference],
    token_budget: int | None = None,
    step_id: int | None = None,
    parent_agent_id: str | None = None,
) -> CoworkDelegation:
    if session.status in {"cancelled", "completed", "failed"} or session.stop_requested:
        raise RuntimeError("已结束或停止的会话不能创建专家委派")
    spec = EXPERT_ROLES.get(role)
    if not spec:
        raise ValueError("未知专家角色")
    context_refs = _validated_context_refs(db, session.id, context_refs)
    supervisor = ensure_supervisor(db, session)
    parent = db.get(CoworkAgentInstance, parent_agent_id) if parent_agent_id else supervisor
    if not parent or parent.session_id != session.id or parent.role != "supervisor":
        raise PermissionError("只有本会话主协调 Agent 可以委派专家")
    if step_id is not None:
        step = db.get(CoworkStep, step_id)
        if not step or step.task.session_id != session.id:
            raise ValueError("步骤不属于当前会话")
    total = db.scalar(select(func.count()).select_from(CoworkDelegation).where(CoworkDelegation.session_id == session.id)) or 0
    if total >= session.delegation_budget:
        raise RuntimeError("已达到本会话专家委派次数上限")
    active = db.scalar(select(func.count()).select_from(CoworkAgentInstance).where(CoworkAgentInstance.session_id == session.id, CoworkAgentInstance.parent_agent_id.is_not(None), CoworkAgentInstance.status.in_(AGENT_ACTIVE_STATUSES))) or 0
    if active >= session.max_parallel_agents:
        raise RuntimeError("已达到并行专家上限，请等待、暂停或停止现有专家")
    reserved = db.scalar(select(func.coalesce(func.sum(CoworkDelegation.token_budget), 0)).where(CoworkDelegation.session_id == session.id, CoworkDelegation.status.in_(["pending", "running", "paused"]))) or 0
    remaining = session.agent_token_budget - session.agent_tokens_used - reserved
    allocated = token_budget or spec.default_token_budget
    if allocated < 1000 or allocated > 50_000 or allocated > remaining:
        raise ValueError("专家 Token 预算必须在 1000–50000 且不超过会话剩余预算")
    parent_tools = set(_loads(parent.allowed_tools_json, []))
    child_tools = set(spec.allowed_tools)
    if not child_tools < parent_tools:
        raise PermissionError("专家工具能力必须是主协调 Agent 能力的严格子集")
    task = db.scalar(select(CoworkTask).where(CoworkTask.session_id == session.id).order_by(CoworkTask.id.desc()))
    child = CoworkAgentInstance(
        id=str(uuid.uuid4()), session_id=session.id, task_id=task.id if task else None,
        parent_agent_id=parent.id, role=spec.role, display_name=spec.display_name,
        status="queued", objective=objective.strip(), instructions=spec.instructions,
        allowed_tools_json=json.dumps(spec.allowed_tools, ensure_ascii=False),
        context_refs_json=json.dumps([item.model_dump() for item in context_refs], ensure_ascii=False),
        token_budget=allocated, max_iterations=spec.max_iterations,
    )
    delegation = CoworkDelegation(
        id=str(uuid.uuid4()), session_id=session.id, task_id=task.id if task else None,
        step_id=step_id, parent_agent_id=parent.id, child_agent_id=child.id,
        objective=objective.strip(), input_context_json=child.context_refs_json,
        output_schema_json=json.dumps(AgentResult.model_json_schema(), ensure_ascii=False),
        token_budget=allocated,
    )
    db.add_all([child, delegation]); db.flush()
    write_audit(db, "agent.delegated", f"委派专家：{spec.display_name}", session_id=session.id, details={"delegation_id": delegation.id, "agent_id": child.id, "role": role, "token_budget": allocated, "context_refs": len(context_refs)})
    return delegation


def _validated_context_refs(db: Session, session_id: str, refs: list[ContextReference]) -> list[ContextReference]:
    """Accept only server-verifiable references already inside the session boundary."""
    result: list[ContextReference] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        key = (ref.resource_type, ref.resource_id)
        if key in seen:
            continue
        seen.add(key)
        if ref.resource_type == "message":
            try:
                item = db.get(CoworkMessage, int(ref.resource_id))
            except ValueError as exc:
                raise PermissionError("消息上下文编号无效") from exc
            if not item or item.session_id != session_id:
                raise PermissionError("不能向专家委派其他会话的消息")
        elif ref.resource_type == "artifact":
            item = db.get(CoworkArtifact, ref.resource_id)
            if not item or item.session_id != session_id:
                raise PermissionError("不能向专家委派其他会话的产物")
        elif ref.resource_type == "file":
            resolve_authorized_path(db, session_id, ref.resource_id)
        elif not has_object_permission(db, session_id, ref.resource_type, ref.resource_id):
            raise PermissionError(f"未授权将该 {ref.resource_type} 资料委派给专家")
        safe_excerpt = redact_sensitive(ref.excerpt)
        result.append(ref.model_copy(update={"excerpt": safe_excerpt[:4000]}))
    return result


def start_delegation(db: Session, delegation: CoworkDelegation) -> None:
    if delegation.status == "running":
        return
    if delegation.status not in {"pending", "paused"}:
        raise RuntimeError("只有等待或暂停的委派可以启动")
    child = db.get(CoworkAgentInstance, delegation.child_agent_id)
    if not child:
        raise RuntimeError("专家实例不存在")
    now = datetime.now(timezone.utc)
    delegation.status = child.status = "running"
    delegation.started_at = delegation.started_at or now
    child.started_at = child.started_at or now
    child.iterations_used += 1
    write_audit(db, "agent.started", f"专家开始：{child.display_name}", session_id=delegation.session_id, details={"delegation_id": delegation.id, "agent_id": child.id})


def complete_delegation(db: Session, delegation: CoworkDelegation, result: AgentResult, *, tokens_used: int) -> None:
    if delegation.status == "completed":
        if delegation.tokens_used == tokens_used and _loads(delegation.result_json, {}) == result.model_dump():
            return
        raise RuntimeError("已完成的委派不能用不同结果覆盖")
    if delegation.status != "running":
        raise RuntimeError("只有运行中的专家可以提交结果")
    child = db.get(CoworkAgentInstance, delegation.child_agent_id)
    session = db.get(CoworkSession, delegation.session_id)
    if not child or not session:
        raise RuntimeError("专家或会话不存在")
    if tokens_used < 0 or tokens_used > delegation.token_budget:
        raise ValueError("专家 Token 用量超过委派预算")
    if session.agent_tokens_used + tokens_used > session.agent_token_budget:
        raise ValueError("会话 Token 总预算不足")
    allowed_sources = {item.get("source_id") for item in _loads(delegation.input_context_json, [])}
    referenced_sources = {source for finding in result.findings for source in finding.source_ids}
    if not referenced_sources.issubset(allowed_sources):
        raise ValueError("专家结果引用了未分配的来源")
    now = datetime.now(timezone.utc)
    payload = result.model_dump()
    delegation.status = child.status = "completed"
    delegation.result_json = json.dumps(payload, ensure_ascii=False)
    delegation.result_summary = result.summary
    delegation.tokens_used = child.tokens_used = tokens_used
    delegation.finished_at = child.finished_at = now
    session.agent_tokens_used += tokens_used
    write_audit(db, "agent.completed", f"专家完成：{child.display_name}", session_id=session.id, details={"delegation_id": delegation.id, "agent_id": child.id, "tokens_used": tokens_used, "finding_count": len(result.findings)})


async def execute_delegation(db: Session, delegation: CoworkDelegation) -> CoworkDelegation:
    """Execute a frozen work packet; stale or cancelled results are discarded."""
    start_delegation(db, delegation)
    child = db.get(CoworkAgentInstance, delegation.child_agent_id)
    session = db.get(CoworkSession, delegation.session_id)
    if not child or not session:
        raise RuntimeError("专家或会话不存在")
    client = LLMClient(db)
    if not client.configured:
        child.status = delegation.status = "paused"
        write_audit(db, "agent.paused_no_model", f"专家暂停：{child.display_name}", session_id=session.id, details={"agent_id": child.id})
        db.commit()
        raise LLMNotConfigured("未配置模型，专家 Agent 已安全暂停")
    work_packet = {
        "role": child.role,
        "display_name": child.display_name,
        "objective": child.objective,
        "instructions": child.instructions,
        "allowed_tools": _loads(child.allowed_tools_json, []),
        "context": _loads(delegation.input_context_json, []),
        "token_budget": delegation.token_budget,
        "max_iterations": child.max_iterations,
    }
    db.commit()  # Publish running state so pause/cancel can revoke this lease while the model is in flight.
    try:
        raw_result = await client.run_cowork_expert(work_packet, AgentResult.model_json_schema())
        result = AgentResult.model_validate(raw_result)
    except Exception as exc:
        db.expire_all()
        current = db.get(CoworkDelegation, delegation.id)
        current_child = db.get(CoworkAgentInstance, delegation.child_agent_id)
        current_session = db.get(CoworkSession, delegation.session_id)
        if current and current_child and current_session and current.status == "running" and not current_session.stop_requested:
            current.status = current_child.status = "failed"
            current.error = current_child.error = str(exc)[:2000]
            current.finished_at = current_child.finished_at = datetime.now(timezone.utc)
            write_audit(db, "agent.failed", f"专家失败：{current_child.display_name}", session_id=current_session.id, details={"agent_id": current_child.id, "error": str(exc)})
            db.commit()
        raise
    db.expire_all()
    current = db.get(CoworkDelegation, delegation.id)
    current_child = db.get(CoworkAgentInstance, delegation.child_agent_id)
    current_session = db.get(CoworkSession, delegation.session_id)
    if not current or not current_child or not current_session:
        raise RuntimeError("专家执行记录已不存在")
    if current.status != "running" or current_child.status != "running" or current_session.stop_requested or current_session.status == "cancelled":
        write_audit(db, "agent.result_discarded", f"丢弃已停止专家的迟到结果：{current_child.display_name}", session_id=current_session.id, details={"agent_id": current_child.id})
        db.commit()
        return current
    used = estimate_tokens(json.dumps(work_packet, ensure_ascii=False)) + estimate_tokens(json.dumps(raw_result, ensure_ascii=False))
    complete_delegation(db, current, result, tokens_used=used)
    db.commit()
    return current


def invoke_agent_tool(db: Session, agent: CoworkAgentInstance, name: str, arguments: dict, *, step_id: int | None = None) -> dict:
    """The sole expert tool boundary; it never bypasses approval or session grants."""
    if agent.parent_agent_id is None or agent.status != "running":
        raise PermissionError("只有运行中的受控专家可以调用专家工具边界")
    if name not in set(_loads(agent.allowed_tools_json, [])):
        raise PermissionError("该专家未获此工具能力")
    from .cowork_tools import DEFAULT_REGISTRY

    spec = DEFAULT_REGISTRY.get(name)
    if spec.approval != "never":
        raise PermissionError("专家不能直接执行写入或需审批工具，只能返回结构化建议")
    return DEFAULT_REGISTRY.invoke(db, agent.session_id, name, arguments, approved=False, step_id=step_id)


def stop_agent(db: Session, agent: CoworkAgentInstance, *, actor: str = "user") -> None:
    if agent.status in AGENT_TERMINAL_STATUSES:
        return
    now = datetime.now(timezone.utc)
    agent.status = "cancelled"; agent.finished_at = now
    delegation = db.scalar(select(CoworkDelegation).where(CoworkDelegation.child_agent_id == agent.id))
    if delegation and delegation.status not in AGENT_TERMINAL_STATUSES:
        delegation.status = "cancelled"; delegation.finished_at = now
    write_audit(db, "agent.cancelled", f"停止专家：{agent.display_name}", session_id=agent.session_id, actor=actor, details={"agent_id": agent.id})


def stop_all_experts(db: Session, session: CoworkSession, *, actor: str = "user") -> int:
    agents = db.scalars(select(CoworkAgentInstance).where(CoworkAgentInstance.session_id == session.id, CoworkAgentInstance.parent_agent_id.is_not(None), CoworkAgentInstance.status.not_in(AGENT_TERMINAL_STATUSES))).all()
    for agent in agents:
        stop_agent(db, agent, actor=actor)
    return len(agents)


def pause_experts(db: Session, session_id: str) -> int:
    agents = db.scalars(select(CoworkAgentInstance).where(CoworkAgentInstance.session_id == session_id, CoworkAgentInstance.parent_agent_id.is_not(None), CoworkAgentInstance.status.in_(["queued", "running"]))).all()
    for agent in agents:
        agent.status = "paused"
        delegation = db.scalar(select(CoworkDelegation).where(CoworkDelegation.child_agent_id == agent.id))
        if delegation and delegation.status in {"pending", "running"}:
            delegation.status = "paused"
    return len(agents)


def resume_experts(db: Session, session_id: str) -> int:
    agents = db.scalars(select(CoworkAgentInstance).where(CoworkAgentInstance.session_id == session_id, CoworkAgentInstance.parent_agent_id.is_not(None), CoworkAgentInstance.status == "paused")).all()
    for agent in agents:
        agent.status = "queued"
        delegation = db.scalar(select(CoworkDelegation).where(CoworkDelegation.child_agent_id == agent.id))
        if delegation and delegation.status == "paused":
            delegation.status = "pending"
    return len(agents)


def agent_dict(agent: CoworkAgentInstance, delegation: CoworkDelegation | None = None) -> dict:
    return {
        "id": agent.id, "role": agent.role, "display_name": agent.display_name,
        "status": agent.status, "objective": agent.objective,
        "allowed_tools": _loads(agent.allowed_tools_json, []),
        "context_refs": _loads(agent.context_refs_json, []),
        "token_budget": agent.token_budget, "tokens_used": agent.tokens_used,
        "max_iterations": agent.max_iterations, "iterations_used": agent.iterations_used,
        "error": agent.error, "parent_agent_id": agent.parent_agent_id,
        "delegation_id": delegation.id if delegation else None,
        "result": _loads(delegation.result_json, {}) if delegation else {},
        "created_at": agent.created_at.isoformat(),
    }


def agent_state(db: Session, session: CoworkSession) -> dict:
    supervisor = ensure_supervisor(db, session)
    agents = db.scalars(select(CoworkAgentInstance).where(CoworkAgentInstance.session_id == session.id, CoworkAgentInstance.parent_agent_id.is_not(None)).order_by(CoworkAgentInstance.created_at)).all()
    delegations = {item.child_agent_id: item for item in db.scalars(select(CoworkDelegation).where(CoworkDelegation.session_id == session.id)).all()}
    return {
        "supervisor_status": supervisor.status,
        "max_parallel": session.max_parallel_agents,
        "budget": {"limit": session.agent_token_budget, "used": session.agent_tokens_used, "remaining": max(0, session.agent_token_budget - session.agent_tokens_used), "delegations_limit": session.delegation_budget, "delegations_used": len(delegations)},
        "agents": [agent_dict(item, delegations.get(item.id)) for item in agents],
    }
