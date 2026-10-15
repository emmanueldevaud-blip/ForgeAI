import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from app.db.session import Base, get_db
from app.main import app
from app.models import Group, UserGroup
from app.models.module import Module, ModuleStatus
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


async def _setup_env(db):
    await seed_default_rbac(db)
    register_all_modules()
    # Reproduce the startup sync: create module rows in DB from registry
    from app.modules import module_registry
    for code, reg_module in module_registry._modules.items():
        db.add(Module(
            code=code,
            name=reg_module.info.name,
            description=reg_module.info.description,
            icon=reg_module.info.icon,
            order=reg_module.info.order,
            status=reg_module.info.status,
            version=reg_module.info.version,
            route_path=reg_module.info.route_path,
            component_path=reg_module.info.component_path,
            required_permissions=reg_module.info.required_permissions,
            is_core=reg_module.info.is_core,
        ))
    await db.commit()
    return await _create_admin_with_rbac(db, 'modadmin', 'modadmin@example.com')


@pytest.mark.asyncio
async def test_list_modules():
    """Admin can list all modules via GET /modules."""
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
        await _setup_env(db)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "username": "modadmin",
            "password": "password123",
        })
        access_token = response.cookies.get("access_token")
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await client.get("/modules", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert data["total"] > 0
        codes = [m["code"] for m in data["modules"]]
        assert "dashboard" in codes

    await engine.dispose()


@pytest.mark.asyncio
async def test_disable_and_enable_module():
    """Admin can disable a module then re-enable it."""
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
        await _setup_env(db)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "username": "modadmin",
            "password": "password123",
        })
        access_token = response.cookies.get("access_token")
        headers = {"Authorization": f"Bearer {access_token}"}

        # Disable the dashboard module (initially active)
        response = await client.post("/modules/dashboard/disable", headers=headers)
        assert response.status_code == 200
        assert response.json()["module"]["status"] == ModuleStatus.INACTIVE.value

        # DB reflects the change
        async with async_session() as check_db:
            result = await check_db.execute(select(Module).where(Module.code == "dashboard"))
            module = result.scalar_one()
            assert module.status == ModuleStatus.INACTIVE

        # Re-enable it
        response = await client.post("/modules/dashboard/enable", headers=headers)
        assert response.status_code == 200
        assert response.json()["module"]["status"] == ModuleStatus.ACTIVE.value

        async with async_session() as check_db:
            result = await check_db.execute(select(Module).where(Module.code == "dashboard"))
            module = result.scalar_one()
            assert module.status == ModuleStatus.ACTIVE

    await engine.dispose()


@pytest.mark.asyncio
async def test_enable_disable_unknown_module_returns_404():
    """Enabling/disabling a non-existent module returns 404."""
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
        await _setup_env(db)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "username": "modadmin",
            "password": "password123",
        })
        access_token = response.cookies.get("access_token")
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await client.post("/modules/does_not_exist/enable", headers=headers)
        assert response.status_code == 404

        response = await client.post("/modules/does_not_exist/disable", headers=headers)
        assert response.status_code == 404

    await engine.dispose()
