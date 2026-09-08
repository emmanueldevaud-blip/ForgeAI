from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.models import User, UserRole
from app.services.ad import DatabaseADService


class FakeResult:
    def __init__(self, user=None):
        self.user = user

    def scalar_one_or_none(self):
        return self.user

    def scalars(self):
        return self

    def all(self):
        return []


class FakeSession:
    def __init__(self, existing_user=None):
        self.users = []
        self.existing_user = existing_user
        self.rollback_called = False

    def add(self, instance):
        if isinstance(instance, User):
            self.users.append(instance)

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
        if self.existing_user is not None:
            parameters = statement.compile().params.values()
            if (
                self.existing_user.ad_dn in parameters
                or self.existing_user.username in parameters
                or self.existing_user.email in parameters
            ):
                return FakeResult(self.existing_user)
        return FakeResult()


class FakeLDAPConnection:
    def __init__(self, user_entry, group_entry):
        self.user_entry = user_entry
        self.group_entry = group_entry
        self.entries = []
        self.search_filter = None

    def search(self, *, search_filter, **kwargs):
        self.search_filter = search_filter
        if "userAccountControl" in search_filter or "(objectCategory=person)" in search_filter:
            self.entries = [self.user_entry]
        else:
            self.entries = [self.user_entry, self.group_entry]
        return True

    def unbind(self):
        pass


@pytest.fixture
async def seed_rbac():
    """Avoid the global database fixture: this isolated service test has no RBAC dependency."""
    yield


@pytest.mark.asyncio
async def test_sync_users_excludes_ad_groups_from_user_sync(monkeypatch):
    config = SimpleNamespace(
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
        group_search_base=None,
        connect_timeout=10,
        receive_timeout=10,
        page_size=1000,
        follow_referrals=False,
        last_sync_at=None,
        last_sync_status=None,
        group_mappings=[],
    )
    user_entry = SimpleNamespace(
        distinguishedName="CN=Alice,OU=Users,DC=example,DC=test",
        sAMAccountName="alice",
        mail="alice@example.test",
        givenName="Alice",
        sn="Example",
        memberOf=[],
    )
    group_entry = SimpleNamespace(
        distinguishedName="CN=Contrôleurs de domaine d’entreprise en lecture seule,OU=Groups,DC=example,DC=test",
        sAMAccountName="Contrôleurs de domaine d’entreprise en lecture seule",
        mail=None,
        givenName=None,
        sn=None,
        memberOf=[],
    )
    ldap_connection = FakeLDAPConnection(user_entry, group_entry)
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
    config = SimpleNamespace(
        id=1,
        name="AD existing user",
        server="ad.example.test",
        port=636,
        use_ssl=True,
        base_dn="DC=example,DC=test",
        user_dn=None,
        bind_user="service@example.test",
        bind_password="not-used",
        user_search_filter="(sAMAccountName={username})",
        group_search_base=None,
        connect_timeout=10,
        receive_timeout=10,
        page_size=1000,
        follow_referrals=False,
        last_sync_at=None,
        last_sync_status=None,
        group_mappings=[],
    )
    user_entry = SimpleNamespace(
        distinguishedName="CN=Administrateur,OU=Users,DC=example,DC=test",
        sAMAccountName="Administrateur",
        mail="administrateur@example.test",
        givenName="Administrateur",
        sn="AD",
        memberOf=[],
    )
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
    ldap_connection = FakeLDAPConnection(user_entry, user_entry)
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
