from datetime import UTC, datetime

from ldap3 import ALL, NTLM, SIMPLE, SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models import ADConfig, ADSyncLog, ADSyncStatus, Group, GroupRole, Role, User, UserGroup, UserRole
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
            config.server,
            port=config.port,
            use_ssl=config.use_ssl,
            get_info=ALL,
            connect_timeout=config.connect_timeout,
        )

    @staticmethod
    def _bind_authentication(bind_user: str) -> str:
        if "@" in bind_user:
            return SIMPLE
        if "\\" in bind_user:
            return NTLM
        raise ValueError("Le compte Bind doit utiliser un UPN ou le format DOMAINE\\utilisateur pour NTLM")

    def _create_connection(
        self,
        server: Server,
        user_dn: str,
        password: str,
        config: ADConfig,
        authentication: str = NTLM,
    ) -> Connection:
        return Connection(
            server,
            user=user_dn,
            password=password,
            authentication=authentication,
            auto_bind=True,
            receive_timeout=config.receive_timeout,
            auto_referrals=config.follow_referrals,
        )

    def test_connection(
        self,
        server: str,
        port: int,
        use_ssl: bool,
        base_dn: str,
        bind_user: str,
        bind_password: str,
        connect_timeout: int,
        receive_timeout: int,
        follow_referrals: bool = False,
    ) -> tuple[bool, str, str | None]:
        try:
            ldap_server = Server(
                server,
                port=port,
                use_ssl=use_ssl,
                get_info=ALL,
                connect_timeout=connect_timeout,
            )
            conn = Connection(
                ldap_server,
                user=bind_user,
                password=bind_password,
                authentication=self._bind_authentication(bind_user),
                auto_bind=True,
                receive_timeout=receive_timeout,
                auto_referrals=follow_referrals,
            )

            if not conn.search(
                search_base=base_dn,
                search_filter="(objectClass=*)",
                search_scope=SUBTREE,
                attributes=["distinguishedName"],
                size_limit=1,
            ):
                details = conn.result.get("message") or conn.result.get("description")
                conn.unbind()
                return False, "Échec de la recherche LDAP", details

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
            admin_conn = self._create_connection(
                server,
                config.bind_user,
                config.bind_password,
                config,
                authentication=self._bind_authentication(config.bind_user),
            )

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
                return None, None, None

            entry = admin_conn.entries[0]
            user_dn = str(entry.distinguishedName)
            admin_conn.unbind()

            user_conn = self._create_connection(server, user_dn, password, config)
            if not user_conn.bound:
                return None, None, None

            groups = [str(group) for group in entry.memberOf] if entry.memberOf else []
            if config.group_search_base:
                user_conn.search(
                    search_base=config.group_search_base,
                    search_filter=f"(member={user_dn})",
                    search_scope=SUBTREE,
                    attributes=["cn"],
                )
                groups.extend(str(group_entry.cn) for group_entry in user_conn.entries)

            user_conn.unbind()
            return user_dn, groups, config

        except LDAPException:
            return None, None, None
        except Exception:
            return None, None, None

    def map_groups_to_roles(self, ad_groups: list[str], config: ADConfig) -> UserRole:
        role = UserRole.USER
        for group_dn in ad_groups:
            for mapping in self._matching_mappings(group_dn, config):
                # Keep the historical enum only as a compatibility marker.  The
                # actual permissions are granted by the group-role relation.
                if mapping.role_code == "admin":
                    return UserRole.ADMIN

        return role

    @staticmethod
    def _group_cn(group_dn: str) -> str:
        """Extract the CN without assuming a particular AD OU layout."""
        first_part = group_dn.split(",", 1)[0]
        return first_part[3:] if first_part.casefold().startswith("cn=") else group_dn

    def _matching_mappings(self, group_dn: str, config: ADConfig):
        group_cn = self._group_cn(group_dn).casefold()
        normalized_dn = group_dn.casefold()
        return [
            mapping for mapping in config.group_mappings
            if mapping.is_active and (
                mapping.ad_group_cn.casefold() == group_cn
                or (mapping.ad_group_dn and mapping.ad_group_dn.casefold() == normalized_dn)
            )
        ]

    async def _unique_ad_group_code(self, group_cn: str) -> str:
        base = "".join(c.lower() if c.isalnum() else "_" for c in group_cn).strip("_")[:45] or "ad_group"
        code = f"ad_{base}"[:50]
        suffix = 1
        while (await self.db.execute(select(Group.id).where(Group.code == code))).scalar_one_or_none() is not None:
            suffix += 1
            code = f"ad_{base[:45]}_{suffix}"[:50]
        return code

    async def _ensure_ad_groups(self, group_dns: list[str], config: ADConfig) -> dict[str, Group]:
        """Upsert only AD-owned groups; local groups are never repurposed."""
        groups: dict[str, Group] = {}
        for group_dn in dict.fromkeys(group_dns):
            result = await self.db.execute(select(Group).where(Group.ad_dn == group_dn))
            group = result.scalar_one_or_none()
            group_cn = self._group_cn(group_dn)
            if group is None:
                group = Group(
                    code=await self._unique_ad_group_code(group_cn),
                    name=group_cn,
                    ad_dn=group_dn,
                    ad_config_id=config.id,
                    source="ad",
                    is_active=True,
                )
                self.db.add(group)
                await self.db.flush()
            else:
                group.name = group_cn
                group.ad_config_id = config.id
                group.source = "ad"
                group.is_active = True
            groups[group_dn.casefold()] = group

            # A configured AD mapping grants its ForgeAI role through the AD group.
            for mapping in self._matching_mappings(group_dn, config):
                role = (await self.db.execute(select(Role).where(Role.code == mapping.role_code))).scalar_one_or_none()
                if role is None:
                    continue
                assigned = await self.db.execute(
                    select(GroupRole).where(GroupRole.group_id == group.id, GroupRole.role_id == role.id)
                )
                if assigned.scalar_one_or_none() is None:
                    self.db.add(GroupRole(group_id=group.id, role_id=role.id))
        return groups

    async def _sync_user_ad_groups(self, user: User, group_dns: list[str], config: ADConfig) -> None:
        groups = await self._ensure_ad_groups(group_dns, config)
        desired_ids = {group.id for group in groups.values()}
        result = await self.db.execute(
            select(UserGroup.group_id)
            .join(Group, Group.id == UserGroup.group_id)
            .where(UserGroup.user_id == user.id, Group.source == "ad")
        )
        current_ids = set(result.scalars().all())
        for group_id in desired_ids - current_ids:
            self.db.add(UserGroup(user_id=user.id, group_id=group_id))
        if current_ids - desired_ids:
            await self.db.execute(
                delete(UserGroup).where(
                    UserGroup.user_id == user.id,
                    UserGroup.group_id.in_(current_ids - desired_ids),
                )
            )

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

        found_ad_dns = set()
        found_group_dns = set()
        groups_processed = 0
        groups_created = 0
        groups_updated = 0

        try:
            server = self._create_server(config)
            admin_conn = self._create_connection(
                server,
                config.bind_user,
                config.bind_password,
                config,
                authentication=self._bind_authentication(config.bind_user),
            )

            admin_conn.search(
                search_base=config.user_dn or config.base_dn,
                search_filter=(
                    "(&"
                    "(!(userAccountControl:1.2.840.113556.1.4.803:=2))"
                    f"{config.user_search_filter.format(username='*')})"
                ),
                search_scope=SUBTREE,
                attributes=["distinguishedName", "sAMAccountName", "mail", "givenName", "sn", "memberOf", "userAccountControl"],
                paged_size=config.page_size,
            )

            users_processed = 0
            users_created = 0
            users_updated = 0
            users_deactivated = 0

            for entry in admin_conn.entries:
                if not entry.distinguishedName:
                    print(f"[AD-SYNC] Entrée ignorée (pas de distinguishedName)")
                    continue

                users_processed += 1
                user_dn = str(entry.distinguishedName)
                found_ad_dns.add(user_dn)
                
                role = UserRole.USER
                groups = []
                if entry.memberOf:
                    groups = [str(g) for g in entry.memberOf]
                    role = self.map_groups_to_roles(groups, config)

                sam_account = str(entry.sAMAccountName) if entry.sAMAccountName else f"ad_user_{users_processed}"
                email = str(entry.mail) if entry.mail else f"{sam_account}@ad.local"

                user = None
                if user_dn:
                    result = await self.db.execute(
                        select(User).where(User.source == "ad", User.ad_dn == user_dn)
                    )
                    user = result.scalar_one_or_none()

                if user is None:
                    result = await self.db.execute(
                        select(User).where(User.source == "ad", User.username == sam_account)
                    )
                    user = result.scalar_one_or_none()

                username_owner = None
                if user is None:
                    result = await self.db.execute(select(User).where(User.username == sam_account))
                    username_owner = result.scalar_one_or_none()

                email_owner = None
                if user is None and entry.mail:
                    result = await self.db.execute(select(User).where(User.email == email))
                    email_owner = result.scalar_one_or_none()

                if user:
                    user.is_active = True
                    user.role = role
                    user.last_login = datetime.now(UTC)
                    if entry.mail:
                        result = await self.db.execute(select(User).where(User.email == email))
                        email_owner = result.scalar_one_or_none()
                        if email_owner is None or email_owner.id == user.id:
                            user.email = email
                    if entry.givenName:
                        user.first_name = str(entry.givenName)
                    if entry.sn:
                        user.last_name = str(entry.sn)
                    if entry.sAMAccountName:
                        result = await self.db.execute(select(User).where(User.username == sam_account))
                        username_owner = result.scalar_one_or_none()
                        if username_owner is None or username_owner.id == user.id:
                            user.username = sam_account
                    result = await self.db.execute(select(User).where(User.ad_dn == user_dn))
                    ad_dn_owner = result.scalar_one_or_none()
                    if ad_dn_owner is None or ad_dn_owner.id == user.id:
                        user.ad_dn = user_dn
                    users_updated += 1
                elif username_owner is not None or email_owner is not None:
                    # Un compte local portant déjà cet identifiant ne doit jamais être
                    # transformé en compte AD, ni provoquer une violation d'unicité.
                    continue
                else:
                    try:
                        async with self.db.begin_nested():
                            user = User(
                                username=sam_account,
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
                            await self.db.flush()
                        users_created += 1
                    except IntegrityError:
                        # Une création concurrente ne doit pas rendre la session invalide.
                        continue

                # Local group memberships remain untouched.  Only memberships
                # managed from AD are reconciled here.
                await self._sync_user_ad_groups(user, groups, config)

            if config.group_search_base:
                admin_conn.search(
                    search_base=config.group_search_base,
                    search_filter=config.group_search_filter,
                    search_scope=SUBTREE,
                    attributes=["cn", "distinguishedName", "member"],
                    paged_size=config.page_size,
                )

                for entry in admin_conn.entries:
                    if not entry.cn or not entry.distinguishedName:
                        print(f"[AD-SYNC] Entrée groupe ignorée (cn ou distinguishedName manquant)")
                        continue

                    groups_processed += 1
                    group_cn = str(entry.cn) if entry.cn else None
                    group_dn = str(entry.distinguishedName) if entry.distinguishedName else None
                    
                    if not group_cn:
                        continue

                    found_group_dns.add(group_dn)
                    result = await self.db.execute(select(Group.id).where(Group.ad_dn == group_dn))
                    existed = result.scalar_one_or_none() is not None
                    await self._ensure_ad_groups([group_dn], config)
                    if existed:
                        groups_updated += 1
                    else:
                        groups_created += 1

                groups_deleted = 0
                if found_group_dns:
                    result = await self.db.execute(
                        select(Group).where(
                            Group.source == "ad",
                            Group.ad_config_id == config.id,
                            Group.ad_dn.notin_(list(found_group_dns)),
                        )
                    )
                    stale_groups = result.scalars().all()
                    for group in stale_groups:
                        await self.db.delete(group)
                        groups_deleted += 1
                    if groups_deleted:
                        print(f"[AD-SYNC] {groups_deleted} groupes AD supprimés (absents de l'AD)")

            if found_ad_dns:
                result = await self.db.execute(
                    select(User).where(
                        User.source == "ad",
                        User.ad_dn.notin_(list(found_ad_dns)),
                        User.is_active == True
                    )
                )
                ad_users_not_found = result.scalars().all()
                for user in ad_users_not_found:
                    await self.db.delete(user)
                    users_deactivated += 1

                if users_deactivated:
                    print(f"[AD-SYNC] {users_deactivated} utilisateurs AD supprimés (absents de l'AD)")

            admin_conn.unbind()

            sync_log.status = ADSyncStatus.SUCCESS
            sync_log.completed_at = datetime.now(UTC)
            sync_log.users_processed = users_processed
            sync_log.users_created = users_created
            sync_log.users_updated = users_updated
            sync_log.users_deactivated = users_deactivated
            sync_log.groups_processed = groups_processed
            sync_log.groups_created = groups_created
            sync_log.groups_updated = groups_updated

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
                        "groups_processed": groups_processed,
                        "groups_created": groups_created,
                        "groups_updated": groups_updated,
                        "groups_deleted": groups_deleted,
                    },
                    status="success",
                )
                await self.db.commit()

            return sync_log

        except Exception as e:
            await self.db.rollback()
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
                await self.db.commit()

            return sync_log


async def get_ad_service(
    db: AsyncSession,
    current_user: User | None = None,
) -> DatabaseADService:
    audit = await get_audit_service(db)
    return DatabaseADService(db, audit=audit, current_user=current_user)
