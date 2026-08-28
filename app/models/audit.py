from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String,
    DateTime,
    ForeignKey,
    func,
    Index,
    Text,
    JSON,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    object_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    object_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    object_repr: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    old_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("ix_audit_logs_user_module_created", "user_id", "module", "created_at"),
        Index("ix_audit_logs_module_action_created", "module", "action", "created_at"),
        Index("ix_audit_logs_object", "object_type", "object_id"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(user={self.username}, action={self.action}, module={self.module})>"