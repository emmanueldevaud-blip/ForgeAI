"""Regressions ciblées sur les correctifs d'audit du 2026-09-29.

Couvre :
- fermeture des routes /volunteers/* (authentification + RBAC) ;
- couverture du catalogue de permissions par les codes utilisés par l'API ;
- absence du rôle super_admin ;
- suppression des routes occupancies dupliquées ;
- quota rate limiting sur /auth/login ;
- exigence de admin.access pour la gestion des utilisateurs.
"""

import pathlib
import re

import pytest

from app.api.housing import router as housing_router
from app.core.config import get_settings
from app.core.limiter import limiter
from app.services.rbac import RBACService

VOLUNTEER_PAYLOAD = {"first_name": "Ana", "last_name": "Test"}


def _catalog_codes() -> set[str]:
    src = (pathlib.Path("app/services/rbac.py")).read_text(encoding="utf-8")
    block = src.split("default_permissions = [", 1)[1].split("]", 1)[0]
    return set(re.findall(r'\("([a-z0-9_.:]+)"', block))


def _api_permission_codes() -> set[str]:
    codes: set[str] = set()
    for path in pathlib.Path("app/api").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in (
            r'require_permission\(\s*"([a-z0-9_.:]+)"',
            r'require_any_permission\(([^)]*)\)',
            r'require_all_permissions\(([^)]*)\)',
            r'require_permissions\(([^)]*)\)',
            r'user_has_permission\([^,]+,\s*"([a-z0-9_.:]+)"',
        ):
            for match in re.findall(pattern, text):
                if isinstance(match, tuple):
                    match = match[0]
                for code in re.findall(r'"([a-z0-9_.:]+)"', match) or [match]:
                    if re.fullmatch(r"[a-z0-9_.:]+", code):
                        codes.add(code)
    return codes


class TestVolunteersAuth:
    @pytest.mark.asyncio
    async def test_anonymous_cannot_touch_volunteers(self, client):
        assert (await client.get("/volunteers/")).status_code == 401
        assert (
            await client.post("/volunteers/", json=VOLUNTEER_PAYLOAD)
        ).status_code == 401
        assert (
            await client.put("/volunteers/1", json=VOLUNTEER_PAYLOAD)
        ).status_code == 401
        assert (await client.delete("/volunteers/1")).status_code == 401

    @pytest.mark.asyncio
    async def test_authenticated_without_permission_can_only_read(
        self, client, auth_headers
    ):
        assert (await client.get("/volunteers/", headers=auth_headers)).status_code == 200
        assert (
            await client.post("/volunteers/", json=VOLUNTEER_PAYLOAD, headers=auth_headers)
        ).status_code == 403
        assert (
            await client.put("/volunteers/1", json=VOLUNTEER_PAYLOAD, headers=auth_headers)
        ).status_code == 403
        assert (
            await client.delete("/volunteers/1", headers=auth_headers)
        ).status_code == 403

    @pytest.mark.asyncio
    async def test_volunteers_manage_allows_writes(self, client, auth_user, auth_headers, db_session):
        rbac = RBACService(db_session)
        role = await rbac.create_role("vol-manager-test", "Gestion volontaires")
        perm = await rbac.get_permission_by_code("volunteers.manage")
        assert perm is not None, "volunteers.manage doit exister dans le catalogue"
        await rbac.assign_permission_to_role(role.id, perm.id)
        await rbac.assign_role_to_user(auth_user.id, role.id)
        db_session.expire_all()

        created = await client.post(
            "/volunteers/", json=VOLUNTEER_PAYLOAD, headers=auth_headers
        )
        assert created.status_code == 201
        volunteer_id = created.json()["id"]

        assert (
            await client.delete(f"/volunteers/{volunteer_id}", headers=auth_headers)
        ).status_code == 204


