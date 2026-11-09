"""Tests de l'API de configuration Meta (/admin/settings/meta)."""

import httpx
import pytest
from sqlalchemy import select

from app.models.module import Module, ModuleConfig, ModuleStatus


@pytest.fixture(autouse=True)
async def administration_module(db_session):
    """Ligne module « administration » requise pour stocker les configs."""
    result = await db_session.execute(select(Module).where(Module.code == "administration"))
    module = result.scalar_one_or_none()
    if module is None:
        module = Module(
            code="administration",
            name="Administration",
            description="Administration système et configuration",
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

def payload(**overrides):
    body = {
        "app_id": "",
        "app_secret": "",
        "redirect_uri": "",
        "config_id": "",
    }
    body.update(overrides)
    return body

async def test_get_meta_settings_returns_empty_by_default(client, admin_headers):
    response = await client.get("/admin/settings/meta", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["app_id"] == ""
    assert data["app_secret_configured"] is False
    assert data["redirect_uri"] == ""
    assert data["access_token_configured"] is False
    assert data["client_business_id"] == ""
    assert data["instagram_user_id"] == ""

async def test_put_meta_settings_persists_and_masks_secret(client, admin_headers, db_session):
    response = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="123456", app_secret="super-secret", redirect_uri="https://example.com/cb"),
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["app_id"] == "123456"
    assert data["app_secret_configured"] is True
    assert data["redirect_uri"] == "https://example.com/cb"
    # Le secret ne remonte jamais dans la réponse.
    assert "super-secret" not in response.text

    # Stocké en DB comme secret.
    result = await db_session.execute(select(ModuleConfig).where(ModuleConfig.key == "meta_app_secret"))
    config = result.scalar_one()
    assert config.is_secret is True
    assert config.value == "super-secret"

async def test_put_meta_settings_persists_business_and_instagram_ids(client, admin_headers):
    response = await client.put(
        "/admin/settings/meta",
        json=payload(
            app_id="123456",
            app_secret="super-secret",
            redirect_uri="https://example.com/cb",
            config_id="cfg-123",
            access_token="SUAT-PLAINTEXT-TOKEN",
            client_business_id="bus-456",
            instagram_user_id="ig-789",
        ),
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token_configured"] is True
    assert data["client_business_id"] == "bus-456"
    assert data["instagram_user_id"] == "ig-789"
    assert "SUAT-PLAINTEXT-TOKEN" not in response.text

async def test_put_meta_settings_encrypts_access_token(client, admin_headers, db_session):
    """Le jeton SUAT est chiffré en base (Fernet) et jamais exposé en clair dans la réponse."""
    response = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="123456", app_secret="super-secret", redirect_uri="https://example.com/cb", config_id="cfg-123"),
        headers=admin_headers,
    )
    assert response.status_code == 200

    response = await client.put(
        "/admin/settings/meta",
        json=payload(
            app_id="123456",
            app_secret="super-secret",
            redirect_uri="https://example.com/cb",
            config_id="cfg-123",
            access_token="SUAT-PLAINTEXT-TOKEN",
        ),
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["access_token_configured"] is True
    assert "SUAT-PLAINTEXT-TOKEN" not in response.text

    result = await db_session.execute(select(ModuleConfig).where(ModuleConfig.key == "meta_access_token"))
    config = result.scalar_one()
    assert config.is_secret is True
    from app.services.sport_instagram import _decrypt_token

    assert _decrypt_token(config.value) == "SUAT-PLAINTEXT-TOKEN"

async def test_put_with_empty_secret_preserves_existing(client, admin_headers):
    first = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="123456", app_secret="first-secret"),
        headers=admin_headers,
    )
    assert first.status_code == 200

    second = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="123456", app_secret=""),
        headers=admin_headers,
    )

    assert second.status_code == 200
    assert second.json()["app_secret_configured"] is True

async def test_put_with_empty_access_token_preserves_existing(client, admin_headers, db_session):
    first = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="123456", app_secret="first-secret", access_token="SUAT-FIRST"),
        headers=admin_headers,
    )
    assert first.status_code == 200

    second = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="123456", app_secret="", access_token=""),
        headers=admin_headers,
    )

    assert second.status_code == 200
    assert second.json()["access_token_configured"] is True

    result = await db_session.execute(select(ModuleConfig).where(ModuleConfig.key == "meta_access_token"))
    assert result.scalar_one().value is not None

