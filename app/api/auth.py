from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel, ConfigDict
from typing import Optional, List

from app.db.session import get_db
from app.api.deps import get_current_user, get_current_active_user, require_admin
from app.services.auth import (
    authenticate_local,
    authenticate_ad,
    create_tokens,
    decode_refresh_token,
    get_user_by_id,
    update_last_login,
    create_user,
    update_user,
    logout_user,
    hash_password,
    verify_password,
)
from app.services.audit import get_audit_service
from app.services.ad import DatabaseADService
from app.schemas.auth import (
    Token,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    UserResponse,
    UserCreate,
    UserCreateAdmin,
    UserUpdate,
    UserPasswordUpdate,
    AdminPasswordReset,
    MessageResponse,
    ErrorResponse,
    ADSettingsResponse,
    ADSettingsUpdate,
    ADTestRequest,
    ADTestResponse,
)

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
    user_dn: Optional[str] = None
    user_search_filter: str = "(sAMAccountName={username})"
    group_search_base: Optional[str] = None
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
    name: Optional[str] = None
    is_default: Optional[bool] = None
    server: Optional[str] = None
    port: Optional[int] = None
    use_ssl: Optional[bool] = None
    base_dn: Optional[str] = None
    user_dn: Optional[str] = None
    user_search_filter: Optional[str] = None
    group_search_base: Optional[str] = None
    bind_user: Optional[str] = None
    bind_password: Optional[str] = None
    connect_timeout: Optional[int] = None
    receive_timeout: Optional[int] = None
    page_size: Optional[int] = None
    follow_referrals: Optional[bool] = None
    is_active: Optional[bool] = None


