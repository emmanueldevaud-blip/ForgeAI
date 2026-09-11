import re
from datetime import UTC, datetime
from typing import Optional, List

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.rbac import Role, PermissionModel, UserRoleAssignment
from app.models import Group
from app.models.rbac import GroupRole, RolePermission
from app.services.auth import hash_password, verify_password, get_user_by_id
from app.services.rbac import RBACService
from app.services.audit import AuditService


def slugify(text: str, max_length: int = 50) -> str:
    """Generate a URL-friendly slug from text."""
    text = re.sub(r'[^\w\s-]', '', text.lower())
    text = re.sub(r'[\s_-]+', '_', text)
    text = text.strip('_')
    return text[:max_length]


class AdminUserService:
    def __init__(
        self,
        db: AsyncSession,
        audit: AuditService = None,
        current_user: User = None
    ):
        self.db = db
        self.audit = audit
        self.current_user = current_user

    # ============================================================
    # USERS
    # ============================================================

    async def search_users(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        source: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[User], int]:

        query = select(User).options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.groups),
        )

        conditions = []

        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    User.username.ilike(search_term),
                    User.email.ilike(search_term),
                    User.first_name.ilike(search_term),
                    User.last_name.ilike(search_term),
                )
            )

        if is_active is not None:
            conditions.append(User.is_active == is_active)

        if source:
            conditions.append(User.source == source)

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "username": User.username,
            "email": User.email,
            "first_name": User.first_name,
            "last_name": User.last_name,
            "is_active": User.is_active,
            "role": User.role,
            "source": User.source,
            "last_login": User.last_login,
            "created_at": User.created_at,
            "updated_at": User.updated_at,
        }

        sort_column = allowed_sort_fields.get(
            sort_by,
            User.created_at
        )

        if sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        count_query = select(func.count()).select_from(
            query.subquery()
        )

        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        users = result.scalars().all()

        return list(users), total

    async def get_user_with_roles(
        self,
        user_id: int
    ) -> Optional[User]:

        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.roles).selectinload(Role.permissions),
                selectinload(User.groups)
                .selectinload(Group.roles)
                .selectinload(Role.permissions)
            )
            .where(User.id == user_id)
            .execution_options(populate_existing=True)
        )

        return result.scalar_one_or_none()

    async def create_user(self, user_data: dict) -> User:

        if "password" in user_data:
            user_data["password_hash"] = hash_password(
                user_data.pop("password")
            )
        else:
            user_data["password_hash"] = None

        user_data.pop("role", None)

        user = User(**user_data)

        self.db.add(user)

        await self.db.commit()
        await self.db.refresh(user)

        result = await self.db.execute(
            select(User)
            .options(
            selectinload(User.roles)
            .selectinload(Role.permissions),
            selectinload(User.groups)
            )
            .where(User.id == user.id)
        )

        user = result.scalar_one()

        if self.audit:
            await self.audit.log(
                action="user_create",
                module="admin",
                user=self.current_user,
                object_type="user",
                object_id=str(user.id),
                object_repr=user.username,
                new_values={
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_active": user.is_active,
                    "role": user.role.value,
                    "source": user.source,
                },
                status="success",
            )

        return user

    async def update_user(
        self,
        user: User,
        updates: dict
    ) -> User:

        old_values = {
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
            "role": user.role.value,
            "source": user.source,
        }

        for key, value in updates.items():
            if value is None:
                continue

            if key == "password":
                user.password_hash = hash_password(value)

            elif key == "role":
                continue

            elif hasattr(user, key):
                setattr(user, key, value)

        user.updated_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(user)

        result = await self.db.execute(
            select(User)
            .options(
            selectinload(User.roles)
            .selectinload(Role.permissions),
            selectinload(User.groups)
            )
            .where(User.id == user.id)
        )

        user = result.scalar_one()

        new_values = {
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
            "role": user.role.value,
            "source": user.source,
        }

        if self.audit:
            await self.audit.log(
                action="user_update",
                module="admin",
                user=self.current_user,
                object_type="user",
                object_id=str(user.id),
                object_repr=user.username,
                old_values=old_values,
                new_values=new_values,
                status="success",
            )

        return user

    async def toggle_active(
        self,
        user: User,
        is_active: bool
    ) -> User:

        old_values = {
            "is_active": user.is_active
        }

        user.is_active = is_active
        user.updated_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(user)

        result = await self.db.execute(
            select(User)
            .options(
            selectinload(User.roles)
            .selectinload(Role.permissions),
            selectinload(User.groups)
            )
            .where(User.id == user.id)
        )

        user = result.scalar_one()

        if self.audit:
            await self.audit.log(
                action=(
                    "user_toggle_active"
                    if is_active
                    else "user_deactivate"
                ),
                module="admin",
                user=self.current_user,
                object_type="user",
                object_id=str(user.id),
                object_repr=user.username,
                old_values=old_values,
                new_values={
                    "is_active": user.is_active
                },
                status="success",
            )

        return user

    async def reset_password(
        self,
        user: User,
        new_password: str
    ) -> User:

        if user.source != "local":
            raise ValueError(
                "Impossible de réinitialiser le mot de passe pour un compte AD"
            )

        user.password_hash = hash_password(new_password)
        user.updated_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(user)

        if self.audit:
            await self.audit.log(
                action="user_reset_password",
                module="admin",
                user=self.current_user,
                object_type="user",
                object_id=str(user.id),
                object_repr=user.username,
                status="success",
            )

        return user

    async def delete_user(self, user: User) -> None:

        if self.audit:
            await self.audit.log(
                action="user_delete",
                module="admin",
                user=self.current_user,
                object_type="user",
                object_id=str(user.id),
                object_repr=user.username,
                old_values={
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_active": user.is_active,
                    "role": user.role.value,
                    "source": user.source,
                },
                status="success",
            )

        await self.db.delete(user)
        await self.db.commit()

    async def assign_role(
        self,
        user_id: int,
        role_id: int
    ) -> UserRoleAssignment:

        rbac = RBACService(
            self.db,
            audit=self.audit,
            current_user=self.current_user
        )

        assignment = await rbac.assign_role_to_user(
            user_id,
            role_id,
            self.current_user.id
            if self.current_user
            else None
        )

        return assignment

    async def remove_role(
        self,
        user_id: int,
        role_id: int
    ) -> bool:

        rbac = RBACService(
            self.db,
            audit=self.audit,
            current_user=self.current_user
        )

        return await rbac.remove_role_from_user(
            user_id,
            role_id
        )

    async def list_roles(self) -> List[Role]:
        """
        Retourne tous les rôles, actifs et inactifs.

        Un rôle désactivé reste visible dans l'administration.
        Son statut actif/inactif est géré séparément par RBAC.
        """

        result = await self.db.execute(
            select(Role)
            .options(
                selectinload(Role.permissions)
            )
            .order_by(Role.code)
        )

        return list(result.scalars().all())

    async def get_role_by_id(
        self,
        role_id: int
    ) -> Optional[Role]:

        result = await self.db.execute(
            select(Role)
            .options(
                selectinload(Role.permissions)
            )
            .where(Role.id == role_id)
        )

        return result.scalar_one_or_none()

    # ============================================================
    # GROUPS
    # ============================================================

    async def search_groups(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[Group], int]:

        query = select(Group).options(
            selectinload(Group.roles),
            selectinload(Group.users)
        )

        conditions = []

        if search:
            search_term = f"%{search}%"

            conditions.append(
                or_(
                    Group.code.ilike(search_term),
                    Group.name.ilike(search_term),
                )
            )

        if is_active is not None:
            conditions.append(
                Group.is_active == is_active
            )

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "code": Group.code,
            "name": Group.name,
            "is_active": Group.is_active,
            "created_at": Group.created_at,
        }

        sort_column = allowed_sort_fields.get(
            sort_by,
            Group.created_at
        )

        if sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        count_query = select(func.count()).select_from(
            query.subquery()
        )

        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size

        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        groups = result.scalars().all()

        return list(groups), total

    async def get_group_with_details(
        self,
        group_id: int
    ) -> Optional[Group]:

        result = await self.db.execute(
            select(Group)
            .options(
                selectinload(Group.users).selectinload(User.roles),
                selectinload(Group.users).selectinload(User.groups),
                selectinload(Group.roles)
            )
            .where(Group.id == group_id)
        )

        return result.scalar_one_or_none()

    async def create_group(
        self,
        group_data: dict
    ) -> Group:

        if (
            "code" not in group_data
            or not group_data.get("code")
        ):
            group_data["code"] = slugify(
                group_data.get("name", "")
            )

        group = Group(**group_data)

        self.db.add(group)

        await self.db.commit()
        await self.db.refresh(group)

        if self.audit:
            await self.audit.log(
                action="group_create",
                module="admin",
                user=self.current_user,
                object_type="group",
                object_id=str(group.id),
                object_repr=group.code,
                new_values={
                    "code": group.code,
                    "name": group.name,
                    "description": group.description,
                },
                status="success",
            )

        return group

    async def update_group(
        self,
        group: Group,
        updates: dict
    ) -> Group:

        old_values = {
            "code": group.code,
            "name": group.name,
            "description": group.description,
            "is_active": group.is_active,
        }

        for key, value in updates.items():
            if value is None:
                continue

            if hasattr(group, key):
                setattr(group, key, value)

        group.updated_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(group)

        new_values = {
            "code": group.code,
            "name": group.name,
            "description": group.description,
            "is_active": group.is_active,
        }

        if self.audit:
            await self.audit.log(
                action="group_update",
                module="admin",
                user=self.current_user,
                object_type="group",
                object_id=str(group.id),
                object_repr=group.code,
                old_values=old_values,
                new_values=new_values,
                status="success",
            )

        return group

    async def delete_group(
        self,
        group: Group
    ) -> None:

        if self.audit:
            await self.audit.log(
                action="group_delete",
                module="admin",
                user=self.current_user,
                object_type="group",
                object_id=str(group.id),
                object_repr=group.code,
                old_values={
                    "code": group.code,
                    "name": group.name,
                    "description": group.description,
                },
                status="success",
            )

        await self.db.delete(group)
        await self.db.commit()

    async def add_user_to_group(
        self,
        group_id: int,
        user_id: int
    ) -> bool:

        from app.models import UserGroup

        existing = await self.db.execute(
            select(UserGroup).where(
                UserGroup.user_id == user_id,
                UserGroup.group_id == group_id
            )
        )

        if existing.scalar_one_or_none():
            raise ValueError(
                "User already in group"
            )

        user = await self.db.get(
            User,
            user_id
        )

        group = await self.db.get(
            Group,
            group_id
        )

        membership = UserGroup(
            user_id=user_id,
            group_id=group_id
        )

        self.db.add(membership)

        await self.db.commit()
        await self.db.refresh(membership)

        if self.audit and user and group:
            await self.audit.log(
                action="group_add_user",
                module="admin",
                user=self.current_user,
                object_type="group_user",
                object_id=str(group_id),
                object_repr=(
                    f"{group.code} -> {user.username}"
                ),
                new_values={
                    "group_id": group_id,
                    "group_code": group.code,
                    "user_id": user_id,
                    "user_username": user.username,
                },
                status="success",
            )

        return True

    async def remove_user_from_group(
        self,
        group_id: int,
        user_id: int
    ) -> bool:

        from app.models import UserGroup

        result = await self.db.execute(
            select(UserGroup).where(
                UserGroup.user_id == user_id,
                UserGroup.group_id == group_id
            )
        )

        membership = result.scalar_one_or_none()

        if membership:
            user = await self.db.get(
                User,
                user_id
            )

            group = await self.db.get(
                Group,
                group_id
            )

            await self.db.delete(membership)
            await self.db.commit()

            if self.audit and user and group:
                await self.audit.log(
                    action="group_remove_user",
                    module="admin",
                    user=self.current_user,
                    object_type="group_user",
                    object_id=str(group_id),
                    object_repr=(
                        f"{group.code} -> {user.username}"
                    ),
                    old_values={
                        "group_id": group_id,
                        "group_code": group.code,
                        "user_id": user_id,
                        "user_username": user.username,
                    },
                    status="success",
                )

            return True

        return False

    async def add_role_to_group(
        self,
        group_id: int,
        role_id: int
    ) -> GroupRole:

        existing = await self.db.execute(
            select(GroupRole).where(
                GroupRole.group_id == group_id,
                GroupRole.role_id == role_id
            )
        )

        if existing.scalar_one_or_none():
            raise ValueError(
                "Role already assigned to group"
            )

        group = await self.db.get(
            Group,
            group_id
        )

        role = await self.db.get(
            Role,
            role_id
        )

        assignment = GroupRole(
            group_id=group_id,
            role_id=role_id
        )

        self.db.add(assignment)

        await self.db.commit()
        await self.db.refresh(assignment)

        if self.audit and group and role:
            await self.audit.log(
                action="group_role_assign",
                module="admin",
                user=self.current_user,
                object_type="group_role",
                object_id=str(group_id),
                object_repr=(
                    f"{group.code} -> {role.code}"
                ),
                new_values={
                    "group_id": group_id,
                    "group_code": group.code,
                    "role_id": role_id,
                    "role_code": role.code,
                },
                status="success",
            )

        return assignment

    async def remove_role_from_group(
        self,
        group_id: int,
        role_id: int
    ) -> bool:

        result = await self.db.execute(
            select(GroupRole).where(
                GroupRole.group_id == group_id,
                GroupRole.role_id == role_id
            )
        )

        assignment = result.scalar_one_or_none()

        if assignment:
            group = await self.db.get(
                Group,
                group_id
            )

            role = await self.db.get(
                Role,
                role_id
            )

            await self.db.delete(assignment)
            await self.db.commit()

            if self.audit and group and role:
                await self.audit.log(
                    action="group_role_remove",
                    module="admin",
                    user=self.current_user,
                    object_type="group_role",
                    object_id=str(group_id),
                    object_repr=(
                        f"{group.code} -> {role.code}"
                    ),
                    old_values={
                        "group_id": group_id,
                        "group_code": group.code,
                        "role_id": role_id,
                        "role_code": role.code,
                    },
                    status="success",
                )

            return True

        return False

    async def list_groups_with_user_count(
        self
    ) -> List[dict]:

        """Get groups with user and role counts for list view"""

        result = await self.db.execute(
            select(Group)
            .options(
                selectinload(Group.users),
                selectinload(Group.roles)
            )
            .where(Group.is_active == True)
            .order_by(Group.code)
        )

        groups = result.scalars().all()

        return [
            {
                "id": g.id,
                "code": g.code,
                "name": g.name,
                "description": g.description,
                "is_active": g.is_active,
                "created_at": g.created_at,
                "updated_at": g.updated_at,
                "user_count": len(g.users),
                "role_count": len(g.roles),
            }
            for g in groups
        ]

    # ============================================================
    # ROLES
    # ============================================================

    async def search_roles(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_system: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[Role], int]:

        query = select(Role).options(
            selectinload(Role.permissions)
        )

        conditions = []

        if search:
            search_term = f"%{search}%"

            conditions.append(
                or_(
                    Role.code.ilike(search_term),
                    Role.name.ilike(search_term),
                )
            )

        if is_active is not None:
            conditions.append(
                Role.is_active == is_active
            )

        if is_system is not None:
            conditions.append(
                Role.is_system == is_system
            )

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "code": Role.code,
            "name": Role.name,
            "is_active": Role.is_active,
            "is_system": Role.is_system,
            "created_at": Role.created_at,
        }

        sort_column = allowed_sort_fields.get(
            sort_by,
            Role.created_at
        )

        if sort_order == "asc":
            query = query.order_by(
                sort_column.asc()
            )
        else:
            query = query.order_by(
                sort_column.desc()
            )

        count_query = select(func.count()).select_from(
            query.subquery()
        )

        total_result = await self.db.execute(
            count_query
        )

        total = total_result.scalar()

        offset = (page - 1) * page_size

        query = query.offset(offset).limit(
            page_size
        )

        result = await self.db.execute(query)

        roles = result.scalars().all()

        return list(roles), total

    async def create_role(
        self,
        role_data: dict
    ) -> Role:

        if (
            "code" not in role_data
            or not role_data.get("code")
        ):
            role_data["code"] = slugify(
                role_data.get("name", "")
            )

        role = Role(**role_data)

        self.db.add(role)

        await self.db.commit()

        await self.db.refresh(role)
        await self.db.refresh(
            role,
            attribute_names=[
                "permissions",
                "groups"
            ]
        )

        if self.audit:
            await self.audit.log(
                action="role_create",
                module="admin",
                user=self.current_user,
                object_type="role",
                object_id=str(role.id),
                object_repr=role.code,
                new_values={
                    "code": role.code,
                    "name": role.name,
                    "description": role.description,
                    "is_system": role.is_system,
                },
                status="success",
            )

        return role

    async def update_role(
        self,
        role: Role,
        updates: dict
    ) -> Role:

        old_values = {
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "is_system": role.is_system,
            "is_active": role.is_active,
        }

        for key, value in updates.items():
            if value is None:
                continue

            if hasattr(role, key):
                setattr(role, key, value)

        role.updated_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(role)

        new_values = {
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "is_system": role.is_system,
            "is_active": role.is_active,
        }

        if self.audit:
            await self.audit.log(
                action="role_update",
                module="admin",
                user=self.current_user,
                object_type="role",
                object_id=str(role.id),
                object_repr=role.code,
                old_values=old_values,
                new_values=new_values,
                status="success",
            )

        return role

    async def delete_role(
        self,
        role: Role
    ) -> None:

        if self.audit:
            await self.audit.log(
                action="role_delete",
                module="admin",
                user=self.current_user,
                object_type="role",
                object_id=str(role.id),
                object_repr=role.code,
                old_values={
                    "code": role.code,
                    "name": role.name,
                    "description": role.description,
                    "is_system": role.is_system,
                },
                status="success",
            )

        await self.db.delete(role)
        await self.db.commit()

    async def add_permission_to_role(
        self,
        role_id: int,
        permission_id: int
    ) -> RolePermission:

        existing = await self.db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id
            )
        )

        if existing.scalar_one_or_none():
            raise ValueError(
                "Permission already assigned to role"
            )

        role = await self.db.get(
            Role,
            role_id
        )

        permission = await self.db.get(
            PermissionModel,
            permission_id
        )

        assignment = RolePermission(
            role_id=role_id,
            permission_id=permission_id
        )

        self.db.add(assignment)

        await self.db.commit()
        await self.db.refresh(assignment)

        if self.audit and role and permission:
            await self.audit.log(
                action="permission_assign",
                module="admin",
                user=self.current_user,
                object_type="role_permission",
                object_id=str(role_id),
                object_repr=(
                    f"{role.code} -> {permission.code}"
                ),
                new_values={
                    "role_id": role_id,
                    "role_code": role.code,
                    "permission_id": permission_id,
                    "permission_code": permission.code,
                },
                status="success",
            )

        return assignment

    async def remove_permission_from_role(
        self,
        role_id: int,
        permission_id: int
    ) -> bool:

        result = await self.db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id
            )
        )

        assignment = result.scalar_one_or_none()

        if assignment:
            role = await self.db.get(
                Role,
                role_id
            )

            permission = await self.db.get(
                PermissionModel,
                permission_id
            )

            await self.db.delete(assignment)
            await self.db.commit()

            if self.audit and role and permission:
                await self.audit.log(
                    action="permission_remove",
                    module="admin",
                    user=self.current_user,
                    object_type="role_permission",
                    object_id=str(role_id),
                    object_repr=(
                        f"{role.code} -> {permission.code}"
                    ),
                    old_values={
                        "role_id": role_id,
                        "role_code": role.code,
                        "permission_id": permission_id,
                        "permission_code": permission.code,
                    },
                    status="success",
                )

            return True

        return False

    async def get_role_with_permissions(
        self,
        role_id: int
    ) -> Optional[Role]:

        result = await self.db.execute(
            select(Role)
            .options(
                selectinload(Role.permissions)
            )
            .where(Role.id == role_id)
        )

        return result.scalar_one_or_none()

    async def replace_role_permissions(
        self,
        role_id: int,
        permission_ids: list[int]
    ) -> Role:

        role = await self.db.get(Role, role_id)

        if not role:
            raise ValueError("Rôle non trouvé")

        if permission_ids:
            result = await self.db.execute(
                select(PermissionModel.id).where(
                    PermissionModel.id.in_(permission_ids)
                )
            )
            found_ids = {row[0] for row in result.all()}
            missing = set(permission_ids) - found_ids
            if missing:
                raise ValueError(
                    f"Permissions non trouvées: {sorted(missing)}"
                )

        from sqlalchemy import delete as sa_delete

        await self.db.execute(
            sa_delete(RolePermission).where(
                RolePermission.role_id == role_id
            )
        )

        for pid in permission_ids:
            self.db.add(
                RolePermission(
                    role_id=role_id,
                    permission_id=pid
                )
            )

        await self.db.commit()

        result = await self.db.execute(
            select(Role)
            .options(
                selectinload(Role.permissions)
            )
            .where(Role.id == role_id)
        )

        role = result.scalar_one()

        if self.audit:
            await self.audit.log(
                action="role_permissions_replace",
                module="admin",
                user=self.current_user,
                object_type="role",
                object_id=str(role.id),
                object_repr=role.code,
                new_values={
                    "role_id": role.id,
                    "role_code": role.code,
                    "permission_ids": permission_ids,
                },
                status="success",
            )

        return role

    # ============================================================
    # PERMISSIONS
    # ============================================================

    async def search_permissions(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        module: Optional[str] = None,
        is_system: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[PermissionModel], int]:

        query = select(PermissionModel)

        conditions = []

        if search:
            search_term = f"%{search}%"

            conditions.append(
                or_(
                    PermissionModel.code.ilike(search_term),
                    PermissionModel.name.ilike(search_term),
                )
            )

        if module:
            conditions.append(
                PermissionModel.module == module
            )

        if is_system is not None:
            conditions.append(
                PermissionModel.is_system == is_system
            )

        if conditions:
            query = query.where(and_(*conditions))

        allowed_sort_fields = {
            "code": PermissionModel.code,
            "name": PermissionModel.name,
            "module": PermissionModel.module,
            "is_system": PermissionModel.is_system,
            "created_at": PermissionModel.created_at,
        }

        sort_column = allowed_sort_fields.get(
            sort_by,
            PermissionModel.created_at
        )

        if sort_order == "asc":
            query = query.order_by(
                sort_column.asc()
            )
        else:
            query = query.order_by(
                sort_column.desc()
            )

        count_query = select(func.count()).select_from(
            query.subquery()
        )

        total_result = await self.db.execute(
            count_query
        )

        total = total_result.scalar()

        offset = (page - 1) * page_size

        query = query.offset(offset).limit(
            page_size
        )

        result = await self.db.execute(query)

        permissions = result.scalars().all()

        return list(permissions), total

    async def create_permission(
        self,
        permission_data: dict
    ) -> PermissionModel:

        perm = PermissionModel(**permission_data)

        self.db.add(perm)

        await self.db.commit()
        await self.db.refresh(perm)

        if self.audit:
            await self.audit.log(
                action="permission_create",
                module="admin",
                user=self.current_user,
                object_type="permission",
                object_id=str(perm.id),
                object_repr=perm.code,
                new_values={
                    "code": perm.code,
                    "name": perm.name,
                    "description": perm.description,
                    "module": perm.module,
                    "is_system": perm.is_system,
                },
                status="success",
            )

        return perm

    async def update_permission(
        self,
        perm: PermissionModel,
        updates: dict
    ) -> PermissionModel:

        old_values = {
            "code": perm.code,
            "name": perm.name,
            "description": perm.description,
            "module": perm.module,
            "is_system": perm.is_system,
        }

        for key, value in updates.items():
            if value is None:
                continue

            if hasattr(perm, key):
                setattr(perm, key, value)

        await self.db.commit()
        await self.db.refresh(perm)

        new_values = {
            "code": perm.code,
            "name": perm.name,
            "description": perm.description,
            "module": perm.module,
            "is_system": perm.is_system,
        }

        if self.audit:
            await self.audit.log(
                action="permission_update",
                module="admin",
                user=self.current_user,
                object_type="permission",
                object_id=str(perm.id),
                object_repr=perm.code,
                old_values=old_values,
                new_values=new_values,
                status="success",
            )

        return perm

    async def delete_permission(
        self,
        perm: PermissionModel
    ) -> None:

        if perm.is_system:
            raise ValueError(
                "Cannot delete system permission"
            )

        if self.audit:
            await self.audit.log(
                action="permission_delete",
                module="admin",
                user=self.current_user,
                object_type="permission",
                object_id=str(perm.id),
                object_repr=perm.code,
                old_values={
                    "code": perm.code,
                    "name": perm.name,
                    "description": perm.description,
                    "module": perm.module,
                    "is_system": perm.is_system,
                },
                status="success",
            )

        await self.db.delete(perm)
        await self.db.commit()

    async def get_permission_by_id(
        self,
        permission_id: int
    ) -> Optional[PermissionModel]:

        result = await self.db.execute(
            select(PermissionModel)
            .where(
                PermissionModel.id == permission_id
            )
        )

        return result.scalar_one_or_none()
