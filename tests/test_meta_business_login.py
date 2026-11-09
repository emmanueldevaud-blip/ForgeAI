"""Tests du parcours Facebook Login for Business (Meta centralise)."""

import httpx
import pytest
from sqlalchemy import select

from app.models.module import Module, ModuleConfig, ModuleStatus
from app.services.sport_instagram import (
    SportInstagramConnectService,
    _decrypt_token,
)
from app.services.sport_instagram_publish import MetaPublishService


@pytest.fixture(autouse=True)
async def administration_module(db_session):
    result = await db_session.execute(select(Module).where(Module.code == "administration"))
    module = result.scalar_one_or_none()
    if module is None:
        module = Module(
            code="administration",
            name="Administration",
            description="Administration systeme et configuration",
            icon="settings",
            order=1000,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/administration",
            component_path="Administration",
            is_core=True,
        )
        db_session.add(module)
        await db_session.commit()
    return module


def _mock_httpx_client(monkeypatch, handler):
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("app.services.sport_instagram.httpx.AsyncClient", factory)


def _handler_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "oauth/access_token" in url:
            return httpx.Response(200, json={"access_token": "BI-TOKEN-123", "user_id": "999"}, request=request)
        if "assigned_instagram_accounts" in url:
            return httpx.Response(200, json={"data": [{"id": "17841463605067187", "username": "trailrunner"}]}, request=request)
        if "/me" in url:
            return httpx.Response(200, json={"id": "1660869362118926", "client_business_id": "17841463605067187"}, request=request)
        return httpx.Response(404, json={}, request=request)

    return handler


def _handler_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "Code has expired or is invalid", "type": "OAuthException", "code": 190}},
            request=request,
        )

    return handler


async def _save_config(db, **values):
    result = await db.execute(select(Module).where(Module.code == "administration"))
    module = result.scalar_one()
    for key, value in values.items():
        existing = await db.execute(
            select(ModuleConfig).where(
                ModuleConfig.module_id == module.id,
                ModuleConfig.key == key,
            )
        )
        config = existing.scalar_one_or_none()
        if config is not None:
            config.value = value
        else:
            db.add(ModuleConfig(
                module_id=module.id,
                key=key,
                value=value,
                value_type="string",
                is_secret=key == "meta_access_token",
            ))
    await db.commit()


class TestMetaLoginState:
    @pytest.mark.asyncio
    async def test_initiate_meta_login_returns_state_and_stores(self, db_session):
        service = SportInstagramConnectService(db_session)
        info = await service.initiate_meta_login()
        assert info["state"]
        stored = await db_session.execute(select(ModuleConfig).where(ModuleConfig.key == "meta_oauth_state"))
        config = stored.scalar_one_or_none()
        assert config is not None
        assert config.value == info["state"]

    @pytest.mark.asyncio
    async def test_validate_meta_state_rejects_unknown_state(self, db_session):
        service = SportInstagramConnectService(db_session)
        assert await service.validate_meta_state("state-inexistante") is False

    @pytest.mark.asyncio
    async def test_validate_meta_state_consumes_valid_state(self, db_session):
        service = SportInstagramConnectService(db_session)
        info = await service.initiate_meta_login()
        assert await service.validate_meta_state(info["state"]) is True
        again = await db_session.execute(select(ModuleConfig).where(ModuleConfig.key == "meta_oauth_state"))
        assert (again.scalar_one_or_none().value or "") == ""


