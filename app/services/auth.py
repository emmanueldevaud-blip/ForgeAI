from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from ldap3 import SUBTREE
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User, UserRole
from app.schemas.auth import Token, TokenData
from app.services.ad import DatabaseADService
from app.services.audit import AuditService

settings = get_settings()

pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
    bcrypt_sha256__rounds=settings.BCRYPT_ROUNDS,
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> TokenData | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "access":
            return None
        return TokenData(
            sub=payload.get("sub"),
            user_id=payload.get("user_id"),
            role=payload.get("role", ""),
            exp=payload.get("exp"),
        )
    except JWTError:
        return None


def decode_refresh_token(token: str) -> TokenData | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return TokenData(
            sub=payload.get("sub"),
            user_id=payload.get("user_id"),
            role=payload.get("role", ""),
            exp=payload.get("exp"),
        )
    except JWTError:
        return None


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user:
        await db.refresh(user)
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    from sqlalchemy.orm import selectinload

    from app.models import Group, Role
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.groups).selectinload(Group.roles).selectinload(Role.permissions)
        )
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    return user


async def authenticate_local(db: AsyncSession, username: str, password: str, audit: AuditService | None = None, ip_address: str | None = None, user_agent: str | None = None) -> User | None:
    user = await get_user_by_username(db, username)
    if not user:
        if audit:
            await audit.log(
                action="login",
                module="auth",
                username=username,
                status="failure",
                error_message="User not found",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return None
    if not user.is_active:
        if audit:
            await audit.log(
                action="login",
                module="auth",
                user=user,
                status="failure",
                error_message="Account disabled",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return None
    if user.source != "local":
        if audit:
            await audit.log(
                action="login",
                module="auth",
                user=user,
                status="failure",
                error_message="Not a local account",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return None
    if not user.password_hash:
        if audit:
            await audit.log(
                action="login",
                module="auth",
                user=user,
                status="failure",
                error_message="No password set",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return None
    if not verify_password(password, user.password_hash):
        if audit:
            await audit.log(
                action="login",
                module="auth",
                user=user,
                status="failure",
                error_message="Invalid password",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return None

    if audit:
        await audit.log(
            action="login",
            module="auth",
            user=user,
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
        )
    return user




async def authenticate_ad(
    db: AsyncSession,
    username: str,
    password: str,
    audit: AuditService | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User | None:
    ad_service = DatabaseADService(db, audit=audit)
    
    user_dn, groups, config, user_info = await ad_service.authenticate(username, password)
    if not user_dn:
        if audit:
            await audit.log(
                action="login",
                module="auth",
                username=username,
                status="failure",
                error_message="AD authentication failed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return None

    result = await db.execute(select(User).where(User.ad_dn == user_dn))
    user = result.scalar_one_or_none()

    if user:
        if user.source != "ad":
            return None
        user.is_active = True
        user.last_login = datetime.now(UTC)
        await ad_service._sync_user_ad_groups(user, groups or [], config)
        await db.commit()
        await db.refresh(user)

        if audit:
            await audit.log(
                action="login",
                module="auth",
                user=user,
                status="success",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return user

    if not config or not user_info:
        return None

    try:
        ad_username = user_info.get("sAMAccountName", username)
        email = user_info.get("mail")
        if not email:
            email = f"{ad_username}@forgeai.local"
        first_name = user_info.get("givenName")
        last_name = user_info.get("sn")

        username_owner = (await db.execute(select(User).where(User.username == ad_username))).scalar_one_or_none()
        if username_owner is not None:
            if username_owner.source != "ad":
                return None
            username_owner.ad_dn = user_dn
            username_owner.is_active = True
            username_owner.last_login = datetime.now(UTC)
            await ad_service._sync_user_ad_groups(username_owner, groups or [], config)
            await db.commit()
            await db.refresh(username_owner)
            return username_owner

        user = User(
            username=ad_username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=None,
            is_active=True,
            source="ad",
            ad_dn=user_dn,
            last_login=datetime.now(UTC),
        )
        try:
            async with db.begin_nested():
                db.add(user)
                await db.flush()
                await ad_service._sync_user_ad_groups(user, groups or [], config)
            await db.commit()
            await db.refresh(user)
        except IntegrityError:
            existing = (await db.execute(select(User).where(User.ad_dn == user_dn))).scalar_one_or_none()
            if existing is None or existing.source != "ad":
                return None
            return existing

        if audit:
            await audit.log(
                action="login",
                module="auth",
                user=user,
                status="success",
                new_values={
                    "username": user.username,
                    "email": user.email,
                    "source": "ad",
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return user

    except Exception as e:
        if audit:
            await audit.log(
                action="login",
                module="auth",
                username=username,
                status="failure",
                error_message=f"AD user creation failed: {e!s}",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return None


async def _user_has_authorized_mapping(
    ad_service: DatabaseADService,
    config,
    user_dn: str,
    entry,
    admin_conn,
) -> tuple[bool, list[str]]:
    """Check if AD user has at least one authorized group mapping.

    Returns (has_mapping, group_dns) where group_dns are the AD groups
    that have active mappings in ForgeAI.

    admin_conn is an open, bound admin LDAP connection owned by the caller.
    Groups are searched with this connection (never by binding as the user,
    which SSO cannot do since it has no user password).
    """
    # Collect user's AD groups
    groups = [str(group) for group in entry.memberOf] if entry.memberOf else []
    if config.group_search_base:
        admin_conn.search(
            search_base=config.group_search_base,
            search_filter=f"(member={escape_filter_chars(user_dn)})",
            search_scope=SUBTREE,
            attributes=["distinguishedName"],
        )
        groups.extend(str(group_entry.distinguishedName) for group_entry in admin_conn.entries if group_entry.distinguishedName)
    
    if not groups:
        return False, []
    
    # Check if any group has an active mapping
    active_mappings = [m for m in config.group_mappings if m.is_active]
    if not active_mappings:
        return False, groups
    
    # Normalize group DNs for comparison
    group_dns_lower = {g.casefold() for g in groups}
    
    for mapping in active_mappings:
        if mapping.ad_group_dn and mapping.ad_group_dn.casefold() in group_dns_lower:
            return True, groups
        if mapping.ad_group_cn:
            group_cn = ad_service._group_cn(mapping.ad_group_dn or "").casefold()
            for g in groups:
                if ad_service._group_cn(g).casefold() == group_cn:
                    return True, groups
    
    return False, groups


async def authenticate_sso(
    db: AsyncSession,
    username: str,
    audit: AuditService | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User | None:
    """Authenticate user via SSO (Kerberos/SPNEGO).
    
    Called after Apache has validated the Kerberos ticket and set X-Remote-User.
    The username is the sAMAccountName or UPN from Active Directory.
    
    Security:
    - Rejects disabled AD accounts (userAccountControl & 2)
    - Requires at least one active ADGroupMapping for user's groups
    - Preserves existing local accounts (never converts local to AD)
    - Preserves existing roles/permissions for existing AD users
    """
    from app.services.ad import DatabaseADService
    
    ad_service = DatabaseADService(db, audit=audit)
    
    config = await ad_service.get_default_config()
    if not config:
        return None

    try:
        server = ad_service._create_server(config)
        normalized_user = ad_service._normalize_bind_user(config.bind_user)
        admin_conn = ad_service._create_connection(
            server,
            normalized_user,
            config.bind_password,
            config,
            authentication=ad_service._bind_authentication(config.bind_user),
        )

        if "@" in username:
            username = username.split("@", 1)[0]

        search_filter = config.user_search_filter.format(
            username=escape_filter_chars(username)
        )
        admin_conn.search(
            search_base=config.user_dn or config.base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["distinguishedName", "sAMAccountName", "mail", "givenName", "sn", "memberOf", "userAccountControl"],
        )

        if not admin_conn.entries:
            admin_conn.unbind()
            return None

        entry = admin_conn.entries[0]
        
        # Check if AD account is disabled (userAccountControl & 2 = ACCOUNTDISABLE)
        uac = entry.userAccountControl
        if uac and int(str(uac)) & 2:
            admin_conn.unbind()
            if audit:
                await audit.log(
                    action="sso_login",
                    module="auth",
                    username=username,
                    status="failure",
                    error_message="AD account disabled",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            return None
        
        user_dn = str(entry.distinguishedName)

        # Verify user has authorized group mapping BEFORE any account creation/update.
        # Uses the still-open admin connection (no bind with an empty user password).
        try:
            has_mapping, groups = await _user_has_authorized_mapping(ad_service, config, user_dn, entry, admin_conn)
        finally:
            admin_conn.unbind()
        if not has_mapping:
            if audit:
                await audit.log(
                    action="sso_login",
                    module="auth",
                    username=username,
                    status="failure",
                    error_message="No authorized AD group mapping",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            return None

        # Check if user already exists in ForgeAI by AD DN
        result = await db.execute(select(User).where(User.ad_dn == user_dn))
        user = result.scalar_one_or_none()

        if user:
            if user.source != "ad":
                # Local account with same AD DN should not exist, but protect anyway
                return None
            user.is_active = True
            user.last_login = datetime.now(UTC)
            await ad_service._sync_user_ad_groups(user, groups or [], config)
            await db.commit()
            await db.refresh(user)

            if audit:
                await audit.log(
                    action="sso_login",
                    module="auth",
                    user=user,
                    status="success",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            return user

        # Create new user from AD info
        ad_username = str(entry.sAMAccountName) if entry.sAMAccountName else username
        email = str(entry.mail) if entry.mail else f"{ad_username}@forgeai.local"
        first_name = str(entry.givenName) if entry.givenName else None
        last_name = str(entry.sn) if entry.sn else None

        # Check for username conflict with local account
        username_owner = (await db.execute(select(User).where(User.username == ad_username))).scalar_one_or_none()
        if username_owner is not None:
            if username_owner.source != "ad":
                # Local account exists with same username - protect it, don't convert
                if audit:
                    await audit.log(
                        action="sso_login",
                        module="auth",
                        username=username,
                        status="failure",
                        error_message="Username conflict with local account",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                return None
            # Existing AD account with same username but different DN - update it
            username_owner.ad_dn = user_dn
            username_owner.is_active = True
            username_owner.last_login = datetime.now(UTC)
            await ad_service._sync_user_ad_groups(username_owner, groups or [], config)
            await db.commit()
            await db.refresh(username_owner)
            return username_owner

        user = User(
            username=ad_username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=None,
            is_active=True,
            source="ad",
            ad_dn=user_dn,
            last_login=datetime.now(UTC),
        )
        try:
            async with db.begin_nested():
                db.add(user)
                await db.flush()
                await ad_service._sync_user_ad_groups(user, groups or [], config)
            await db.commit()
            await db.refresh(user)
        except IntegrityError:
            existing = (await db.execute(select(User).where(User.ad_dn == user_dn))).scalar_one_or_none()
            if existing is None or existing.source != "ad":
                return None
            return existing

        if audit:
            await audit.log(
                action="sso_login",
                module="auth",
                user=user,
                status="success",
                new_values={
                    "username": user.username,
                    "email": user.email,
                    "source": "ad",
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return user

    except LDAPException as e:
        print(f"[AD-SSO] LDAP error during SSO authentication for user '{username}': {e}")
        return None
    except Exception as e:
        print(f"[AD-SSO] Unexpected error during SSO authentication for user '{username}': {e}")
        return None


async def create_user(db: AsyncSession, user_data: dict, audit: AuditService | None = None, current_user: User | None = None) -> User:
    user = User(
        username=user_data["username"],
        email=user_data["email"],
        first_name=user_data.get("first_name"),
        last_name=user_data.get("last_name"),
        password_hash=hash_password(user_data["password"]) if user_data.get("password") else None,
        is_active=user_data.get("is_active", True),
        role=user_data.get("role", UserRole.USER),
        source=user_data.get("source", "local"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    if audit:
        await audit.log(
            action="user_create",
            module="users",
            user=current_user,
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
    db: AsyncSession,
    user: User,
    updates: dict,
    audit: AuditService | None = None,
    current_user: User | None = None,
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
    await db.commit()
    await db.refresh(user)

    new_values = {
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "role": user.role.value,
        "source": user.source,
    }

    if audit:
        await audit.log(
            action="user_update",
            module="users",
            user=current_user,
            object_type="user",
            object_id=str(user.id),
            object_repr=user.username,
            old_values=old_values,
            new_values=new_values,
            status="success",
        )
    return user


async def update_last_login(db: AsyncSession, user: User) -> None:
    user.last_login = datetime.now(UTC)
    await db.commit()


async def logout_user(db: AsyncSession, user: User, audit: AuditService | None = None) -> None:
    if audit:
        await audit.log(
            action="logout",
            module="auth",
            user=user,
            status="success",
        )


def create_tokens(user: User) -> Token:
    token_data = {
        "sub": user.username,
        "user_id": user.id,
    }
    access_token = create_access_token(token_data)
    return Token(
        access_token=access_token,
        refresh_token=create_refresh_token(token_data),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
