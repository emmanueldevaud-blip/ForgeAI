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

