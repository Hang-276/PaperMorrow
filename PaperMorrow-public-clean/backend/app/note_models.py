from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .models import utcnow


class Note(Base):
    """Canonical note shared by the paper reader and the standalone notebook."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="未命名笔记")
    content: Mapped[str] = mapped_column(Text, default="")
    document_format: Mapped[str] = mapped_column(String(16), default="markdown", index=True)
    editor_mode: Mapped[str] = mapped_column(String(16), default="standard")
    origin: Mapped[str] = mapped_column(String(16), default="standalone", index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    legacy_paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)

    paper_links: Mapped[list["NotePaperLink"]] = relationship(back_populates="note", cascade="all, delete-orphan")
    artifacts: Mapped[list["NoteArtifact"]] = relationship(back_populates="note", cascade="all, delete-orphan")


class NotePaperLink(Base):
    __tablename__ = "note_paper_links"
    __table_args__ = (UniqueConstraint("note_id", "paper_id", name="uq_note_paper_link"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    citation_key: Mapped[str] = mapped_column(String(120), default="")
    locator: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    note: Mapped[Note] = relationship(back_populates="paper_links")


class NoteArtifact(Base):
    __tablename__ = "note_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="completed")
    content: Mapped[str] = mapped_column(Text, default="")
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    note: Mapped[Note] = relationship(back_populates="artifacts")
