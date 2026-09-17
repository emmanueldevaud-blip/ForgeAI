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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Housing(Base):
    __tablename__ = "housings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    housing_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    beds: Mapped[int | None] = mapped_column(Integer, nullable=True)
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

    occupancies: Mapped[list["Occupancy"]] = relationship("Occupancy", back_populates="occupant")

    __table_args__ = (
        Index("ix_occupants_name", "last_name", "first_name"),
    )

    def __repr__(self) -> str:
        return f"<Occupant(id={self.id}, name={self.last_name} {self.first_name})>"


class Occupancy(Base):
    __tablename__ = "occupancies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    housing_id: Mapped[int] = mapped_column(ForeignKey("housings.id", ondelete="CASCADE"), nullable=False, index=True)
    occupant_id: Mapped[int] = mapped_column(ForeignKey("occupants.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="pre_reserved", nullable=False, index=True)
    arrival_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    departure_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_arrival: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(200), nullable=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    nb_persons: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    housing: Mapped["Housing"] = relationship("Housing", back_populates="occupancies")
    occupant: Mapped["Occupant"] = relationship("Occupant", back_populates="occupancies")

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
