from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional
from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    ForeignKey,
    func,
    Index,
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class UserRole(str, PyEnum):
    USER = "user"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, native_enum=False), default=UserRole.USER, nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), default="local", nullable=False)
    ad_dn: Mapped[str] = mapped_column(String(500), nullable=True, unique=True)
    last_login: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_users_email_active", "email", "is_active"),
        Index("ix_users_username_active", "username", "is_active"),
    )

    roles: Mapped[List["Role"]] = relationship(
        "Role", 
        secondary="user_roles", 
        back_populates="users",
        primaryjoin="User.id == UserRoleAssignment.user_id",
        secondaryjoin="Role.id == UserRoleAssignment.role_id"
    )
    groups: Mapped[List["Group"]] = relationship("Group", secondary="user_groups", back_populates="users")
    assigned_user_roles: Mapped[List["UserRoleAssignment"]] = relationship(
        "UserRoleAssignment", 
        foreign_keys="UserRoleAssignment.assigned_by", 
        back_populates="assigned_by_user"
    )

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or self.username

    todos: Mapped[list["Todo"]] = relationship("Todo", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"