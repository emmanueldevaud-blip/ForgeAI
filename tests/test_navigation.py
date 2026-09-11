import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from app.db.session import Base, get_db
from app.main import app
from app.models import Group, UserGroup
from app.models.user import UserRole
from app.services.auth import create_user
from app.services.rbac import seed_default_rbac
from app.modules import register_all_modules


async def _create_admin_with_rbac(db, username, email):
    """Create a user and add to administrators group for RBAC permissions."""
    admin = await create_user(db, {
        'username': username,
        'email': email,
        'password': 'password123',
        'is_active': True,
        'role': UserRole.ADMIN,
        'source': 'local',
    })
    result = await db.execute(select(Group).where(Group.code == 'administrators'))
    admin_group = result.scalar_one_or_none()
    if admin_group:
        exists = await db.execute(
            select(UserGroup).where(UserGroup.user_id == admin.id, UserGroup.group_id == admin_group.id)
        )
        if exists.scalar_one_or_none() is None:
            db.add(UserGroup(user_id=admin.id, group_id=admin_group.id))
            await db.commit()
    return admin


@pytest.mark.asyncio
async def test_navigation_includes_administration():
    """Test that /modules/navigation includes Administration for admin user."""
    engine = create_async_engine(
        'sqlite+aiosqlite:///:memory:',
        poolclass=StaticPool,
        connect_args={'check_same_thread': False},
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as db:
        await seed_default_rbac(db)
        register_all_modules()

        admin = await _create_admin_with_rbac(db, 'navadmin', 'navadmin@example.com')

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "username": "navadmin",
            "password": "password123",
        })
        access_token = response.cookies.get("access_token")
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await client.get("/modules/navigation", headers=headers)
        assert response.status_code == 200

        nav = response.json().get("navigation", [])
        codes = [item["code"] for item in nav]

        assert "dashboard" in codes, f"Dashboard should be in navigation, got: {codes}"
        assert "todos" in codes, f"Todos should be in navigation, got: {codes}"
        assert "administration" in codes, f"Administration should be in navigation, got: {codes}"

    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_user_has_admin_access_permission():
    """Test that admin user gets permissions via RBAC (groups -> roles -> permissions)."""
    engine = create_async_engine(
        'sqlite+aiosqlite:///:memory:',
        poolclass=StaticPool,
        connect_args={'check_same_thread': False},
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as db:
        await seed_default_rbac(db)
        register_all_modules()

        admin = await _create_admin_with_rbac(db, 'permadmin', 'permadmin@example.com')

        # Reload admin with roles, permissions, and groups
        from sqlalchemy.orm import selectinload
        from app.models.rbac import Role
        result = await db.execute(
            select(admin.__class__)
            .options(
                selectinload(admin.__class__.roles).selectinload(Role.permissions),
                selectinload(admin.__class__.groups).selectinload(Group.roles).selectinload(Role.permissions)
            )
            .where(admin.__class__.id == admin.id)
        )
        admin = result.scalar_one()

        from app.services.rbac import RBACService
        rbac = RBACService(db)
        perms = await rbac.get_user_permissions(admin)

        # Admin user gets permissions via RBAC: group administrators -> role admin -> all permissions
        assert len(perms) > 0, f"Admin should have permissions, got: {perms}"
        has_admin_access = await rbac.user_has_permission(admin, "admin.access")
        assert has_admin_access, "Admin should have admin.access via RBAC group membership"
        has_user_view = await rbac.user_has_permission(admin, "user_view")
        assert has_user_view, "Admin should have user_view via RBAC group membership"

    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_access_permission_exists():
    """Test that admin.access permission is created by seed."""
    engine = create_async_engine(
        'sqlite+aiosqlite:///:memory:',
        poolclass=StaticPool,
        connect_args={'check_same_thread': False},
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as db:
        await seed_default_rbac(db)

        from app.services.rbac import RBACService
        rbac = RBACService(db)
        perm = await rbac.get_permission_by_code("admin.access")

        assert perm is not None, "admin.access permission should exist"
        assert perm.code == "admin.access"
        assert perm.name == "Accès à l'administration"
        assert perm.module == "admin"
        assert perm.is_system is True

    await engine.dispose()