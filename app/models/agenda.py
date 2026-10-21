from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class AgendaPresence(Base):
    __tablename__ = "agenda_presences"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    presence_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # NULL = télétravail : présence sans local (invariant : room_id NULL <=> is_remote).
    room_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), nullable=True, index=True
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
    needs_meal: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=false()
    )
    # Télétravail : présence hors local (room_id NULL), sans poste ni repas.
    is_remote: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=false()
    )
    # full = journée entière | morning = matin | afternoon = après-midi
    period: Mapped[str] = mapped_column(
        String(10), default="full", nullable=False, server_default="full"
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    room: Mapped[Optional["Room"]] = relationship("Room")
    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        # One presence row per user, per day and per room.
        UniqueConstraint(
            "presence_date",
            "user_id",
            "room_id",
            name="uq_agenda_presence_date_user_room",
        ),
        Index("ix_agenda_presences_date_room", "presence_date", "room_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AgendaPresence(id={self.id}, date={self.presence_date}, "
            f"room_id={self.room_id}, user_id={self.user_id})>"
        )


class AgendaImportBatch(Base):
    __tablename__ = "agenda_import_batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="analyzed", nullable=False)
    uploaded_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    rows_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_ready: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_needs_review: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_skipped_existing: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_excluded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    week_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    week_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    staged_rows: Mapped[list["AgendaImportStagedRow"]] = relationship(
        "AgendaImportStagedRow",
        back_populates="batch",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AgendaImportBatch(reference={self.reference}, status={self.status})>"


class AgendaImportStagedRow(Base):
    __tablename__ = "agenda_import_staged_rows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("agenda_import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sheet_name: Mapped[str] = mapped_column(String(100), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    presence_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(10), default="full", nullable=False)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    raw_label: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    room_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True, index=True
    )
    site_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    needs_workstation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_meal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="ready", nullable=False)
    review_reason: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    suggestions: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)

    created_presence_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    batch: Mapped[AgendaImportBatch] = relationship("AgendaImportBatch", back_populates="staged_rows")

    def __repr__(self) -> str:
        return f"<AgendaImportStagedRow(batch={self.batch_id}, line={self.line_number}, date={self.presence_date})>"
