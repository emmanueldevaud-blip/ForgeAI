from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Date,
    func,
    Table,
    Column,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


# Association table for Occupancy <-> Occupant (many-to-many)
occupancy_occupants = Table(
    "occupancy_occupants",
    Base.metadata,
    Column("occupancy_id", Integer, ForeignKey("occupancies.id", ondelete="CASCADE"), primary_key=True, index=True),
    Column("occupant_id", Integer, ForeignKey("occupants.id", ondelete="CASCADE"), primary_key=True, index=True),
    Column("is_primary", Boolean, default=False, nullable=False),  # Primary occupant for communications
)


class Housing(Base):
    __tablename__ = "housings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    housing_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    beds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nb_rooms: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    bed_configuration: Mapped[str | None] = mapped_column(Text, nullable=True)
    room_names: Mapped[str | None] = mapped_column(Text, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_kitchen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_balcony: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    floor_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    room: Mapped["Room"] = relationship("Room", back_populates="housings")
    occupancies: Mapped[list["Occupancy"]] = relationship("Occupancy", back_populates="housing", cascade="all, delete-orphan")
    unavailabilities: Mapped[list["Unavailability"]] = relationship("Unavailability", back_populates="housing", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_housings_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Housing(id={self.id}, room_id={self.room_id})>"


class Occupant(Base):
    __tablename__ = "occupants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    id_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    id_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    occupancies: Mapped[list["Occupancy"]] = relationship("Occupancy", secondary="occupancy_occupants", back_populates="occupants")

    __table_args__ = (
        Index("ix_occupants_name", "last_name", "first_name"),
    )

    def __repr__(self) -> str:
        return f"<Occupant(id={self.id}, name={self.last_name} {self.first_name})>"


class Occupancy(Base):
    __tablename__ = "occupancies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    housing_id: Mapped[int] = mapped_column(ForeignKey("housings.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="pre_reserved", nullable=False, index=True)
    room_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arrival_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    departure_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_arrival: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(200), nullable=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    nb_persons: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    guest_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    housing: Mapped["Housing"] = relationship("Housing", back_populates="occupancies")
    occupants: Mapped[list["Occupant"]] = relationship("Occupant", secondary="occupancy_occupants", back_populates="occupancies")
    cleanings: Mapped[list["Cleaning"]] = relationship("Cleaning", back_populates="occupancy", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_occupancies_dates", "arrival_date", "departure_date"),
    )

    def __repr__(self) -> str:
        return f"<Occupancy(id={self.id}, housing_id={self.housing_id}, status={self.status})>"


class Unavailability(Base):
    __tablename__ = "housing_unavailabilities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    housing_id: Mapped[int] = mapped_column(ForeignKey("housings.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    housing: Mapped["Housing"] = relationship("Housing", back_populates="unavailabilities")

    __table_args__ = (
        Index("ix_housing_unavail_dates", "start_date", "end_date"),
    )

    def __repr__(self) -> str:
        return f"<Unavailability(id={self.id}, housing_id={self.housing_id}, reason={self.reason})>"


class HousingStatusHistory(Base):
    __tablename__ = "housing_status_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    housing_id: Mapped[int] = mapped_column(ForeignKey("housings.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_housing_status_history_housing", "housing_id", "changed_at"),
    )


class OccupancyStatusHistory(Base):
    __tablename__ = "occupancy_status_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occupancy_id: Mapped[int] = mapped_column(ForeignKey("occupancies.id", ondelete="CASCADE"), nullable=False, index=True)
    old_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_occupancy_status_history_occupancy", "occupancy_id", "changed_at"),
    )


# ============================================================
# CLEANING (Ménage de sortie)
# ============================================================

CLEANING_STATUSES = ["planned", "in_progress", "to_check", "checked", "completed", "cancelled"]
CLEANING_TYPES = ["exit", "intermediate", "deep"]


class Cleaning(Base):
    __tablename__ = "housing_cleanings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    housing_id: Mapped[int] = mapped_column(ForeignKey("housings.id", ondelete="CASCADE"), nullable=False, index=True)
    occupancy_id: Mapped[int | None] = mapped_column(ForeignKey("occupancies.id", ondelete="SET NULL"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(20), default="exit", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="planned", nullable=False, index=True)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scheduled_time_start: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM
    scheduled_time_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of checklist items
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    housing: Mapped["Housing"] = relationship("Housing")
    occupancy: Mapped[Optional["Occupancy"]] = relationship("Occupancy", back_populates="cleanings")
    assigned_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_to])

    __table_args__ = (
        Index("ix_cleanings_date_status", "scheduled_date", "status"),
        Index("ix_cleanings_housing_date", "housing_id", "scheduled_date"),
    )

    def __repr__(self) -> str:
        return f"<Cleaning(id={self.id}, housing_id={self.housing_id}, status={self.status})>"


# ============================================================
# EMAIL TEMPLATES
# ============================================================


class EmailTemplate(Base):
    __tablename__ = "housing_email_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    template_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "confirmation", "reminder", "custom"
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    attachments: Mapped[list["EmailTemplateAttachment"]] = relationship("EmailTemplateAttachment", back_populates="template", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_email_templates_type_active", "template_type", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<EmailTemplate(id={self.id}, name={self.name}, type={self.template_type})>"


class EmailTemplateAttachment(Base):
    __tablename__ = "housing_email_template_attachments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("housing_email_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    template: Mapped["EmailTemplate"] = relationship("EmailTemplate", back_populates="attachments")

    def __repr__(self) -> str:
        return f"<EmailTemplateAttachment(id={self.id}, template_id={self.template_id}, filename={self.filename})>"


# ============================================================
# EMAIL LOG
# ============================================================


class EmailLog(Base):
    __tablename__ = "housing_email_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("housing_email_templates.id", ondelete="SET NULL"), nullable=True)
    occupancy_id: Mapped[int | None] = mapped_column(ForeignKey("occupancies.id", ondelete="SET NULL"), nullable=True)
    recipient_email: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)  # pending, sent, failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_email_logs_occupancy", "occupancy_id"),
        Index("ix_email_logs_status_date", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<EmailLog(id={self.id}, to={self.recipient_email}, status={self.status})>"
