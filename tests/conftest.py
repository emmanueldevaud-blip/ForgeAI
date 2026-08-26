import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import Base, get_db
from app.core.config import get_settings
from app.services.auth import create_user
from app.models.user import User, UserRole


@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_engine():
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
        "is_admin": False,
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
        "is_admin": True,
        "role": UserRole.ADMIN,
        "source": "local",
    }
    return await create_user(db_session, user_data)


@pytest.fixture
async def admin_headers(client, admin_user):
    response = await client.post("/auth/login", json={
        "username": "adminuser",
        "password": "adminpassword123",
    })
    access_token = response.cookies.get("access_token")
    return {"Authorization": f"Bearer {access_token}"}