import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Group, GroupRole, PermissionModel, Role, RolePermission, UserGroup
from app.models.user import User, UserRole
from app.services.auth import create_user, get_user_by_id
from app.services.rbac import RBACService, seed_default_rbac


@pytest.fixture
async def seed_rbac():
    """The test creates exactly the RBAC records it needs."""
    yield


@pytest.mark.asyncio
async def test_local_user_in_group_receives_group_role_permissions(db_session):
    user = await create_user(db_session, {
        "username": "jean-rbac", "email": "jean-rbac@example.com",
        "password": "password123", "source": "local",
    })
    permission = PermissionModel(code="projects.create", name="Créer les projets", module="projects")
    role = Role(code="engineering", name="Bureau d'études")
    group = Group(code="engineering-local", name="Bureau d'études", source="local")
    db_session.add_all([permission, role, group])
    await db_session.flush()
    db_session.add_all([
        RolePermission(role_id=role.id, permission_id=permission.id),
        GroupRole(group_id=group.id, role_id=role.id),
        UserGroup(user_id=user.id, group_id=group.id),
    ])
    await db_session.commit()

    loaded_user = await get_user_by_id(db_session, user.id)
    permissions = await RBACService(db_session).get_user_permissions(loaded_user)
    assert permissions == {"projects.create"}


@pytest.mark.asyncio
async def test_me_exposes_backend_computed_permissions(client, db_session):
    user = await create_user(db_session, {
        "username": "direct-rbac", "email": "direct-rbac@example.com",
        "password": "password123", "source": "local",
    })
    role = Role(code="project-reader", name="Lecture projets")
    permission = PermissionModel(code="projects.read", name="Voir les projets", module="projects")
    db_session.add_all([role, permission])
    await db_session.flush()
    db_session.add_all([
        RolePermission(role_id=role.id, permission_id=permission.id),
    ])
    from app.models import UserRoleAssignment
    db_session.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    await db_session.commit()

    login = await client.post("/auth/login", json={"username": "direct-rbac", "password": "password123"})
    assert login.status_code == 200
    assert login.json()["user"]["permissions"] == ["projects.read"]
    token = login.cookies.get("access_token")
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["roles"] == ["project-reader"]
    assert me.json()["permissions"] == ["projects.read"]


# ============================================================
# SUB-PHASE A TESTS — Legacy user.role no longer grants permissions
# ============================================================

@pytest.mark.asyncio
async def test_legacy_admin_role_no_longer_grants_wildcard(db_session):
    """user.role=ADMIN alone must NOT grant any RBAC permissions."""
    user = await create_user(db_session, {
        "username": "legacy-admin", "email": "legacy-admin@example.com",
        "password": "password123", "is_active": True,
        "role": UserRole.ADMIN, "source": "local",
    })
    # No group membership, no direct role assignment — only legacy role

    loaded = await get_user_by_id(db_session, user.id)
    perms = await RBACService(db_session).get_user_permissions(loaded)

    assert "*" not in perms, "Legacy user.role=ADMIN must not grant wildcard"
    assert len(perms) == 0, "Legacy admin without RBAC should have no permissions"


@pytest.mark.asyncio
async def test_legacy_admin_cannot_access_admin_endpoints(client, db_session):
    """A user with user.role=ADMIN but no RBAC must get 403 on admin endpoints."""
    await seed_default_rbac(db_session)
    user = await create_user(db_session, {
        "username": "legacy-admin2", "email": "legacy-admin2@example.com",
        "password": "password123", "is_active": True,
        "role": UserRole.ADMIN, "source": "local",
    })

    login = await client.post("/auth/login", json={
        "username": "legacy-admin2", "password": "password123",
    })
    assert login.status_code == 200
    token = login.cookies.get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Old admin endpoint (uses require_admin -> user_view permission)
    resp = await client.get("/auth/users", headers=headers)
    assert resp.status_code == 403, "Legacy admin without RBAC must not access admin endpoints"

    # New admin endpoint (uses require_permission -> user_view)
    resp = await client.get("/admin/users", headers=headers)
    assert resp.status_code == 403, "Legacy admin without RBAC must not access admin endpoints"


