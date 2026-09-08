from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Permission(str, PyEnum):
    MODULE_ACCESS = "module_access"
    MODULE_CONFIG = "module_config"
    USER_VIEW = "user_view"
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    USER_MANAGE_ROLES = "user_manage_roles"
    GROUP_VIEW = "group_view"
    GROUP_CREATE = "group_create"
    GROUP_UPDATE = "group_update"
    GROUP_DELETE = "group_delete"
    GROUP_MANAGE_MEMBERS = "group_manage_members"
    ROLE_VIEW = "role_view"
    ROLE_CREATE = "role_create"
    ROLE_UPDATE = "role_update"
    ROLE_DELETE = "role_delete"
    ROLE_MANAGE_PERMISSIONS = "role_manage_permissions"
    MODULE_VIEW = "module_view"
    MODULE_ENABLE = "module_enable"
    MODULE_DISABLE = "module_disable"
    MODULE_CONFIGURE = "module_configure"
    AD_CONFIG = "ad_config"
    AD_SYNC = "ad_sync"
    AD_TEST = "ad_test"
    AUDIT_LOG_VIEW = "audit_log_view"
    SETTINGS_VIEW = "settings_view"
    SETTINGS_UPDATE = "settings_update"


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    permissions: Mapped[list["PermissionModel"]] = relationship("PermissionModel", secondary="role_permissions", back_populates="roles")
    users: Mapped[list["User"]] = relationship(
        "User", 
        secondary="user_roles", 
        back_populates="roles",
        primaryjoin="Role.id == UserRoleAssignment.role_id",
        secondaryjoin="User.id == UserRoleAssignment.user_id"
    )
    groups: Mapped[list["Group"]] = relationship("Group", secondary="group_roles", back_populates="roles")

    __table_args__ = (
        Index("ix_roles_code_active", "code", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Role(code={self.code}, name={self.name})>"


class PermissionModel(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    module: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    roles: Mapped[list["Role"]] = relationship("Role", secondary="role_permissions", back_populates="permissions")

    __table_args__ = (
        Index("ix_permissions_module_code", "module", "code"),
    )

    def __repr__(self) -> str:
        return f"<Permission(code={self.code}, module={self.module})>"


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<RolePermission(role_id={self.role_id}, permission_id={self.permission_id})>"


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ad_dn: Mapped[str | None] = mapped_column(String(500), nullable=True, unique=True, index=True)
    ad_config_id: Mapped[int | None] = mapped_column(ForeignKey("ad_configs.id", ondelete="SET NULL"), nullable=True, index=True)
    # A group imported from AD must remain distinguishable from a local group even
    # when its DN is no longer available (for example after an AD cleanup).
    source: Mapped[str] = mapped_column(String(20), default="local", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    roles: Mapped[list["Role"]] = relationship("Role", secondary="group_roles", back_populates="groups")
    users: Mapped[list["User"]] = relationship("User", secondary="user_groups", back_populates="groups")

    __table_args__ = (
        Index("ix_groups_code_active", "code", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Group(code={self.code}, name={self.name})>"


class GroupRole(Base):
    __tablename__ = "group_roles"

    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<GroupRole(group_id={self.group_id}, role_id={self.role_id})>"


class UserRoleAssignment(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    assigned_by_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_by], back_populates="assigned_user_roles")

    def __repr__(self) -> str:
        return f"<UserRoleAssignment(user_id={self.user_id}, role_id={self.role_id})>"


class UserGroup(Base):
    __tablename__ = "user_groups"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<UserGroup(user_id={self.user_id}, group_id={self.group_id})>"
