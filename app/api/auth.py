from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

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
    hash_password,
    verify_password,
)
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
)

class AuthSettingsResponse(BaseModel):
    auth_local_enabled: bool
    ad_enabled: bool

from app.models.user import User
from app.core.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(
    response: Response,
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_local(db, credentials.username, credentials.password)

    if not user and settings.AD_ENABLED:
        user = await authenticate_ad(db, credentials.username, credentials.password)

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
async def logout(response: Response):
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

    user = await create_user(db, user_data.model_dump())
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

    user = await update_user(db, current_user, update_data)
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

    user = await create_user(db, user_data.model_dump())
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
    user = await update_user(db, user, update_data)
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

    await update_user(db, user, {"password": reset_data.new_password})
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

    await db.delete(user)
    await db.commit()
    return MessageResponse(message="Utilisateur supprimé")


@router.get("/settings", response_model=AuthSettingsResponse)
async def get_auth_settings():
    return AuthSettingsResponse(
        auth_local_enabled=settings.AUTH_LOCAL_ENABLED,
        ad_enabled=settings.AD_ENABLED,
    )