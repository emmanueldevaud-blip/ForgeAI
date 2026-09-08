
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, require_admin, require_permission
from app.db.session import get_db
from app.models import ADConfig, ADGroupMapping, ADSyncLog, Group, Role
from app.models.user import User, UserRole
from app.schemas.auth import (
    AdminPasswordReset,
    ADTestRequest,
    ADTestResponse,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RefreshTokenRequest,
    Token,
    UserCreate,
    UserCreateAdmin,
    UserPasswordUpdate,
    UserResponse,
    UserUpdate,
)
from app.services.ad import DatabaseADService, get_ad_service
from app.services.audit import get_audit_service
from app.services.auth import (
    authenticate_ad,
    authenticate_local,
    create_tokens,
    create_user,
    decode_refresh_token,
    get_user_by_id,
    logout_user,
    update_last_login,
    update_user,
    verify_password,
)
from app.services.rbac import RBACService


class AuthSettingsResponse(BaseModel):
    auth_local_enabled: bool
    ad_enabled: bool


class ADConfigBase(BaseModel):
    name: str
    is_default: bool = False
    server: str
    port: int = 636
    use_ssl: bool = True
    base_dn: str
    user_dn: str | None = None
    user_search_filter: str = "(sAMAccountName={username})"
    group_search_filter: str = "(&(objectCategory=group)(cn=GG_FORGEAI*))"
    group_search_base: str | None = None
    bind_user: str
    bind_password: str
    connect_timeout: int = 10
    receive_timeout: int = 10
    page_size: int = 1000
    follow_referrals: bool = False
    is_active: bool = True


class ADConfigCreate(ADConfigBase):
    pass


class ADConfigUpdate(BaseModel):
    name: str | None = None
    is_default: bool | None = None
    server: str | None = None
    port: int | None = None
    use_ssl: bool | None = None
    base_dn: str | None = None
    user_dn: str | None = None
    user_search_filter: str | None = None
    group_search_filter: str | None = None
    group_search_base: str | None = None
    bind_user: str | None = None
    bind_password: str | None = None
    connect_timeout: int | None = None
    receive_timeout: int | None = None
    page_size: int | None = None
    follow_referrals: bool | None = None
    is_active: bool | None = None


