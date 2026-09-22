"""Integration tests for MySQL 8.4.

These tests require a running MySQL 8.4 instance.
Set TEST_DATABASE_URL environment variable to run against MySQL.

Example:
    export TEST_DATABASE_URL="mysql+asyncmy://forgeai:forgeai_password@localhost:3306/forgeai_test"
    pytest tests/test_integration_mysql.py -v
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import Base, get_db
from app.main import app
from app.models.user import UserRole
from app.services.auth import create_user


@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def mysql_engine():
    """Create MySQL test engine - requires TEST_DATABASE_URL env var."""
    import os
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url or not database_url.startswith("mysql"):
        pytest.skip("TEST_DATABASE_URL not set or not MySQL - skipping MySQL integration tests")
    
    engine = create_async_engine(
        database_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def mysql_db_session(mysql_engine):
    async_session = async_sessionmaker(mysql_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session


@pytest.fixture(scope="function")
async def mysql_client(mysql_db_session):
    def override_get_db():
        yield mysql_db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.integration
class TestMySQLIntegration:
    @pytest.mark.asyncio
    async def test_create_user_mysql(self, mysql_db_session):
        user_data = {
            "username": "mysql_test_user",
            "email": "mysql_test@example.com",
            "password": "password123",
            "is_active": True,
            "is_admin": False,
            "role": UserRole.USER,
            "source": "local",
        }
        user = await create_user(mysql_db_session, user_data)
        assert user.id is not None
        assert user.username == "mysql_test_user"

    @pytest.mark.asyncio
    async def test_login_mysql(self, mysql_client, mysql_db_session):
        user_data = {
            "username": "mysql_login_user",
            "email": "mysql_login@example.com",
            "password": "loginpassword",
            "is_active": True,
            "is_admin": False,
            "role": UserRole.USER,
            "source": "local",
        }
        await create_user(mysql_db_session, user_data)

        response = await mysql_client.post("/auth/login", json={
            "username": "mysql_login_user",
            "password": "loginpassword",
        })
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "tokens" in data
        assert data["user"]["username"] == "mysql_login_user"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
