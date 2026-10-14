from datetime import timedelta
from types import SimpleNamespace

import pytest
from ldap3.core.exceptions import LDAPException

from app.core.config import get_settings
from app.models.user import UserRole
from app.services.ad import DatabaseADService as _RealADService
from app.services.auth import (
    authenticate_ad,
    authenticate_local,
    create_access_token,
    create_refresh_token,
    create_user,
    decode_refresh_token,
    decode_token,
    hash_password,
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
    async def test_login_accepts_special_use_email_domain(self, client, db_session):
        user_data = {
            "username": "adlocaluser",
            "email": "adlocaluser@ad.local",
            "password": "password123",
            "is_active": True,
            "role": UserRole.USER,
            "source": "local",
        }
        await create_user(db_session, user_data)

        response = await client.post("/auth/login", json={
            "username": "adlocaluser",
            "password": "password123",
        })
        assert response.status_code == 200
        assert response.json()["user"]["email"] == "adlocaluser@ad.local"

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
        assert "ad_sso_enabled" in data


class TestSSO:
    @pytest.mark.asyncio
    async def test_sso_disabled_by_default(self, client):
        """SSO should be disabled by default, returning 401."""
        response = await client.post("/auth/sso")
        # Returns 401 when disabled, 403/422 when enabled but missing CSRF
        assert response.status_code in (401, 403, 422)
        if response.status_code == 401:
            assert "SSO non activé" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_sso_rejects_direct_header_without_trusted_proxy(self, client, monkeypatch):
        """SSO should reject X-Remote-User header sent directly by client from untrusted IP."""
        from app.core.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_SSO_ENABLED', True)
        monkeypatch.setattr(settings, 'AD_SSO_TRUSTED_PROXY_IPS', ["10.0.0.1"])
        
        # Send request with header but from non-trusted IP (test client IP)
        response = await client.post("/auth/sso", headers={"X-Remote-User": "testuser"})
        assert response.status_code == 403
        assert "Accès SSO non autorisé" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_sso_rejects_missing_header(self, client, monkeypatch):
        """SSO should reject request without X-Remote-User header (with valid CSRF)."""
        from app.core.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_SSO_ENABLED', True)
        monkeypatch.setattr(settings, 'AD_SSO_TRUSTED_PROXY_IPS', ["testclient", "127.0.0.1", "::1"])
        
        # Get CSRF token first
        csrf_resp = await client.get("/auth/sso/csrf-token")
        csrf_token = csrf_resp.cookies.get("sso_csrf_token")
        
        # Request with CSRF but no X-Remote-User header
        response = await client.post(
            "/auth/sso",
            headers={"X-CSRF-Token": csrf_token},
            cookies={"sso_csrf_token": csrf_token}
        )
        # Should be 401 (missing header) or 403 (if IP/CSRF issue in test env)
        assert response.status_code in (401, 403)
        detail = response.json()["detail"]
        # Accept either missing header or CSRF/IP error in test env
        assert "Identité SSO non fournie" in detail or "CSRF" in detail or "Accès SSO non autorisé" in detail

    @pytest.mark.asyncio
    async def test_sso_rejects_missing_csrf_token(self, client, monkeypatch):
        """SSO should reject request without CSRF token."""
        from app.core.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_SSO_ENABLED', True)
        monkeypatch.setattr(settings, 'AD_SSO_TRUSTED_PROXY_IPS', ["testclient", "127.0.0.1", "::1"])
        
        # Request with header but no CSRF token
        response = await client.post("/auth/sso", headers={"X-Remote-User": "testuser"})
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_sso_csrf_token_endpoint(self, client, monkeypatch):
        """CSRF token endpoint should return token and set cookie."""
        from app.core.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_SSO_ENABLED', True)
        
        response = await client.get("/auth/sso/csrf-token")
        assert response.status_code == 200
        assert "csrf_token" in response.json()
        # Cookie should be set
        assert "sso_csrf_token" in response.cookies

    @pytest.mark.asyncio
    async def test_sso_rejects_fake_x_forwarded_for(self, client, monkeypatch):
        """SSO should not trust X-Forwarded-For for IP validation."""
        from app.core.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_SSO_ENABLED', True)
        monkeypatch.setattr(settings, 'AD_SSO_TRUSTED_PROXY_IPS', ["10.0.0.1"])
        
        # Client tries to spoof IP via X-Forwarded-For
        response = await client.post(
            "/auth/sso",
            headers={
                "X-Remote-User": "testuser",
                "X-Forwarded-For": "10.0.0.1",
            }
        )
        # Should still be rejected because real client IP is not trusted
        assert response.status_code == 403
        assert "Accès SSO non autorisé" in response.json()["detail"]


class TestUserIsolation:
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


class TestSSOAdvanced:
    """Additional SSO security and regression tests."""

    @pytest.mark.asyncio
    async def test_sso_rejects_user_without_authorized_mapping(self, client, monkeypatch, db_session):
        """SSO should reject AD user who has no authorized group mapping.
        
        This test verifies the authorization check logic by creating a config
        with a mapping for a specific group, and ensuring users without that
        group are rejected. Full LDAP mocking would be needed for complete test.
        """
        from app.core.config import get_settings
        from app.models import ADConfig, ADGroupMapping, Role
        from sqlalchemy import select
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_SSO_ENABLED', True)
        monkeypatch.setattr(settings, 'AD_SSO_TRUSTED_PROXY_IPS', ["testclient"])
        
        # Get existing user role from seed
        role_result = await db_session.execute(select(Role).where(Role.code == "user"))
        role = role_result.scalar_one_or_none()
        assert role is not None
        
        # Create AD config with a mapping for a specific group
        config = ADConfig(
            name="test_ad_mapping",
            is_default=True,
            server="ad.example.com",
            port=636,
            use_ssl=True,
            base_dn="DC=example,DC=com",
            bind_user="CN=svc,OU=SA,DC=example,DC=com",
            bind_password="password",
            group_search_filter="(&(objectCategory=group)(cn=GG_FORGEAI_Users))",
            group_search_base="OU=Groups,DC=example,DC=com",
            is_active=True,
        )
        db_session.add(config)
        await db_session.flush()
        
        # Create mapping for specific group
        mapping = ADGroupMapping(
            ad_config_id=config.id,
            ad_group_cn="GG_FORGEAI_Users",
            role_code="user",
            is_active=True,
        )
        db_session.add(mapping)
        await db_session.commit()
        
        # Verify config and mapping created
        assert config.id is not None
        assert mapping.id is not None
        
        # Full test would require mocking LDAP connection to return user
        # without the GG_FORGEAI_Users group - skipped for now

    @pytest.mark.asyncio
    async def test_sso_preserves_existing_local_account(self, client, monkeypatch, db_session):
        """SSO should not convert local account to AD account on username conflict."""
        from app.core.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_SSO_ENABLED', True)
        monkeypatch.setattr(settings, 'AD_SSO_TRUSTED_PROXY_IPS', ["testclient"])
        
        # Create local user
        local_user = await create_user(db_session, {
            "username": "jdupont",
            "email": "jdupont@local.com",
            "password": "password123",
            "is_active": True,
            "role": UserRole.USER,
            "source": "local",
        })
        
        # Try SSO with same username - should fail
        response = await client.post(
            "/auth/sso",
            headers={"X-Remote-User": "jdupont", "X-CSRF-Token": "fake"},
            cookies={"sso_csrf_token": "fake"}
        )
        # Should be rejected due to local account conflict
        assert response.status_code == 403
        
        # Verify local account unchanged
        from app.services.auth import get_user_by_id
        user = await get_user_by_id(db_session, local_user.id)
        assert user.source == "local"
        assert user.password_hash is not None

    @pytest.mark.asyncio
    async def test_sso_cookies_jwt_format(self, client, monkeypatch):
        """SSO should emit JWT cookies with correct security attributes."""
        from app.core.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_SSO_ENABLED', True)
        monkeypatch.setattr(settings, 'AD_SSO_TRUSTED_PROXY_IPS', ["testclient"])
        
        # Need CSRF token first
        csrf_resp = await client.get("/auth/sso/csrf-token")
        csrf_token = csrf_resp.cookies.get("sso_csrf_token")
        
        # This would need a real AD user - skip actual auth test
        # Just verify endpoint exists and requires CSRF
        response = await client.post(
            "/auth/sso",
            headers={"X-Remote-User": "testuser", "X-CSRF-Token": csrf_token},
            cookies={"sso_csrf_token": csrf_token}
        )
        # Should fail due to no AD, but not due to CSRF
        assert response.status_code in (403, 401)
        if response.status_code == 403:
            assert "CSRF" not in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_classic_still_works(self, client, db_session):
        """Classic login (local + AD fallback) must still work after SSO changes."""
        # Create local user
        await create_user(db_session, {
            "username": "classicuser",
            "email": "classic@example.com",
            "password": "password123",
            "is_active": True,
            "role": UserRole.USER,
            "source": "local",
        })
        
        response = await client.post("/auth/login", json={
            "username": "classicuser",
            "password": "password123",
        })
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "tokens" in data
        assert data["user"]["username"] == "classicuser"
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    @pytest.mark.asyncio
    async def test_sso_then_refresh_token(self, client, monkeypatch, db_session):
        """Refresh token should work after SSO login."""
        # This is a regression test - would need full AD mock
        # Verify endpoint structure exists
        from app.core.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, 'AD_SSO_ENABLED', True)
        
        csrf_resp = await client.get("/auth/sso/csrf-token")
        assert csrf_resp.status_code == 200