class ADConfigResponse(ADConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_sync_at: datetime | None
    last_sync_status: str | None
    created_at: datetime
    updated_at: datetime
    bind_password: str = ""


class ADGroupMappingBase(BaseModel):
    ad_group_cn: str
    ad_group_dn: str | None = None
    role_code: str
    is_active: bool = True


class ADGroupMappingCreate(ADGroupMappingBase):
    pass


class ADGroupMappingUpdate(BaseModel):
    ad_group_cn: str | None = None
    ad_group_dn: str | None = None
    role_code: str | None = None
    is_active: bool | None = None


class ADGroupMappingResponse(ADGroupMappingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ad_config_id: int
    created_at: datetime
    updated_at: datetime


class ADSyncLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ad_config_id: int
    status: str
    started_at: datetime
    completed_at: datetime | None
    users_processed: int
    users_created: int
    users_updated: int
    users_deactivated: int
    groups_processed: int
    groups_created: int
    groups_updated: int
    error_message: str | None
    details: dict | None
    triggered_by: int | None


async def user_response_with_authorization(db: AsyncSession, user: User) -> UserResponse:
    """Return identity and backend-computed RBAC data for the authenticated UI."""
    permissions = await RBACService(db).get_user_permissions(user)
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_active=user.is_active,
        role=user.role.value,
        source=user.source,
        last_login=user.last_login,
        created_at=user.created_at,
        updated_at=user.updated_at,
        roles=sorted(role.code for role in user.roles if role.is_active),
        groups=sorted(group.code for group in user.groups if group.is_active),
        permissions=sorted(permissions),
    )


from app.core.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(
    response: Response,
    credentials: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user = await authenticate_local(
        db,
        credentials.username,
        credentials.password,
        audit=audit,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if not user and settings.AD_ENABLED:
        user = await authenticate_ad(
            db,
            credentials.username,
            credentials.password,
            audit=audit,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await update_last_login(db, user)
    # Authentication helpers may have loaded only the scalar user.  Reload the
    # RBAC graph before serialising effective permissions for the client.
    user = await get_user_by_id(db, user.id)
    tokens = create_tokens(user)

    cookie_secure = not settings.DEBUG
    cookie_samesite = "lax" if settings.DEBUG else "none"

    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )

    return LoginResponse(user=await user_response_with_authorization(db, user), tokens=tokens)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    await logout_user(db, current_user, audit=audit)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return MessageResponse(message="Déconnexion réussie")


@router.post("/refresh", response_model=Token)
async def refresh_token(
    response: Response,
    refresh_request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    token_data = decode_refresh_token(refresh_request.refresh_token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de rafraîchissement invalide",
        )

    user = await get_user_by_id(db, token_data.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé ou inactif",
        )

    tokens = create_tokens(user)

    cookie_secure = not settings.DEBUG
    cookie_samesite = "lax" if settings.DEBUG else "none"

    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )

    return tokens


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await user_response_with_authorization(db, current_user)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not settings.AUTH_LOCAL_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inscription locale désactivée",
        )

    existing = await db.execute(
        text("SELECT 1 FROM users WHERE username = :username OR email = :email"),
        {"username": user_data.username, "email": user_data.email},
    )
    if existing.scalar():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom d'utilisateur ou email déjà utilisé",
        )

    audit = await get_audit_service(db)
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    user = await create_user(db, user_data.model_dump(), audit=audit, current_user=None)
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    updates: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    update_data = updates.model_dump(exclude_unset=True)
    if "role" in update_data and current_user.role != UserRole.ADMIN:
        del update_data["role"]
    if "is_active" in update_data and current_user.role != UserRole.ADMIN:
        del update_data["is_active"]

    audit = await get_audit_service(db)
    user = await update_user(db, current_user, update_data, audit=audit, current_user=current_user)
    return UserResponse.model_validate(user)


@router.post("/me/password", response_model=MessageResponse)
async def change_password(
    passwords: UserPasswordUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.source != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de changer le mot de passe pour un compte AD",
        )

    if not current_user.password_hash or not verify_password(passwords.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe actuel incorrect",
        )

    await update_user(db, current_user, {"password": passwords.new_password})
    return MessageResponse(message="Mot de passe mis à jour")


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user_admin(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )
    return UserResponse.model_validate(user)


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_admin(
    user_data: UserCreateAdmin,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not settings.AUTH_LOCAL_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Création d'utilisateurs locaux désactivée",
        )

    existing = await db.execute(
        text("SELECT 1 FROM users WHERE username = :username OR email = :email"),
        {"username": user_data.username, "email": user_data.email},
    )
    if existing.scalar():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom d'utilisateur ou email déjà utilisé",
        )

    audit = await get_audit_service(db)
    user = await create_user(db, user_data.model_dump(), audit=audit, current_user=current_user)
    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user_admin(
    user_id: int,
    updates: UserUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    update_data = updates.model_dump(exclude_unset=True)
    audit = await get_audit_service(db)
    user = await update_user(db, user, update_data, audit=audit, current_user=current_user)
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/reset-password", response_model=MessageResponse)
async def reset_password_admin(
    user_id: int,
    reset_data: AdminPasswordReset,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
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

    audit = await get_audit_service(db)
    await update_user(db, user, {"password": reset_data.new_password}, audit=audit, current_user=current_user)
    return MessageResponse(message="Mot de passe réinitialisé")


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def delete_user_admin(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer son propre compte",
        )

    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    audit = await get_audit_service(db)
    await audit.log(
        action="user_delete",
        module="users",
        user=current_user,
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

    await db.delete(user)
    await db.commit()
    return MessageResponse(message="Utilisateur supprimé")


@router.get("/settings", response_model=AuthSettingsResponse)
async def get_auth_settings():
    return AuthSettingsResponse(
        auth_local_enabled=settings.AUTH_LOCAL_ENABLED,
        ad_enabled=settings.AD_ENABLED,
    )




@router.get("/ad-configs", response_model=list[ADConfigResponse])
async def list_ad_configs(
    current_user: User = Depends(require_permission("ad_config")),
    db: AsyncSession = Depends(get_db),
):
    ad_service = DatabaseADService(db)
    configs = await ad_service.get_active_configs()
    responses = [ADConfigResponse.model_validate(c) for c in configs]
    for response in responses:
        response.bind_password = ""
    return responses


@router.post("/ad-configs", response_model=ADConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_ad_config(
    config_data: ADConfigCreate,
    current_user: User = Depends(require_permission("ad_config")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from app.models import ADConfig
    audit = await get_audit_service(db)

    if config_data.is_default:
        existing_default = await db.execute(
            select(ADConfig).where(ADConfig.is_default == True)
        )
        for cfg in existing_default.scalars().all():
            cfg.is_default = False

    config = ADConfig(
        name=config_data.name,
        is_default=config_data.is_default,
        server=config_data.server,
        port=config_data.port,
        use_ssl=config_data.use_ssl,
        base_dn=config_data.base_dn,
        user_dn=config_data.user_dn,
        user_search_filter=config_data.user_search_filter,
        group_search_filter=config_data.group_search_filter,
        group_search_base=config_data.group_search_base,
        bind_user=config_data.bind_user,
        bind_password=config_data.bind_password,
        connect_timeout=config_data.connect_timeout,
        receive_timeout=config_data.receive_timeout,
        page_size=config_data.page_size,
        follow_referrals=config_data.follow_referrals,
        is_active=config_data.is_active,
    )
    db.add(config)
    try:
        await db.commit()
        await db.refresh(config)
    except IntegrityError as e:
        await db.rollback()
        if "ad_configs_name" in str(e.orig) or "uq_ad_configs_name" in str(e.orig) or "ix_ad_configs_name" in str(e.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Une configuration avec ce nom existe déjà"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur de base de données: {e.orig}"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création: {str(e)}"
        )

    await audit.log(
        action="ad_config_create",
        module="ad",
        user=current_user,
        object_type="ad_config",
        object_id=str(config.id),
        object_repr=config.name,
        new_values={
            "name": config.name,
            "is_default": config.is_default,
            "server": config.server,
            "port": config.port,
            "use_ssl": config.use_ssl,
            "base_dn": config.base_dn,
            "bind_user": config.bind_user,
            "connect_timeout": config.connect_timeout,
            "receive_timeout": config.receive_timeout,
            "page_size": config.page_size,
            "follow_referrals": config.follow_referrals,
            "is_active": config.is_active,
        },
        status="success",
    )
    await db.commit()

    response = ADConfigResponse.model_validate(config)
    response.bind_password = ""
    return response


@router.get("/ad-configs/{config_id}", response_model=ADConfigResponse)
async def get_ad_config(
    config_id: int,
    current_user: User = Depends(require_permission("ad_config")),
    db: AsyncSession = Depends(get_db),
):
    ad_service = DatabaseADService(db)
    config = await ad_service.get_config_by_id(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration AD non trouvée")
    response = ADConfigResponse.model_validate(config)
    response.bind_password = ""
    return response


@router.patch("/ad-configs/{config_id}", response_model=ADConfigResponse)
async def update_ad_config(
    config_id: int,
    updates: ADConfigUpdate,
    current_user: User = Depends(require_permission("ad_config")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    from sqlalchemy.exc import IntegrityError
    audit = await get_audit_service(db)

    ad_service = DatabaseADService(db)
    config = await ad_service.get_config_by_id(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration AD non trouvée")

    old_values = {
        "name": config.name,
        "is_default": config.is_default,
        "server": config.server,
        "port": config.port,
        "use_ssl": config.use_ssl,
        "base_dn": config.base_dn,
        "user_dn": config.user_dn,
        "user_search_filter": config.user_search_filter,
        "group_search_base": config.group_search_base,
        "bind_user": config.bind_user,
        "connect_timeout": config.connect_timeout,
        "receive_timeout": config.receive_timeout,
        "page_size": config.page_size,
        "follow_referrals": config.follow_referrals,
        "is_active": config.is_active,
    }

    update_data = updates.model_dump(exclude_unset=True)
    if update_data.get("bind_password") == "":
        update_data.pop("bind_password")
    if update_data.get("is_default"):
        existing_default = await db.execute(
            select(ADConfig).where(ADConfig.is_default == True)
        )
        for cfg in existing_default.scalars().all():
            if cfg.id != config_id:
                cfg.is_default = False

    for key, value in update_data.items():
        setattr(config, key, value)

    config.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
        await db.refresh(config)
    except IntegrityError as e:
        await db.rollback()
        if "ad_configs_name" in str(e.orig) or "uq_ad_configs_name" in str(e.orig) or "ix_ad_configs_name" in str(e.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Une configuration avec ce nom existe déjà"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur de base de données: {e.orig}"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la mise à jour: {str(e)}"
        )

    new_values = {
        "name": config.name,
        "is_default": config.is_default,
        "server": config.server,
        "port": config.port,
        "use_ssl": config.use_ssl,
        "base_dn": config.base_dn,
        "user_dn": config.user_dn,
        "user_search_filter": config.user_search_filter,
        "group_search_base": config.group_search_base,
        "bind_user": config.bind_user,
        "connect_timeout": config.connect_timeout,
        "receive_timeout": config.receive_timeout,
        "page_size": config.page_size,
        "follow_referrals": config.follow_referrals,
        "is_active": config.is_active,
    }

    await audit.log(
        action="ad_config_update",
        module="ad",
        user=current_user,
        object_type="ad_config",
        object_id=str(config.id),
        object_repr=config.name,
        old_values=old_values,
        new_values=new_values,
        status="success",
    )
    await db.commit()

    response = ADConfigResponse.model_validate(config)
    response.bind_password = ""
    return response


@router.delete("/ad-configs/{config_id}", response_model=MessageResponse)
async def delete_ad_config(
    config_id: int,
    current_user: User = Depends(require_permission("ad_config")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)

    ad_service = DatabaseADService(db)
    config = await ad_service.get_config_by_id(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration AD non trouvée")

    print(f"[AD-DELETE] config_id={config.id} config_name={config.name} base_dn={config.base_dn}")

    base_dn_lower = config.base_dn.casefold()

    ad_users = await db.execute(
        select(User).where(
            User.source == "ad",
            User.ad_dn.isnot(None),
        )
    )
    all_ad_users = ad_users.scalars().all()
    print(f"[AD-DELETE] total_ad_users_in_db={len(all_ad_users)}")

    users_to_delete = []
    for user in all_ad_users:
        matches = user.ad_dn and user.ad_dn.casefold().endswith(base_dn_lower)
        if matches:
            users_to_delete.append(user)
            print(f"[AD-DELETE] deleting user id={user.id} username={user.username} ad_dn={user.ad_dn}")
        else:
            print(f"[AD-DELETE] skipping user id={user.id} username={user.username} ad_dn={user.ad_dn} (base_dn mismatch)")

    ad_groups = await db.execute(
        select(Group).where(
            Group.source == "ad",
            Group.ad_dn.isnot(None),
        )
    )
    all_ad_groups = ad_groups.scalars().all()
    print(f"[AD-DELETE] total_ad_groups_in_db={len(all_ad_groups)}")

    groups_to_delete = []
    for group in all_ad_groups:
        matches = group.ad_dn and group.ad_dn.casefold().endswith(base_dn_lower)
        if matches:
            groups_to_delete.append(group)
            print(f"[AD-DELETE] deleting group id={group.id} name={group.name} ad_dn={group.ad_dn}")
        else:
            print(f"[AD-DELETE] skipping group id={group.id} name={group.name} ad_dn={group.ad_dn} (base_dn mismatch)")

    for user in users_to_delete:
        await db.delete(user)
    for group in groups_to_delete:
        await db.delete(group)

    print(f"[AD-DELETE] users_to_delete={len(users_to_delete)} groups_to_delete={len(groups_to_delete)}")

    await audit.log(
        action="ad_config_delete",
        module="ad",
        user=current_user,
        object_type="ad_config",
        object_id=str(config.id),
        object_repr=config.name,
        old_values={
            "name": config.name,
            "is_default": config.is_default,
            "server": config.server,
            "port": config.port,
            "use_ssl": config.use_ssl,
            "base_dn": config.base_dn,
            "bind_user": config.bind_user,
            "is_active": config.is_active,
        },
        status="success",
    )

    await db.delete(config)
    await db.commit()
    print(f"[AD-DELETE] commit OK — config_id={config_id} deleted")
    return MessageResponse(message="Configuration AD supprimée")


@router.get("/ad-configs/{config_id}/mappings", response_model=list[ADGroupMappingResponse])
async def list_ad_group_mappings(
    config_id: int,
    current_user: User = Depends(require_permission("ad_config")),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(ADConfig, config_id):
        raise HTTPException(status_code=404, detail="Configuration AD non trouvée")

    result = await db.execute(
        select(ADGroupMapping).where(ADGroupMapping.ad_config_id == config_id)
    )
    mappings = result.scalars().all()
    return [ADGroupMappingResponse.model_validate(m) for m in mappings]


@router.post("/ad-configs/{config_id}/mappings", response_model=ADGroupMappingResponse, status_code=status.HTTP_201_CREATED)
async def create_ad_group_mapping(
    config_id: int,
    mapping_data: ADGroupMappingCreate,
    current_user: User = Depends(require_permission("ad_config")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    from sqlalchemy.exc import IntegrityError
    audit = await get_audit_service(db)

    config = await db.get(ADConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration AD non trouvée")
    role = (await db.execute(select(Role).where(Role.code == mapping_data.role_code))).scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le rôle ForgeAI indiqué n'existe pas",
        )

    mapping = ADGroupMapping(
        ad_config_id=config_id,
        ad_group_cn=mapping_data.ad_group_cn,
        ad_group_dn=mapping_data.ad_group_dn,
        role_code=mapping_data.role_code,
        is_active=mapping_data.is_active,
    )
    db.add(mapping)
    try:
        await db.commit()
        await db.refresh(mapping)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un mapping existe déjà pour ce groupe AD",
        )

    await audit.log(
        action="ad_group_mapping_create",
        module="ad",
        user=current_user,
        object_type="ad_group_mapping",
        object_id=str(mapping.id),
        object_repr=f"{config.name} -> {mapping.ad_group_cn}",
        new_values={
            "ad_config_id": mapping.ad_config_id,
            "ad_group_cn": mapping.ad_group_cn,
            "ad_group_dn": mapping.ad_group_dn,
            "role_code": mapping.role_code,
            "is_active": mapping.is_active,
        },
        status="success",
    )
    await db.commit()

    return ADGroupMappingResponse.model_validate(mapping)


@router.patch("/ad-configs/{config_id}/mappings/{mapping_id}", response_model=ADGroupMappingResponse)
async def update_ad_group_mapping(
    config_id: int,
    mapping_id: int,
    updates: ADGroupMappingUpdate,
    current_user: User = Depends(require_permission("ad_config")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    from sqlalchemy.exc import IntegrityError
    audit = await get_audit_service(db)

    result = await db.execute(
        select(ADGroupMapping).where(
            ADGroupMapping.id == mapping_id,
            ADGroupMapping.ad_config_id == config_id
        )
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping de groupe AD non trouvé")

    old_values = {
        "ad_group_cn": mapping.ad_group_cn,
        "ad_group_dn": mapping.ad_group_dn,
        "role_code": mapping.role_code,
        "is_active": mapping.is_active,
    }

    update_data = updates.model_dump(exclude_unset=True)
    if "role_code" in update_data:
        role = (await db.execute(select(Role).where(Role.code == update_data["role_code"]))).scalar_one_or_none()
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Le rôle ForgeAI indiqué n'existe pas",
            )
    for key, value in update_data.items():
        setattr(mapping, key, value)

    mapping.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
        await db.refresh(mapping)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un mapping existe déjà pour ce groupe AD",
        )

    new_values = {
        "ad_group_cn": mapping.ad_group_cn,
        "ad_group_dn": mapping.ad_group_dn,
        "role_code": mapping.role_code,
        "is_active": mapping.is_active,
    }

    await audit.log(
        action="ad_group_mapping_update",
        module="ad",
        user=current_user,
        object_type="ad_group_mapping",
        object_id=str(mapping.id),
        object_repr=f"{mapping.ad_group_cn}",
        old_values=old_values,
        new_values=new_values,
        status="success",
    )
    await db.commit()

    return ADGroupMappingResponse.model_validate(mapping)


@router.delete("/ad-configs/{config_id}/mappings/{mapping_id}", response_model=MessageResponse)
async def delete_ad_group_mapping(
    config_id: int,
    mapping_id: int,
    current_user: User = Depends(require_permission("ad_config")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)

    result = await db.execute(
        select(ADGroupMapping).where(
            ADGroupMapping.id == mapping_id,
            ADGroupMapping.ad_config_id == config_id
        )
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping de groupe AD non trouvé")

    await audit.log(
        action="ad_group_mapping_delete",
        module="ad",
        user=current_user,
        object_type="ad_group_mapping",
        object_id=str(mapping.id),
        object_repr=f"{mapping.ad_group_cn}",
        old_values={
            "ad_group_cn": mapping.ad_group_cn,
            "ad_group_dn": mapping.ad_group_dn,
            "role_code": mapping.role_code,
            "is_active": mapping.is_active,
        },
        status="success",
    )

    await db.delete(mapping)
    await db.commit()
    return MessageResponse(message="Mapping de groupe AD supprimé")


@router.post("/ad-configs/{config_id}/sync", response_model=ADSyncLogResponse)
async def sync_ad_config(
    config_id: int,
    current_user: User = Depends(require_permission("ad_sync")),
    db: AsyncSession = Depends(get_db),
):
    ad_service = await get_ad_service(db, current_user)
    config = await ad_service.get_config_by_id(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration AD non trouvée")
    if not config.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Configuration AD inactive")

    sync_log = await ad_service.sync_users(config)
    return ADSyncLogResponse.model_validate(sync_log)


@router.get("/ad-configs/{config_id}/sync-logs", response_model=list[ADSyncLogResponse])
async def list_ad_sync_logs(
    config_id: int,
    current_user: User = Depends(require_permission("ad_sync")),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(ADConfig, config_id):
        raise HTTPException(status_code=404, detail="Configuration AD non trouvée")

    result = await db.execute(
        select(ADSyncLog)
        .where(ADSyncLog.ad_config_id == config_id)
        .order_by(ADSyncLog.started_at.desc())
    )
    logs = result.scalars().all()
    return [ADSyncLogResponse.model_validate(l) for l in logs]


@router.post("/ad-configs/test", response_model=ADTestResponse)
async def test_ad_config(
    test_data: ADTestRequest,
    current_user: User = Depends(require_permission("ad_test")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)

    ad_service = DatabaseADService(db)
    bind_password = test_data.ad_bind_password
    if not bind_password:
        if test_data.ad_config_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Un mot de passe Bind ou une configuration AD existante est requis",
            )
        config = await ad_service.get_config_by_id(test_data.ad_config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Configuration AD non trouvée")
        bind_password = config.bind_password

    success, message, details = ad_service.test_connection(
        server=test_data.ad_server,
        port=test_data.ad_port,
        use_ssl=test_data.ad_use_ssl,
        base_dn=test_data.ad_base_dn,
        bind_user=test_data.ad_bind_user,
        bind_password=bind_password,
        connect_timeout=test_data.ad_connect_timeout,
        receive_timeout=test_data.ad_receive_timeout,
        follow_referrals=test_data.ad_follow_referrals,
    )

    await audit.log(
        action="ad_test_connection",
        module="ad",
        user=current_user,
        object_type="ad_config",
        object_id="test",
        new_values={
            "ad_server": test_data.ad_server,
            "ad_port": test_data.ad_port,
            "ad_use_ssl": test_data.ad_use_ssl,
            "ad_base_dn": test_data.ad_base_dn,
            "ad_bind_user": test_data.ad_bind_user,
            "ad_connect_timeout": test_data.ad_connect_timeout,
            "ad_receive_timeout": test_data.ad_receive_timeout,
            "ad_follow_referrals": test_data.ad_follow_referrals,
        },
        status="success" if success else "failure",
        error_message=details if not success else None,
    )
    await db.commit()

    return ADTestResponse(success=success, message=message, details=details)
