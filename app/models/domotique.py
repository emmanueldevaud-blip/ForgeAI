"""Modeles du module Domotique (supervision d'installations domotiques).

Architecture generique : chaque installation est un DomotiqueDevice
(premier device : le sechoir a saucisson, pilote par Raspberry Pi en
passerelle pure : sonde I2C temperature/humidite + 8 sorties GPIO).
"""
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum as PyEnum

from app.db.session import Base


class DeviceStatus(str, PyEnum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


class OutputMode(str, PyEnum):
    AUTO = "auto"
    MANUAL = "manual"


class CycleStatus(str, PyEnum):
    PREPARING = "preparing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ERROR = "error"


class ExitCondition(str, PyEnum):
    TIME = "time"
    WEIGHT = "weight"
    MANUAL = "manual"


def _empty_dict() -> dict[str, Any]:
    return {}


class DomotiqueDevice(Base):
    __tablename__ = "domotique_devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), default="dryer", nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    poll_interval_s: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    status: Mapped[str] = mapped_column(
        SQLEnum(DeviceStatus, native_enum=False, length=20),
        default=DeviceStatus.UNKNOWN,
        nullable=False,
    )
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=_empty_dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    sensors: Mapped[list["DomotiqueSensor"]] = relationship(
        "DomotiqueSensor", back_populates="device", cascade="all, delete-orphan"
    )
    outputs: Mapped[list["DomotiqueOutput"]] = relationship(
        "DomotiqueOutput", back_populates="device", cascade="all, delete-orphan"
    )
    cycles: Mapped[list["DomotiqueCycle"]] = relationship(
        "DomotiqueCycle", back_populates="device"
    )


class DomotiqueSensor(Base):
    __tablename__ = "domotique_sensors"
    __table_args__ = (UniqueConstraint("device_id", "key", name="uq_domotique_sensor_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("domotique_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device: Mapped["DomotiqueDevice"] = relationship("DomotiqueDevice", back_populates="sensors")
    readings: Mapped[list["DomotiqueSensorReading"]] = relationship(
        "DomotiqueSensorReading", back_populates="sensor", cascade="all, delete-orphan"
    )


class DomotiqueSensorReading(Base):
    __tablename__ = "domotique_sensor_readings"
    __table_args__ = (
        Index("ix_domotique_readings_sensor_recorded", "sensor_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("domotique_sensors.id", ondelete="CASCADE"), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sensor: Mapped["DomotiqueSensor"] = relationship("DomotiqueSensor", back_populates="readings")


class DomotiqueOutput(Base):
    __tablename__ = "domotique_outputs"
    __table_args__ = (UniqueConstraint("device_id", "index", name="uq_domotique_output_index"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("domotique_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="other", nullable=False)
    mode: Mapped[str] = mapped_column(
        SQLEnum(OutputMode, native_enum=False, length=10),
        default=OutputMode.AUTO,
        nullable=False,
    )
    state: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    device: Mapped["DomotiqueDevice"] = relationship("DomotiqueDevice", back_populates="outputs")


class DomotiqueProfile(Base):
    __tablename__ = "domotique_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_weight_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_loss_min_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_loss_max_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    phases: Mapped[list["DomotiquePhase"]] = relationship(
        "DomotiquePhase",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="DomotiquePhase.order",
        lazy="selectin",
    )
    cycles: Mapped[list["DomotiqueCycle"]] = relationship("DomotiqueCycle", back_populates="profile")


class DomotiquePhase(Base):
    __tablename__ = "domotique_phases"
    __table_args__ = (UniqueConstraint("profile_id", "order", name="uq_domotique_phase_order"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("domotique_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    tolerance_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    tolerance_humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_loss_target_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_condition: Mapped[str] = mapped_column(
        SQLEnum(ExitCondition, native_enum=False, length=10),
        default=ExitCondition.TIME,
        nullable=False,
    )

    profile: Mapped["DomotiqueProfile"] = relationship("DomotiqueProfile", back_populates="phases")


class DomotiqueCycle(Base):
    __tablename__ = "domotique_cycles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("domotique_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("domotique_profiles.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    product: Mapped[str | None] = mapped_column(String(100), nullable=True)
    casing_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        SQLEnum(CycleStatus, native_enum=False, length=20),
        default=CycleStatus.PREPARING,
        nullable=False,
        index=True,
    )
    current_phase_id: Mapped[int | None] = mapped_column(ForeignKey("domotique_phases.id", ondelete="SET NULL"), nullable=True)
    phase_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    initial_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_weight_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    manual_outputs: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=_empty_dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    device: Mapped["DomotiqueDevice"] = relationship("DomotiqueDevice", back_populates="cycles")
    profile: Mapped["DomotiqueProfile"] = relationship(
        "DomotiqueProfile", back_populates="cycles", lazy="selectin"
    )
    events: Mapped[list["DomotiqueEvent"]] = relationship(
        "DomotiqueEvent", back_populates="cycle", cascade="all, delete-orphan"
    )

    @property
    def weight_loss_pct(self) -> float | None:
        if not self.initial_weight or self.initial_weight <= 0 or self.current_weight is None:
            return None
        return round(((self.initial_weight - self.current_weight) / self.initial_weight) * 100, 2)


class DomotiqueEvent(Base):
    __tablename__ = "domotique_events"
    __table_args__ = (
        Index("ix_domotique_events_device_created", "device_id", "created_at"),
        Index("ix_domotique_events_cycle_created", "cycle_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("domotique_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("domotique_cycles.id", ondelete="CASCADE"), nullable=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=_empty_dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cycle: Mapped["DomotiqueCycle | None"] = relationship("DomotiqueCycle", back_populates="events")
