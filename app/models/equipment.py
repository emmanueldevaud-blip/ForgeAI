from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class EquipmentType(Base):
    __tablename__ = "equipment_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    equipments: Mapped[list["Equipment"]] = relationship("Equipment", back_populates="equipment_type")

    __table_args__ = (
        Index("ix_equipment_types_code_active", "code", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<EquipmentType(code={self.code}, name={self.name})>"


class Equipment(Base):
    __tablename__ = "equipments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_type_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_types.id", ondelete="SET NULL"), nullable=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    installation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    commissioning_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    warranty_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="en_service", index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    equipment_type: Mapped[Optional["EquipmentType"]] = relationship("EquipmentType", back_populates="equipments")
    room: Mapped["Room"] = relationship("Room", back_populates="equipments")

    __table_args__ = (
        Index("ix_equipments_type_active", "equipment_type_id", "is_active"),
        Index("ix_equipments_room_active", "room_id", "is_active"),
        Index("ix_equipments_status_active", "status", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Equipment(reference={self.reference}, name={self.name})>"
