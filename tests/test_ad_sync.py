from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.models import User, UserRole
from app.models.rbac import Group
from app.services.ad import DatabaseADService


class FakeResult:
    def __init__(self, user=None, items=None):
        self.user = user
        self._items = items or []

    def scalar_one_or_none(self):
        return self.user

    def scalars(self):
        return self

    def all(self):
        return self._items


class FakeSession:
    def __init__(self, existing_user=None, existing_groups=None):
        self.users = []
        self.groups = []
        self.deleted = []
        self.existing_user = existing_user
        self.existing_groups = existing_groups or []
        self.rollback_called = False

    def add(self, instance):
        if isinstance(instance, User):
            self.users.append(instance)
        elif isinstance(instance, Group):
            self.groups.append(instance)

    async def commit(self):
        pass

    async def rollback(self):
        self.rollback_called = True

    async def flush(self):
        pass

    @asynccontextmanager
    async def begin_nested(self):
        yield

    async def refresh(self, instance):
        if getattr(instance, "id", None) is None:
            instance.id = 1

    async def execute(self, statement):
        compiled = statement.compile()
        params = compiled.params

        if hasattr(statement, 'whereclause') and statement.whereclause is not None:
            clause_str = str(statement.whereclause)

            # select(Group).where(Group.ad_dn == group_dn)
            if "groups.ad_dn" in clause_str and "groups.source" not in clause_str and "groups.ad_config_id" not in clause_str:
                for g in self.existing_groups:
                    if g.ad_dn in params.values():
                        return FakeResult(g)
                return FakeResult()

            # select(Group.id).where(Group.ad_dn == group_dn)
            if "groups.id" in clause_str and "groups.ad_dn" in clause_str and "groups.source" not in clause_str:
                for g in self.existing_groups:
                    if g.ad_dn in params.values():
                        return FakeResult(g)
                return FakeResult()

            # Reconciliation: select(Group).where(source=="ad", ad_config_id==config.id, ad_dn.notin_(...))
            if "groups.source" in clause_str and "groups.ad_config_id" in clause_str and "groups.ad_dn" in clause_str:
                notin_values = set()
                config_id = None
                for k, v in params.items():
                    if isinstance(v, (list, tuple, set)):
                        notin_values.update(v)
                    elif "ad_config_id" in k:
                        config_id = v
                stale = [
                    g for g in self.existing_groups
                    if g.source == "ad"
                    and getattr(g, "ad_config_id", None) == config_id
                    and g.ad_dn not in notin_values
                ]
                return FakeResult(items=stale)

            # User queries
            if "users.ad_dn" in clause_str or "users.username" in clause_str or "users.email" in clause_str:
                if self.existing_user is not None:
                    if (
                        self.existing_user.ad_dn in params.values()
                        or self.existing_user.username in params.values()
                        or self.existing_user.email in params.values()
                    ):
                        return FakeResult(self.existing_user)
                return FakeResult()

            # select(Group.id).where(Group.code == code)
            if "groups.code" in clause_str:
                return FakeResult()

            # select(GroupRole)...
            if "group_roles" in clause_str:
                return FakeResult()

            # select(UserGroup.group_id)...
            if "user_groups" in clause_str:
                return FakeResult(items=[])

            # select(User).where(source=="ad", ad_dn.notin_(...))
            if "users.source" in clause_str and "users.ad_dn" in clause_str:
                return FakeResult(items=[])

        return FakeResult()

    async def delete(self, instance):
        self.deleted.append(instance)


class FakeLDAPConnection:
    def __init__(self, user_entries=None, group_entries=None):
        self.user_entries = user_entries or []
        self.group_entries = group_entries or []
        self.entries = []
        self.search_filter = None

    def search(self, *, search_filter, **kwargs):
        self.search_filter = search_filter
        if "userAccountControl" in search_filter or "(objectCategory=person)" in search_filter:
            self.entries = self.user_entries
        else:
            self.entries = self.group_entries
        return True

    def unbind(self):
        pass


@pytest.fixture
async def seed_rbac():
    yield


