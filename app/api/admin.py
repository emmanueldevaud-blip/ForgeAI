from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.rbac import Group, PermissionModel
from app.models.user import User
from app.schemas.admin import (
    AdminPasswordReset,
    GroupCreate,
    GroupListParams,
    GroupListResponse,
    GroupResponse,
    GroupUpdate,
    GroupUserAssign,
    GroupRoleAssign,
    GroupWithDetailsResponse,
    MessageResponse,
    PermissionCreate,
    PermissionListParams,
    PermissionListResponse,
    PermissionResponse,
    PermissionUpdate,
    RoleAssignRequest,
    RoleCreate,
    RoleListParams,
    RoleListResponse,
    RoleResponse,
    RoleUpdate,
    RoleWithPermissionsResponse,
    RolePermissionAssign,
    UserCreateAdmin,
    UserListParams,
    UserListResponse,
    UserToggleActive,
    UserUpdateAdmin,
    UserWithRolesResponse,
)
from app.services.admin import AdminUserService
from app.services.audit import get_audit_service


router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"]
)


async def get_admin_service(
    current_user: User = Depends(
        require_permission("user_view")
    ),
    db: AsyncSession = Depends(get_db),
) -> AdminUserService:

    audit = await get_audit_service(db)

    return AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )


# ============================================================
# GROUPS
# ============================================================

