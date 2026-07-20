from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from backend.app.cowork_agents import (
    AgentFinding,
    AgentResult,
    ContextReference,
    agent_state,
    complete_delegation,
    create_delegation,
    invoke_agent_tool,
    start_delegation,
    stop_all_experts,
)
from backend.app.cowork_models import CoworkAgentInstance, CoworkDelegation
from backend.app.cowork_runtime import create_session
from backend.app.cowork_security import create_grant
from backend.app.database import Base
from backend.app.migrations import run_migrations


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _reference(source_id: str = "P1") -> ContextReference:
    return ContextReference(resource_type="paper", resource_id="1", source_id=source_id, label="Paper 1", evidence_scope="abstract")


def test_multi_agent_migration_is_incremental_and_declares_budget_columns():
    engine = create_engine("sqlite:///:memory:")
    completed = run_migrations(engine)
    assert "011_cowork_multi_agent" in completed
    assert {"cowork_agent_instances", "cowork_delegations"}.issubset(inspect(engine).get_table_names())
    columns = {item["name"] for item in inspect(engine).get_columns("cowork_sessions")}
    assert {"agent_token_budget", "agent_tokens_used", "max_parallel_agents", "delegation_budget"}.issubset(columns)


def test_expert_capability_is_strict_subset_and_budget_is_reserved():
    with Session(_engine()) as db:
        session = create_session(db, "核验论文证据")
        session.agent_token_budget = 2500
        create_grant(db, session.id, "paper", "1", can_read=True, can_write=False)
        first = create_delegation(db, session, role="literature_evidence", objective="检查 P1", context_refs=[_reference()], token_budget=2000)
        child = db.get(CoworkAgentInstance, first.child_agent_id)
        parent = db.get(CoworkAgentInstance, first.parent_agent_id)
        assert set(json.loads(child.allowed_tools_json)) < set(json.loads(parent.allowed_tools_json))
        with pytest.raises(ValueError, match="剩余预算"):
            create_delegation(db, session, role="experiment_analysis", objective="分析实验", context_refs=[], token_budget=1000)
        with pytest.raises(PermissionError, match="主协调"):
            create_delegation(db, session, role="research_synthesis", objective="越级委派", context_refs=[], token_budget=1000, parent_agent_id=child.id)


def test_structured_result_rejects_unassigned_sources_and_completion_is_idempotent():
    with Session(_engine()) as db:
        session = create_session(db, "形成证据报告")
        create_grant(db, session.id, "paper", "1", can_read=True, can_write=False)
        delegation = create_delegation(db, session, role="literature_evidence", objective="核验 P1", context_refs=[_reference()], token_budget=2000)
        start_delegation(db, delegation)
        start_delegation(db, delegation)
        invalid = AgentResult(summary="错误引用", findings=[AgentFinding(kind="paper_fact", statement="事实", source_ids=["P2"])])
        with pytest.raises(ValueError, match="未分配"):
            complete_delegation(db, delegation, invalid, tokens_used=200)
        valid = AgentResult(summary="仅摘要可支持该结论", findings=[AgentFinding(kind="author_claim", statement="作者在摘要中提出该方法", source_ids=["P1"])], limitations=["只有摘要"])
        complete_delegation(db, delegation, valid, tokens_used=200)
        complete_delegation(db, delegation, valid, tokens_used=200)
        assert session.agent_tokens_used == 200
        assert delegation.status == "completed"
        with pytest.raises(RuntimeError, match="不能用不同结果覆盖"):
            complete_delegation(db, delegation, AgentResult(summary="替换结果"), tokens_used=200)


def test_expert_context_must_be_inside_session_grants():
    with Session(_engine()) as db:
        session = create_session(db, "不能泄露未授权论文")
        with pytest.raises(PermissionError, match="未授权"):
            create_delegation(db, session, role="literature_evidence", objective="越权读取", context_refs=[_reference()], token_budget=1000)


def test_expert_tool_boundary_is_read_only_and_never_bypasses_approval():
    with Session(_engine()) as db:
        session = create_session(db, "搜索本地论文")
        delegation = create_delegation(db, session, role="literature_evidence", objective="搜索候选", context_refs=[], token_budget=1000)
        start_delegation(db, delegation)
        child = db.get(CoworkAgentInstance, delegation.child_agent_id)
        result = invoke_agent_tool(db, child, "library.search", {"query": "agent"})
        assert result["summary"].startswith("在学习库找到")
        with pytest.raises(PermissionError, match="未获此工具"):
            invoke_agent_tool(db, child, "notes.create_draft", {"title": "越权", "content": "x"})


def test_stop_all_cascades_to_agents_and_delegations_and_is_idempotent():
    with Session(_engine()) as db:
        session = create_session(db, "并行核验")
        first = create_delegation(db, session, role="literature_evidence", objective="文献", context_refs=[], token_budget=1000)
        second = create_delegation(db, session, role="experiment_analysis", objective="实验", context_refs=[], token_budget=1000)
        start_delegation(db, first)
        assert stop_all_experts(db, session) == 2
        assert stop_all_experts(db, session) == 0
        agents = db.scalars(select(CoworkAgentInstance).where(CoworkAgentInstance.parent_agent_id.is_not(None))).all()
        delegations = db.scalars(select(CoworkDelegation)).all()
        assert all(item.status == "cancelled" for item in agents)
        assert all(item.status == "cancelled" for item in delegations)
        state = agent_state(db, session)
        assert set(state) == {"supervisor_status", "max_parallel", "budget", "agents"}
        assert len(state["agents"]) == 2
