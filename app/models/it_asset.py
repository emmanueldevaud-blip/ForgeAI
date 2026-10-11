from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, List

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
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

from app.db.session import Base


class ITAssetType(str, PyEnum):
    PC_WINDOWS = "pc_windows"
    PC_LINUX = "pc_linux"
    SERVER = "server"
    PRINTER = "printer"
    SWITCH = "switch"
    ROUTER = "router"
    FIREWALL = "firewall"
    ACCESS_POINT = "access_point"
    OTHER = "other"


class ITAssetStatus(str, PyEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    MAINTENANCE = "maintenance"


class DiscoverySource(str, PyEnum):
    MANUAL = "manual"
    SNMP = "snmp"
    AGENT = "agent"
    AD = "ad"
    MESHCENTRAL = "meshcentral"
    NETWORK_SCAN = "network_scan"


class ITAlertSeverity(str, PyEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ITAlertType(str, PyEnum):
    STATUS_CHANGE = "status_change"
    UNREACHABLE = "unreachable"
    HIGH_LATENCY = "high_latency"
    SNMP_ERROR = "snmp_error"
    AGENT_SILENT = "agent_silent"
    NEW_ASSET = "new_asset"
    IP_CONFLICT = "ip_conflict"
    MAC_CONFLICT = "mac_conflict"


class ITAsset(Base):
    __tablename__ = "it_assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asset_type: Mapped[ITAssetType] = mapped_column(SQLEnum(ITAssetType, native_enum=False), nullable=False, index=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True, index=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(17), nullable=True, index=True)
    os: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    os_build: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    os_architecture: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # e.g., "64-bit"
    cpu_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    cpu_cores: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ram_total_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ram_free_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    disk_total_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    disk_free_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bios_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    manufacturer_system: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # Dell, HP, Lenovo, etc.
    domain: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # Active Directory domain
    computer_name_ad: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # Nom du compte ordinateur dans AD
    organizational_unit: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Unité organisationnelle
    last_ad_activity: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # Dernière activité connue dans l'annuaire
    is_domain_joined: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)  # Le poste est-il joint au domaine
    domain_last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # Dernière synchronisation AD
    last_collection: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    agent_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[ITAssetStatus] = mapped_column(SQLEnum(ITAssetStatus, native_enum=False), default=ITAssetStatus.UNKNOWN, nullable=False, index=True)
    discovery_source: Mapped[DiscoverySource] = mapped_column(SQLEnum(DiscoverySource, native_enum=False), default=DiscoverySource.MANUAL, nullable=False)
    discovery_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    snmp_manufacturer: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # Collecté via SNMP
    snmp_model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # Collecté via SNMP
    snmp_firmware_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Collecté via SNMP
    snmp_contact: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # Collecté via SNMP
    snmp_location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Collecté via SNMP
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False, index=True)
    meshcentral_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True, index=True)
    wol_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wol_mac: Mapped[Optional[str]] = mapped_column(String(17), nullable=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    room: Mapped["Room"] = relationship("Room", back_populates="it_assets")
    observations: Mapped[List["AssetObservation"]] = relationship("AssetObservation", back_populates="asset", cascade="all, delete-orphan", order_by="desc(AssetObservation.checked_at)")
    alerts: Mapped[List["ITAlert"]] = relationship("ITAlert", back_populates="asset", cascade="all, delete-orphan", order_by="desc(ITAlert.created_at)")
    history: Mapped[List["ITAssetHistory"]] = relationship("ITAssetHistory", back_populates="asset", cascade="all, delete-orphan", order_by="desc(ITAssetHistory.created_at)")

    __table_args__ = (
        Index("ix_it_assets_type_active", "asset_type", "is_active"),
        Index("ix_it_assets_room_active", "room_id", "is_active"),
        Index("ix_it_assets_status_active", "status", "is_active"),
        Index("ix_it_assets_ip_active", "ip_address", "is_active"),
        Index("ix_it_assets_mac_active", "mac_address", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ITAsset(reference={self.reference}, name={self.name}, type={self.asset_type})>"


class NetworkRange(Base):
    __tablename__ = "it_network_ranges"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    cidr: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vlan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    site_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True)
    scan_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scan_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    snmp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    snmp_community: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    snmp_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    snmp_port: Mapped[int] = mapped_column(Integer, default=161, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_scan_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    site: Mapped[Optional["Site"]] = relationship("Site")
    discovery_logs: Mapped[List["DiscoveryLog"]] = relationship("DiscoveryLog", back_populates="network_range", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("cidr", name="uq_network_range_cidr"),
        Index("ix_network_ranges_site_active", "site_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<NetworkRange(name={self.name}, cidr={self.cidr})>"


class DiscoveryLog(Base):
    __tablename__ = "it_discovery_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    network_range_id: Mapped[int] = mapped_column(ForeignKey("it_network_ranges.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    hosts_scanned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hosts_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assets_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assets_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    network_range: Mapped["NetworkRange"] = relationship("NetworkRange", back_populates="discovery_logs")

    __table_args__ = (
        Index("ix_discovery_logs_range_started", "network_range_id", "started_at"),
    )

    def __repr__(self) -> str:
        return f"<DiscoveryLog(range_id={self.network_range_id}, status={self.status})>"


class AssetObservation(Base):
    __tablename__ = "it_asset_observations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("it_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[ITAssetStatus] = mapped_column(SQLEnum(ITAssetStatus, native_enum=False), nullable=False)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    check_method: Mapped[str] = mapped_column(String(50), default="ping", nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    asset: Mapped["ITAsset"] = relationship("ITAsset", back_populates="observations")

    __table_args__ = (
        Index("ix_asset_observations_asset_checked", "asset_id", "checked_at"),
    )

    def __repr__(self) -> str:
        return f"<AssetObservation(asset_id={self.asset_id}, status={self.status})>"


class ITAlert(Base):
    __tablename__ = "it_alerts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("it_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type: Mapped[ITAlertType] = mapped_column(SQLEnum(ITAlertType, native_enum=False), nullable=False, index=True)
    severity: Mapped[ITAlertSeverity] = mapped_column(SQLEnum(ITAlertSeverity, native_enum=False), default=ITAlertSeverity.INFO, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset: Mapped["ITAsset"] = relationship("ITAsset", back_populates="alerts")

    __table_args__ = (
        Index("ix_it_alerts_asset_resolved", "asset_id", "resolved"),
        Index("ix_it_alerts_severity_created", "severity", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ITAlert(asset_id={self.asset_id}, type={self.alert_type}, severity={self.severity})>"


class ITAssetHistory(Base):
    __tablename__ = "it_asset_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("it_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    change_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset: Mapped["ITAsset"] = relationship("ITAsset", back_populates="history")

    __table_args__ = (
        Index("ix_it_asset_history_asset_created", "asset_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ITAssetHistory(asset_id={self.asset_id}, field={self.field_name})>"