@router.get(
    "/groups",
    response_model=GroupListResponse
)
async def list_groups(
    params: GroupListParams = Depends(),
    current_user: User = Depends(
        require_permission("group_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    groups, total = await service.search_groups(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        is_active=params.is_active,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    group_list = []

    for g in groups:
        result = await db.execute(
            select(Group)
            .options(
                selectinload(Group.users),
                selectinload(Group.roles)
            )
            .where(Group.id == g.id)
        )

        group_with_details = result.scalar_one()

        group_list.append(
            GroupResponse(
                id=g.id,
                code=g.code,
                name=g.name,
                description=g.description,
                is_active=g.is_active,
                created_at=g.created_at,
                updated_at=g.updated_at,
                user_count=len(group_with_details.users),
                role_count=len(group_with_details.roles),
            )
        )

    total_pages = (
        (total + params.page_size - 1)
        // params.page_size
    )

    return GroupListResponse(
        groups=group_list,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "/groups",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_group(
    group_data: GroupCreate,
    current_user: User = Depends(
        require_permission("group_create")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group_dict = group_data.model_dump()

    group = await service.create_group(
        group_dict
    )

    return GroupResponse.model_validate(
        group,
        from_attributes=True
    )


@router.get(
    "/groups/{group_id}",
    response_model=GroupWithDetailsResponse
)
async def get_group(
    group_id: int,
    current_user: User = Depends(
        require_permission("group_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group = await service.get_group_with_details(
        group_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé",
        )

    return GroupWithDetailsResponse.model_validate(
        group,
        from_attributes=True
    )


@router.patch(
    "/groups/{group_id}",
    response_model=GroupResponse
)
async def update_group(
    group_id: int,
    updates: GroupUpdate,
    current_user: User = Depends(
        require_permission("group_update")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group = await service.get_group_with_details(
        group_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé",
        )

    update_data = updates.model_dump(
        exclude_unset=True
    )

    group = await service.update_group(
        group,
        update_data
    )

    return GroupResponse.model_validate(
        group,
        from_attributes=True
    )


@router.delete(
    "/groups/{group_id}",
    response_model=MessageResponse
)
async def delete_group(
    group_id: int,
    current_user: User = Depends(
        require_permission("group_delete")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group = await service.get_group_with_details(
        group_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé",
        )

    await service.delete_group(group)

    return MessageResponse(
        message="Groupe supprimé"
    )


@router.post(
    "/groups/{group_id}/users",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED
)
async def add_user_to_group(
    group_id: int,
    user_assign: GroupUserAssign,
    current_user: User = Depends(
        require_permission("group_manage_members")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group = await service.get_group_with_details(
        group_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé",
        )

    try:
        await service.add_user_to_group(
            group_id,
            user_assign.user_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return MessageResponse(
        message="Utilisateur ajouté au groupe"
    )


@router.delete(
    "/groups/{group_id}/users/{user_id}",
    response_model=MessageResponse
)
async def remove_user_from_group(
    group_id: int,
    user_id: int,
    current_user: User = Depends(
        require_permission("group_manage_members")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    removed = await service.remove_user_from_group(
        group_id,
        user_id
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cet utilisateur n'est pas membre du groupe",
        )

    return MessageResponse(
        message="Utilisateur retiré du groupe"
    )


@router.post(
    "/groups/{group_id}/roles",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED
)
async def add_role_to_group(
    group_id: int,
    role_assign: GroupRoleAssign,
    current_user: User = Depends(
        require_permission("group_manage_members")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group = await service.get_group_with_details(
        group_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé",
        )

    role = await service.get_role_by_id(
        role_assign.role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    if not role.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce rôle n'est pas actif",
        )

    try:
        await service.add_role_to_group(
            group_id,
            role_assign.role_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return RoleResponse.model_validate(
        role,
        from_attributes=True
    )


@router.delete(
    "/groups/{group_id}/roles/{role_id}",
    response_model=MessageResponse
)
async def remove_role_from_group(
    group_id: int,
    role_id: int,
    current_user: User = Depends(
        require_permission("group_manage_members")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    removed = await service.remove_role_from_group(
        group_id,
        role_id
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ce rôle n'est pas assigné à ce groupe",
        )

    return MessageResponse(
        message="Rôle retiré du groupe"
    )


# ============================================================
# ROLES
# ============================================================

@router.get(
    "/roles",
    response_model=RoleListResponse
)
async def list_roles(
    params: RoleListParams = Depends(),
    current_user: User = Depends(
        require_permission("role_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    roles, total = await service.search_roles(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        is_active=params.is_active,
        is_system=params.is_system,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    role_responses = [
        RoleResponse.model_validate(
            role,
            from_attributes=True
        )
        for role in roles
    ]

    total_pages = (
        (total + params.page_size - 1)
        // params.page_size
    )

    return RoleListResponse(
        roles=role_responses,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "/roles",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_role(
    role_data: RoleCreate,
    current_user: User = Depends(
        require_permission("role_create")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role_dict = role_data.model_dump()

    role = await service.create_role(
        role_dict
    )

    return RoleResponse.model_validate(
        role,
        from_attributes=True
    )


@router.get(
    "/roles/{role_id}",
    response_model=RoleWithPermissionsResponse
)
async def get_role(
    role_id: int,
    current_user: User = Depends(
        require_permission("role_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role = await service.get_role_with_permissions(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    return RoleWithPermissionsResponse.model_validate(
        role,
        from_attributes=True
    )


@router.patch(
    "/roles/{role_id}",
    response_model=RoleResponse
)
async def update_role(
    role_id: int,
    updates: RoleUpdate,
    current_user: User = Depends(
        require_permission("role_update")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role = await service.get_role_by_id(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de modifier un rôle système",
        )

    update_data = updates.model_dump(
        exclude_unset=True
    )

    role = await service.update_role(
        role,
        update_data
    )

    return RoleResponse.model_validate(
        role,
        from_attributes=True
    )


@router.delete(
    "/roles/{role_id}",
    response_model=MessageResponse
)
async def delete_role(
    role_id: int,
    current_user: User = Depends(
        require_permission("role_delete")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role = await service.get_role_by_id(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer un rôle système",
        )

    await service.delete_role(role)

    return MessageResponse(
        message="Rôle supprimé"
    )


@router.post(
    "/roles/{role_id}/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED
)
async def add_permission_to_role(
    role_id: int,
    perm_assign: RolePermissionAssign,
    current_user: User = Depends(
        require_permission("role_manage_permissions")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role = await service.get_role_by_id(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    permission = await service.get_permission_by_id(
        perm_assign.permission_id
    )

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission non trouvée",
        )

    try:
        await service.add_permission_to_role(
            role_id,
            perm_assign.permission_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return PermissionResponse.model_validate(
        permission,
        from_attributes=True
    )


@router.delete(
    "/roles/{role_id}/permissions/{permission_id}",
    response_model=MessageResponse
)
async def remove_permission_from_role(
    role_id: int,
    permission_id: int,
    current_user: User = Depends(
        require_permission("role_manage_permissions")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    removed = await service.remove_permission_from_role(
        role_id,
        permission_id
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cette permission n'est pas assignée à ce rôle",
        )

    return MessageResponse(
        message="Permission retirée du rôle"
    )


@router.get(
    "/roles/{role_id}/permissions",
    response_model=list[PermissionResponse]
)
async def list_role_permissions(
    role_id: int,
    current_user: User = Depends(
        require_permission("role_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role = await service.get_role_with_permissions(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    return [
        PermissionResponse.model_validate(
            permission,
            from_attributes=True
        )
        for permission in role.permissions
    ]


# ============================================================
# PERMISSIONS
# ============================================================

@router.get(
    "/permissions",
    response_model=PermissionListResponse
)
async def list_permissions(
    params: PermissionListParams = Depends(),
    current_user: User = Depends(
        require_permission("permission_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    permissions, total = await service.search_permissions(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        module=params.module,
        is_system=params.is_system,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    permission_responses = [
        PermissionResponse.model_validate(
            permission,
            from_attributes=True
        )
        for permission in permissions
    ]

    total_pages = (
        (total + params.page_size - 1)
        // params.page_size
    )

    return PermissionListResponse(
        permissions=permission_responses,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_permission(
    permission_data: PermissionCreate,
    current_user: User = Depends(
        require_permission("permission_create")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    permission_dict = permission_data.model_dump()

    permission = await service.create_permission(
        permission_dict
    )

    return PermissionResponse.model_validate(
        permission,
        from_attributes=True
    )


@router.get(
    "/permissions/{permission_id}",
    response_model=PermissionResponse
)
async def get_permission(
    permission_id: int,
    current_user: User = Depends(
        require_permission("permission_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    permission = await service.get_permission_by_id(
        permission_id
    )

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission non trouvée",
        )

    return PermissionResponse.model_validate(
        permission,
        from_attributes=True
    )


@router.patch(
    "/permissions/{permission_id}",
    response_model=PermissionResponse
)
async def update_permission(
    permission_id: int,
    updates: PermissionUpdate,
    current_user: User = Depends(
        require_permission("permission_update")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    permission = await service.get_permission_by_id(
        permission_id
    )

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission non trouvée",
        )

    if permission.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de modifier une permission système",
        )

    update_data = updates.model_dump(
        exclude_unset=True
    )

    permission = await service.update_permission(
        permission,
        update_data
    )

    return PermissionResponse.model_validate(
        permission,
        from_attributes=True
    )


@router.delete(
    "/permissions/{permission_id}",
    response_model=MessageResponse
)
async def delete_permission(
    permission_id: int,
    current_user: User = Depends(
        require_permission("permission_delete")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    permission = await service.get_permission_by_id(
        permission_id
    )

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission non trouvée",
        )

    if permission.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer une permission système",
        )

    await service.delete_permission(
        permission
    )

    return MessageResponse(
        message="Permission supprimée"
    )


# ============================================================
# USERS
# ============================================================

@router.get(
    "",
    response_model=UserListResponse
)
async def list_users(
    params: UserListParams = Depends(),
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    users, total = await service.search_users(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        role=params.role,
        is_active=params.is_active,
        source=params.source,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    user_responses = [
        UserWithRolesResponse.model_validate(
            user,
            from_attributes=True
        )
        for user in users
    ]

    total_pages = (
        (total + params.page_size - 1)
        // params.page_size
    )

    return UserListResponse(
        users=user_responses,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{user_id}/permissions",
    response_model=list[PermissionResponse]
)
async def get_user_permissions(
    user_id: int,
    current_user: User = Depends(
        require_permission("user_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    from app.services.rbac import RBACService

    rbac = RBACService(db)

    result = await db.execute(
        select(User)
        .where(User.id == user_id)
    )

    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    permissions = await rbac.get_user_permissions(
        user
    )

    if "*" in permissions:
        result = await db.execute(
            select(PermissionModel)
        )

        permissions_list = result.scalars().all()

        permission_responses = [
            PermissionResponse.model_validate(
                permission,
                from_attributes=True
            )
            for permission in permissions_list
        ]

        permission_responses.append(
            PermissionResponse(
                id=0,
                code="*",
                name="Accès total (admin)",
                description=(
                    "Permission wildcard pour administrateurs"
                ),
                module="rbac",
                is_system=True
            )
        )

        return permission_responses

    result = await db.execute(
        select(PermissionModel)
        .where(
            PermissionModel.code.in_(permissions)
        )
    )

    permissions_list = result.scalars().all()

    return [
        PermissionResponse.model_validate(
            permission,
            from_attributes=True
        )
        for permission in permissions_list
    ]


@router.get(
    "/{user_id}",
    response_model=UserWithRolesResponse
)
async def get_user(
    user_id: int,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    return UserWithRolesResponse.model_validate(
        user,
        from_attributes=True
    )


@router.post(
    "",
    response_model=UserWithRolesResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_user(
    user_data: UserCreateAdmin,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    from app.core.config import get_settings

    settings = get_settings()

    if (
        not settings.AUTH_LOCAL_ENABLED
        and user_data.source == "local"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Création d'utilisateurs locaux désactivée",
        )

    from sqlalchemy import text

    existing = await service.db.execute(
        text(
            "SELECT 1 FROM users "
            "WHERE username = :username "
            "OR email = :email"
        ),
        {
            "username": user_data.username,
            "email": user_data.email
        },
    )

    if existing.scalar():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom d'utilisateur ou email déjà utilisé",
        )

    user_dict = user_data.model_dump()

    user = await service.create_user(
        user_dict
    )

    return UserWithRolesResponse.model_validate(
        user,
        from_attributes=True
    )


@router.patch(
    "/{user_id}",
    response_model=UserWithRolesResponse
)
async def update_user(
    user_id: int,
    updates: UserUpdateAdmin,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    update_data = updates.model_dump(
        exclude_unset=True
    )

    user = await service.update_user(
        user,
        update_data
    )

    return UserWithRolesResponse.model_validate(
        user,
        from_attributes=True
    )


@router.post(
    "/{user_id}/toggle-active",
    response_model=UserWithRolesResponse
)
async def toggle_user_active(
    user_id: int,
    toggle: UserToggleActive,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    if (
        user.id == service.current_user.id
        and not toggle.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de désactiver son propre compte",
        )

    user = await service.toggle_active(
        user,
        toggle.is_active
    )

    return UserWithRolesResponse.model_validate(
        user,
        from_attributes=True
    )


@router.post(
    "/{user_id}/reset-password",
    response_model=MessageResponse
)
async def reset_password(
    user_id: int,
    reset_data: AdminPasswordReset,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    if user.source != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de réinitialiser le mot de passe pour un compte AD",
        )

    await service.reset_password(
        user,
        reset_data.new_password
    )

    return MessageResponse(
        message="Mot de passe réinitialisé"
    )


@router.delete(
    "/{user_id}",
    response_model=MessageResponse
)
async def delete_user(
    user_id: int,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    if user.id == service.current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer son propre compte",
        )

    await service.delete_user(user)

    return MessageResponse(
        message="Utilisateur supprimé"
    )


@router.post(
    "/{user_id}/roles",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED
)
async def assign_role_to_user(
    user_id: int,
    role_assign: RoleAssignRequest,
    current_user: User = Depends(
        require_permission("user_manage_roles")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    role = await service.get_role_by_id(
        role_assign.role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    if not role.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce rôle n'est pas actif",
        )

    try:
        await service.assign_role(
            user_id,
            role_assign.role_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return RoleResponse.model_validate(
        role,
        from_attributes=True
    )


@router.delete(
    "/{user_id}/roles/{role_id}",
    response_model=MessageResponse
)
async def remove_role_from_user(
    user_id: int,
    role_id: int,
    current_user: User = Depends(
        require_permission("user_manage_roles")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    role = await service.get_role_by_id(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    removed = await service.remove_role(
        user_id,
        role_id
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ce rôle n'est pas assigné à l'utilisateur",
        )

    return MessageResponse(
        message="Rôle retiré de l'utilisateur"
    )