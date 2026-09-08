import pytest


class TestRoleCrud:
    @pytest.mark.asyncio
    async def test_create_role_returns_valid_response(
        self, client, admin_headers
    ):
        """POST /admin/users/roles returns 201 with id, code, name,
        created_at, updated_at — no MissingGreenlet."""
        response = await client.post(
            "/admin/users/roles",
            headers=admin_headers,
            json={
                "name": "Test Role",
                "description": "A test role",
            },
        )
        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert data["code"] == "test_role"
        assert data["name"] == "Test Role"
        assert data["description"] == "A test role"
        assert data["is_system"] is False
        assert data["is_active"] is True
        assert "created_at" in data
        assert "updated_at" in data
        assert "permissions" in data

    @pytest.mark.asyncio
    async def test_create_role_with_custom_code(
        self, client, admin_headers
    ):
        """POST /admin/users/roles with explicit code uses it."""
        response = await client.post(
            "/admin/users/roles",
            headers=admin_headers,
            json={
                "code": "custom_code",
                "name": "Custom Code Role",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["code"] == "custom_code"

    @pytest.mark.asyncio
    async def test_update_role_returns_valid_response(
        self, client, admin_headers
    ):
        """PATCH /admin/users/roles/{id} returns 200 with updated
        timestamps — no MissingGreenlet."""
        create_resp = await client.post(
            "/admin/users/roles",
            headers=admin_headers,
            json={"name": "Update Test Role"},
        )
        assert create_resp.status_code == 201
        role_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/admin/users/roles/{role_id}",
            headers=admin_headers,
            json={"name": "Updated Role Name"},
        )
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["name"] == "Updated Role Name"
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_get_role_returns_valid_response(
        self, client, admin_headers
    ):
        """GET /admin/users/roles/{id} returns full role with
        permissions — no MissingGreenlet."""
        create_resp = await client.post(
            "/admin/users/roles",
            headers=admin_headers,
            json={"name": "Get Test Role"},
        )
        assert create_resp.status_code == 201
        role_id = create_resp.json()["id"]

        get_resp = await client.get(
            f"/admin/users/roles/{role_id}",
            headers=admin_headers,
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == role_id
        assert data["name"] == "Get Test Role"
        assert "created_at" in data
        assert "updated_at" in data
        assert "permissions" in data