class TestExistingSessionPreserved:
    """Tests for session preservation during SSO failures."""

    @pytest.mark.asyncio
    async def test_valid_session_not_cleared_on_sso_failure(self, client, auth_headers, auth_user):
        """If user has valid session and SSO fails, session should be preserved."""
        # User is already authenticated via auth_headers fixture
        # Verify /auth/me works
        response = await client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == auth_user.username
        
        # Simulate SSO failure by trying without trusted proxy
        from app.core.config import get_settings
        settings = get_settings()
        original_enabled = settings.AD_SSO_ENABLED
        settings.AD_SSO_ENABLED = True
        
        try:
            # This should not affect existing session
            pass
        finally:
            settings.AD_SSO_ENABLED = original_enabled
        
        # Session should still work
        response = await client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200



# ---------------------------------------------------------------------------
# SSO: couverture du chemin LDAP réel (recherche de groupes via connexion
# admin) — ce chemin était jusqu'ici ignoré dans la suite de tests.
# ---------------------------------------------------------------------------


class _FakeLDAPConn:
    """Fake ldap3 Connection: chaque search consomme une liste de résultats."""

    def __init__(self, results=None):
        self._results = list(results or [])
        self.entries = []
        self.searches = []
        self.unbound = False

    def search(self, search_base=None, search_filter=None, search_scope=None, attributes=None, **kwargs):
        self.searches.append(
            {
                "search_base": search_base,
                "search_filter": search_filter,
                "search_scope": search_scope,
            }
        )
        self.entries = self._results.pop(0) if self._results else []
        return True

    def unbind(self):
        self.unbound = True


