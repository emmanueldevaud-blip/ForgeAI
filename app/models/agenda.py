from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class AgendaPresence(Base):
    __tablename__ = "agenda_presences"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    presence_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), default="user", nullable=False
    )  # user | manual
    source_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_present: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    needs_workstation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    room: Mapped["Room"] = relationship("Room")
    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        # One presence row per user and per day (external rows have user_id NULL).
        UniqueConstraint("presence_date", "user_id", name="uq_agenda_presence_date_user"),
        Index("ix_agenda_presences_date_room", "presence_date", "room_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AgendaPresence(id={self.id}, date={self.presence_date}, "
            f"room_id={self.room_id}, user_id={self.user_id})>"
        )
