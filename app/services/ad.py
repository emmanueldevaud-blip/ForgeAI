from datetime import UTC, datetime

from ldap3 import ALL, NTLM, SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models import ADConfig, ADSyncLog, ADSyncStatus, User, UserRole
from app.services.audit import AuditService, get_audit_service

settings = get_settings()


class DatabaseADService:
    def __init__(self, db: AsyncSession, audit: AuditService | None = None, current_user: User | None = None):
        self.db = db
        self.audit = audit
        self.current_user = current_user

    async def get_default_config(self) -> ADConfig | None:
        result = await self.db.execute(
            select(ADConfig)
            .options(selectinload(ADConfig.group_mappings))
            .where(ADConfig.is_default == True, ADConfig.is_active == True)
        )
        return result.scalar_one_or_none()

    async def get_active_configs(self) -> list[ADConfig]:
        result = await self.db.execute(
            select(ADConfig)
            .options(selectinload(ADConfig.group_mappings))
            .where(ADConfig.is_active == True)
        )
        return list(result.scalars().all())

    async def get_config_by_id(self, config_id: int) -> ADConfig | None:
        result = await self.db.execute(
            select(ADConfig)
            .options(selectinload(ADConfig.group_mappings))
            .where(ADConfig.id == config_id)
        )
        return result.scalar_one_or_none()

    def _create_server(self, config: ADConfig) -> Server:
        return Server(
            config.ad_url,
            use_ssl=config.use_ssl,
            get_info=ALL,
            connect_timeout=config.connect_timeout,
        )

    def _create_connection(self, server: Server, user_dn: str, password: str, config: ADConfig) -> Connection:
        return Connection(
            server,
            user=user_dn,
            password=password,
            authentication=NTLM,
            auto_bind=True,
            receive_timeout=config.receive_timeout,
        )

    def test_connection(
        self,
        server_url: str,
        use_ssl: bool,
        base_dn: str,
        bind_user: str,
        bind_password: str,
        connect_timeout: int,
        receive_timeout: int,
    ) -> tuple[bool, str, str | None]:
        try:
            protocol = "ldaps" if use_ssl else "ldap"
            full_url = f"{protocol}://{server_url}"
            server = Server(
                full_url,
                use_ssl=use_ssl,
                get_info=ALL,
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

    async def authenticate(
        self,
        username: str,
        password: str,
        config: ADConfig | None = None,
    ) -> tuple[str | None, list[str] | None, ADConfig | None]:
        if config is None:
            config = await self.get_default_config()
        
        if not config:
            return None, None, None

        try:
            server = self._create_server(config)
            admin_conn = Connection(
                server,
                user=config.bind_user,
                password=config.bind_password,
                authentication=NTLM,
                auto_bind=True,
                receive_timeout=config.receive_timeout,
            )

            search_filter = config.user_search_filter.format(username=username)
            admin_conn.search(
                search_base=config.base_dn,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=["distinguishedName", "sAMAccountName", "mail", "givenName", "sn", "memberOf", "userAccountControl"],
            )

            if not admin_conn.entries:
                admin_conn.unbind()
                return None, None, None

            entry = admin_conn.entries[0]
            user_dn = str(entry.distinguishedName)
            admin_conn.unbind()

            user_conn = self._create_connection(server, user_dn, password, config)
            if not user_conn.bound:
                return None, None, None

            groups = []
            if config.group_search_base:
                user_conn.search(
                    search_base=config.group_search_base,
                    search_filter=f"(member={user_dn})",
                    search_scope=SUBTREE,
                    attributes=["cn"],
                )
                groups = [str(entry.cn) for entry in user_conn.entries]

            user_conn.unbind()
            return user_dn, groups, config

        except LDAPException:
            return None, None, None
        except Exception:
            return None, None, None

    def map_groups_to_roles(self, ad_groups: list[str], config: ADConfig) -> UserRole:
        role = UserRole.USER

        for mapping in config.group_mappings:
            if not mapping.is_active:
                continue
            if mapping.ad_group_cn in ad_groups:
                if mapping.role_code == "admin":
                    role = UserRole.ADMIN
                    break
                elif mapping.role_code == "user" and role == UserRole.USER:
                    role = UserRole.USER

        return role

    async def sync_users(self, config: ADConfig) -> ADSyncLog:
        sync_log = ADSyncLog(
            ad_config_id=config.id,
            status=ADSyncStatus.RUNNING,
            started_at=datetime.now(UTC),
            triggered_by=self.current_user.id if self.current_user else None,
        )
        self.db.add(sync_log)
        await self.db.commit()
        await self.db.refresh(sync_log)

        try:
            server = self._create_server(config)
            admin_conn = Connection(
                server,
                user=config.bind_user,
                password=config.bind_password,
                authentication=NTLM,
                auto_bind=True,
                receive_timeout=config.receive_timeout,
            )

            admin_conn.search(
                search_base=config.base_dn,
                search_filter=config.user_search_filter.format(username="*"),
                search_scope=SUBTREE,
                attributes=["distinguishedName", "sAMAccountName", "mail", "givenName", "sn", "memberOf", "userAccountControl"],
                paged_size=config.page_size,
            )

            users_processed = 0
            users_created = 0
            users_updated = 0
            users_deactivated = 0

            for entry in admin_conn.entries:
                users_processed += 1
                user_dn = str(entry.distinguishedName)
                
                role = UserRole.USER
                groups = []
                if entry.memberOf:
                    groups = [str(g) for g in entry.memberOf]
                    role = self.map_groups_to_roles(groups, config)

                result = await self.db.execute(select(User).where(User.ad_dn == user_dn))
                user = result.scalar_one_or_none()

                if user:
                    user.is_active = True
                    user.role = role
                    user.last_login = datetime.now(UTC)
                    if entry.mail:
                        user.email = str(entry.mail)
                    if entry.givenName:
                        user.first_name = str(entry.givenName)
                    if entry.sn:
                        user.last_name = str(entry.sn)
                    if entry.sAMAccountName:
                        user.username = str(entry.sAMAccountName)
                    users_updated += 1
                else:
                    email = str(entry.mail) if entry.mail else f"{username}@ad.local"
                    user = User(
                        username=str(entry.sAMAccountName) if entry.sAMAccountName else f"ad_user_{users_processed}",
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
                    self.db.add(user)
                    users_created += 1

            admin_conn.unbind()

            sync_log.status = ADSyncStatus.SUCCESS
            sync_log.completed_at = datetime.now(UTC)
            sync_log.users_processed = users_processed
            sync_log.users_created = users_created
            sync_log.users_updated = users_updated
            sync_log.users_deactivated = users_deactivated

            config.last_sync_at = datetime.now(UTC)
            config.last_sync_status = "success"

            await self.db.commit()

            if self.audit:
                await self.audit.log(
                    action="ad_sync",
                    module="ad",
                    user=self.current_user,
                    object_type="ad_sync",
                    object_id=str(sync_log.id),
                    new_values={
                        "config_id": config.id,
                        "config_name": config.name,
                        "users_processed": users_processed,
                        "users_created": users_created,
                        "users_updated": users_updated,
                        "users_deactivated": users_deactivated,
                    },
                    status="success",
                )

            return sync_log

        except Exception as e:
            sync_log.status = ADSyncStatus.FAILED
            sync_log.completed_at = datetime.now(UTC)
            sync_log.error_message = str(e)
            config.last_sync_status = "failed"
            await self.db.commit()

            if self.audit:
                await self.audit.log(
                    action="ad_sync",
                    module="ad",
                    user=self.current_user,
                    object_type="ad_sync",
                    object_id=str(sync_log.id),
                    status="failure",
                    error_message=str(e),
                )

            return sync_log


async def get_ad_service(
    db: AsyncSession,
    current_user: User | None = None,
) -> DatabaseADService:
    audit = await get_audit_service(db)
    return DatabaseADService(db, audit=audit, current_user=current_user)