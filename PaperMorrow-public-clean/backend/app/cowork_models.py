from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .models import utcnow


class CoworkSession(Base):
    __tablename__ = "cowork_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="新研究任务")
    goal: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    model_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str] = mapped_column(String(160), default="")
    response_detail: Mapped[str] = mapped_column(String(16), default="rich")
    thinking_effort: Mapped[str] = mapped_column(String(16), default="medium")
    context_summary: Mapped[str] = mapped_column(Text, default="")
    stop_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list["CoworkMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    tasks: Mapped[list["CoworkTask"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    grants: Mapped[list["PermissionGrant"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class CoworkMessage(Base):
    __tablename__ = "cowork_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("cowork_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content_blocks_json: Mapped[str] = mapped_column(Text, default="[]")
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    attachments_json: Mapped[str] = mapped_column(Text, default="[]")
    tool_calls_json: Mapped[str] = mapped_column(Text, default="[]")
    approval_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    session: Mapped[CoworkSession] = relationship(back_populates="messages")


class CoworkTask(Base):
    __tablename__ = "cowork_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("cowork_sessions.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(24), default="planned", index=True)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    session: Mapped[CoworkSession] = relationship(back_populates="tasks")
    steps: Mapped[list["CoworkStep"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class CoworkStep(Base):
    __tablename__ = "cowork_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("cowork_tasks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    depends_on_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint_json: Mapped[str] = mapped_column(Text, default="{}")
    result_summary: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[CoworkTask] = relationship(back_populates="steps")


class PermissionGrant(Base):
    __tablename__ = "cowork_permission_grants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("cowork_sessions.id", ondelete="CASCADE"), index=True)
    resource_type: Mapped[str] = mapped_column(String(40), index=True)
    resource_scope: Mapped[str] = mapped_column(Text)
    normalized_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    can_read: Mapped[bool] = mapped_column(Boolean, default=False)
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)
    duration: Mapped[str] = mapped_column(String(16), default="session")
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[CoworkSession] = relationship(back_populates="grants")


class ToolCall(Base):
    __tablename__ = "cowork_tool_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("cowork_sessions.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[int | None] = mapped_column(ForeignKey("cowork_steps.id", ondelete="SET NULL"), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(160), index=True)
    arguments_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    approval_status: Mapped[str] = mapped_column(String(24), default="not_required", index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    user_summary: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    undo_hint_json: Mapped[str] = mapped_column(Text, default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CoworkApproval(Base):
    __tablename__ = "cowork_approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("cowork_sessions.id", ondelete="CASCADE"), index=True)
    tool_call_id: Mapped[str] = mapped_column(ForeignKey("cowork_tool_calls.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    action_summary: Mapped[str] = mapped_column(Text)
    impact_summary: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    reversible: Mapped[bool] = mapped_column(Boolean, default=False)
    destination: Mapped[str] = mapped_column(Text, default="仅本机")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CoworkArtifact(Base):
    __tablename__ = "cowork_artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("cowork_sessions.id", ondelete="CASCADE"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(500))
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SkillManifest(Base):
    __tablename__ = "cowork_skill_manifests"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_cowork_skill_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(40))
    entrypoint: Mapped[str] = mapped_column(Text)
    allowed_tools_json: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(Text, default="builtin")
    license: Mapped[str] = mapped_column(String(120), default="PaperMorrow built-in")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    checksum: Mapped[str] = mapped_column(String(128), default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CoworkAuditLog(Base):
    __tablename__ = "cowork_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("cowork_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor: Mapped[str] = mapped_column(String(24), default="system")
    summary: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
