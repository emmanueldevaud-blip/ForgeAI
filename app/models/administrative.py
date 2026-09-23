from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class AdministrativeCapability(Base):
    __tablename__ = "administrative_capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    volunteers: Mapped[list["VolunteerCapability"]] = relationship(back_populates="capability")
    roles: Mapped[list["AdministrativeRoleType"]] = relationship(back_populates="required_capability")


class VolunteerCapability(Base):
    __tablename__ = "administrative_volunteer_capabilities"

    volunteer_id: Mapped[int] = mapped_column(ForeignKey("volunteers.id", ondelete="CASCADE"), primary_key=True)
    capability_id: Mapped[int] = mapped_column(ForeignKey("administrative_capabilities.id", ondelete="CASCADE"), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    volunteer: Mapped["Volunteer"] = relationship()
    capability: Mapped[AdministrativeCapability] = relationship(back_populates="volunteers")


class VolunteerUnavailability(Base):
    __tablename__ = "administrative_volunteer_unavailabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    volunteer_id: Mapped[int] = mapped_column(ForeignKey("volunteers.id", ondelete="CASCADE"), nullable=False, index=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    volunteer: Mapped["Volunteer"] = relationship()


class AdministrativeProgramType(Base):
    __tablename__ = "administrative_program_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), default="weekly", nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    interval: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    roles: Mapped[list["AdministrativeRoleType"]] = relationship(back_populates="program_type", cascade="all, delete-orphan")
    sessions: Mapped[list["AdministrativeMonthlySession"]] = relationship(back_populates="program_type")


class AdministrativeRoleType(Base):
    __tablename__ = "administrative_role_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_type_id: Mapped[int] = mapped_column(ForeignKey("administrative_program_types.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    required_capability_id: Mapped[int | None] = mapped_column(ForeignKey("administrative_capabilities.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    program_type: Mapped[AdministrativeProgramType] = relationship(back_populates="roles")
    required_capability: Mapped[AdministrativeCapability | None] = relationship(back_populates="roles")

    __table_args__ = (UniqueConstraint("program_type_id", "code", name="uq_administrative_role_type_code"),)


class AdministrativeMonthlySession(Base):
    __tablename__ = "administrative_monthly_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_type_id: Mapped[int] = mapped_column(ForeignKey("administrative_program_types.id", ondelete="RESTRICT"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    program_type: Mapped[AdministrativeProgramType] = relationship(back_populates="sessions")
    assignments: Mapped[list["AdministrativeAssignment"]] = relationship(back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("program_type_id", "year", "month", name="uq_administrative_session_month"),)


class AdministrativeAssignment(Base):
    __tablename__ = "administrative_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("administrative_monthly_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role_type_id: Mapped[int] = mapped_column(ForeignKey("administrative_role_types.id", ondelete="RESTRICT"), nullable=False)
    volunteer_id: Mapped[int] = mapped_column(ForeignKey("volunteers.id", ondelete="RESTRICT"), nullable=False, index=True)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    session: Mapped[AdministrativeMonthlySession] = relationship(back_populates="assignments")
    role_type: Mapped[AdministrativeRoleType] = relationship()
    volunteer: Mapped["Volunteer"] = relationship()

    __table_args__ = (
        UniqueConstraint("session_id", "role_type_id", "scheduled_date", name="uq_administrative_assignment_role_date"),
        Index("ix_administrative_assignment_volunteer_session", "volunteer_id", "session_id"),
    )
