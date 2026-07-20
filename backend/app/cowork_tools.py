from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .cowork_models import CoworkApproval, ToolCall
from .cowork_security import has_object_permission, write_audit
from .models import LibraryEntry, Paper, PlannerTask, ResearchProject
from .note_models import Note
from .serializers import paper_dict


class StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchPapersArgs(StrictArguments):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=10, ge=1, le=25)


class ReadPaperArgs(StrictArguments):
    paper_id: int = Field(gt=0)


class SearchNotesArgs(StrictArguments):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=25)


class ReadNoteArgs(StrictArguments):
    note_id: int = Field(gt=0)


class SearchProjectsArgs(StrictArguments):
    query: str = Field(default="", max_length=500)
    limit: int = Field(default=10, ge=1, le=25)


class CreateTaskArgs(StrictArguments):
    title: str = Field(min_length=1, max_length=500)
    details: str = Field(default="", max_length=20_000)
    due_at: datetime | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    project_id: int | None = Field(default=None, gt=0)


class CreateNoteDraftArgs(StrictArguments):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(default="", max_length=100_000)
    project_id: int | None = Field(default=None, gt=0)


ArgsT = TypeVar("ArgsT", bound=StrictArguments)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments: type[StrictArguments]
    risk: Literal["low", "medium", "high", "critical"]
    permission: str | None
    approval: Literal["never", "write", "always"]
    handler: Callable[[Session, StrictArguments], dict[str, Any]]

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.arguments.model_json_schema(),
            "risk": self.risk,
            "permission": self.permission,
            "approval": self.approval,
        }


class ToolDenied(RuntimeError):
    pass


class ToolApprovalRequired(RuntimeError):
    def __init__(self, approval: CoworkApproval):
        self.approval = approval
        super().__init__("操作需要用户批准")