async def test_meta_settings_requires_permission(client, auth_headers):
    response = await client.get("/admin/settings/meta", headers=auth_headers)
    assert response.status_code == 403

    response = await client.put("/admin/settings/meta", json=payload(), headers=auth_headers)
    assert response.status_code == 403

async def test_meta_settings_returns_config_id(client, admin_headers):
    response = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="123456", app_secret="secret", redirect_uri="https://example.com/cb", config_id="cfg-456"),
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["config_id"] == "cfg-456"

def _mock_meta_client(monkeypatch, handler):
    """Remplace httpx.AsyncClient par un client MockTransport (API Meta factice)."""
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("app.api.admin.httpx.AsyncClient", factory)

async def test_meta_test_requires_saved_config(client, admin_headers):
    response = await client.post("/admin/settings/meta/test", json={}, headers=admin_headers)

    assert response.status_code == 400
    assert "App ID" in response.json()["detail"]

async def test_meta_test_no_token_returns_diagnostic(client, admin_headers, monkeypatch):
    """Sans jeton enrolé : diagnostic complet des identifiants, puis étape token 'skip'."""
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="test-app-id", app_secret="test-secret"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"access_token": "app-token", "token_type": "bearer"},
            request=request,
        )

    _mock_meta_client(monkeypatch, handler)

    response = await client.post("/admin/settings/meta/test", json={}, headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "no_token"
    assert data["access_token_configured"] is False
    assert data["configured"] is True
    assert len(data["steps"]) == 2
    assert data["steps"][0]["key"] == "app_credentials"
    assert data["steps"][0]["status"] == "ok"
    assert data["steps"][1]["key"] == "access_token"
    assert data["steps"][1]["status"] == "skipped"
    assert "validée" in data["message"]
    assert "test-app-id" in data["message"]
    assert "test-secret" not in response.text

async def test_meta_test_valid_token_returns_operational(client, admin_headers, monkeypatch):
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(
            app_id="test-app-id",
            app_secret="test-secret",
            config_id="cfg-123",
            access_token="SUAT-PLAINTEXT-TOKEN",
            client_business_id="bus-456",
            instagram_user_id="ig-789",
        ),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth/access_token"):
            if request.url.params.get("grant_type") == "client_credentials":
                return httpx.Response(200, json={"access_token": "app-token"}, request=request)
            return httpx.Response(200, json={"access_token": "long-token"}, request=request)
        if path.endswith("/me"):
            return httpx.Response(200, json={"id": "suat-1", "client_business_id": "bus-456"}, request=request)
        if path.endswith("/me/assigned_instagram_accounts"):
            return httpx.Response(
                200,
                json={"data": [{"id": "ig-789", "username": "athlete789"}]},
                request=request,
            )
        return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

    _mock_meta_client(monkeypatch, handler)

    response = await client.post("/admin/settings/meta/test", json={}, headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "validée" in data["message"]
    assert data["access_token_configured"] is True
    assert data["client_business_id"] == "bus-456"
    assert data["instagram_user_id"] == "ig-789"
    assert data["instagram_username"] == "athlete789"
    assert len(data["steps"]) == 3
    assert data["steps"][0]["status"] == "ok"
    assert data["steps"][1]["status"] == "ok"
    assert data["steps"][2]["status"] == "ok"
    assert "test-secret" not in response.text
    assert "SUAT-PLAINTEXT-TOKEN" not in response.text

async def test_meta_test_expired_token_returns_token_expired(client, admin_headers, monkeypatch):
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="test-app-id", app_secret="test-secret", access_token="SUAT-EXPIRED"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth/access_token"):
            if request.url.params.get("grant_type") == "client_credentials":
                return httpx.Response(200, json={"access_token": "app-token"}, request=request)
            return httpx.Response(200, json={"access_token": "long-token"}, request=request)
        if path.endswith("/me"):
            return httpx.Response(
                400,
                json={"error": {"message": "Error validating access token: Session expired", "type": "OAuthException", "code": 190}},
                request=request,
            )
        return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

    _mock_meta_client(monkeypatch, handler)

    response = await client.post("/admin/settings/meta/test", json={}, headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "token_expired"
    assert data["access_token_configured"] is True
    assert data["steps"][1]["status"] == "error"
    assert "expir" in data["steps"][1]["detail"]

async def test_meta_test_invalid_token_returns_token_invalid(client, admin_headers, monkeypatch):
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="test-app-id", app_secret="test-secret", access_token="SUAT-BAD"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth/access_token"):
            if request.url.params.get("grant_type") == "client_credentials":
                return httpx.Response(200, json={"access_token": "app-token"}, request=request)
            return httpx.Response(200, json={"access_token": "long-token"}, request=request)
        if path.endswith("/me"):
            return httpx.Response(
                400,
                json={"error": {"message": "Error validating access token: invalid", "type": "OAuthException", "code": 190}},
                request=request,
            )
        return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

    _mock_meta_client(monkeypatch, handler)

    response = await client.post("/admin/settings/meta/test", json={}, headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "token_invalid"
    assert data["steps"][1]["status"] == "error"

async def test_meta_test_unreadable_token_returns_token_unreadable(client, admin_headers, db_session, monkeypatch):
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="test-app-id", app_secret="test-secret", access_token="SUAT-PLAINTEXT-TOKEN"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    # Corrompre le jeton en base pour forcer un echec de dechiffrement.
    result = await db_session.execute(select(ModuleConfig).where(ModuleConfig.key == "meta_access_token"))
    config = result.scalar_one()
    config.value = "not-a-fernet-token"
    await db_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "app-token"}, request=request)

    _mock_meta_client(monkeypatch, handler)

    response = await client.post("/admin/settings/meta/test", json={}, headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "token_unreadable"
    assert data["steps"][1]["status"] == "error"

async def test_meta_test_business_mismatch_returns_partial(client, admin_headers, monkeypatch):
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="test-app-id", app_secret="test-secret", access_token="SUAT-PLAINTEXT-TOKEN", client_business_id="bus-999"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth/access_token"):
            if request.url.params.get("grant_type") == "client_credentials":
                return httpx.Response(200, json={"access_token": "app-token"}, request=request)
            return httpx.Response(200, json={"access_token": "long-token"}, request=request)
        if path.endswith("/me"):
            return httpx.Response(200, json={"id": "suat-1", "client_business_id": "bus-456"}, request=request)
        return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

    _mock_meta_client(monkeypatch, handler)

    response = await client.post("/admin/settings/meta/test", json={}, headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "partial"
    assert data["client_business_id"] == "bus-456"
    business_step = data["steps"][1]
    assert business_step["status"] == "warning"
    assert "bus-999" in (business_step["detail"] or "")

async def test_meta_test_instagram_id_not_shared_returns_partial(client, admin_headers, monkeypatch):
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="test-app-id", app_secret="test-secret", access_token="SUAT-PLAINTEXT-TOKEN", instagram_user_id="ig-404"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth/access_token"):
            if request.url.params.get("grant_type") == "client_credentials":
                return httpx.Response(200, json={"access_token": "app-token"}, request=request)
            return httpx.Response(200, json={"access_token": "long-token"}, request=request)
        if path.endswith("/me"):
            return httpx.Response(200, json={"id": "suat-1", "client_business_id": "bus-456"}, request=request)
        if path.endswith("/me/assigned_instagram_accounts"):
            return httpx.Response(200, json={"data": [{"id": "ig-789", "username": "athlete789"}]}, request=request)
        return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

    _mock_meta_client(monkeypatch, handler)

    response = await client.post("/admin/settings/meta/test", json={}, headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "partial"
    ig_step = data["steps"][2]
    assert ig_step["status"] == "error"
    assert "ig-404" in (ig_step["detail"] or "")

async def test_meta_test_invalid_credentials_returns_502(client, admin_headers, monkeypatch):
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="bad-app", app_secret="bad-secret"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "Invalid client_id"}},
            request=request,
        )

    _mock_meta_client(monkeypatch, handler)

    response = await client.post("/admin/settings/meta/test", json={}, headers=admin_headers)

    assert response.status_code == 502
    assert "Invalid client_id" in response.json()["detail"]

async def test_meta_test_requires_permission(client, auth_headers):
    response = await client.post("/admin/settings/meta/test", json={}, headers=auth_headers)
    assert response.status_code == 403