class TestMetaBusinessExchange:
    @pytest.mark.asyncio
    async def test_exchange_business_code_uses_authorization_code(self, db_session, monkeypatch):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            url = str(request.url)
            if "oauth/access_token" in url:
                return httpx.Response(200, json={"access_token": "BI-TOKEN-123", "user_id": "999"}, request=request)
            if "assigned_instagram_accounts" in url:
                return httpx.Response(200, json={"data": [{"id": "17841463605067187", "username": "trailrunner"}]}, request=request)
            if "/me" in url:
                return httpx.Response(200, json={"id": "1660869362118926", "client_business_id": "17841463605067187"}, request=request)
            return httpx.Response(404, json={}, request=request)

        _mock_httpx_client(monkeypatch, handler)
        await _save_config(
            db_session,
            meta_app_id="12345",
            meta_app_secret="app-secret",
            meta_redirect_uri="https://forgeai.design-ede.fr/sport/publications/meta/callback",
            instagram_api_version="v27.0",
        )
        service = SportInstagramConnectService(db_session)
        result = await service.exchange_business_code("CODE-XYZ")

        token_call = calls[0]
        assert token_call.method == "GET"
        params = token_call.url.params
        assert params.get("grant_type") == "authorization_code"
        assert params.get("client_id") == "12345"
        assert params.get("client_secret") == "app-secret"
        assert params.get("code") == "CODE-XYZ"
        assert params.get("redirect_uri") == "https://forgeai.design-ede.fr/sport/publications/meta/callback"
        assert "fb_exchange_token" not in params
        assert result["access_token"] == "BI-TOKEN-123"

    @pytest.mark.asyncio
    async def test_exchange_business_code_rejects_expired_or_used_code(self, db_session, monkeypatch):
        _mock_httpx_client(monkeypatch, _handler_error())
        service = SportInstagramConnectService(db_session)
        with pytest.raises(httpx.HTTPStatusError):
            await service.exchange_business_code("CODE-EXPIRED")

    @pytest.mark.asyncio
    async def test_exchange_business_code_without_client_business_id(self, db_session, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "oauth/access_token" in url:
                return httpx.Response(200, json={"access_token": "BI-TOKEN-123", "user_id": "999"}, request=request)
            if "/me" in url:
                return httpx.Response(200, json={"id": "1660869362118926"}, request=request)
            if "assigned_instagram_accounts" in url:
                return httpx.Response(200, json={"data": [{"id": "17841463605067187", "username": "trailrunner"}]}, request=request)
            return httpx.Response(404, json={}, request=request)

        _mock_httpx_client(monkeypatch, handler)
        service = SportInstagramConnectService(db_session)
        result = await service.exchange_business_code("CODE-XYZ")
        assert result["client_business_id"] == ""

    @pytest.mark.asyncio
    async def test_meta_publish_base_url_uses_v27(self, db_session):
        service = MetaPublishService(db_session)
        assert service._base_url == "https://graph.facebook.com/v27.0"

    @pytest.mark.asyncio
    async def test_exchange_business_code_retrieves_business_and_instagram_accounts(self, db_session, monkeypatch):
        _mock_httpx_client(monkeypatch, _handler_ok())
        service = SportInstagramConnectService(db_session)
        result = await service.exchange_business_code("CODE-XYZ")
        assert result["access_token"] == "BI-TOKEN-123"
        assert result["client_business_id"] == "17841463605067187"
        assert result["instagram_accounts"][0]["id"] == "17841463605067187"

    @pytest.mark.asyncio
    async def test_failed_exchange_does_not_overwrite_existing_credentials(self, db_session):
        service = SportInstagramConnectService(db_session)
        await service.save_meta_credentials(
            token="BI-TOKEN-123",
            client_business_id="17841463605067187",
            instagram_user_id="17841463605067187",
        )
        service2 = SportInstagramConnectService(db_session)
        with pytest.raises(httpx.HTTPStatusError):
            await service2.exchange_business_code("CODE-EXPIRED")
        result = await db_session.execute(select(ModuleConfig).where(ModuleConfig.key == "meta_access_token"))
        config = result.scalar_one_or_none()
        assert config is not None
        assert _decrypt_token(config.value) == "BI-TOKEN-123"

    @pytest.mark.asyncio
    async def test_full_fb_login_flow_stores_and_resolves(self, db_session, monkeypatch):
        _mock_httpx_client(monkeypatch, _handler_ok())
        service = SportInstagramConnectService(db_session)
        info = await service.initiate_meta_login()
        assert await service.validate_meta_state(info["state"])
        result = await service.exchange_business_code("CODE-XYZ")
        await service.save_meta_credentials(
            token=result["access_token"],
            client_business_id=result["client_business_id"],
            instagram_user_id="17841463605067187",
        )
        publish_service = MetaPublishService(db_session)
        context = await publish_service.resolve_publish_context()
        assert context is not None
        assert context.instagram_business_account_id == "17841463605067187"
        assert _decrypt_token(context.encrypted_long_lived_token) == "BI-TOKEN-123"