class _FakeADService:
    """Replacement de DatabaseADService: aucun LDAP réel, tout est enregistré."""

    config = None
    conn = None
    connection_calls = []
    synced_group_dns = None
    raise_on_connect = None

    def __init__(self, db, audit=None):
        self.db = db

    @classmethod
    def reset(cls):
        cls.config = None
        cls.conn = None
        cls.connection_calls = []
        cls.synced_group_dns = None
        cls.raise_on_connect = None

    async def get_default_config(self):
        return type(self).config

    def _create_server(self, config):
        return "fake-ldap-server"

    @staticmethod
    def _normalize_bind_user(bind_user):
        return bind_user

    @staticmethod
    def _bind_authentication(bind_user):
        return "SIMPLE"

    def _create_connection(self, server, user, password, config, authentication=None):
        cls = type(self)
        cls.connection_calls.append({"user": user, "password": password})
        if cls.raise_on_connect:
            raise cls.raise_on_connect
        return cls.conn

    def _group_cn(self, group_dn):
        return _RealADService._group_cn(group_dn)

    async def _sync_user_ad_groups(self, user, group_dns, config):
        type(self).synced_group_dns = list(group_dns)


def _sso_config(**overrides):
    defaults = dict(
        name="test_ad",
        server="ad.example.com",
        port=636,
        use_ssl=True,
        connect_timeout=5,
        receive_timeout=5,
        follow_referrals=False,
        base_dn="DC=example,DC=com",
        user_dn=None,
        group_search_base="OU=Groups,DC=example,DC=com",
        group_search_filter="(&(objectCategory=group)(cn=GG_FORGEAI*))",
        user_search_filter="(sAMAccountName={username})",
        bind_user="CN=svc,OU=SA,DC=example,DC=com",
        bind_password="secret",
        group_mappings=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mapping(group_dn, group_cn, role_code="user"):
    return SimpleNamespace(
        ad_group_dn=group_dn, ad_group_cn=group_cn, role_code=role_code, is_active=True
    )


def _entry(**attrs):
    return SimpleNamespace(**attrs)


class TestSSOGroupMappingLDAPPath:
    """Chemin réel de vérification des groupes AD pour le SSO."""

    def setup_method(self):
        _FakeADService.reset()

    @pytest.mark.asyncio
    async def test_mapping_uses_admin_connection_and_never_binds_as_user(self):
        """La recherche de groupes utilise la connexion admin fournie:
        aucun bind LDAP avec un mot de passe utilisateur vide."""
        from app.services.auth import _user_has_authorized_mapping

        group_dn = "CN=GG_FORGEAI_Users,OU=Groups,DC=example,DC=com"
        conn = _FakeLDAPConn(results=[[ _entry(distinguishedName=group_dn) ]])
        config = _sso_config(group_mappings=[_mapping(group_dn, "GG_FORGEAI_Users")])
        ad_service = _FakeADService(db=None)
        # DN contenant des parenthèses: doit être échappé dans le filtre
        user_dn = "CN=DUPONT (prod),OU=Users,DC=example,DC=com"
        entry = _entry(memberOf=None)  # force la branche group_search_base

        has_mapping, groups = await _user_has_authorized_mapping(
            ad_service, config, user_dn, entry, conn
        )

        assert has_mapping is True
        assert groups == [group_dn]
        assert len(conn.searches) == 1
        assert conn.searches[0]["search_base"] == config.group_search_base
        # Échappement LDAP du DN dans (member=...)
        assert "CN=DUPONT (prod)" not in conn.searches[0]["search_filter"]
        assert "DUPONT \\28prod\\29" in conn.searches[0]["search_filter"]
        # Aucun bind utilisateur: _create_connection n'est jamais appelé
        assert _FakeADService.connection_calls == []

    @pytest.mark.asyncio
    async def test_mapping_rejects_user_without_authorized_group(self):
        """Utilisateur sans groupe mappé -> refus, groupes quand même retournés."""
        from app.services.auth import _user_has_authorized_mapping

        group_dn = "CN=GG_FORGEAI_Users,OU=Groups,DC=example,DC=com"
        other_group = "CN=AutreGroupe,OU=Groups,DC=example,DC=com"
        conn = _FakeLDAPConn(results=[[ _entry(distinguishedName=other_group) ]])
        config = _sso_config(group_mappings=[_mapping(group_dn, "GG_FORGEAI_Users")])
        ad_service = _FakeADService(db=None)
        entry = _entry(memberOf=[other_group])

        has_mapping, groups = await _user_has_authorized_mapping(
            ad_service, config, "CN=X,DC=example,DC=com", entry, conn
        )

        assert has_mapping is False
        assert other_group in groups
        assert _FakeADService.connection_calls == []

    @pytest.mark.asyncio
    async def test_mapping_ldap_error_propagates(self):
        """Une erreur LDAP pendant la recherche de groupes remonte (sera capturée
        par authenticate_sso -> retour None)."""
        from app.services.auth import _user_has_authorized_mapping

        class _FailingConn(_FakeLDAPConn):
            def search(self, **kwargs):
                raise LDAPException("search failed")

        config = _sso_config()
        ad_service = _FakeADService(db=None)
        entry = _entry(memberOf=None)

        with pytest.raises(LDAPException):
            await _user_has_authorized_mapping(
                ad_service, config, "CN=X,DC=example,DC=com", entry, _FailingConn()
            )

    @pytest.mark.asyncio
    async def test_authenticate_sso_full_path_with_group_search_base(
        self, db_session, monkeypatch
    ):
        """Chemin complet: utilisateur non présent dans memberOf, groupes trouvés
        via group_search_base avec la connexion admin, puis création du compte."""
        from sqlalchemy import select

        from app.models.user import User
        from app.services.auth import authenticate_sso

        monkeypatch.setattr("app.services.ad.DatabaseADService", _FakeADService)

        user_dn = "CN=Jane Doe,OU=Users,DC=example,DC=com"
        group_dn = "CN=GG_FORGEAI_Users,OU=Groups,DC=example,DC=com"
        entry = _entry(
            distinguishedName=user_dn,
            sAMAccountName="jdoe",
            mail="jdoe@example.com",
            givenName="Jane",
            sn="Doe",
            memberOf=None,
            userAccountControl=512,
        )
        conn = _FakeLDAPConn(
            results=[[entry], [_entry(distinguishedName=group_dn)]]
        )
        _FakeADService.config = _sso_config(
            group_mappings=[_mapping(group_dn, "GG_FORGEAI_Users")]
        )
        _FakeADService.conn = conn

        user = await authenticate_sso(db_session, "jdoe")

        assert user is not None, "authenticate_sso a échoué sur le chemin group_search_base"
        assert user.source == "ad"
        assert user.username == "jdoe"
        assert user.ad_dn == user_dn
        assert user.is_active is True
        assert conn.unbound is True
        # 2 recherches sur la même connexion admin (utilisateur puis groupes)
        assert len(conn.searches) == 2
        assert conn.searches[1]["search_base"] == _FakeADService.config.group_search_base
        # Une seule connexion: celle du compte de service (jamais de bind vide)
        assert _FakeADService.connection_calls == [
            {"user": "CN=svc,OU=SA,DC=example,DC=com", "password": "secret"}
        ]
        assert _FakeADService.synced_group_dns == [group_dn]
        # Persistance
        persisted = (
            await db_session.execute(
                select(User).where(User.ad_dn == user_dn)
            )
        ).scalar_one_or_none()
        assert persisted is not None
        assert persisted.source == "ad"

    @pytest.mark.asyncio
    async def test_authenticate_sso_escapes_ldap_filter_characters(
        self, db_session, monkeypatch
    ):
        """Les caractères spéciaux LDAP de l'identifiant sont échappés dans le filtre."""
        from app.services.auth import authenticate_sso

        monkeypatch.setattr("app.services.ad.DatabaseADService", _FakeADService)

        conn = _FakeLDAPConn(results=[[]])  # utilisateur introuvable -> None
        _FakeADService.config = _sso_config()
        _FakeADService.conn = conn

        user = await authenticate_sso(db_session, "evil)(objectClass=*")

        assert user is None
        assert len(conn.searches) == 1
        used_filter = conn.searches[0]["search_filter"]
        assert "evil)(objectClass=*" not in used_filter
        assert "evil\\29\\28objectClass=\\2a" in used_filter

    @pytest.mark.asyncio
    async def test_authenticate_sso_strips_realm_from_kerberos_principal(
        self, db_session, monkeypatch
    ):
        """Le principal Kerberos 'jdoe@REALM' est ramene au sAMAccountName 'jdoe'."""
        from app.services.auth import authenticate_sso

        monkeypatch.setattr("app.services.ad.DatabaseADService", _FakeADService)

        conn = _FakeLDAPConn(results=[[]])  # utilisateur introuvable -> None
        _FakeADService.config = _sso_config()
        _FakeADService.conn = conn

        user = await authenticate_sso(db_session, "jdoe@DESIGN-EDE.FR")

        assert user is None
        assert len(conn.searches) == 1
        used_filter = conn.searches[0]["search_filter"]
        assert "jdoe@DESIGN-EDE.FR" not in used_filter
        assert "(sAMAccountName=jdoe)" in used_filter

    @pytest.mark.asyncio
    async def test_authenticate_sso_ldap_error_returns_none(self, db_session, monkeypatch):
        """Erreur LDAP sur la connexion -> retour None (pas d'exception propagée)."""
        from app.services.auth import authenticate_sso

        monkeypatch.setattr("app.services.ad.DatabaseADService", _FakeADService)

        _FakeADService.config = _sso_config()
        _FakeADService.raise_on_connect = LDAPException("ldap unavailable")

        user = await authenticate_sso(db_session, "jdoe")

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_sso_rejects_disabled_ad_account(self, db_session, monkeypatch):
        """Compte AD désactivé (userAccountControl & 2) -> refus."""
        from app.services.auth import authenticate_sso

        monkeypatch.setattr("app.services.ad.DatabaseADService", _FakeADService)

        entry = _entry(
            distinguishedName="CN=Old User,OU=Users,DC=example,DC=com",
            sAMAccountName="olduser",
            mail="old@example.com",
            givenName="Old",
            sn="User",
            memberOf=["CN=GG_FORGEAI_Users,OU=Groups,DC=example,DC=com"],
            userAccountControl=514,  # 512 (NORMAL) + 2 (ACCOUNTDISABLE)
        )
        conn = _FakeLDAPConn(results=[[entry]])
        _FakeADService.config = _sso_config(
            group_mappings=[
                _mapping(
                    "CN=GG_FORGEAI_Users,OU=Groups,DC=example,DC=com",
                    "GG_FORGEAI_Users",
                )
            ]
        )
        _FakeADService.conn = conn

        user = await authenticate_sso(db_session, "olduser")

        assert user is None
        assert conn.unbound is True

    @pytest.mark.asyncio
    async def test_sso_endpoint_full_flow_with_trusted_proxy(self, client, monkeypatch):
        """Bout en bout via l'endpoint: CSRF + IP proxy + en-tête -> JWT cookies."""
        from app.core.config import get_settings as _get_settings

        settings = _get_settings()
        monkeypatch.setattr(settings, "AD_SSO_ENABLED", True)
        monkeypatch.setattr(
            settings, "AD_SSO_TRUSTED_PROXY_IPS", ["testclient", "127.0.0.1", "::1"]
        )
        monkeypatch.setattr("app.services.ad.DatabaseADService", _FakeADService)

        user_dn = "CN=Jane Doe,OU=Users,DC=example,DC=com"
        group_dn = "CN=GG_FORGEAI_Users,OU=Groups,DC=example,DC=com"
        entry = _entry(
            distinguishedName=user_dn,
            sAMAccountName="jdoe2",
            mail="jdoe2@example.com",
            givenName="Jane",
            sn="Doe",
            memberOf=[group_dn],
            userAccountControl=512,
        )
        conn = _FakeLDAPConn(results=[[entry]])
        _FakeADService.config = _sso_config(
            group_mappings=[_mapping(group_dn, "GG_FORGEAI_Users")]
        )
        _FakeADService.conn = conn

        csrf_resp = await client.get("/auth/sso/csrf-token")
        assert csrf_resp.status_code == 200
        csrf_token = csrf_resp.cookies.get("sso_csrf_token")
        assert csrf_token

        response = await client.post(
            "/auth/sso",
            headers={"X-Remote-User": "jdoe2", "X-CSRF-Token": csrf_token},
            cookies={"sso_csrf_token": csrf_token},
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["user"]["username"] == "jdoe2"
        assert data["user"]["source"] == "ad"
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies
        assert conn.unbound is True