class TestPermissionCatalog:
    def test_every_api_permission_code_exists_in_catalog(self):
        missing = sorted(_api_permission_codes() - _catalog_codes())
        assert missing == [], f"Permissions utilisées par l'API mais absentes du seed : {missing}"

    def test_formerly_missing_codes_are_seeded(self):
        catalog = _catalog_codes()
        for code in (
            "permission_create",
            "permission_update",
            "permission_delete",
            "volunteers.manage",
            "admin.access",
        ):
            assert code in catalog, f"{code} doit être présent dans default_permissions"

    def test_frontend_permission_codes_exist_in_catalog(self):
        catalog = _catalog_codes()
        used = set()
        for path in pathlib.Path("src/public/js").rglob("*.js"):
            text = path.read_text(encoding="utf-8", errors="replace")
            used |= set(re.findall(r"hasPermission\(\s*'([a-z0-9_.:]+)'\s*\)", text))
        missing = sorted(used - catalog)
        assert missing == [], f"Permissions frontend absentes du catalogue : {missing}"


class TestSuperAdminRemoved:
    @pytest.mark.asyncio
    async def test_seed_creates_no_super_admin_role(self, db_session):
        rbac = RBACService(db_session)
        assert await rbac.get_role_by_code("super_admin") is None
        assert await rbac.get_role_by_code("admin") is not None
        assert await rbac.get_role_by_code("user") is not None

    def test_require_super_admin_is_gone(self):
        import app.api.deps as deps

        assert not hasattr(deps, "require_super_admin")


class TestHousingRouteDeduplication:
    def test_occupancy_routes_defined_once(self):
        counts: dict[tuple[str, str], int] = {}
        for route in housing_router.routes:
            methods = getattr(route, "methods", None) or set()
            for method in methods:
                key = (method.upper(), route.path)
                counts[key] = counts.get(key, 0) + 1
        duplicates = {k: v for k, v in counts.items() if v > 1}
        assert duplicates == {}, f"Routes dupliquées dans le router housing : {duplicates}"


class TestAdminAccessGate:
    @pytest.mark.asyncio
    async def test_user_view_alone_cannot_manage_users(
        self, client, auth_user, db_session
    ):
        rbac = RBACService(db_session)
        username = auth_user.username
        role = await rbac.create_role("limited-admin-test", "Administration restreinte")
        user_view = await rbac.get_permission_by_code("user_view")
        await rbac.assign_permission_to_role(role.id, user_view.id)
        await rbac.assign_role_to_user(auth_user.id, role.id)
        db_session.expire_all()

        login = await client.post(
            "/auth/login",
            json={"username": username, "password": "testpassword123"},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.cookies.get('access_token')}"}

        assert (await client.get("/admin/users", headers=headers)).status_code == 403
        assert (await client.get("/auth/users", headers=headers)).status_code == 403

        admin_access = await rbac.get_permission_by_code("admin.access")
        await rbac.assign_permission_to_role(role.id, admin_access.id)
        db_session.expire_all()

        assert (await client.get("/admin/users", headers=headers)).status_code == 200
        assert (await client.get("/auth/users", headers=headers)).status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_still_manage_users(self, client, admin_headers):
        assert (await client.get("/admin/users", headers=admin_headers)).status_code == 200
        assert (await client.get("/auth/users", headers=admin_headers)).status_code == 200


class TestLoginRateLimit:
    @pytest.mark.asyncio
    async def test_login_is_rate_limited(self, client):
        settings = get_settings()
        assert settings.RATE_LIMIT_ENABLED is False, (
            "La suite de tests doit désactiver le quota (voir tests/conftest.py)"
        )

        limiter.enabled = True
        try:
            statuses = []
            for _ in range(settings.RATE_LIMIT_REQUESTS + 1):
                response = await client.post(
                    "/auth/login", json={"username": "unknown", "password": "bad"}
                )
                statuses.append(response.status_code)
            assert statuses[-1] == 429, f"Statuts observés : {statuses}"
            assert all(s in (401, 429) for s in statuses), statuses
        finally:
            limiter.enabled = False
