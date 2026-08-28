from typing import List, Optional, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import User, Role, PermissionModel, Group, UserRoleAssignment, UserGroup, GroupRole


class RBACService:
    def __init__(self, db: AsyncSession):
        self.db = db

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

        assignment = UserRoleAssignment(
            user_id=user_id,
            role_id=role_id,
            assigned_by=assigned_by
        )
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)
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
            await self.db.delete(assignment)
            await self.db.commit()
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

        membership = UserGroup(user_id=user_id, group_id=group_id)
        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(membership)
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
            await self.db.delete(membership)
            await self.db.commit()
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

        assignment = GroupRole(group_id=group_id, role_id=role_id)
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)
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
            await self.db.delete(assignment)
            await self.db.commit()
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
        return role

    async def create_permission(self, code: str, name: str, description: Optional[str] = None, module: Optional[str] = None, is_system: bool = False) -> PermissionModel:
        perm = PermissionModel(code=code, name=name, description=description, module=module, is_system=is_system)
        self.db.add(perm)
        await self.db.commit()
        await self.db.refresh(perm)
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
        assignment = RolePermission(role_id=role_id, permission_id=permission_id)
        self.db.add(assignment)
        await self.db.commit()

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
            await self.db.delete(assignment)
            await self.db.commit()
            return True
        return False


async def get_rbac_service(db: AsyncSession) -> RBACService:
    return RBACService(db)


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