class CoworkToolRegistry:
    """Model-neutral, schema-validated boundary for PaperMorrow capabilities."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"工具重复注册: {spec.name}")
        self._tools[spec.name] = spec

    def list_tools(self) -> list[dict[str, Any]]:
        return [item.public_dict() for item in self._tools.values()]

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ValueError("未知工具") from exc

    def invoke(self, db: Session, session_id: str, name: str, arguments: dict[str, Any], *, approved: bool = False, page_scope: set[str] | None = None, step_id: int | None = None) -> dict[str, Any]:
        if approved:
            write_audit(db, "tool.approval_bypass_rejected", f"拒绝工具 {name} 的布尔审批旁路", session_id=session_id)
            db.flush()
            raise ToolDenied("不能通过 approved=True 执行工具；必须批准已冻结参数的 ToolCall")
        spec = self.get(name)
        try:
            parsed = spec.arguments.model_validate(arguments)
        except ValidationError as exc:
            write_audit(db, "tool.schema_rejected", f"工具 {name} 参数校验失败", session_id=session_id, details={"errors": exc.errors(include_input=False)})
            db.flush()
            raise

        resource_scope = self._resource_scope(spec, parsed)
        if spec.permission and not self._permitted(db, session_id, spec.permission, resource_scope, page_scope or set()):
            write_audit(db, "tool.permission_denied", f"工具 {name} 缺少最小权限", session_id=session_id, details={"resource_type": spec.permission, "scope": resource_scope})
            db.flush()
            raise ToolDenied("未获得读取该资料的权限")

        call = ToolCall(
            id=str(uuid.uuid4()), session_id=session_id, step_id=step_id, tool_name=name,
            arguments_summary_json=json.dumps(arguments, ensure_ascii=False), risk_level=spec.risk,
            approval_status="approved" if approved else ("pending" if spec.approval != "never" else "not_required"),
            status="pending",
        )
        db.add(call); db.flush()
        if spec.approval != "never" and not approved:
            approval = CoworkApproval(
                id=str(uuid.uuid4()), session_id=session_id, tool_call_id=call.id,
                action_summary=f"运行 {name}", impact_summary=self._impact(spec, parsed),
                reason="该操作会写入或改变 PaperMorrow 数据", reversible=True,
                destination="仅本机 PaperMorrow",
            )
            db.add(approval); db.flush()
            write_audit(db, "tool.approval_requested", f"工具 {name} 等待审批", session_id=session_id, details={"tool_call_id": call.id, "approval_id": approval.id})
            raise ToolApprovalRequired(approval)

        call.status = "running"; call.started_at = datetime.now(timezone.utc)
        try:
            result = spec.handler(db, parsed)
            call.status = "completed"; call.result_json = json.dumps(result, ensure_ascii=False, default=str)
            call.user_summary = str(result.get("summary") or "工具执行完成")
            write_audit(db, "tool.completed", f"工具 {name} 执行完成", session_id=session_id, details={"tool_call_id": call.id, "result_summary": call.user_summary})
            return {"tool_call_id": call.id, **result}
        except Exception as exc:
            call.status = "failed"; call.error = str(exc)[:2000]
            write_audit(db, "tool.failed", f"工具 {name} 执行失败", session_id=session_id, details={"tool_call_id": call.id, "error": str(exc)})
            raise
        finally:
            call.finished_at = datetime.now(timezone.utc)
            db.flush()

    @staticmethod
    def _resource_scope(spec: ToolSpec, args: StrictArguments) -> str:
        values = args.model_dump()
        for key in ("paper_id", "note_id", "project_id"):
            if values.get(key):
                return str(values[key])
        return "*"

    @staticmethod
    def _permitted(db: Session, session_id: str, resource_type: str, scope: str, page_scope: set[str]) -> bool:
        key = f"{resource_type}:{scope}"
        return key in page_scope or has_object_permission(db, session_id, resource_type, scope) or has_object_permission(db, session_id, resource_type, "*")

    @staticmethod
    def _impact(spec: ToolSpec, args: StrictArguments) -> str:
        values = args.model_dump()
        if spec.name == "notes.create_draft":
            return f"新建可恢复的 Markdown 草稿《{values['title']}》"
        if spec.name == "planner.create_task":
            return f"新建待办“{values['title']}”"
        return f"调用 {spec.name}"


def _search_papers(db: Session, args: SearchPapersArgs) -> dict[str, Any]:
    pattern = f"%{args.query.strip()}%"
    items = db.scalars(select(Paper).join(LibraryEntry).where(or_(Paper.title_en.ilike(pattern), Paper.title_zh.ilike(pattern), Paper.abstract_en.ilike(pattern), Paper.doi.ilike(pattern), Paper.arxiv_id.ilike(pattern))).limit(args.limit)).unique().all()
    return {"summary": f"在学习库找到 {len(items)} 篇论文", "items": [{"id": item.id, "title": item.title_en, "doi": item.doi, "arxiv_id": item.arxiv_id, "source_scope": "abstract" if item.abstract_en else "metadata"} for item in items]}


def _read_paper(db: Session, args: ReadPaperArgs) -> dict[str, Any]:
    item = db.get(Paper, args.paper_id)
    if not item or not item.library_entry:
        raise ValueError("学习库论文不存在")
    data = paper_dict(item)
    return {"summary": f"已读取论文《{item.title_en}》", "item": {"id": item.id, "title": item.title_en, "abstract": item.abstract_en, "authors": data.get("authors", []), "doi": item.doi, "arxiv_id": item.arxiv_id, "evidence_scope": "abstract" if item.abstract_en else "metadata"}}


def _search_notes(db: Session, args: SearchNotesArgs) -> dict[str, Any]:
    pattern = f"%{args.query.strip()}%"
    items = db.scalars(select(Note).where(or_(Note.title.ilike(pattern), Note.content.ilike(pattern))).order_by(Note.updated_at.desc()).limit(args.limit)).all()
    return {"summary": f"找到 {len(items)} 篇授权范围内候选笔记", "items": [{"id": item.id, "title": item.title, "updated_at": item.updated_at.isoformat()} for item in items]}


def _read_note(db: Session, args: ReadNoteArgs) -> dict[str, Any]:
    item = db.get(Note, args.note_id)
    if not item:
        raise ValueError("笔记不存在")
    return {"summary": f"已读取笔记《{item.title}》", "item": {"id": item.id, "title": item.title, "content": item.content, "project_id": item.project_id}}


def _search_projects(db: Session, args: SearchProjectsArgs) -> dict[str, Any]:
    statement = select(ResearchProject)
    if args.query.strip():
        pattern = f"%{args.query.strip()}%"
        statement = statement.where(or_(ResearchProject.title.ilike(pattern), ResearchProject.research_question.ilike(pattern)))
    items = db.scalars(statement.order_by(ResearchProject.updated_at.desc()).limit(args.limit)).all()
    return {"summary": f"找到 {len(items)} 个项目", "items": [{"id": item.id, "title": item.title, "research_question": item.research_question} for item in items]}


def _create_task(db: Session, args: CreateTaskArgs) -> dict[str, Any]:
    item = PlannerTask(**args.model_dump())
    db.add(item); db.flush()
    return {"summary": f"已创建待办“{item.title}”", "item": {"id": item.id, "title": item.title, "status": item.status}, "undo": {"action": "delete_draft", "object_type": "planner_task", "object_id": item.id}}


def _create_note(db: Session, args: CreateNoteDraftArgs) -> dict[str, Any]:
    item = Note(title=args.title, content=args.content, project_id=args.project_id, origin="standalone", document_format="markdown")
    db.add(item); db.flush()
    return {"summary": f"已创建 Markdown 草稿《{item.title}》", "item": {"id": item.id, "title": item.title}, "undo": {"action": "delete_draft", "object_type": "note", "object_id": item.id}}


def build_default_registry() -> CoworkToolRegistry:
    registry = CoworkToolRegistry()
    registry.register(ToolSpec("library.search", "仅搜索本机学习库；外部文本只作为不可信资料返回。", SearchPapersArgs, "low", None, "never", _search_papers))
    registry.register(ToolSpec("library.read_paper", "读取一篇已授权学习库论文的元数据和可用摘要。", ReadPaperArgs, "low", "paper", "never", _read_paper))
    registry.register(ToolSpec("notes.search", "搜索用户明确授权的笔记范围。", SearchNotesArgs, "low", "note", "never", _search_notes))
    registry.register(ToolSpec("notes.read", "读取一篇明确授权的笔记。", ReadNoteArgs, "low", "note", "never", _read_note))
    registry.register(ToolSpec("projects.search", "搜索用户明确授权的研究项目。", SearchProjectsArgs, "low", "project", "never", _search_projects))
    registry.register(ToolSpec("planner.create_task", "预览并创建一个可恢复待办。", CreateTaskArgs, "medium", None, "write", _create_task))
    registry.register(ToolSpec("notes.create_draft", "预览并创建一篇 Markdown 草稿，不覆盖现有文件。", CreateNoteDraftArgs, "medium", None, "write", _create_note))
    return registry


DEFAULT_REGISTRY = build_default_registry()
