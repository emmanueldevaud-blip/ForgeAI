import os

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


@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


def _get_test_database_url():
    """Get test database URL - supports MySQL for integration tests."""
    mysql_url = os.getenv("TEST_DATABASE_URL")
    if mysql_url:
        return mysql_url
    return "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def test_engine():
    database_url = _get_test_database_url()
    is_mysql = database_url.startswith("mysql")
    
    if is_mysql:
        engine = create_async_engine(
            database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )
    else:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session


@pytest.fixture(scope="function", autouse=True)
async def seed_rbac(db_session):
    """Seed default RBAC data for each test."""
    await seed_default_rbac(db_session)


@pytest.fixture(scope="function")
async def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_user(db_session):
    user_data = {
        "username": "testauth",
        "email": "testauth@example.com",
        "password": "testpassword123",
        "is_active": True,
        "role": UserRole.USER,
        "source": "local",
    }
    return await create_user(db_session, user_data)


@pytest.fixture
async def auth_headers(client, auth_user):
    response = await client.post("/auth/login", json={
        "username": "testauth",
        "password": "testpassword123",
    })
    access_token = response.cookies.get("access_token")
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def admin_user(db_session):
    user_data = {
        "username": "adminuser",
        "email": "admin@example.com",
        "password": "adminpassword123",
        "is_active": True,
        "role": UserRole.ADMIN,
        "source": "local",
    }
    user = await create_user(db_session, user_data)

    # Add to the 'administrators' group so the user gets RBAC admin permissions.
    result = await db_session.execute(select(Group).where(Group.code == "administrators"))
    admin_group = result.scalar_one_or_none()
    if admin_group:
        exists = await db_session.execute(
            select(UserGroup).where(UserGroup.user_id == user.id, UserGroup.group_id == admin_group.id)
        )
        if exists.scalar_one_or_none() is None:
            db_session.add(UserGroup(user_id=user.id, group_id=admin_group.id))
            await db_session.commit()

    return user


@pytest.fixture
async def admin_headers(client, admin_user):
    response = await client.post("/auth/login", json={
        "username": "adminuser",
        "password": "adminpassword123",
    })
    access_token = response.cookies.get("access_token")
    return {"Authorization": f"Bearer {access_token}"}