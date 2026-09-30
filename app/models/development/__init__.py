"""Modèles de données de l'Agent Développement."""

from __future__ import annotations

import json
import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class DevelopmentTaskStatus(str, enum.Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    DEVELOPING = "developing"
    TESTING = "testing"
    FIXING = "fixing"
    READY_FOR_REVIEW = "ready_for_review"
    COMMITTED = "committed"
    PUSHED = "pushed"
    DEPLOYED = "deployed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DevelopmentTask(Base):
    """Tâche de développement persistée."""

    __tablename__ = "development_tasks"
    __table_args__ = (
        Index("ix_development_tasks_user_status", "user_id", "status"),
        Index("ix_development_tasks_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    request: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DevelopmentTaskStatus] = mapped_column(
        Enum(DevelopmentTaskStatus, native_enum=False, length=30),
        nullable=False,
        default=DevelopmentTaskStatus.PENDING,
        index=True,
    )
    branch: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    repository: Mapped[str] = mapped_column(String(500), nullable=False, default=".")
    opencode_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    modified_files: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    diff_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    commit_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    push_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    deployment_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    current_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="development_tasks")
    executions: Mapped[list["DevelopmentAgentExecution"]] = relationship(
        "DevelopmentAgentExecution", back_populates="task", cascade="all, delete-orphan"
    )


class DevelopmentAgentExecution(Base):
    """Trace d'une exécution de l'Agent Développement."""

    __tablename__ = "development_agent_executions"
    __table_args__ = (
        Index("ix_development_agent_executions_task", "task_id"),
        Index("ix_development_agent_executions_started", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("development_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    step_count: Mapped[int] = mapped_column(default=0)
    steps_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["DevelopmentTask"] = relationship("DevelopmentTask", back_populates="executions")