from datetime import timedelta

import pytest

from app.core.config import get_settings
from app.models.user import UserRole
from app.services.auth import (
    LDAPAuthService,
    authenticate_ad,
    authenticate_local,
    create_access_token,
    create_refresh_token,
    create_user,
    decode_refresh_token,
    decode_token,
    hash_password,
    ldap_service,
    update_user,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_password_returns_hash(self):
        password = "testpassword123"
        hashed = hash_password(password)
        assert hashed != password
        # Accept both bcrypt ($2b$) and bcrypt_sha256 ($bcrypt-sha256$) formats
        assert hashed.startswith("$2b$") or hashed.startswith("$bcrypt-sha256$")
        # Length varies by algorithm; just verify it's a reasonable hash length
        assert len(hashed) > 50

    def test_verify_password_correct(self):
        password = "testpassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        password = "testpassword123"
        hashed = hash_password(password)
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty_hash(self):
        assert verify_password("password", "") is False

    def test_hash_password_long_password_over_72_bytes(self):
        """Test that passwords longer than 72 bytes work with bcrypt_sha256."""
        password = "a" * 100  # 100 bytes, exceeds bcrypt's 72-byte limit
        hashed = hash_password(password)
        assert hashed.startswith("$bcrypt-sha256$")
        assert verify_password(password, hashed) is True

    def test_hash_password_very_long_password(self):
        """Test that very long passwords (500 bytes) work."""
        password = "b" * 500
        hashed = hash_password(password)
        assert hashed.startswith("$bcrypt-sha256$")
        assert verify_password(password, hashed) is True

    def test_verify_legacy_bcrypt_hash(self):
        """Test that legacy bcrypt $2b$ hashes can still be verified."""
        # This is a bcrypt hash for "shortpassword" with rounds=12
        legacy_hash = "$2b$12$aY7gjVO8NVMvqkE4PE1kGu64dp.KJF0iHGxTj9toflahbXX0Sz5ey"
        assert verify_password("shortpassword", legacy_hash) is True
        assert verify_password("wrongpassword", legacy_hash) is False

    def test_new_hashes_use_bcrypt_sha256(self):
        """Test that new hashes use bcrypt_sha256 format (not classic bcrypt)."""
        password = "testpassword123"
        hashed = hash_password(password)
        assert hashed.startswith("$bcrypt-sha256$"), f"Expected bcrypt_sha256, got: {hashed[:30]}"


class TestJWTTokens:
    def test_create_access_token(self):
        data = {"sub": "testuser", "user_id": 1, "role": "user"}
        token = create_access_token(data)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_access_token(self):
        data = {"sub": "testuser", "user_id": 1, "role": "user"}
        token = create_access_token(data)
        decoded = decode_token(token)
        assert decoded is not None
        assert decoded.sub == "testuser"
        assert decoded.user_id == 1
        assert decoded.role == "user"

    def test_decode_expired_token(self):
        data = {"sub": "testuser", "user_id": 1, "role": "user"}
        token = create_access_token(data, expires_delta=timedelta(seconds=-1))
        decoded = decode_token(token)
        assert decoded is None

    def test_decode_invalid_token(self):
        decoded = decode_token("invalid.token.string")
        assert decoded is None

    def test_decode_wrong_type_token(self):
        data = {"sub": "testuser", "user_id": 1, "role": "user"}
        token = create_refresh_token(data)
        decoded = decode_token(token)
        assert decoded is None

    def test_refresh_token_flow(self):
        data = {"sub": "testuser", "user_id": 1, "role": "user"}
        refresh = create_refresh_token(data)
        decoded = decode_refresh_token(refresh)
        assert decoded is not None
        assert decoded.sub == "testuser"


class TestUserCRUD:
    @pytest.mark.asyncio
    async def test_create_user(self, db_session):
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "password123",
            "first_name": "Test",
            "last_name": "User",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        user = await create_user(db_session, user_data)
        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.is_active is True
        assert user.role == UserRole.USER
        assert user.role == UserRole.USER
        assert user.source == "local"
        assert user.password_hash is not None
        assert user.password_hash != "password123"

    @pytest.mark.asyncio
    async def test_create_user_without_password(self, db_session):
        user_data = {
            "username": "aduser",
            "email": "ad@example.com",
            "first_name": "AD",
            "last_name": "User",
            "is_active": True,            "role": UserRole.USER,
            "source": "ad",
        }
        user = await create_user(db_session, user_data)
        assert user.password_hash is None
        assert user.source == "ad"

    @pytest.mark.asyncio
    async def test_update_user(self, db_session):
        user_data = {
            "username": "updateuser",
            "email": "update@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        user = await create_user(db_session, user_data)
        original_updated = user.updated_at

        updated_user = await update_user(db_session, user, {"first_name": "Updated", "last_name": "Name"})
        assert updated_user.first_name == "Updated"
        assert updated_user.last_name == "Name"
        assert updated_user.updated_at >= original_updated

    @pytest.mark.asyncio
    async def test_update_user_password(self, db_session):
        user_data = {
            "username": "passuser",
            "email": "pass@example.com",
            "password": "oldpassword",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        user = await create_user(db_session, user_data)
        old_hash = user.password_hash

        updated_user = await update_user(db_session, user, {"password": "newpassword123"})
        assert updated_user.password_hash != old_hash
        assert verify_password("newpassword123", updated_user.password_hash)


class TestLocalAuthentication:
    @pytest.mark.asyncio
    async def test_authenticate_local_valid(self, db_session):
        user_data = {
            "username": "authuser",
            "email": "auth@example.com",
            "password": "correctpassword",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        await create_user(db_session, user_data)

        user = await authenticate_local(db_session, "authuser", "correctpassword")
        assert user is not None
        assert user.username == "authuser"

    @pytest.mark.asyncio
    async def test_authenticate_local_invalid_password(self, db_session):
        user_data = {
            "username": "authuser2",
            "email": "auth2@example.com",
            "password": "correctpassword",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        await create_user(db_session, user_data)

        user = await authenticate_local(db_session, "authuser2", "wrongpassword")
        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_local_nonexistent_user(self, db_session):
        user = await authenticate_local(db_session, "nonexistent", "password")
        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_local_inactive_user(self, db_session):
        user_data = {
            "username": "inactiveuser",
            "email": "inactive@example.com",
            "password": "password123",
            "is_active": False,            "role": UserRole.USER,
            "source": "local",
        }
        await create_user(db_session, user_data)

        user = await authenticate_local(db_session, "inactiveuser", "password123")
        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_local_ad_user(self, db_session):
        user_data = {
            "username": "aduser",
            "email": "ad@example.com",
            "first_name": "AD",
            "last_name": "User",
            "is_active": True,            "role": UserRole.USER,
            "source": "ad",
        }
        await create_user(db_session, user_data)

        user = await authenticate_local(db_session, "aduser", "anypassword")
        assert user is None


class TestADAuthentication:
    @pytest.mark.asyncio
    async def test_authenticate_ad_disabled(self, db_session, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_ENABLED', False)

        user = await authenticate_ad(db_session, "aduser", "password")
        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_ad_no_bind_credentials(self, db_session, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_ENABLED', True)
        monkeypatch.setattr(settings, 'AD_BIND_USER', '')
        monkeypatch.setattr(settings, 'AD_BIND_PASSWORD', '')

        user = await authenticate_ad(db_session, "aduser", "password")
        assert user is None

    @pytest.mark.asyncio
    async def test_ldap_map_groups_to_roles_admin(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_ADMIN_GROUP', 'AppAdmins')
        monkeypatch.setattr(settings, 'AD_GROUP_MAPPING', {"admin": "AppAdmins", "user": "AppUsers"})

        role = ldap_service.map_groups_to_roles(["AppUsers", "AppAdmins"])
        
        assert role == UserRole.ADMIN

    @pytest.mark.asyncio
    async def test_ldap_map_groups_to_roles_user(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_ADMIN_GROUP', 'AppAdmins')
        monkeypatch.setattr(settings, 'AD_GROUP_MAPPING', {"admin": "AppAdmins", "user": "AppUsers"})

        role = ldap_service.map_groups_to_roles(["AppUsers"])
        
        assert role == UserRole.USER

    @pytest.mark.asyncio
    async def test_ldap_map_groups_to_roles_no_match(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_ADMIN_GROUP', 'AppAdmins')
        monkeypatch.setattr(settings, 'AD_GROUP_MAPPING', {"admin": "AppAdmins", "user": "AppUsers"})

        role = ldap_service.map_groups_to_roles(["OtherGroup"])
        
        assert role == UserRole.USER


class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_login_local_success(self, client, db_session):
        user_data = {
            "username": "loginuser",
            "email": "login@example.com",
            "password": "loginpassword",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        await create_user(db_session, user_data)

        response = await client.post("/auth/login", json={
            "username": "loginuser",
            "password": "loginpassword",
        })
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "tokens" in data
        assert data["user"]["username"] == "loginuser"
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client):
        response = await client.post("/auth/login", json={
            "username": "nonexistent",
            "password": "password",
        })
        assert response.status_code == 401
        assert "Identifiants invalides" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, client, db_session):
        user_data = {
            "username": "inactivelogin",
            "email": "inactivelogin@example.com",
            "password": "password123",
            "is_active": False,            "role": UserRole.USER,
            "source": "local",
        }
        await create_user(db_session, user_data)

        response = await client.post("/auth/login", json={
            "username": "inactivelogin",
            "password": "password123",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_register_success(self, client):
        response = await client.post("/auth/register", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "newpassword123",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "new@example.com"
        assert data["is_active"] is True
        assert data["role"] == "user"

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, client, db_session):
        user_data = {
            "username": "duplicate",
            "email": "dup1@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        await create_user(db_session, user_data)

        response = await client.post("/auth/register", json={
            "username": "duplicate",
            "email": "dup2@example.com",
            "password": "password123",
        })
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_register_local_disabled(self, client, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, 'AUTH_LOCAL_ENABLED', False)

        response = await client.post("/auth/register", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "newpassword123",
        })
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_me(self, client, auth_headers):
        response = await client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "username" in data
        assert "email" in data

    @pytest.mark.asyncio
    async def test_get_me_unauthorized(self, client):
        response = await client.get("/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_logout(self, client, auth_headers):
        response = await client.post("/auth/logout", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_refresh_token(self, client, auth_headers, db_session, auth_user):
        login_response = await client.post("/auth/login", json={
            "username": "testauth",
            "password": "testpassword123",
        })
        refresh_token = login_response.cookies.get("refresh_token")

        response = await client.post("/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_admin_access_allowed(self, client, admin_headers):
        response = await client.get("/auth/users", headers=admin_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_access_denied_for_user(self, client, auth_headers):
        response = await client.get("/auth/users", headers=auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_user_admin(self, client, admin_headers):
        response = await client.post("/auth/users", headers=admin_headers, json={
            "username": "admincreated",
            "email": "admincreated@example.com",
            "password": "password123",            "role": "admin",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "admincreated"
        

    @pytest.mark.asyncio
    async def test_update_user_admin(self, client, admin_headers, db_session):
        user_data = {
            "username": "toupdate",
            "email": "toupdate@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        user = await create_user(db_session, user_data)

        response = await client.patch(f"/auth/users/{user.id}", headers=admin_headers, json={
            "first_name": "Updated",        })
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Updated"
        

    @pytest.mark.asyncio
    async def test_reset_password_admin(self, client, admin_headers, db_session):
        user_data = {
            "username": "toreset",
            "email": "toreset@example.com",
            "password": "oldpassword",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        user = await create_user(db_session, user_data)

        response = await client.post(f"/auth/users/{user.id}/reset-password", headers=admin_headers, json={"new_password": "newpassword123"})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_user_admin(self, client, admin_headers, db_session):
        user_data = {
            "username": "todelete",
            "email": "todelete@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        user = await create_user(db_session, user_data)

        response = await client.delete(f"/auth/users/{user.id}", headers=admin_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_self_denied(self, client, admin_headers, admin_user):
        response = await client.delete(f"/auth/users/{admin_user.id}", headers=admin_headers)
        assert response.status_code == 400


class TestSettings:
    @pytest.mark.asyncio
    async def test_get_auth_settings(self, client):
        response = await client.get("/auth/settings")
        assert response.status_code == 200
        data = response.json()
        assert "auth_local_enabled" in data
        assert "ad_enabled" in data


class TestUserIsolation:
    @pytest.mark.asyncio
    async def test_todos_isolation_between_users(self, client, db_session):
        user1_data = {
            "username": "isolation_user1",
            "email": "user1@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        user2_data = {
            "username": "isolation_user2",
            "email": "user2@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        user1 = await create_user(db_session, user1_data)
        user2 = await create_user(db_session, user2_data)

        login1 = await client.post("/auth/login", json={"username": "isolation_user1", "password": "password123"})
        login2 = await client.post("/auth/login", json={"username": "isolation_user2", "password": "password123"})
        
        token1 = login1.cookies.get("access_token")
        token2 = login2.cookies.get("access_token")
        
        headers1 = {"Authorization": f"Bearer {token1}"}
        headers2 = {"Authorization": f"Bearer {token2}"}

        create1 = await client.post("/api/todos", headers=headers1, json={"title": "User1 Todo"})
        assert create1.status_code == 201
        todo1_id = create1.json()["id"]

        create2 = await client.post("/api/todos", headers=headers2, json={"title": "User2 Todo"})
        assert create2.status_code == 201
        todo2_id = create2.json()["id"]

        list1 = await client.get("/api/todos", headers=headers1)
        assert list1.status_code == 200
        todos1 = list1.json()
        assert len(todos1) == 1
        assert todos1[0]["title"] == "User1 Todo"

        list2 = await client.get("/api/todos", headers=headers2)
        assert list2.status_code == 200
        todos2 = list2.json()
        assert len(todos2) == 1
        assert todos2[0]["title"] == "User2 Todo"

        get_other = await client.get(f"/api/todos/{todo2_id}", headers=headers1)
        assert get_other.status_code == 404

        get_own = await client.get(f"/api/todos/{todo1_id}", headers=headers1)
        assert get_own.status_code == 200
        assert get_own.json()["title"] == "User1 Todo"

        update_other = await client.patch(f"/api/todos/{todo2_id}", headers=headers1, json={"title": "Hacked"})
        assert update_other.status_code == 404

        delete_other = await client.delete(f"/api/todos/{todo2_id}", headers=headers1)
        assert delete_other.status_code == 404

        delete_own = await client.delete(f"/api/todos/{todo1_id}", headers=headers1)
        assert delete_own.status_code == 204

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_user_profile(self, client, db_session):
        user1_data = {
            "username": "profile_user1",
            "email": "profile1@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        user2_data = {
            "username": "profile_user2",
            "email": "profile2@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        }
        user1 = await create_user(db_session, user1_data)
        user2 = await create_user(db_session, user2_data)

        login1 = await client.post("/auth/login", json={"username": "profile_user1", "password": "password123"})
        token1 = login1.cookies.get("access_token")
        headers1 = {"Authorization": f"Bearer {token1}"}

        response = await client.get(f"/auth/users/{user2.id}", headers=headers1)
        assert response.status_code == 403


class TestADSettings:
    @pytest.mark.asyncio
    async def test_get_ad_settings_admin(self, client, admin_headers):
        response = await client.get("/auth/ad-settings", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "ad_enabled" in data
        assert "ad_server" in data
        assert "ad_port" in data
        assert "ad_use_ssl" in data
        assert "ad_base_dn" in data
        assert "ad_bind_user" in data
        assert "ad_bind_password" in data
        assert data["ad_bind_password"] == ""

    @pytest.mark.asyncio
    async def test_get_ad_settings_denied_for_user(self, client, auth_headers):
        response = await client.get("/auth/ad-settings", headers=auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_ad_settings_admin(self, client, admin_headers):
        update_data = {
            "ad_enabled": True,
            "ad_server": "ad.test.com",
            "ad_port": 389,
            "ad_use_ssl": False,
            "ad_base_dn": "DC=test,DC=com",
            "ad_bind_user": "CN=svc_test,OU=ServiceAccounts,DC=test,DC=com",
            "ad_bind_password": "newpassword",
            "ad_connect_timeout": 15,
            "ad_receive_timeout": 15,
        }
        response = await client.put("/auth/ad-settings", headers=admin_headers, json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["ad_enabled"] is True
        assert data["ad_server"] == "ad.test.com"
        assert data["ad_port"] == 389
        assert data["ad_use_ssl"] is False
        assert data["ad_base_dn"] == "DC=test,DC=com"
        assert data["ad_bind_user"] == "CN=svc_test,OU=ServiceAccounts,DC=test,DC=com"
        assert data["ad_bind_password"] == ""
        assert data["ad_connect_timeout"] == 15
        assert data["ad_receive_timeout"] == 15

    @pytest.mark.asyncio
    async def test_update_ad_settings_partial(self, client, admin_headers):
        update_data = {
            "ad_enabled": False,
        }
        response = await client.put("/auth/ad-settings", headers=admin_headers, json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["ad_enabled"] is False

    @pytest.mark.asyncio
    async def test_update_ad_settings_denied_for_user(self, client, auth_headers):
        response = await client.put("/auth/ad-settings", headers=auth_headers, json={"ad_enabled": True})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_test_ad_connection_admin(self, client, admin_headers):
        test_data = {
            "ad_server": "nonexistent.ad.com",
            "ad_port": 636,
            "ad_use_ssl": True,
            "ad_base_dn": "DC=test,DC=com",
            "ad_bind_user": "CN=svc_test,OU=ServiceAccounts,DC=test,DC=com",
            "ad_bind_password": "password",
            "ad_connect_timeout": 5,
            "ad_receive_timeout": 5,
        }
        response = await client.post("/auth/ad-test", headers=admin_headers, json=test_data)
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "message" in data
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_test_ad_connection_missing_fields(self, client, admin_headers):
        test_data = {
            "ad_server": "",
            "ad_port": 636,
            "ad_use_ssl": True,
            "ad_base_dn": "",
            "ad_bind_user": "",
            "ad_bind_password": "",
            "ad_connect_timeout": 5,
            "ad_receive_timeout": 5,
        }
        response = await client.post("/auth/ad-test", headers=admin_headers, json=test_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_test_ad_connection_denied_for_user(self, client, auth_headers):
        test_data = {
            "ad_server": "ad.test.com",
            "ad_port": 636,
            "ad_use_ssl": True,
            "ad_base_dn": "DC=test,DC=com",
            "ad_bind_user": "CN=svc_test,OU=ServiceAccounts,DC=test,DC=com",
            "ad_bind_password": "password",
            "ad_connect_timeout": 5,
            "ad_receive_timeout": 5,
        }
        response = await client.post("/auth/ad-test", headers=auth_headers, json=test_data)
        assert response.status_code == 403


class TestLDAPService:
    @pytest.mark.asyncio
    async def test_ldap_test_connection_invalid_server(self, monkeypatch):
        service = LDAPAuthService()

        success, message, details = service.test_connection(
            server_url="ldaps://invalid-server:636",
            use_ssl=True,
            base_dn="DC=test,DC=com",
            bind_user="CN=test,DC=test,DC=com",
            bind_password="password",
            connect_timeout=2,
            receive_timeout=2,
        )
        assert success is False
        assert "Échec" in message or "Erreur" in message or "invalid" in message.lower()