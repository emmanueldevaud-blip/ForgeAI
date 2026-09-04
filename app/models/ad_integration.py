from datetime import datetime
from enum import Enum as PyEnum

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
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ADSyncStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class ADConfig(Base):
    __tablename__ = "ad_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    server: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=636, nullable=False)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    base_dn: Mapped[str] = mapped_column(String(500), nullable=False)
    user_dn: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_search_filter: Mapped[str] = mapped_column(String(255), default="(sAMAccountName={username})", nullable=False)
    group_search_base: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bind_user: Mapped[str] = mapped_column(String(255), nullable=False)
    bind_password: Mapped[str] = mapped_column(String(255), nullable=False)
    connect_timeout: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    receive_timeout: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    page_size: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    follow_referrals: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    group_mappings: Mapped[list["ADGroupMapping"]] = relationship("ADGroupMapping", back_populates="ad_config", cascade="all, delete-orphan")
    sync_logs: Mapped[list["ADSyncLog"]] = relationship("ADSyncLog", back_populates="ad_config", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_ad_configs_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ADConfig(name={self.name}, server={self.server})>"


class ADGroupMapping(Base):
    __tablename__ = "ad_group_mappings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ad_config_id: Mapped[int] = mapped_column(ForeignKey("ad_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    ad_group_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    ad_group_dn: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    ad_config: Mapped["ADConfig"] = relationship("ADConfig", back_populates="group_mappings")

    __table_args__ = (
        UniqueConstraint("ad_config_id", "ad_group_cn", name="uq_ad_group_mapping"),
        Index("ix_ad_group_mappings_role", "role_code"),
    )

    def __repr__(self) -> str:
        return f"<ADGroupMapping(ad_group={self.ad_group_cn}, role={self.role_code})>"


class ADSyncLog(Base):
    __tablename__ = "ad_sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ad_config_id: Mapped[int] = mapped_column(ForeignKey("ad_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[ADSyncStatus] = mapped_column(SQLEnum(ADSyncStatus, native_enum=False), default=ADSyncStatus.PENDING, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    users_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users_deactivated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    groups_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    groups_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    groups_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    ad_config: Mapped["ADConfig"] = relationship("ADConfig", back_populates="sync_logs")

    __table_args__ = (
        Index("ix_ad_sync_logs_config_started", "ad_config_id", "started_at"),
    )

    def __repr__(self) -> str:
        return f"<ADSyncLog(config_id={self.ad_config_id}, status={self.status})>"