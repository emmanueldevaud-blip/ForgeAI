from datetime import timedelta

import pytest

from app.core.config import get_settings
from app.models.user import UserRole
from app.services.auth import create_user, hash_password
from app.services.rbac import RBACService


class TestAdminUsersEndpoints:
    @pytest.mark.asyncio
    async def test_admin_can_list_users(self, client, admin_headers, db_session):
        """Admin can list users with pagination."""
        for i in range(5):
            await create_user(db_session, {
                "username": f"listuser{i}",
                "email": f"listuser{i}@example.com",
                "password": "password123",
                "is_active": True,                "role": UserRole.USER,
                "source": "local",
            })

        response = await client.get("/admin/users", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert data["total"] >= 5
        assert data["page"] == 1
        assert data["page_size"] == 20

    @pytest.mark.asyncio
    async def test_admin_can_list_users_with_pagination(self, client, admin_headers, db_session):
        """Admin can paginate user list."""
        for i in range(25):
            await create_user(db_session, {
                "username": f"pageuser{i}",
                "email": f"pageuser{i}@example.com",
                "password": "password123",
                "is_active": True,                "role": UserRole.USER,
                "source": "local",
            })

        response = await client.get("/admin/users?page=2&page_size=10", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 10
        assert len(data["users"]) == 10

    @pytest.mark.asyncio
    async def test_admin_can_search_users_by_username(self, client, admin_headers, db_session):
        """Admin can search users by username."""
        await create_user(db_session, {
            "username": "searchuser_unique",
            "email": "search@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.get("/admin/users?search=searchuser_unique", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(u["username"] == "searchuser_unique" for u in data["users"])

    @pytest.mark.asyncio
    async def test_admin_can_search_users_by_email(self, client, admin_headers, db_session):
        """Admin can search users by email."""
        await create_user(db_session, {
            "username": "emailuser",
            "email": "unique_email_search@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.get("/admin/users?search=unique_email_search", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(u["email"] == "unique_email_search@example.com" for u in data["users"])

    @pytest.mark.asyncio
    async def test_admin_can_search_users_by_name(self, client, admin_headers, db_session):
        """Admin can search users by first/last name."""
        await create_user(db_session, {
            "username": "nameuser",
            "email": "name@example.com",
            "password": "password123",
            "first_name": "Jean",
            "last_name": "Dupont",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.get("/admin/users?search=Jean", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(u["first_name"] == "Jean" for u in data["users"])

    @pytest.mark.asyncio
    async def test_admin_can_filter_by_role(self, client, admin_headers, db_session):
        """Admin can filter users by role."""
        await create_user(db_session, {
            "username": "adminrole",
            "email": "adminrole@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.ADMIN,
            "source": "local",
        })
        await create_user(db_session, {
            "username": "userrole",
            "email": "userrole@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.get("/admin/users?role=admin", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert all(u["role"] == "admin" for u in data["users"])

    @pytest.mark.asyncio
    async def test_admin_can_filter_by_is_active(self, client, admin_headers, db_session):
        """Admin can filter users by active status."""
        await create_user(db_session, {
            "username": "activeuser",
            "email": "active@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })
        await create_user(db_session, {
            "username": "inactiveuser",
            "email": "inactive@example.com",
            "password": "password123",
            "is_active": False,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.get("/admin/users?is_active=true", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert all(u["is_active"] is True for u in data["users"])

        response = await client.get("/admin/users?is_active=false", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert all(u["is_active"] is False for u in data["users"])

    @pytest.mark.asyncio
    async def test_admin_can_filter_by_source(self, client, admin_headers, db_session):
        """Admin can filter users by source."""
        await create_user(db_session, {
            "username": "localuser",
            "email": "local@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })
        await create_user(db_session, {
            "username": "aduser",
            "email": "ad@example.com",
            "first_name": "AD",
            "last_name": "User",
            "is_active": True,            "role": UserRole.USER,
            "source": "ad",
        })

        response = await client.get("/admin/users?source=local", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert all(u["source"] == "local" for u in data["users"])

        response = await client.get("/admin/users?source=ad", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert all(u["source"] == "ad" for u in data["users"])

    @pytest.mark.asyncio
    async def test_admin_can_get_user_detail(self, client, admin_headers, db_session):
        """Admin can get user detail with roles."""
        user = await create_user(db_session, {
            "username": "detailuser",
            "email": "detail@example.com",
            "password": "password123",
            "first_name": "Detail",
            "last_name": "User",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.get(f"/admin/users/{user.id}", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user.id
        assert data["username"] == "detailuser"
        assert data["email"] == "detail@example.com"
        assert data["first_name"] == "Detail"
        assert data["last_name"] == "User"
        assert data["is_active"] is True
        assert data["role"] == "user"
        assert data["source"] == "local"
        assert "roles" in data
        assert "password" not in data
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_admin_get_nonexistent_user_returns_404(self, client, admin_headers):
        """Getting non-existent user returns 404."""
        response = await client.get("/admin/users/99999", headers=admin_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_can_create_user(self, client, admin_headers):
        """Admin can create a new user."""
        response = await client.post("/admin/users", headers=admin_headers, json={
            "username": "newadminuser",
            "email": "newadmin@example.com",
            "password": "newpassword123",
            "first_name": "New",
            "last_name": "Admin",
            "is_active": True,
            "role": "admin",
            "source": "local",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newadminuser"
        assert data["email"] == "newadmin@example.com"
        assert data["first_name"] == "New"
        assert data["last_name"] == "Admin"
        assert data["is_active"] is True
        assert data["role"] == "admin"
        assert "password" not in data
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_admin_create_user_duplicate_username_rejected(self, client, admin_headers, db_session):
        """Creating user with duplicate username is rejected."""
        await create_user(db_session, {
            "username": "duplicate",
            "email": "dup1@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.post("/admin/users", headers=admin_headers, json={
            "username": "duplicate",
            "email": "dup2@example.com",
            "password": "password123",
        })
        assert response.status_code == 400
        assert "déjà utilisé" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_admin_create_user_duplicate_email_rejected(self, client, admin_headers, db_session):
        """Creating user with duplicate email is rejected."""
        await create_user(db_session, {
            "username": "user1",
            "email": "duplicate@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.post("/admin/users", headers=admin_headers, json={
            "username": "user2",
            "email": "duplicate@example.com",
            "password": "password123",
        })
        assert response.status_code == 400
        assert "déjà utilisé" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_admin_create_user_local_disabled_rejected(self, client, admin_headers, monkeypatch):
        """Creating local user when local auth disabled is rejected."""
        settings = get_settings()
        monkeypatch.setattr(settings, 'AUTH_LOCAL_ENABLED', False)

        response = await client.post("/admin/users", headers=admin_headers, json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "newpassword123",
        })
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_update_user(self, client, admin_headers, db_session):
        """Admin can update user details."""
        user = await create_user(db_session, {
            "username": "updateuser",
            "email": "update@example.com",
            "password": "password123",
            "first_name": "Old",
            "last_name": "Name",
            "is_active": True,
            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.patch(f"/admin/users/{user.id}", headers=admin_headers, json={
            "first_name": "Updated",
            "last_name": "Name",
            "role": "admin",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Updated"
        assert data["last_name"] == "Name"
        assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_admin_can_deactivate_user(self, client, admin_headers, db_session):
        """Admin can deactivate a user."""
        user = await create_user(db_session, {
            "username": "deactivateuser",
            "email": "deactivate@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.post(f"/admin/users/{user.id}/toggle-active", headers=admin_headers, json={
            "is_active": False
        })
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

        response = await client.get(f"/admin/users/{user.id}", headers=admin_headers)
        assert response.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_admin_can_reactivate_user(self, client, admin_headers, db_session):
        """Admin can reactivate a user."""
        user = await create_user(db_session, {
            "username": "reactivateuser",
            "email": "reactivate@example.com",
            "password": "password123",
            "is_active": False,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.post(f"/admin/users/{user.id}/toggle-active", headers=admin_headers, json={
            "is_active": True
        })
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_admin_cannot_deactivate_self(self, client, admin_headers, admin_user):
        """Admin cannot deactivate their own account."""
        response = await client.post(f"/admin/users/{admin_user.id}/toggle-active", headers=admin_headers, json={
            "is_active": False
        })
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_deactivated_user_cannot_login(self, client, db_session):
        """Deactivated user cannot authenticate."""
        user = await create_user(db_session, {
            "username": "deactivatedlogin",
            "email": "deactivatedlogin@example.com",
            "password": "password123",
            "is_active": False,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.post("/auth/login", json={
            "username": "deactivatedlogin",
            "password": "password123",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_can_reset_password(self, client, admin_headers, db_session):
        """Admin can reset user password."""
        user = await create_user(db_session, {
            "username": "resetuser",
            "email": "reset@example.com",
            "password": "oldpassword",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.post(f"/admin/users/{user.id}/reset-password", headers=admin_headers, json={
            "new_password": "newpassword123"
        })
        assert response.status_code == 200

        login = await client.post("/auth/login", json={
            "username": "resetuser",
            "password": "newpassword123",
        })
        assert login.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_cannot_reset_password_ad_user(self, client, admin_headers, db_session):
        """Admin cannot reset password for AD user."""
        user = await create_user(db_session, {
            "username": "adresetuser",
            "email": "adreset@example.com",
            "first_name": "AD",
            "last_name": "User",
            "is_active": True,            "role": UserRole.USER,
            "source": "ad",
        })

        response = await client.post(f"/admin/users/{user.id}/reset-password", headers=admin_headers, json={
            "new_password": "newpassword123"
        })
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_admin_can_delete_user(self, client, admin_headers, db_session):
        """Admin can delete a user."""
        user = await create_user(db_session, {
            "username": "deleteuser",
            "email": "delete@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.delete(f"/admin/users/{user.id}", headers=admin_headers)
        assert response.status_code == 200

        response = await client.get(f"/admin/users/{user.id}", headers=admin_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_cannot_delete_self(self, client, admin_headers, admin_user):
        """Admin cannot delete their own account."""
        response = await client.delete(f"/admin/users/{admin_user.id}", headers=admin_headers)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_admin_delete_nonexistent_user_returns_404(self, client, admin_headers):
        """Deleting non-existent user returns 404."""
        response = await client.delete("/admin/users/99999", headers=admin_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_non_admin_cannot_access_admin_users(self, client, auth_headers):
        """Non-admin user gets 403 on admin user endpoints."""
        endpoints = [
            ("GET", "/admin/users"),
            ("GET", "/admin/users/1"),
            ("POST", "/admin/users"),
            ("PATCH", "/admin/users/1"),
            ("POST", "/admin/users/1/toggle-active"),
            ("POST", "/admin/users/1/reset-password"),
            ("DELETE", "/admin/users/1"),
        ]
        for method, endpoint in endpoints:
            if method == "GET":
                response = await client.get(endpoint, headers=auth_headers)
            elif method == "POST":
                response = await client.post(endpoint, headers=auth_headers, json={})
            elif method == "PATCH":
                response = await client.patch(endpoint, headers=auth_headers, json={})
            elif method == "DELETE":
                response = await client.delete(endpoint, headers=auth_headers)
            assert response.status_code == 403, f"{method} {endpoint} should return 403"

    @pytest.mark.asyncio
    async def test_admin_can_assign_role(self, client, admin_headers, db_session):
        """Admin can assign a role to a user."""
        user = await create_user(db_session, {
            "username": "roleuser",
            "email": "role@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        rbac = RBACService(db_session)
        role = await rbac.get_role_by_code("admin")
        if not role:
            role = await rbac.create_role("test_admin", "Test Admin", is_system=False)

        response = await client.post(f"/admin/users/{user.id}/roles", headers=admin_headers, json={
            "role_id": role.id
        })
        assert response.status_code == 201

        response = await client.get(f"/admin/users/{user.id}", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert any(r["code"] == role.code for r in data["roles"])

    @pytest.mark.asyncio
    async def test_admin_can_remove_role(self, client, admin_headers, db_session):
        """Admin can remove a role from a user."""
        rbac = RBACService(db_session)
        role = await rbac.get_role_by_code("admin")
        if not role:
            role = await rbac.create_role("test_admin2", "Test Admin 2", is_system=False)

        user = await create_user(db_session, {
            "username": "removeroleuser",
            "email": "removerole@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })
        await rbac.assign_role_to_user(user.id, role.id)

        response = await client.delete(f"/admin/users/{user.id}/roles/{role.id}", headers=admin_headers)
        assert response.status_code == 200

        response = await client.get(f"/admin/users/{user.id}", headers=admin_headers)
        data = response.json()
        assert not any(r["code"] == role.code for r in data["roles"])

    @pytest.mark.asyncio
    async def test_admin_can_list_roles(self, client, admin_headers):
        """Admin can list available roles."""
        response = await client.get("/admin/users/roles", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert any(r["code"] == "admin" for r in data)

    @pytest.mark.asyncio
    async def test_admin_can_get_user_permissions(self, client, admin_headers, db_session):
        """Admin can get user's effective permissions."""
        user = await create_user(db_session, {
            "username": "permuser",
            "email": "perm@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.ADMIN,
            "source": "local",
        })

        response = await client.get(f"/admin/users/{user.id}/permissions", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert any(p["code"] == "*" for p in data)

    @pytest.mark.asyncio
    async def test_password_hash_never_in_response(self, client, admin_headers, db_session):
        """Password hash is never returned in API responses."""
        user = await create_user(db_session, {
            "username": "hashcheck",
            "email": "hash@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        endpoints = [
            ("GET", f"/admin/users/{user.id}"),
            ("GET", "/admin/users"),
            ("POST", "/admin/users", {"username": "newuser", "email": "new@example.com", "password": "password123"}),
            ("PATCH", f"/admin/users/{user.id}", {"first_name": "Updated"}),
        ]

        for method, endpoint, *body in endpoints:
            if method == "GET":
                response = await client.get(endpoint, headers=admin_headers)
            elif method == "POST":
                response = await client.post(endpoint, headers=admin_headers, json=body[0])
            elif method == "PATCH":
                response = await client.patch(endpoint, headers=admin_headers, json=body[0])

            if response.status_code in (200, 201):
                data = response.json()
                if isinstance(data, dict) and "users" in data:
                    users = data["users"]
                elif isinstance(data, list):
                    users = data
                else:
                    users = [data]

                for u in users:
                    assert "password" not in u
                    assert "password_hash" not in u

    @pytest.mark.asyncio
    async def test_admin_user_sorting(self, client, admin_headers, db_session):
        """Admin can sort users by different fields."""
        await create_user(db_session, {
            "username": "zuser",
            "email": "z@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })
        await create_user(db_session, {
            "username": "auser",
            "email": "a@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.get("/admin/users?sort_by=username&sort_order=asc&page_size=5", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        usernames = [u["username"] for u in data["users"] if u["username"] in ("auser", "zuser")]
        assert usernames.index("auser") < usernames.index("zuser")

        response = await client.get("/admin/users?sort_by=username&sort_order=desc&page_size=5", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        usernames = [u["username"] for u in data["users"] if u["username"] in ("auser", "zuser")]
        assert usernames.index("zuser") < usernames.index("auser")

    @pytest.mark.asyncio
    async def test_combined_filters(self, client, admin_headers, db_session):
        """Admin can combine search, filter, and pagination."""
        await create_user(db_session, {
            "username": "filteradmin",
            "email": "filteradmin@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.ADMIN,
            "source": "local",
        })
        await create_user(db_session, {
            "username": "filteruser",
            "email": "filteruser@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })
        await create_user(db_session, {
            "username": "inactiveadmin",
            "email": "inactiveadmin@example.com",
            "password": "password123",
            "is_active": False,            "role": UserRole.ADMIN,
            "source": "local",
        })

        response = await client.get(
            "/admin/users?search=filter&role=admin&is_active=true&page_size=10",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["users"][0]["username"] == "filteradmin"


class TestAdminUsersSecurity:
    @pytest.mark.asyncio
    async def test_requires_user_view_permission(self, client, auth_headers, db_session):
        """Endpoints require user_view permission."""
        user = await create_user(db_session, {
            "username": "permtest",
            "email": "permtest@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        rbac = RBACService(db_session)
        role = await rbac.get_role_by_code("user")
        if role:
            perm = await rbac.get_permission_by_code("user_view")
            if perm:
                await rbac.remove_permission_from_role(role.id, perm.id)

        response = await client.get("/admin/users", headers=auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_requires_user_create_permission(self, client, auth_headers):
        """Create user requires user_create permission."""
        response = await client.post("/admin/users", headers=auth_headers, json={
            "username": "new", "email": "new@example.com", "password": "password123"
        })
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_requires_user_update_permission(self, client, auth_headers, db_session):
        """Update user requires user_update permission."""
        user = await create_user(db_session, {
            "username": "updateperm",
            "email": "updateperm@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })
        response = await client.patch(f"/admin/users/{user.id}", headers=auth_headers, json={
            "first_name": "Updated"
        })
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_requires_user_delete_permission(self, client, auth_headers, db_session):
        """Delete user requires user_delete permission."""
        user = await create_user(db_session, {
            "username": "deleteperm",
            "email": "deleteperm@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })
        response = await client.delete(f"/admin/users/{user.id}", headers=auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_requires_user_manage_roles_permission(self, client, auth_headers, db_session):
        """Assign/remove role requires user_manage_roles permission."""
        rbac = RBACService(db_session)
        role = await rbac.get_role_by_code("admin")
        if not role:
            role = await rbac.create_role("test_admin3", "Test Admin 3", is_system=False)

        user = await create_user(db_session, {
            "username": "roleperm",
            "email": "roleperm@example.com",
            "password": "password123",
            "is_active": True,            "role": UserRole.USER,
            "source": "local",
        })

        response = await client.post(f"/admin/users/{user.id}/roles", headers=auth_headers, json={
            "role_id": role.id
        })
        assert response.status_code == 403

        response = await client.delete(f"/admin/users/{user.id}/roles/{role.id}", headers=auth_headers)
        assert response.status_code == 403