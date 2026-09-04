import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from app.db.session import Base, get_db
from app.main import app
from app.models.user import UserRole
from app.services.auth import create_user
from app.services.rbac import seed_default_rbac
from app.modules import register_all_modules


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

        admin = await create_user(db, {
            'username': 'navadmin',
            'email': 'navadmin@example.com',
            'password': 'password123',
            'is_active': True,
            'role': UserRole.ADMIN,
            'source': 'local',
        })

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
    """Test that admin user gets admin_access permission via wildcard."""
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

        admin = await create_user(db, {
            'username': 'permadmin',
            'email': 'permadmin@example.com',
            'password': 'password123',
            'is_active': True,
            'role': UserRole.ADMIN,
            'source': 'local',
        })

        # Reload admin with roles, permissions, and groups
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models.rbac import Role, Group
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

        # Admin users get wildcard permission which implies all permissions
        assert "*" in perms, f"Admin should have wildcard permission, got: {perms}"
        # Verify wildcard satisfies admin.access check
        has_admin_access = await rbac.user_has_permission(admin, "admin.access")
        assert has_admin_access, "Admin should have admin.access via wildcard"

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