@pytest.mark.asyncio
async def test_rbac_admin_has_all_permissions(client, db_session):
    """An admin via RBAC (group administrators -> role admin) gets all permissions."""
    await seed_default_rbac(db_session)
    user = await create_user(db_session, {
        "username": "rbac-admin", "email": "rbac-admin@example.com",
        "password": "password123", "is_active": True,
        "role": UserRole.USER, "source": "local",
    })
    # Add to administrators group (which has admin role with all permissions)
    result = await db_session.execute(select(Group).where(Group.code == "administrators"))
    admin_group = result.scalar_one_or_none()
    assert admin_group is not None
    db_session.add(UserGroup(user_id=user.id, group_id=admin_group.id))
    await db_session.commit()

    loaded = await get_user_by_id(db_session, user.id)
    perms = await RBACService(db_session).get_user_permissions(loaded)

    assert "user_view" in perms
    assert "admin.access" in perms
    assert "building.view" in perms
    assert await RBACService(db_session).user_has_permission(loaded, "user_view")


@pytest.mark.asyncio
async def test_rbac_admin_can_access_admin_endpoints(client, db_session):
    """An admin via RBAC can access admin endpoints."""
    await seed_default_rbac(db_session)
    user = await create_user(db_session, {
        "username": "rbac-admin2", "email": "rbac-admin2@example.com",
        "password": "password123", "is_active": True,
        "role": UserRole.USER, "source": "local",
    })
    result = await db_session.execute(select(Group).where(Group.code == "administrators"))
    admin_group = result.scalar_one_or_none()
    db_session.add(UserGroup(user_id=user.id, group_id=admin_group.id))
    await db_session.commit()

    login = await client.post("/auth/login", json={
        "username": "rbac-admin2", "password": "password123",
    })
    assert login.status_code == 200
    token = login.cookies.get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/admin/users", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_standard_user_cannot_access_admin_endpoints(client, db_session):
    """A standard user (no admin role) gets 403 on admin endpoints."""
    await seed_default_rbac(db_session)
    user = await create_user(db_session, {
        "username": "standard-user", "email": "standard@example.com",
        "password": "password123", "is_active": True,
        "role": UserRole.USER, "source": "local",
    })

    login = await client.post("/auth/login", json={
        "username": "standard-user", "password": "password123",
    })
    assert login.status_code == 200
    token = login.cookies.get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/admin/users", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_multi_group_permissions_union(db_session):
    """User in two groups gets the union of both groups' role permissions."""
    user = await create_user(db_session, {
        "username": "multi-group", "email": "multi@example.com",
        "password": "password123", "source": "local",
    })

    perm_a = PermissionModel(code="project.view", name="Voir projets", module="project")
    perm_b = PermissionModel(code="building.view", name="Voir bâtiments", module="building")
    role_a = Role(code="viewer", name="Viewer")
    role_b = Role(code="builder", name="Builder")
    group_a = Group(code="viewers", name="Viewers", source="local")
    group_b = Group(code="builders", name="Builders", source="local")
    db_session.add_all([perm_a, perm_b, role_a, role_b, group_a, group_b])
    await db_session.flush()
    db_session.add_all([
        RolePermission(role_id=role_a.id, permission_id=perm_a.id),
        RolePermission(role_id=role_b.id, permission_id=perm_b.id),
        GroupRole(group_id=group_a.id, role_id=role_a.id),
        GroupRole(group_id=group_b.id, role_id=role_b.id),
        UserGroup(user_id=user.id, group_id=group_a.id),
        UserGroup(user_id=user.id, group_id=group_b.id),
    ])
    await db_session.commit()

    loaded = await get_user_by_id(db_session, user.id)
    perms = await RBACService(db_session).get_user_permissions(loaded)

    assert "project.view" in perms
    assert "building.view" in perms


@pytest.mark.asyncio
async def test_user_role_field_still_exists_in_db(db_session):
    """The user.role column still exists and is readable (compatibility)."""
    user = await create_user(db_session, {
        "username": "compat-user", "email": "compat@example.com",
        "password": "password123", "is_active": True,
        "source": "local",
    })
    # The column still exists and can be set directly on the model
    user.role = UserRole.ADMIN
    await db_session.commit()
    await db_session.refresh(user)
    result = await db_session.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    assert db_user.role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_multi_group_permissions_additive(client, db_session):
    """User in two groups with different roles gets additive permissions via API."""
    await seed_default_rbac(db_session)
    user = await create_user(db_session, {
        "username": "additive-user", "email": "additive@example.com",
        "password": "password123", "is_active": True,
        "role": UserRole.USER, "source": "local",
    })

    # Add to administrators group (gets all admin permissions)
    result = await db_session.execute(select(Group).where(Group.code == "administrators"))
    admin_group = result.scalar_one_or_none()
    db_session.add(UserGroup(user_id=user.id, group_id=admin_group.id))
    await db_session.commit()

    login = await client.post("/auth/login", json={
        "username": "additive-user", "password": "password123",
    })
    assert login.status_code == 200
    data = login.json()
    perms = data["user"]["permissions"]
    assert "user_view" in perms
    assert "building.view" in perms
