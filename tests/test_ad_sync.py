from types import SimpleNamespace

import pytest

from app.models import User
from app.services.ad import DatabaseADService


class FakeResult:
    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return []


class FakeSession:
    def __init__(self):
        self.users = []

    def add(self, instance):
        if isinstance(instance, User):
            self.users.append(instance)

    async def commit(self):
        pass

    async def refresh(self, instance):
        if getattr(instance, "id", None) is None:
            instance.id = 1

    async def execute(self, statement):
        return FakeResult()


class FakeLDAPConnection:
    def __init__(self, user_entry, group_entry):
        self.user_entry = user_entry
        self.group_entry = group_entry
        self.entries = []
        self.search_filter = None

    def search(self, *, search_filter, **kwargs):
        self.search_filter = search_filter
        if "(objectCategory=person)" in search_filter and "(objectClass=user)" in search_filter:
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
    assert "(objectCategory=person)" in ldap_connection.search_filter
    assert "(objectClass=user)" in ldap_connection.search_filter
