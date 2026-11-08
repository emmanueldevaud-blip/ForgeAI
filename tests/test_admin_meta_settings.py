"""Tests de l'API de configuration Meta (/admin/settings/meta)."""

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
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


async def test_meta_settings_requires_permission(client, auth_headers):
    response = await client.get("/admin/settings/meta", headers=auth_headers)
    assert response.status_code == 403

    response = await client.put("/admin/settings/meta", json=payload(), headers=auth_headers)
    assert response.status_code == 403


async def test_meta_status_uses_db_values_over_env(client, admin_headers, monkeypatch):
    """Les valeurs en DB priment sur l'environnement (overlay DB > env)."""
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="db-app-id", app_secret="db-secret", redirect_uri="https://example.com/cb", config_id="cfg-db"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    settings = get_settings()
    monkeypatch.setattr(settings, "META_APP_ID", "", raising=False)
    monkeypatch.setattr(settings, "META_APP_SECRET", "", raising=False)
    monkeypatch.setattr(settings, "META_CONFIG_ID", "", raising=False)

    response = await client.get("/sport/publications/meta/status", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["configured"] is True


async def test_meta_auth_builds_url_from_db_values(client, admin_headers, monkeypatch):
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="db-app-id", app_secret="db-secret", redirect_uri="https://example.com/cb", config_id="cfg-db"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    settings = get_settings()
    monkeypatch.setattr(settings, "META_APP_ID", "", raising=False)
    monkeypatch.setattr(settings, "META_APP_SECRET", "", raising=False)
    monkeypatch.setattr(settings, "META_REDIRECT_URI", "", raising=False)
    monkeypatch.setattr(settings, "META_CONFIG_ID", "", raising=False)

    response = await client.get("/sport/publications/meta/auth?athlete_id=1", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert "www.facebook.com/dialog/oauth" in body["authorize_url"]
    assert "client_id=db-app-id" in body["authorize_url"]
    assert "config_id=cfg-db" in body["authorize_url"]
    assert "redirect_uri=https%3A%2F%2Fexample.com%2Fcb" in body["authorize_url"]


async def test_meta_settings_returns_config_id(client, admin_headers):
    response = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="123456", app_secret="secret", redirect_uri="https://example.com/cb", config_id="cfg-456"),
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["config_id"] == "cfg-456"


async def test_meta_auth_builds_url_with_config_id(client, admin_headers, monkeypatch):
    """Unified Login : l'URL passe par facebook.com avec le Configuration ID."""
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(
            app_id="db-app-id",
            app_secret="db-secret",
            redirect_uri="https://example.com/cb",
            config_id="cfg-123",
        ),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    settings = get_settings()
    monkeypatch.setattr(settings, "META_APP_ID", "", raising=False)
    monkeypatch.setattr(settings, "META_APP_SECRET", "", raising=False)
    monkeypatch.setattr(settings, "META_REDIRECT_URI", "", raising=False)
    monkeypatch.setattr(settings, "META_CONFIG_ID", "", raising=False)

    response = await client.get("/sport/publications/meta/auth?athlete_id=1", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert "www.facebook.com/dialog/oauth" in body["authorize_url"]
    assert "client_id=db-app-id" in body["authorize_url"]
    assert "config_id=cfg-123" in body["authorize_url"]
    assert "response_type=code" in body["authorize_url"]
    # Les permissions sont definies par la configuration, pas par un parametre scope
    assert "scope=" not in body["authorize_url"]
    assert "www.instagram.com" not in body["authorize_url"]


async def test_meta_auth_requires_config_id(client, admin_headers, monkeypatch):
    """Unified Login : sans Configuration ID, l'autorisation est refusee (503)."""
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="db-app-id", app_secret="db-secret", redirect_uri="https://example.com/cb"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    settings = get_settings()
    monkeypatch.setattr(settings, "META_APP_ID", "", raising=False)
    monkeypatch.setattr(settings, "META_APP_SECRET", "", raising=False)
    monkeypatch.setattr(settings, "META_REDIRECT_URI", "", raising=False)
    monkeypatch.setattr(settings, "META_CONFIG_ID", "", raising=False)

    response = await client.get("/sport/publications/meta/auth?athlete_id=1", headers=admin_headers)

    assert response.status_code == 503
    assert "Configuration ID" in response.json()["detail"]


async def test_meta_status_requires_config_id(client, admin_headers, monkeypatch):
    """Sans Configuration ID, la connexion est annoncee non configurée."""
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="db-app-id", app_secret="db-secret", redirect_uri="https://example.com/cb"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    settings = get_settings()
    monkeypatch.setattr(settings, "META_CONFIG_ID", "", raising=False)

    response = await client.get("/sport/publications/meta/status", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["status"] == "not_configured"


async def test_meta_status_falls_back_to_env_when_db_empty(client, admin_headers, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "META_APP_ID", "env-app-id", raising=False)
    monkeypatch.setattr(settings, "META_APP_SECRET", "env-secret", raising=False)
    monkeypatch.setattr(settings, "META_CONFIG_ID", "env-cfg", raising=False)

    response = await client.get("/sport/publications/meta/status", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["configured"] is True


# ============================================================
# TEST DE CONNEXION (POST /admin/settings/meta/test)
# ============================================================


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


async def test_meta_test_success_validates_saved_credentials(client, admin_headers, monkeypatch):
    saved = await client.put(
        "/admin/settings/meta",
        json=payload(app_id="test-app-id", app_secret="test-secret"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["client_id"] = request.url.params.get("client_id")
        seen["client_secret"] = request.url.params.get("client_secret")
        return httpx.Response(
            200,
            json={"access_token": "app-token", "token_type": "bearer"},
            request=request,
        )

    _mock_meta_client(monkeypatch, handler)

    response = await client.post("/admin/settings/meta/test", json={}, headers=admin_headers)

    assert response.status_code == 200
    assert "validée" in response.json()["message"]
    assert "test-app-id" in response.json()["message"]
    # Les identifiants enregistrés en DB sont bien ceux envoyés à Meta.
    assert seen["client_id"] == "test-app-id"
    assert seen["client_secret"] == "test-secret"
    assert "graph.facebook.com" in seen["url"]
    # Le secret ne doit jamais figurer dans la réponse.
    assert "test-secret" not in response.text


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
