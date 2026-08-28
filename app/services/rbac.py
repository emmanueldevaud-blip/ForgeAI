from typing import List, Optional, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import Depends

from app.models import User, Role, PermissionModel, Group, UserRoleAssignment, UserGroup, GroupRole
from app.services.audit import AuditService, get_audit_service


class RBACService:
    def __init__(self, db: AsyncSession, audit: Optional[AuditService] = None, current_user: Optional[User] = None):
        self.db = db
        self.audit = audit
        self.current_user = current_user

    async def get_user_permissions(self, user: User) -> Set[str]:
        permissions = set()

        for role in user.roles:
            if role.is_active:
                for perm in role.permissions:
                    permissions.add(perm.code)

        for group in user.groups:
            if group.is_active:
                for role in group.roles:
                    if role.is_active:
                        for perm in role.permissions:
                            permissions.add(perm.code)

        if user.is_admin:
            permissions.add("*")

        return permissions

    async def user_has_permission(self, user: User, permission_code: str) -> bool:
        permissions = await self.get_user_permissions(user)
        return "*" in permissions or permission_code in permissions

    async def user_has_any_permission(self, user: User, permission_codes: List[str]) -> bool:
        permissions = await self.get_user_permissions(user)
        return "*" in permissions or any(p in permissions for p in permission_codes)

    async def user_has_all_permissions(self, user: User, permission_codes: List[str]) -> bool:
        permissions = await self.get_user_permissions(user)
        return "*" in permissions or all(p in permissions for p in permission_codes)

    async def get_user_roles(self, user: User) -> List[Role]:
        return [r for r in user.roles if r.is_active]

    async def get_user_groups(self, user: User) -> List[Group]:
        return [g for g in user.groups if g.is_active]

    async def assign_role_to_user(self, user_id: int, role_id: int, assigned_by: Optional[int] = None) -> UserRoleAssignment:
        existing = await self.db.execute(
            select(UserRoleAssignment).where(
                UserRoleAssignment.user_id == user_id,
                UserRoleAssignment.role_id == role_id
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Role already assigned to user")

        user = await self.db.get(User, user_id)
        role = await self.db.get(Role, role_id)

        assignment = UserRoleAssignment(
            user_id=user_id,
            role_id=role_id,
            assigned_by=assigned_by
        )
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)

        if self.audit and user and role:
            await self.audit.log(
                action="role_assign",
                module="rbac",
                user=self.current_user,
                object_type="user_role",
                object_id=str(user_id),
                object_repr=f"{user.username} -> {role.code}",
                new_values={
                    "user_id": user_id,
                    "user_username": user.username,
                    "role_id": role_id,
                    "role_code": role.code,
                    "assigned_by": assigned_by,
                },
                status="success",
            )
        return assignment

    async def remove_role_from_user(self, user_id: int, role_id: int) -> bool:
        result = await self.db.execute(
            select(UserRoleAssignment).where(
                UserRoleAssignment.user_id == user_id,
                UserRoleAssignment.role_id == role_id
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment:
            user = await self.db.get(User, user_id)
            role = await self.db.get(Role, role_id)
            await self.db.delete(assignment)
            await self.db.commit()

            if self.audit and user and role:
                await self.audit.log(
                    action="role_remove",
                    module="rbac",
                    user=self.current_user,
                    object_type="user_role",
                    object_id=str(user_id),
                    object_repr=f"{user.username} -> {role.code}",
                    old_values={
                        "user_id": user_id,
                        "user_username": user.username,
                        "role_id": role_id,
                        "role_code": role.code,
                    },
                    status="success",
                )
            return True
        return False

    async def add_user_to_group(self, user_id: int, group_id: int) -> UserGroup:
        existing = await self.db.execute(
            select(UserGroup).where(
                UserGroup.user_id == user_id,
                UserGroup.group_id == group_id
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("User already in group")

        user = await self.db.get(User, user_id)
        group = await self.db.get(Group, group_id)

        membership = UserGroup(user_id=user_id, group_id=group_id)
        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(membership)

        if self.audit and user and group:
            await self.audit.log(
                action="group_add_user",
                module="rbac",
                user=self.current_user,
                object_type="user_group",
                object_id=str(user_id),
                object_repr=f"{user.username} -> {group.code}",
                new_values={
                    "user_id": user_id,
                    "user_username": user.username,
                    "group_id": group_id,
                    "group_code": group.code,
                },
                status="success",
            )
        return membership

    async def remove_user_from_group(self, user_id: int, group_id: int) -> bool:
        result = await self.db.execute(
            select(UserGroup).where(
                UserGroup.user_id == user_id,
                UserGroup.group_id == group_id
            )
        )
        membership = result.scalar_one_or_none()
        if membership:
            user = await self.db.get(User, user_id)
            group = await self.db.get(Group, group_id)
            await self.db.delete(membership)
            await self.db.commit()

            if self.audit and user and group:
                await self.audit.log(
                    action="group_remove_user",
                    module="rbac",
                    user=self.current_user,
                    object_type="user_group",
                    object_id=str(user_id),
                    object_repr=f"{user.username} -> {group.code}",
                    old_values={
                        "user_id": user_id,
                        "user_username": user.username,
                        "group_id": group_id,
                        "group_code": group.code,
                    },
                    status="success",
                )
            return True
        return False

    async def assign_role_to_group(self, group_id: int, role_id: int) -> GroupRole:
        existing = await self.db.execute(
            select(GroupRole).where(
                GroupRole.group_id == group_id,
                GroupRole.role_id == role_id
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Role already assigned to group")

        group = await self.db.get(Group, group_id)
        role = await self.db.get(Role, role_id)

        assignment = GroupRole(group_id=group_id, role_id=role_id)
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)

        if self.audit and group and role:
            await self.audit.log(
                action="group_role_assign",
                module="rbac",
                user=self.current_user,
                object_type="group_role",
                object_id=str(group_id),
                object_repr=f"{group.code} -> {role.code}",
                new_values={
                    "group_id": group_id,
                    "group_code": group.code,
                    "role_id": role_id,
                    "role_code": role.code,
                },
                status="success",
            )
        return assignment

    async def remove_role_from_group(self, group_id: int, role_id: int) -> bool:
        result = await self.db.execute(
            select(GroupRole).where(
                GroupRole.group_id == group_id,
                GroupRole.role_id == role_id
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment:
            group = await self.db.get(Group, group_id)
            role = await self.db.get(Role, role_id)
            await self.db.delete(assignment)
            await self.db.commit()

            if self.audit and group and role:
                await self.audit.log(
                    action="group_role_remove",
                    module="rbac",
                    user=self.current_user,
                    object_type="group_role",
                    object_id=str(group_id),
                    object_repr=f"{group.code} -> {role.code}",
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

    async def get_role_by_code(self, code: str) -> Optional[Role]:
        result = await self.db.execute(
            select(Role)
            .options(selectinload(Role.permissions))
            .where(Role.code == code)
        )
        return result.scalar_one_or_none()

    async def get_permission_by_code(self, code: str) -> Optional[PermissionModel]:
        result = await self.db.execute(
            select(PermissionModel).where(PermissionModel.code == code)
        )
        return result.scalar_one_or_none()

    async def create_role(self, code: str, name: str, description: Optional[str] = None, is_system: bool = False) -> Role:
        role = Role(code=code, name=name, description=description, is_system=is_system)
        self.db.add(role)
        await self.db.commit()
        await self.db.refresh(role)

        if self.audit:
            await self.audit.log(
                action="role_create",
                module="rbac",
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

    async def create_permission(self, code: str, name: str, description: Optional[str] = None, module: Optional[str] = None, is_system: bool = False) -> PermissionModel:
        perm = PermissionModel(code=code, name=name, description=description, module=module, is_system=is_system)
        self.db.add(perm)
        await self.db.commit()
        await self.db.refresh(perm)

        if self.audit:
            await self.audit.log(
                action="permission_create",
                module="rbac",
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

    async def assign_permission_to_role(self, role_id: int, permission_id: int):
        from app.models import RolePermission
        existing = await self.db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id
            )
        )
        if existing.scalar_one_or_none():
            return

        role = await self.db.get(Role, role_id)
        permission = await self.db.get(PermissionModel, permission_id)

        assignment = RolePermission(role_id=role_id, permission_id=permission_id)
        self.db.add(assignment)
        await self.db.commit()

        if self.audit and role and permission:
            await self.audit.log(
                action="permission_assign",
                module="rbac",
                user=self.current_user,
                object_type="role_permission",
                object_id=str(role_id),
                object_repr=f"{role.code} -> {permission.code}",
                new_values={
                    "role_id": role_id,
                    "role_code": role.code,
                    "permission_id": permission_id,
                    "permission_code": permission.code,
                },
                status="success",
            )

    async def remove_permission_from_role(self, role_id: int, permission_id: int) -> bool:
        from app.models import RolePermission
        result = await self.db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment:
            role = await self.db.get(Role, role_id)
            permission = await self.db.get(PermissionModel, permission_id)
            await self.db.delete(assignment)
            await self.db.commit()

            if self.audit and role and permission:
                await self.audit.log(
                    action="permission_remove",
                    module="rbac",
                    user=self.current_user,
                    object_type="role_permission",
                    object_id=str(role_id),
                    object_repr=f"{role.code} -> {permission.code}",
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


async def get_rbac_service(
    db: AsyncSession,
    current_user: User,
) -> RBACService:
    audit = await get_audit_service(db)
    return RBACService(db, audit=audit, current_user=current_user)


async def require_permission(permission_code: str, current_user: User = None, db: AsyncSession = None):
    if current_user is None or db is None:
        from app.api.deps import get_current_active_user, get_db
        raise RuntimeError("require_permission should be used as a FastAPI dependency")

    rbac = RBACService(db)
    has_perm = await rbac.user_has_permission(current_user, permission_code)
    if not has_perm:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission '{permission_code}' required"
        )
    return current_user


def require_permissions(*permission_codes: str):
    async def dependency(
        current_user: User = None,
        db: AsyncSession = None
    ):
        if current_user is None or db is None:
            from app.api.deps import get_current_active_user, get_db
            raise RuntimeError("require_permissions should be used as a FastAPI dependency")

        rbac = RBACService(db)
        has_perm = await rbac.user_has_all_permissions(current_user, list(permission_codes))
        if not has_perm:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permissions required: {', '.join(permission_codes)}"
            )
        return current_user
    return dependency