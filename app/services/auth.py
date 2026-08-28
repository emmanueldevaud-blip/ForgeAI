from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List, Dict
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import ldap3
from ldap3 import Server, Connection, ALL, SUBTREE, NTLM, SASL, KERBEROS
from ldap3.core.exceptions import LDAPException

from app.core.config import get_settings
from app.models.user import User, UserRole
from app.schemas.auth import Token, TokenData, UserResponse

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


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[TokenData]:
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


def decode_refresh_token(token: str) -> Optional[TokenData]:
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


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user:
        await db.refresh(user)
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        await db.refresh(user)
    return user


async def authenticate_local(db: AsyncSession, username: str, password: str) -> Optional[User]:
    user = await get_user_by_username(db, username)
    if not user:
        return None
    if not user.is_active:
        return None
    if user.source != "local":
        return None
    if not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


class LDAPAuthService:
    def __init__(self):
        self.settings = get_settings()

    def _create_server(self, server_url: str = None, use_ssl: bool = None, connect_timeout: int = None) -> Server:
        settings = self.settings
        return Server(
            server_url or settings.ad_url,
            use_ssl=use_ssl if use_ssl is not None else settings.AD_USE_SSL,
            get_info=ALL,
            connect_timeout=connect_timeout or settings.AD_CONNECT_TIMEOUT,
        )

    def _create_connection(self, server: Server, user_dn: str, password: str) -> Connection:
        return Connection(
            server,
            user=user_dn,
            password=password,
            authentication=NTLM,
            auto_bind=True,
            receive_timeout=self.settings.AD_RECEIVE_TIMEOUT,
        )

    def authenticate(self, username: str, password: str) -> Tuple[Optional[str], Optional[List[str]]]:
        if not self.settings.AD_ENABLED:
            return None, None

        try:
            bind_user = self.settings.AD_BIND_USER
            bind_password = self.settings.AD_BIND_PASSWORD

            if not bind_user or not bind_password:
                return None, None

            server = self._create_server()
            admin_conn = Connection(
                server,
                user=bind_user,
                password=bind_password,
                authentication=NTLM,
                auto_bind=True,
                receive_timeout=self.settings.AD_RECEIVE_TIMEOUT,
            )

            search_filter = self.settings.AD_USER_SEARCH_FILTER.format(username=username)
            admin_conn.search(
                search_base=self.settings.AD_BASE_DN,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=["distinguishedName", "sAMAccountName", "mail", "givenName", "sn", "memberOf", "userAccountControl"],
            )

            if not admin_conn.entries:
                admin_conn.unbind()
                return None, None

            entry = admin_conn.entries[0]
            user_dn = str(entry.distinguishedName)
            admin_conn.unbind()

            user_conn = self._create_connection(user_dn, password)
            if not user_conn.bound:
                return None, None

            groups = []
            if self.settings.AD_GROUP_SEARCH_BASE and self.settings.AD_ADMIN_GROUP:
                user_conn.search(
                    search_base=self.settings.AD_GROUP_SEARCH_BASE,
                    search_filter=f"(member={user_dn})",
                    search_scope=SUBTREE,
                    attributes=["cn"],
                )
                groups = [str(entry.cn) for entry in user_conn.entries]

            user_conn.unbind()

            return user_dn, groups

        except LDAPException:
            return None, None
        except Exception:
            return None, None

    def map_groups_to_roles(self, ad_groups: List[str]) -> Tuple[bool, UserRole]:
        is_admin = False
        role = UserRole.USER

        admin_group = self.settings.AD_ADMIN_GROUP
        if admin_group and admin_group in ad_groups:
            is_admin = True
            role = UserRole.ADMIN

        return is_admin, role

    def test_connection(
        self,
        server_url: str,
        use_ssl: bool,
        base_dn: str,
        bind_user: str,
        bind_password: str,
        connect_timeout: int,
        receive_timeout: int,
    ) -> Tuple[bool, str, Optional[str]]:
        try:
            server = self._create_server(
                server_url=server_url,
                use_ssl=use_ssl,
                connect_timeout=connect_timeout,
            )
            conn = Connection(
                server,
                user=bind_user,
                password=bind_password,
                authentication=NTLM,
                auto_bind=True,
                receive_timeout=receive_timeout,
            )

            conn.search(
                search_base=base_dn,
                search_filter="(objectClass=*)",
                search_scope=SUBTREE,
                attributes=["distinguishedName"],
                size_limit=1,
            )

            conn.unbind()
            return True, "Connexion à l'Active Directory réussie", None

        except LDAPException as e:
            return False, "Échec de la connexion LDAP", str(e)
        except Exception as e:
            return False, "Erreur lors du test de connexion", str(e)


ldap_service = LDAPAuthService()


async def authenticate_ad(db: AsyncSession, username: str, password: str) -> Optional[User]:
    if not settings.AD_ENABLED:
        return None

    user_dn, groups = ldap_service.authenticate(username, password)
    if not user_dn:
        return None

    is_admin, role = ldap_service.map_groups_to_roles(groups or [])

    result = await db.execute(select(User).where(User.ad_dn == user_dn))
    user = result.scalar_one_or_none()

    if user:
        user.is_active = True
        user.is_admin = is_admin
        user.role = role
        user.last_login = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(user)
        return user

    try:
        server = ldap_service._create_server()
        bind_user = settings.AD_BIND_USER
        bind_password = settings.AD_BIND_PASSWORD
        admin_conn = Connection(
            server,
            user=bind_user,
            password=bind_password,
            authentication=NTLM,
            auto_bind=True,
            receive_timeout=settings.AD_RECEIVE_TIMEOUT,
        )
        admin_conn.search(
            search_base=settings.AD_BASE_DN,
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
            is_admin=is_admin,
            role=role,
            source="ad",
            ad_dn=user_dn,
            last_login=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    except Exception:
        return None


async def create_user(db: AsyncSession, user_data: dict) -> User:
    user = User(
        username=user_data["username"],
        email=user_data["email"],
        first_name=user_data.get("first_name"),
        last_name=user_data.get("last_name"),
        password_hash=hash_password(user_data["password"]) if user_data.get("password") else None,
        is_active=user_data.get("is_active", True),
        is_admin=user_data.get("is_admin", False),
        role=UserRole(user_data.get("role", "user")),
        source=user_data.get("source", "local"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user: User, updates: dict) -> User:
    for key, value in updates.items():
        if value is None:
            continue
        if key == "password":
            setattr(user, "password_hash", hash_password(value))
        elif hasattr(user, key):
            setattr(user, key, value)
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user


async def update_last_login(db: AsyncSession, user: User) -> None:
    user.last_login = datetime.now(timezone.utc)
    await db.commit()


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