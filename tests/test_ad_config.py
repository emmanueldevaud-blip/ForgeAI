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