def _make_config(**overrides):
    defaults = dict(
        id=1,
        name="AD sync filter",
        server="ad.example.test",
        port=636,
        use_ssl=True,
        base_dn="DC=example,DC=test",
        user_dn=None,
        bind_user="service@example.test",
        bind_password="not-used",
        user_search_filter="(sAMAccountName={username})",
        group_search_filter="(&(objectCategory=group)(cn=GG_*))",
        group_search_base="OU=Groups,DC=example,DC=test",
        connect_timeout=10,
        receive_timeout=10,
        page_size=1000,
        follow_referrals=False,
        last_sync_at=None,
        last_sync_status=None,
        group_mappings=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _user_entry(cn="Alice", sam="alice", mail="alice@example.test", dn=None):
    return SimpleNamespace(
        distinguishedName=dn or f"CN={cn},OU=Users,DC=example,DC=test",
        sAMAccountName=sam,
        mail=mail,
        givenName=cn,
        sn="Example",
        memberOf=[],
    )


def _group_entry(cn, dn=None):
    return SimpleNamespace(
        cn=cn,
        distinguishedName=dn or f"CN={cn},OU=Groups,DC=example,DC=test",
    )


# ── Tests existants ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_users_excludes_ad_groups_from_user_sync(monkeypatch):
    config = _make_config(group_search_base=None)
    user_entry = _user_entry()
    ldap_connection = FakeLDAPConnection(user_entries=[user_entry])
    db_session = FakeSession()
    service = DatabaseADService(db_session)
    monkeypatch.setattr(service, "_create_server", lambda _: object())
    monkeypatch.setattr(service, "_create_connection", lambda *args, **kwargs: ldap_connection)

    sync_log = await service.sync_users(config)

    assert sync_log.status == "success"
    assert sync_log.users_created == 1
    assert [user.username for user in db_session.users] == ["alice"]
    assert "(sAMAccountName=*)" in ldap_connection.search_filter
    assert "userAccountControl" in ldap_connection.search_filter


@pytest.mark.asyncio
async def test_sync_updates_existing_ad_user_with_same_username(monkeypatch):
    config = _make_config(group_search_base=None)
    user_entry = _user_entry(cn="Administrateur", sam="Administrateur", mail="administrateur@example.test")
    existing_user = User(
        id=42,
        username="Administrateur",
        email="administrateur@example.test",
        password_hash=None,
        source="ad",
        ad_dn="CN=Administrateur,OU=Ancien,DC=example,DC=test",
        is_active=False,
        role=UserRole.USER,
    )
    ldap_connection = FakeLDAPConnection(user_entries=[user_entry])
    db_session = FakeSession(existing_user=existing_user)
    service = DatabaseADService(db_session)
    monkeypatch.setattr(service, "_create_server", lambda _: object())
    monkeypatch.setattr(service, "_create_connection", lambda *args, **kwargs: ldap_connection)

    sync_log = await service.sync_users(config)

    assert sync_log.status == "success"
    assert sync_log.users_created == 0
    assert sync_log.users_updated == 1
    assert db_session.users == []
    assert existing_user.ad_dn == user_entry.distinguishedName
    assert existing_user.is_active is True


# ── Tests réconciliation des groupes ────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_groups_creates_new_groups(monkeypatch):
    config = _make_config()
    user_entry = _user_entry()
    groups = [_group_entry("GG_FORGEAI_Dev"), _group_entry("GG_FORGEAI_Prod"), _group_entry("GG_FORGEAI_Admin")]
    ldap_connection = FakeLDAPConnection(user_entries=[user_entry], group_entries=groups)
    db_session = FakeSession()
    service = DatabaseADService(db_session)
    monkeypatch.setattr(service, "_create_server", lambda _: object())
    monkeypatch.setattr(service, "_create_connection", lambda *args, **kwargs: ldap_connection)

    sync_log = await service.sync_users(config)

    assert sync_log.status == "success"
    assert sync_log.groups_created == 3
    assert sync_log.groups_updated == 0
    assert len(db_session.groups) == 3
    created_names = sorted(g.name for g in db_session.groups)
    assert created_names == ["GG_FORGEAI_Admin", "GG_FORGEAI_Dev", "GG_FORGEAI_Prod"]
    for g in db_session.groups:
        assert g.ad_config_id == config.id


@pytest.mark.asyncio
async def test_sync_groups_updates_existing_groups(monkeypatch):
    config = _make_config()
    user_entry = _user_entry()

    existing = Group(
        id=40,
        code="ad_gg_dev",
        name="GG_FORGEAI_Dev",
        ad_dn="CN=GG_FORGEAI_Dev,OU=Groups,DC=example,DC=test",
        ad_config_id=1,
        source="ad",
        is_active=False,
    )

    current_groups = [_group_entry("GG_FORGEAI_Dev")]
    ldap_connection = FakeLDAPConnection(user_entries=[user_entry], group_entries=current_groups)
    db_session = FakeSession(existing_groups=[existing])
    service = DatabaseADService(db_session)
    monkeypatch.setattr(service, "_create_server", lambda _: object())
    monkeypatch.setattr(service, "_create_connection", lambda *args, **kwargs: ldap_connection)

    sync_log = await service.sync_users(config)

    assert sync_log.status == "success"
    assert sync_log.groups_updated == 1
    assert sync_log.groups_created == 0
    assert existing.is_active is True
    assert existing.ad_config_id == config.id
    assert len(db_session.deleted) == 0


@pytest.mark.asyncio
async def test_sync_groups_deletes_stale_groups(monkeypatch):
    config = _make_config()
    user_entry = _user_entry()

    stale_group = Group(
        id=10,
        code="ad_gg_old",
        name="GG_FORGEAI_Old",
        ad_dn="CN=GG_FORGEAI_Old,OU=Groups,DC=example,DC=test",
        ad_config_id=1,
        source="ad",
        is_active=True,
    )
    fresh_group = Group(
        id=11,
        code="ad_gg_dev",
        name="GG_FORGEAI_Dev",
        ad_dn="CN=GG_FORGEAI_Dev,OU=Groups,DC=example,DC=test",
        ad_config_id=1,
        source="ad",
        is_active=True,
    )

    current_groups = [_group_entry("GG_FORGEAI_Dev"), _group_entry("GG_FORGEAI_New")]
    ldap_connection = FakeLDAPConnection(user_entries=[user_entry], group_entries=current_groups)
    db_session = FakeSession(existing_groups=[stale_group, fresh_group])
    service = DatabaseADService(db_session)
    monkeypatch.setattr(service, "_create_server", lambda _: object())
    monkeypatch.setattr(service, "_create_connection", lambda *args, **kwargs: ldap_connection)

    sync_log = await service.sync_users(config)

    assert sync_log.status == "success"
    deleted_dns = [g.ad_dn for g in db_session.deleted]
    assert stale_group.ad_dn in deleted_dns
    assert fresh_group.ad_dn not in deleted_dns


@pytest.mark.asyncio
async def test_sync_groups_does_not_delete_other_config_groups(monkeypatch):
    config = _make_config(id=1)
    user_entry = _user_entry()

    own_group = Group(
        id=20,
        code="ad_gg_own",
        name="GG_Own",
        ad_dn="CN=GG_Own,OU=Groups,DC=example,DC=test",
        ad_config_id=1,
        source="ad",
        is_active=True,
    )
    other_config_group = Group(
        id=21,
        code="ad_gg_other",
        name="GG_Other",
        ad_dn="CN=GG_Other,OU=OtherDept,DC=example,DC=test",
        ad_config_id=2,
        source="ad",
        is_active=True,
    )

    current_groups = [_group_entry("GG_Own")]
    ldap_connection = FakeLDAPConnection(user_entries=[user_entry], group_entries=current_groups)
    db_session = FakeSession(existing_groups=[own_group, other_config_group])
    service = DatabaseADService(db_session)
    monkeypatch.setattr(service, "_create_server", lambda _: object())
    monkeypatch.setattr(service, "_create_connection", lambda *args, **kwargs: ldap_connection)

    sync_log = await service.sync_users(config)

    assert sync_log.status == "success"
    deleted_dns = [g.ad_dn for g in db_session.deleted]
    assert own_group.ad_dn not in deleted_dns
    assert other_config_group.ad_dn not in deleted_dns


@pytest.mark.asyncio
async def test_sync_groups_does_not_delete_local_groups(monkeypatch):
    config = _make_config()
    user_entry = _user_entry()

    local_group = Group(
        id=30,
        code="local_group",
        name="Groupe Local",
        ad_dn=None,
        source="local",
        is_active=True,
    )

    current_groups = []
    ldap_connection = FakeLDAPConnection(user_entries=[user_entry], group_entries=current_groups)
    db_session = FakeSession(existing_groups=[local_group])
    service = DatabaseADService(db_session)
    monkeypatch.setattr(service, "_create_server", lambda _: object())
    monkeypatch.setattr(service, "_create_connection", lambda *args, **kwargs: ldap_connection)

    sync_log = await service.sync_users(config)

    assert sync_log.status == "success"
    assert len(db_session.deleted) == 0


@pytest.mark.asyncio
async def test_sync_groups_skips_reconciliation_when_no_ldap_groups(monkeypatch):
    """Si aucun groupe LDAP n'est retourné, la réconciliation ne supprime rien (sécurité)."""
    config = _make_config(id=1, group_search_base="OU=ForgeAI,DC=example,DC=test")
    user_entry = _user_entry()

    stale_from_other_ou = Group(
        id=50,
        code="ad_gg_old_ou",
        name="GG_FORGEAI_Old",
        ad_dn="CN=GG_FORGEAI_Old,OU=AutreOU,DC=example,DC=test",
        ad_config_id=1,
        source="ad",
        is_active=True,
    )

    current_groups = []
    ldap_connection = FakeLDAPConnection(user_entries=[user_entry], group_entries=current_groups)
    db_session = FakeSession(existing_groups=[stale_from_other_ou])
    service = DatabaseADService(db_session)
    monkeypatch.setattr(service, "_create_server", lambda _: object())
    monkeypatch.setattr(service, "_create_connection", lambda *args, **kwargs: ldap_connection)

    sync_log = await service.sync_users(config)

    assert sync_log.status == "success"
    deleted_dns = [g.ad_dn for g in db_session.deleted]
    assert stale_from_other_ou.ad_dn not in deleted_dns


@pytest.mark.asyncio
async def test_sync_groups_multi_config_scoping(monkeypatch):
    """Deux configs AD avec des périmètres différents : seul le groupe de la config courante est supprimé."""
    config_a = _make_config(id=1, name="ConfigA")
    user_entry = _user_entry()

    group_config_a_stale = Group(
        id=60,
        code="ad_gg_a_stale",
        name="GG_A_Stale",
        ad_dn="CN=GG_A_Stale,OU=Groups,DC=example,DC=test",
        ad_config_id=1,
        source="ad",
        is_active=True,
    )
    group_config_a_fresh = Group(
        id=61,
        code="ad_gg_a_fresh",
        name="GG_A_Fresh",
        ad_dn="CN=GG_A_Fresh,OU=Groups,DC=example,DC=test",
        ad_config_id=1,
        source="ad",
        is_active=True,
    )
    group_config_b = Group(
        id=62,
        code="ad_gg_b",
        name="GG_B_Only",
        ad_dn="CN=GG_B_Only,OU=Groups,DC=example,DC=test",
        ad_config_id=2,
        source="ad",
        is_active=True,
    )
    local = Group(
        id=63,
        code="local_g",
        name="Local",
        ad_dn=None,
        source="local",
        is_active=True,
    )

    current_groups = [_group_entry("GG_A_Fresh")]
    ldap_connection = FakeLDAPConnection(user_entries=[user_entry], group_entries=current_groups)
    db_session = FakeSession(existing_groups=[group_config_a_stale, group_config_a_fresh, group_config_b, local])
    service = DatabaseADService(db_session)
    monkeypatch.setattr(service, "_create_server", lambda _: object())
    monkeypatch.setattr(service, "_create_connection", lambda *args, **kwargs: ldap_connection)

    sync_log = await service.sync_users(config_a)

    assert sync_log.status == "success"
    deleted_dns = [g.ad_dn for g in db_session.deleted]
    assert group_config_a_stale.ad_dn in deleted_dns
    assert group_config_a_fresh.ad_dn not in deleted_dns
    assert group_config_b.ad_dn not in deleted_dns
    assert local not in db_session.deleted
