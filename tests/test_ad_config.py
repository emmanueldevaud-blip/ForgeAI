import pytest
from httpx import ASGITransport, AsyncClient

@pytest.mark.asyncio
async def test_create_ad_config(client, admin_headers):
    """Test creating an AD config"""
    config_data = {
        "name": "Test Config",
        "is_default": True,
        "server": "ad.example.com",
        "port": 636,
        "use_ssl": True,
        "base_dn": "DC=example,DC=com",
        "user_dn": "OU=Users,DC=example,DC=com",
        "user_search_filter": "(sAMAccountName={username})",
        "group_search_base": "OU=Groups,DC=example,DC=com",
        "bind_user": "CN=svc_forgeai,OU=ServiceAccounts,DC=example,DC=com",
        "bind_password": "testpassword123",
        "connect_timeout": 10,
        "receive_timeout": 10,
        "page_size": 1000,
        "follow_referrals": False,
        "is_active": True
    }
    
    response = await client.post("/auth/ad-configs", headers=admin_headers, json=config_data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code != 201:
        print(f"Headers: {response.headers}")
        print(f"Cookies: {response.cookies}")
    
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_get_ad_mappings_and_sync_logs_after_create(client, admin_headers):
    """Test that GET /mappings and GET /sync-logs return 200 after config creation."""
    config_data = {
        "name": "Test Config 2",
        "is_default": False,
        "server": "ad2.example.com",
        "port": 636,
        "use_ssl": True,
        "base_dn": "DC=example,DC=com",
        "bind_user": "CN=svc,DC=example,DC=com",
        "bind_password": "pwd",
    }
    create_resp = await client.post("/auth/ad-configs", headers=admin_headers, json=config_data)
    assert create_resp.status_code == 201
    config_id = create_resp.json()["id"]

    # Test GET /auth/ad-configs/{config_id}/mappings
    mappings_resp = await client.get(f"/auth/ad-configs/{config_id}/mappings", headers=admin_headers)
    assert mappings_resp.status_code == 200
    assert mappings_resp.json() == []

    # Test GET /auth/ad-configs/{config_id}/sync-logs
    sync_logs_resp = await client.get(f"/auth/ad-configs/{config_id}/sync-logs", headers=admin_headers)
    assert sync_logs_resp.status_code == 200
    assert sync_logs_resp.json() == []


@pytest.mark.asyncio
async def test_ad_mappings_crud_endpoints(client, admin_headers):
    """Test full CRUD on AD group mappings to prevent NameError regression."""
    config_data = {
        "name": "Test Config Mappings",
        "is_default": False,
        "server": "ad3.example.com",
        "port": 636,
        "use_ssl": True,
        "base_dn": "DC=example,DC=com",
        "bind_user": "CN=svc,DC=example,DC=com",
        "bind_password": "pwd",
    }
    create_resp = await client.post("/auth/ad-configs", headers=admin_headers, json=config_data)
    assert create_resp.status_code == 201
    config_id = create_resp.json()["id"]

    # Create mapping
    mapping_data = {
        "ad_group_cn": "Domain Admins",
        "ad_group_dn": "CN=Domain Admins,OU=Groups,DC=example,DC=com",
        "role_code": "admin",
        "is_active": True,
    }
    post_map_resp = await client.post(
        f"/auth/ad-configs/{config_id}/mappings",
        headers=admin_headers,
        json=mapping_data,
    )
    assert post_map_resp.status_code == 201
    mapping = post_map_resp.json()
    mapping_id = mapping["id"]
    assert mapping["ad_group_cn"] == "Domain Admins"

    # List mappings
    list_map_resp = await client.get(
        f"/auth/ad-configs/{config_id}/mappings",
        headers=admin_headers,
    )
    assert list_map_resp.status_code == 200
    mappings = list_map_resp.json()
    assert len(mappings) == 1
    assert mappings[0]["id"] == mapping_id

    # Update mapping
    patch_map_resp = await client.patch(
        f"/auth/ad-configs/{config_id}/mappings/{mapping_id}",
        headers=admin_headers,
        json={"role_code": "user"},
    )
    assert patch_map_resp.status_code == 200
    assert patch_map_resp.json()["role_code"] == "user"

    # Delete mapping
    del_map_resp = await client.delete(
        f"/auth/ad-configs/{config_id}/mappings/{mapping_id}",
        headers=admin_headers,
    )
    assert del_map_resp.status_code == 200

    # Verify empty after deletion
    list_after_del = await client.get(
        f"/auth/ad-configs/{config_id}/mappings",
        headers=admin_headers,
    )
    assert list_after_del.status_code == 200
    assert list_after_del.json() == []


@pytest.mark.asyncio
async def test_create_ad_config_persists_group_search_filter(client, admin_headers):
    """Test that group_search_filter is persisted when creating an AD config."""
    custom_filter = "(&(objectCategory=group)(cn=GG_CUSTOM*))"
    config_data = {
        "name": "Test Config GroupFilter",
        "is_default": False,
        "server": "ad.example.com",
        "port": 636,
        "use_ssl": True,
        "base_dn": "DC=example,DC=com",
        "user_search_filter": "(sAMAccountName={username})",
        "group_search_filter": custom_filter,
        "group_search_base": "OU=Groups,DC=example,DC=com",
        "bind_user": "CN=svc,DC=example,DC=com",
        "bind_password": "pwd",
    }

    create_resp = await client.post("/auth/ad-configs", headers=admin_headers, json=config_data)
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["group_search_filter"] == custom_filter

    get_resp = await client.get(f"/auth/ad-configs/{data['id']}", headers=admin_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["group_search_filter"] == custom_filter


@pytest.mark.asyncio
async def test_mapping_link_removed_on_disable_and_delete(client, admin_headers, db_session):
    """Désactiver ou supprimer un mapping retire le lien group_roles."""
    from sqlalchemy import select

    from app.models.rbac import Group, GroupRole

    role_resp = await client.post(
        "/admin/users/roles",
        headers=admin_headers,
        json={"name": "Mapping Link Role"},
    )
    assert role_resp.status_code == 201
    role_code = role_resp.json()["code"]

    config_resp = await client.post(
        "/auth/ad-configs",
        headers=admin_headers,
        json={
            "name": "Config Link Cleanup",
            "is_default": False,
            "server": "ad.example.com",
            "port": 636,
            "base_dn": "DC=example,DC=com",
            "bind_user": "CN=svc,DC=example,DC=com",
            "bind_password": "pwd",
        },
    )
    assert config_resp.status_code == 201, config_resp.text
    config_id = config_resp.json()["id"]

    group_dn = "CN=GG_LINK_CLEANUP,OU=Groups,DC=example,DC=com"
    group = Group(
        code="ad_gg_link_cleanup",
        name="GG_LINK_CLEANUP",
        ad_dn=group_dn,
        ad_config_id=config_id,
        source="ad",
        is_active=True,
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)
    group_id = group.id

    async def link_exists():
        result = await db_session.execute(
            select(GroupRole).where(GroupRole.group_id == group_id)
        )
        return result.scalar_one_or_none() is not None

    mapping_resp = await client.post(
        f"/auth/ad-configs/{config_id}/mappings",
        headers=admin_headers,
        json={
            "ad_group_cn": "GG_LINK_CLEANUP",
            "ad_group_dn": group_dn,
            "role_code": role_code,
        },
    )
    assert mapping_resp.status_code == 201, mapping_resp.text
    mapping_id = mapping_resp.json()["id"]
    assert await link_exists(), "un mapping actif doit créer le lien group_roles"

    # Désactivation : le seul mapping du groupe ne doit plus accorder le rôle.
    patch_resp = await client.patch(
        f"/auth/ad-configs/{config_id}/mappings/{mapping_id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert not await link_exists(), "un mapping désactivé doit retirer son lien"

    # Réactivation : le lien revient.
    patch_resp = await client.patch(
        f"/auth/ad-configs/{config_id}/mappings/{mapping_id}",
        headers=admin_headers,
        json={"is_active": True},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert await link_exists(), "un mapping réactivé doit recréer son lien"

    # Suppression : le lien ne doit pas survivre au mapping.
    del_resp = await client.delete(
        f"/auth/ad-configs/{config_id}/mappings/{mapping_id}",
        headers=admin_headers,
    )
    assert del_resp.status_code == 200, del_resp.text
    assert not await link_exists(), "supprimer un mapping doit retirer son lien"
