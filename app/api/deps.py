
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.module import Module, ModuleStatus
from app.models.user import User
from app.core.config import get_settings
from app.services.auth import (
    authenticate_sso,
    decode_token,
    get_user_by_id,
)
from app.services.rbac import RBACService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Non authentifié",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise credentials_exception

    token_data = decode_token(token)
    if not token_data:
        raise credentials_exception

    user = await get_user_by_id(db, token_data.user_id)
    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé",
        )
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    rbac = RBACService(db)
    if not await rbac.user_has_permission(current_user, "admin.access"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès administrateur requis",
        )
    return current_user


def require_permission(permission_code: str):
    async def dependency(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        rbac = RBACService(db)
        has_perm = await rbac.user_has_permission(current_user, permission_code)
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission_code}' requise"
            )
        return current_user
    return dependency


def require_any_permission(*permission_codes: str):
    async def dependency(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        rbac = RBACService(db)
        has_perm = await rbac.user_has_any_permission(current_user, list(permission_codes))
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"L'une des permissions suivantes est requise: {', '.join(permission_codes)}"
            )
        return current_user
    return dependency


def require_all_permissions(*permission_codes: str):
    async def dependency(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        rbac = RBACService(db)
        has_perm = await rbac.user_has_all_permissions(current_user, list(permission_codes))
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Toutes les permissions suivantes sont requises: {', '.join(permission_codes)}"
            )
        return current_user
    return dependency


def require_module_enabled(*module_codes: str):
    """Dependency bloquant l'accès si l'un des modules est désactivé.

    La base est la source de vérité (statut `modules.status`). Un code sans
    ligne en base n'est pas bloqué (module non synchronisé).
    """
    async def dependency(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if module_codes:
            result = await db.execute(
                select(Module.code, Module.status).where(Module.code.in_(module_codes))
            )
            statuses = {code: st for code, st in result.all()}
            for code in module_codes:
                module_status = statuses.get(code)
                if module_status is not None and module_status != ModuleStatus.ACTIVE:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Module '{code}' désactivé",
                    )
        return current_user
    return dependency


async def get_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return None

    token_data = decode_token(token)
    if not token_data:
        return None

    user = await get_user_by_id(db, token_data.user_id)
    if not user or not user.is_active:
        return None

    return user


def _generate_csrf_token() -> str:
    """Generate a secure CSRF token."""
    import secrets
    return secrets.token_urlsafe(32)


async def _validate_csrf_token(request: Request, settings) -> bool:
    """Validate CSRF token from cookie and header.
    
    For SSO, we use a double-submit cookie pattern:
    - Cookie set by frontend when loading login page
    - Header sent by frontend on SSO request
    Both must match and be present.
    """
    cookie_name = settings.AD_SSO_CSRF_COOKIE_NAME
    header_name = settings.AD_SSO_CSRF_HEADER_NAME
    
    csrf_cookie = request.cookies.get(cookie_name)
    csrf_header = request.headers.get(header_name)
    
    if not csrf_cookie or not csrf_header:
        return False
    
    # Constant-time comparison
    import hmac
    return hmac.compare_digest(csrf_cookie, csrf_header)


async def get_sso_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate user via Kerberos/SPNEGO SSO.
    
    Only accepts identity from a trusted reverse proxy (Apache with mod_auth_gssapi).
    The proxy must:
    1. Validate Kerberos ticket
    2. Strip client-provided identity headers
    3. Set X-Remote-User header after successful authentication
    
    Security:
    - Verifies request comes from trusted proxy IP (TCP peer address)
    - Validates CSRF token (double-submit cookie pattern)
    - Never trusts X-Forwarded-For or client-provided headers for identity
    """
    settings = get_settings()
    
    if not settings.AD_SSO_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SSO non activé",
        )

    # Verify request comes from trusted proxy (real TCP peer address)
    client_ip = request.client.host if request.client else None
    if client_ip not in settings.AD_SSO_TRUSTED_PROXY_IPS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès SSO non autorisé depuis cette adresse",
        )

    # Validate CSRF token (double-submit cookie pattern)
    if not await _validate_csrf_token(request, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF invalide ou manquant",
        )

    # Get identity from trusted header (set by Apache after Kerberos validation)
    header_name = settings.AD_SSO_HEADER_NAME
    remote_user = request.headers.get(header_name)
    if not remote_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identité SSO non fournie par le proxy de confiance",
        )

    # Authenticate/creating user via SSO (no password needed)
    user = await authenticate_sso(db, remote_user)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Utilisateur AD non autorisé ou introuvable",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé",
        )

    return user