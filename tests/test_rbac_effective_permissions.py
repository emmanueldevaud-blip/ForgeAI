import pytest

from app.models import Group, GroupRole, PermissionModel, Role, RolePermission, UserGroup
from app.services.auth import create_user
from app.services.rbac import RBACService


@pytest.fixture
async def seed_rbac():
    """The test creates exactly the RBAC records it needs."""
    yield


@pytest.mark.asyncio
async def test_local_user_in_group_receives_group_role_permissions(db_session):
    user = await create_user(db_session, {
        "username": "jean-rbac", "email": "jean-rbac@example.test",
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

    from app.services.auth import get_user_by_id
    loaded_user = await get_user_by_id(db_session, user.id)
    permissions = await RBACService(db_session).get_user_permissions(loaded_user)
    assert permissions == {"projects.create"}


@pytest.mark.asyncio
async def test_me_exposes_backend_computed_permissions(client, db_session):
    user = await create_user(db_session, {
        "username": "direct-rbac", "email": "direct-rbac@example.test",
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
