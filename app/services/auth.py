from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from ldap3 import NTLM, SUBTREE, Connection
from passlib.context import CryptContext
from sqlalchemy import select
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
            role=payload.get("role"),
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
            role=payload.get("role"),
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
    
    user_dn, groups, config = await ad_service.authenticate(username, password)
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

    role = ad_service.map_groups_to_roles(groups or [], config) if config else UserRole.USER

    result = await db.execute(select(User).where(User.ad_dn == user_dn))
    user = result.scalar_one_or_none()

    if user:
        old_values = {
            "role": user.role.value,
        }
        user.is_active = True
        user.role = role
        user.last_login = datetime.now(UTC)
        await db.commit()
        await db.refresh(user)

        if audit:
            await audit.log(
                action="login",
                module="auth",
                user=user,
                status="success",
                old_values=old_values,
                new_values={"role": user.role.value},
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return user

    if not config:
        return None

    try:
        server = ad_service._create_server(config)
        admin_conn = Connection(
            server,
            user=config.bind_user,
            password=config.bind_password,
            authentication=NTLM,
            auto_bind=True,
            receive_timeout=config.receive_timeout,
            auto_referrals=config.follow_referrals,
        )
        admin_conn.search(
            search_base=config.user_dn or config.base_dn,
            search_filter=f"(distinguishedName={user_dn})",
            search_scope=SUBTREE,
            attributes=["sAMAccountName", "mail", "givenName", "sn"],
        )
        admin_conn.unbind()

        if not admin_conn.entries:
            return None

        entry = admin_conn.entries[0]
        email = str(entry.mail) if entry.mail else f"{username}@ad.local"

        user = User(
            username=str(entry.sAMAccountName) if entry.sAMAccountName else username,
            email=email,
            first_name=str(entry.givenName) if entry.givenName else None,
            last_name=str(entry.sn) if entry.sn else None,
            password_hash=None,
            is_active=True,
            role=role,
            source="ad",
            ad_dn=user_dn,
            last_login=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        if audit:
            await audit.log(
                action="login",
                module="auth",
                user=user,
                status="success",
                new_values={
                    "username": user.username,
                    "email": user.email,
                    "role": user.role.value,
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


async def create_user(db: AsyncSession, user_data: dict, audit: AuditService | None = None, current_user: User | None = None) -> User:
    user = User(
        username=user_data["username"],
        email=user_data["email"],
        first_name=user_data.get("first_name"),
        last_name=user_data.get("last_name"),
        password_hash=hash_password(user_data["password"]) if user_data.get("password") else None,
        is_active=user_data.get("is_active", True),
        role=UserRole(user_data.get("role", "user")),
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
        "role": user.role.value,
    }
    access_token = create_access_token(token_data)
    return Token(
        access_token=access_token,
        refresh_token=create_refresh_token(token_data),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
