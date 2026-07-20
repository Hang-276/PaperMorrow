from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .cowork_models import CoworkMessage, CoworkSession, CoworkStep, CoworkTask
from .cowork_security import write_audit
from .llm import LLMClient, LLMNotConfigured


TERMINAL_STATUSES = {"completed", "cancelled", "failed"}


def create_session(db: Session, goal: str, *, title: str = "", response_detail: str = "rich", thinking_effort: str = "medium") -> CoworkSession:
    goal = goal.strip()
    session = CoworkSession(
        id=str(uuid.uuid4()), title=(title.strip() or goal[:46] or "新研究任务"), goal=goal,
        response_detail=response_detail, thinking_effort=thinking_effort, status="draft",
    )
    db.add(session); db.flush()
    write_audit(db, "session.created", "创建 Cowork 会话", session_id=session.id, actor="user")
    if goal:
        add_message(db, session.id, "user", goal)
        create_plan(db, session)
    return session


def add_message(db: Session, session_id: str, role: str, text: str, *, sources: list[dict] | None = None, blocks: list[dict] | None = None) -> CoworkMessage:
    content_blocks = blocks or [{"type": "markdown", "text": text}]
    message = CoworkMessage(session_id=session_id, role=role, content_blocks_json=json.dumps(content_blocks, ensure_ascii=False), sources_json=json.dumps(sources or [], ensure_ascii=False))
    db.add(message); db.flush()
    return message


def create_plan(db: Session, session: CoworkSession) -> CoworkTask:
    existing = db.scalar(select(CoworkTask).where(CoworkTask.session_id == session.id))
    if existing:
        return existing
    task = CoworkTask(session_id=session.id, title=session.goal[:180] or "研究协作任务", status="planned")
    db.add(task); db.flush()
    steps = [
        ("确认目标与资料边界", "核对交付物、允许读取的对象和禁止操作。"),
        ("检索最小必要上下文", "只检索用户选择的论文、笔记、项目或文件。"),
        ("分析证据并形成草稿", "区分论文事实、作者主张、用户记录和 AI 推断。"),
        ("生成并验证产物", "对写入、导入或外部调用先展示预览并等待审批。"),
        ("汇总来源与未完成项", "给出产物、来源、限制和建议下一步。"),
    ]
    for position, (title, description) in enumerate(steps, start=1):
        db.add(CoworkStep(task_id=task.id, position=position, title=title, description=description, depends_on_json=json.dumps([position - 1] if position > 1 else [])))
    session.status = "planned"
    write_audit(db, "plan.created", "创建 5 步可编辑研究计划", session_id=session.id, details={"task_id": task.id})
    return task


async def run_next_step(db: Session, session: CoworkSession) -> CoworkStep | None:
    if session.stop_requested or session.status == "cancelled":
        raise RuntimeError("任务已停止")
    task = db.scalar(select(CoworkTask).where(CoworkTask.session_id == session.id).order_by(CoworkTask.id.desc())) or create_plan(db, session)
    step = db.scalar(select(CoworkStep).where(CoworkStep.task_id == task.id, CoworkStep.status.in_(["pending", "failed"])).order_by(CoworkStep.position))
    if not step:
        task.status = session.status = "completed"
        add_message(db, session.id, "assistant", "任务计划已完成。请在产物与来源区核对结果；未执行的外部操作不会被视为完成。")
        return None
    step.status = "running"; step.started_at = datetime.now(timezone.utc); session.status = task.status = "running"
    db.flush()
    if session.stop_requested:
        step.status = "cancelled"; session.status = "cancelled"
        return step
    if step.position == 1:
        step.result_summary = "目标已记录；默认拒绝读取未授权资料。"
        add_message(db, session.id, "assistant", "我已建立可编辑计划。开始前请在顶部授权本任务真正需要的论文、笔记、项目或文件夹；未授权资料不会被读取。")
    elif step.position == 2:
        step.result_summary = "等待用户选择资料或通过工具检索授权范围。"
        add_message(db, session.id, "assistant", "资料检索只会覆盖当前授权范围。你可以先添加资料，或让我搜索学习库中的候选论文。")
    else:
        client = LLMClient(db)
        if not client.configured:
            step.status = "paused"; session.status = "paused"
            step.result_summary = "未配置模型，已可靠暂停；计划、权限和历史均已保存。"
            add_message(db, session.id, "assistant", "当前没有可用的 LLM Profile。我已安全暂停任务，没有调用网络或工具；配置模型后可从此检查点继续。")
            return step
        context = _bounded_context(db, session.id)
        answer = await client.chat_about_workspace("AI 协作", context, [{"role": "user", "content": f"研究目标：{session.goal}\n当前步骤：{step.title}\n请只基于已提供上下文推进并说明证据限制。"}], session.response_detail)
        add_message(db, session.id, "assistant", answer)
        step.result_summary = answer[:500]
    step.status = "completed"; step.finished_at = datetime.now(timezone.utc)
    write_audit(db, "step.completed", f"完成步骤：{step.title}", session_id=session.id, details={"step_id": step.id})
    next_step = db.scalar(select(CoworkStep).where(CoworkStep.task_id == task.id, CoworkStep.status == "pending"))
    if not next_step:
        task.status = session.status = "completed"
    return step


def pause_session(db: Session, session: CoworkSession) -> None:
    if session.status not in TERMINAL_STATUSES:
        session.status = "paused"
        write_audit(db, "session.paused", "暂停 Cowork 任务", session_id=session.id, actor="user")


def resume_session(db: Session, session: CoworkSession) -> None:
    if session.status == "cancelled":
        raise RuntimeError("已取消任务不能继续；请新建会话")
    session.stop_requested = False; session.status = "planned"
    for step in db.scalars(select(CoworkStep).join(CoworkTask).where(CoworkTask.session_id == session.id, CoworkStep.status == "paused")).all():
        step.status = "pending"
    write_audit(db, "session.resumed", "从检查点继续 Cowork 任务", session_id=session.id, actor="user")


def cancel_session(db: Session, session: CoworkSession) -> None:
    session.stop_requested = True; session.status = "cancelled"
    for step in db.scalars(select(CoworkStep).join(CoworkTask).where(CoworkTask.session_id == session.id, CoworkStep.status.in_(["pending", "running", "paused"]))).all():
        step.status = "cancelled"; step.finished_at = datetime.now(timezone.utc)
    write_audit(db, "session.cancelled", "立即停止 Cowork 任务", session_id=session.id, actor="user")


def retry_step(db: Session, session: CoworkSession, step: CoworkStep) -> None:
    if step.retry_count >= 2:
        raise RuntimeError("该步骤已达到最大重试次数")
    if step.status not in {"failed", "paused", "cancelled"}:
        raise RuntimeError("只有失败、暂停或取消的步骤可以重试")
    session.stop_requested = False; session.status = "planned"
    step.status = "pending"; step.retry_count += 1; step.error = None; step.finished_at = None


def _bounded_context(db: Session, session_id: str) -> str:
    messages = db.scalars(select(CoworkMessage).where(CoworkMessage.session_id == session_id).order_by(CoworkMessage.id.desc()).limit(12)).all()
    parts = []
    for item in reversed(messages):
        blocks = json.loads(item.content_blocks_json or "[]")
        text = "\n".join(str(block.get("text") or "") for block in blocks if block.get("type") in {"text", "markdown"})
        parts.append(f"{item.role}: {text[:4000]}")
    return "\n\n".join(parts)[-40_000:]