class ADConfigResponse(ADConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    created_at: datetime
    updated_at: datetime
    bind_password: str = ""


class ADGroupMappingBase(BaseModel):
    ad_group_cn: str
    ad_group_dn: Optional[str] = None
    role_code: str
    is_active: bool = True


class ADGroupMappingCreate(ADGroupMappingBase):
    pass


class ADGroupMappingUpdate(BaseModel):
    ad_group_cn: Optional[str] = None
    ad_group_dn: Optional[str] = None
    role_code: Optional[str] = None
    is_active: Optional[bool] = None


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
    completed_at: Optional[datetime]
    users_processed: int
    users_created: int
    users_updated: int
    users_deactivated: int
    groups_processed: int
    groups_created: int
    groups_updated: int
    error_message: Optional[str]
    details: Optional[dict]
    triggered_by: Optional[int]


from app.models.user import User
from app.core.config import get_settings
from datetime import datetime

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
    await db.refresh(user)
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

    return LoginResponse(user=UserResponse.model_validate(user), tokens=tokens)


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
async def get_me(current_user: User = Depends(get_current_active_user)):
    return UserResponse.model_validate(current_user)


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
    if "role" in update_data and not current_user.is_admin:
        del update_data["role"]
    if "is_active" in update_data and not current_user.is_admin:
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
            "is_admin": user.is_admin,
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


@router.get("/ad-settings", response_model=ADSettingsResponse)
async def get_ad_settings(current_user: User = Depends(require_admin)):
    return ADSettingsResponse(
        ad_enabled=settings.AD_ENABLED,
        ad_server=settings.AD_SERVER,
        ad_port=settings.AD_PORT,
        ad_use_ssl=settings.AD_USE_SSL,
        ad_base_dn=settings.AD_BASE_DN,
        ad_user_dn=settings.AD_USER_DN,
        ad_user_search_filter=settings.AD_USER_SEARCH_FILTER,
        ad_group_search_base=settings.AD_GROUP_SEARCH_BASE,
        ad_admin_group=settings.AD_ADMIN_GROUP,
        ad_bind_user=settings.AD_BIND_USER,
        ad_bind_password="",
        ad_connect_timeout=settings.AD_CONNECT_TIMEOUT,
        ad_receive_timeout=settings.AD_RECEIVE_TIMEOUT,
    )


@router.put("/ad-settings", response_model=ADSettingsResponse)
async def update_ad_settings(
    updates: ADSettingsUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    import os
    from pathlib import Path

    audit = await get_audit_service(db)

    old_values = {
        "ad_enabled": settings.AD_ENABLED,
        "ad_server": settings.AD_SERVER,
        "ad_port": settings.AD_PORT,
        "ad_use_ssl": settings.AD_USE_SSL,
        "ad_base_dn": settings.AD_BASE_DN,
        "ad_user_dn": settings.AD_USER_DN,
        "ad_user_search_filter": settings.AD_USER_SEARCH_FILTER,
        "ad_group_search_base": settings.AD_GROUP_SEARCH_BASE,
        "ad_admin_group": settings.AD_ADMIN_GROUP,
        "ad_bind_user": settings.AD_BIND_USER,
        "ad_connect_timeout": settings.AD_CONNECT_TIMEOUT,
        "ad_receive_timeout": settings.AD_RECEIVE_TIMEOUT,
    }

    env_path = Path(".env")
    env_vars = {}

    def strip_quotes(value: str) -> str:
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        return value

    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = strip_quotes(value.strip())

    update_data = updates.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        env_key = key.upper()
        if value is not None:
            if isinstance(value, bool):
                env_vars[env_key] = "true" if value else "false"
            else:
                env_vars[env_key] = str(value)

    def quote_value(key: str, value: str) -> str:
        if key in {"APP_NAME", "APP_VERSION", "SECRET_KEY", "ALGORITHM", "DATABASE_URL", "AD_SERVER", "AD_BASE_DN", "AD_USER_DN", "AD_USER_SEARCH_FILTER", "AD_GROUP_SEARCH_BASE", "AD_ADMIN_GROUP", "AD_BIND_USER", "AD_BIND_PASSWORD"}:
            return f'"{value}"'
        if key in {"CORS_ORIGINS", "AD_GROUP_MAPPING"}:
            return f"'{value}'"
        return value

    with open(env_path, "w") as f:
        f.write("# Application\n")
        f.write(f'APP_NAME={quote_value("APP_NAME", env_vars.get("APP_NAME", "ForgeAI Demo"))}\n')
        f.write(f'APP_VERSION={quote_value("APP_VERSION", env_vars.get("APP_VERSION", "1.0.0"))}\n')
        f.write(f'DEBUG={env_vars.get("DEBUG", "true")}\n\n')

        f.write("# SECURITY\n")
        f.write(f'SECRET_KEY={quote_value("SECRET_KEY", env_vars.get("SECRET_KEY", ""))}\n\n')

        f.write("# JWT\n")
        f.write(f'ALGORITHM={quote_value("ALGORITHM", env_vars.get("ALGORITHM", "HS256"))}\n')
        f.write(f'ACCESS_TOKEN_EXPIRE_MINUTES={env_vars.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30")}\n')
        f.write(f'REFRESH_TOKEN_EXPIRE_DAYS={env_vars.get("REFRESH_TOKEN_EXPIRE_DAYS", "7")}\n\n')

        f.write("# Database\n")
        f.write(f'DATABASE_URL={quote_value("DATABASE_URL", env_vars.get("DATABASE_URL", ""))}\n')
        f.write(f'DATABASE_POOL_SIZE={env_vars.get("DATABASE_POOL_SIZE", "5")}\n')
        f.write(f'DATABASE_MAX_OVERFLOW={env_vars.get("DATABASE_MAX_OVERFLOW", "10")}\n\n')

        f.write("# CORS\n")
        f.write(f'CORS_ORIGINS={quote_value("CORS_ORIGINS", env_vars.get("CORS_ORIGINS", '["http://localhost:3000"]'))}\n\n')

        f.write("# Local Authentication\n")
        f.write(f'AUTH_LOCAL_ENABLED={env_vars.get("AUTH_LOCAL_ENABLED", "true")}\n')
        f.write(f'BCRYPT_ROUNDS={env_vars.get("BCRYPT_ROUNDS", "12")}\n\n')

        f.write("# Active Directory / LDAP Configuration\n")
        f.write(f'AD_ENABLED={env_vars.get("AD_ENABLED", "false")}\n')
        f.write(f'AD_SERVER={quote_value("AD_SERVER", env_vars.get("AD_SERVER", ""))}\n')
        f.write(f'AD_PORT={env_vars.get("AD_PORT", "636")}\n')
        f.write(f'AD_USE_SSL={env_vars.get("AD_USE_SSL", "true")}\n')
        f.write(f'AD_BASE_DN={quote_value("AD_BASE_DN", env_vars.get("AD_BASE_DN", ""))}\n')
        f.write(f'AD_USER_DN={quote_value("AD_USER_DN", env_vars.get("AD_USER_DN", ""))}\n')
        f.write(f'AD_USER_SEARCH_FILTER={quote_value("AD_USER_SEARCH_FILTER", env_vars.get("AD_USER_SEARCH_FILTER", "(sAMAccountName={username})"))}\n')
        f.write(f'AD_GROUP_SEARCH_BASE={quote_value("AD_GROUP_SEARCH_BASE", env_vars.get("AD_GROUP_SEARCH_BASE", ""))}\n')
        f.write(f'AD_ADMIN_GROUP={quote_value("AD_ADMIN_GROUP", env_vars.get("AD_ADMIN_GROUP", ""))}\n')
        f.write(f'AD_BIND_USER={quote_value("AD_BIND_USER", env_vars.get("AD_BIND_USER", ""))}\n')
        f.write(f'AD_BIND_PASSWORD={quote_value("AD_BIND_PASSWORD", env_vars.get("AD_BIND_PASSWORD", ""))}\n')
        f.write(f'AD_CONNECT_TIMEOUT={env_vars.get("AD_CONNECT_TIMEOUT", "10")}\n')
        f.write(f'AD_RECEIVE_TIMEOUT={env_vars.get("AD_RECEIVE_TIMEOUT", "10")}\n')
        f.write(f'AD_GROUP_MAPPING={quote_value("AD_GROUP_MAPPING", env_vars.get("AD_GROUP_MAPPING", '{"admin": "AppAdmins", "user": "AppUsers"}'))}\n\n')

        f.write("# Rate Limiting\n")
        f.write(f'RATE_LIMIT_ENABLED={env_vars.get("RATE_LIMIT_ENABLED", "true")}\n')
        f.write(f'RATE_LIMIT_REQUESTS={env_vars.get("RATE_LIMIT_REQUESTS", "10")}\n')
        f.write(f'RATE_LIMIT_WINDOW_SECONDS={env_vars.get("RATE_LIMIT_WINDOW_SECONDS", "60")}\n')

    get_settings.cache_clear()

    new_settings = get_settings()

    new_values = {
        "ad_enabled": new_settings.AD_ENABLED,
        "ad_server": new_settings.AD_SERVER,
        "ad_port": new_settings.AD_PORT,
        "ad_use_ssl": new_settings.AD_USE_SSL,
        "ad_base_dn": new_settings.AD_BASE_DN,
        "ad_user_dn": new_settings.AD_USER_DN,
        "ad_user_search_filter": new_settings.AD_USER_SEARCH_FILTER,
        "ad_group_search_base": new_settings.AD_GROUP_SEARCH_BASE,
        "ad_admin_group": new_settings.AD_ADMIN_GROUP,
        "ad_bind_user": new_settings.AD_BIND_USER,
        "ad_connect_timeout": new_settings.AD_CONNECT_TIMEOUT,
        "ad_receive_timeout": new_settings.AD_RECEIVE_TIMEOUT,
    }

    await audit.log(
        action="ad_config_update",
        module="ad",
        user=current_user,
        object_type="ad_config",
        object_id="env",
        old_values=old_values,
        new_values=new_values,
        status="success",
    )

    return ADSettingsResponse(
        ad_enabled=new_settings.AD_ENABLED,
        ad_server=new_settings.AD_SERVER,
        ad_port=new_settings.AD_PORT,
        ad_use_ssl=new_settings.AD_USE_SSL,
        ad_base_dn=new_settings.AD_BASE_DN,
        ad_user_dn=new_settings.AD_USER_DN,
        ad_user_search_filter=new_settings.AD_USER_SEARCH_FILTER,
        ad_group_search_base=new_settings.AD_GROUP_SEARCH_BASE,
        ad_admin_group=new_settings.AD_ADMIN_GROUP,
        ad_bind_user=new_settings.AD_BIND_USER,
        ad_bind_password="",
        ad_connect_timeout=new_settings.AD_CONNECT_TIMEOUT,
        ad_receive_timeout=new_settings.AD_RECEIVE_TIMEOUT,
    )


@router.post("/ad-test", response_model=ADTestResponse)
async def test_ad_connection(
    test_data: ADTestRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.auth import ldap_service
    from app.services.audit import get_audit_service

    audit = await get_audit_service(db)

    success, message, details = ldap_service.test_connection(
        server_url=f"{'ldaps' if test_data.ad_use_ssl else 'ldap'}://{test_data.ad_server}:{test_data.ad_port}",
        use_ssl=test_data.ad_use_ssl,
        base_dn=test_data.ad_base_dn,
        bind_user=test_data.ad_bind_user,
        bind_password=test_data.ad_bind_password,
        connect_timeout=test_data.ad_connect_timeout,
        receive_timeout=test_data.ad_receive_timeout,
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
        },
        status="success" if success else "failure",
        error_message=details if not success else None,
    )

    return ADTestResponse(success=success, message=message, details=details)


@router.get("/ad-configs", response_model=List[ADConfigResponse])
async def list_ad_configs(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    ad_service = DatabaseADService(db)
    configs = await ad_service.get_active_configs()
    return [ADConfigResponse.model_validate(c) for c in configs]


@router.post("/ad-configs", response_model=ADConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_ad_config(
    config_data: ADConfigCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)

    if config_data.is_default:
        await db.execute(
            select(ADConfig).where(ADConfig.is_default == True)
        )
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
    await db.commit()
    await db.refresh(config)

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

    response = ADConfigResponse.model_validate(config)
    response.bind_password = ""
    return response


@router.get("/ad-configs/{config_id}", response_model=ADConfigResponse)
async def get_ad_config(
    config_id: int,
    current_user: User = Depends(require_admin),
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
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
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
    if "is_default" in update_data and update_data["is_default"]:
        await db.execute(
            select(ADConfig).where(ADConfig.is_default == True)
        )
        existing_default = await db.execute(
            select(ADConfig).where(ADConfig.is_default == True)
        )
        for cfg in existing_default.scalars().all():
            if cfg.id != config_id:
                cfg.is_default = False

    for key, value in update_data.items():
        setattr(config, key, value)

    config.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(config)

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

    response = ADConfigResponse.model_validate(config)
    response.bind_password = ""
    return response


@router.delete("/ad-configs/{config_id}", response_model=MessageResponse)
async def delete_ad_config(
    config_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)

    ad_service = DatabaseADService(db)
    config = await ad_service.get_config_by_id(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration AD non trouvée")

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
    return MessageResponse(message="Configuration AD supprimée")


@router.get("/ad-configs/{config_id}/mappings", response_model=List[ADGroupMappingResponse])
async def list_ad_group_mappings(
    config_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    result = await db.execute(
        select(ADGroupMapping).where(ADGroupMapping.ad_config_id == config_id)
    )
    mappings = result.scalars().all()
    return [ADGroupMappingResponse.model_validate(m) for m in mappings]


@router.post("/ad-configs/{config_id}/mappings", response_model=ADGroupMappingResponse, status_code=status.HTTP_201_CREATED)
async def create_ad_group_mapping(
    config_id: int,
    mapping_data: ADGroupMappingCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)

    config = await db.get(ADConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration AD non trouvée")

    mapping = ADGroupMapping(
        ad_config_id=config_id,
        ad_group_cn=mapping_data.ad_group_cn,
        ad_group_dn=mapping_data.ad_group_dn,
        role_code=mapping_data.role_code,
        is_active=mapping_data.is_active,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)

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

    return ADGroupMappingResponse.model_validate(mapping)


@router.patch("/ad-configs/{config_id}/mappings/{mapping_id}", response_model=ADGroupMappingResponse)
async def update_ad_group_mapping(
    config_id: int,
    mapping_id: int,
    updates: ADGroupMappingUpdate,
    current_user: User = Depends(require_admin),
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

    old_values = {
        "ad_group_cn": mapping.ad_group_cn,
        "ad_group_dn": mapping.ad_group_dn,
        "role_code": mapping.role_code,
        "is_active": mapping.is_active,
    }

    update_data = updates.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(mapping, key, value)

    mapping.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(mapping)

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
        object_repr=f"{config.name} -> {mapping.ad_group_cn}",
        old_values=old_values,
        new_values=new_values,
        status="success",
    )

    return ADGroupMappingResponse.model_validate(mapping)


@router.delete("/ad-configs/{config_id}/mappings/{mapping_id}", response_model=MessageResponse)
async def delete_ad_group_mapping(
    config_id: int,
    mapping_id: int,
    current_user: User = Depends(require_admin),
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
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    ad_service = DatabaseADService(db, current_user=current_user)
    config = await ad_service.get_config_by_id(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration AD non trouvée")

    sync_log = await ad_service.sync_users(config)
    return ADSyncLogResponse.model_validate(sync_log)


@router.get("/ad-configs/{config_id}/sync-logs", response_model=List[ADSyncLogResponse])
async def list_ad_sync_logs(
    config_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
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
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import get_audit_service
    audit = await get_audit_service(db)

    ad_service = DatabaseADService(db)
    success, message, details = ad_service.test_connection(
        server_url=f"{'ldaps' if test_data.ad_use_ssl else 'ldap'}://{test_data.ad_server}:{test_data.ad_port}",
        use_ssl=test_data.ad_use_ssl,
        base_dn=test_data.ad_base_dn,
        bind_user=test_data.ad_bind_user,
        bind_password=test_data.ad_bind_password,
        connect_timeout=test_data.ad_connect_timeout,
        receive_timeout=test_data.ad_receive_timeout,
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
        },
        status="success" if success else "failure",
        error_message=details if not success else None,
    )

    return ADTestResponse(success=success, message=message, details=details)