from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    ForeignKey,
    func,
    Index,
    Text,
    Integer,
    JSON,
    Enum as SQLEnum,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class ModuleStatus(str, PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    INSTALLING = "installing"
    ERROR = "error"


def _empty_list() -> List[str]:
    return []


def _empty_dict() -> Dict[str, Any]:
    return {}


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[ModuleStatus] = mapped_column(
        SQLEnum(ModuleStatus, native_enum=False),
        default=ModuleStatus.INACTIVE,
        nullable=False
    )
    version: Mapped[str] = mapped_column(String(20), default="1.0.0", nullable=False)
    route_path: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    component_path: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    required_permissions: Mapped[List[str]] = mapped_column(JSON, default=_empty_list, nullable=False)
    settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=_empty_dict, nullable=False)
    is_core: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dependencies: Mapped[List[str]] = mapped_column(JSON, default=_empty_list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    configs: Mapped[List["ModuleConfig"]] = relationship("ModuleConfig", back_populates="module", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_modules_code_status", "code", "status"),
        Index("ix_modules_order", "order"),
    )

    def __repr__(self) -> str:
        return f"<Module(code={self.code}, name={self.name}, status={self.status})>"


class ModuleConfig(Base):
    __tablename__ = "module_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(20), default="string", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validation: Mapped[Dict[str, Any]] = mapped_column(JSON, default=_empty_dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    module: Mapped["Module"] = relationship("Module", back_populates="configs")

    __table_args__ = (
        UniqueConstraint("module_id", "key", name="uq_module_config_key"),
        Index("ix_module_configs_module_key", "module_id", "key"),
    )

    def __repr__(self) -> str:
        return f"<ModuleConfig(module_id={self.module_id}, key={self.key})>"