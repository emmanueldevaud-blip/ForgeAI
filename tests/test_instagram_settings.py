"""Tests de l'API de configuration Instagram (/admin/settings/instagram).

Tous les appels Meta/Instagram sont mockés (httpx.MockTransport). Aucun appel
réel n'est effectué. Aucune publication Instagram n'est jamais déclenchée.
"""

import pytest
from sqlalchemy import select
from unittest.mock import MagicMock, AsyncMock

from app.core.config import get_settings
from app.models.module import Module, ModuleConfig, ModuleStatus


@pytest.fixture(autouse=True)
async def administration_module(db_session):
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


def ig_payload(**overrides):
    body = {
        "app_id": "",
        "app_secret": "",
        "redirect_uri": "",
        "api_version": "v26.0",
    }
    body.update(overrides)
    return body


# ============================================================
# Lecture / sauvegarde de la configuration
# ============================================================

async def test_get_instagram_settings_returns_empty_by_default(client, admin_headers):
    response = await client.get("/admin/settings/instagram", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["app_id"] == ""
    assert data["app_secret_configured"] is False
    assert data["redirect_uri"] == ""
    assert data["api_version"] == "v26.0"


async def test_put_instagram_settings_persists_and_masks_secret(client, admin_headers, db_session):
    response = await client.put(
        "/admin/settings/instagram",
        json=ig_payload(app_id="ig-123456", app_secret="super-ig-secret", redirect_uri="https://example.com/cb"),
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["app_id"] == "ig-123456"
    assert data["app_secret_configured"] is True
    assert data["redirect_uri"] == "https://example.com/cb"
    # Le secret ne remonte jamais dans la réponse.
    assert "super-ig-secret" not in response.text

    # Stocké en DB comme secret.
    result = await db_session.execute(select(ModuleConfig).where(ModuleConfig.key == "instagram_app_secret"))
    config = result.scalar_one()
    assert config.is_secret is True
    assert config.value == "super-ig-secret"


async def test_put_instagram_empty_secret_preserves_existing(client, admin_headers):
    first = await client.put(
        "/admin/settings/instagram",
        json=ig_payload(app_id="ig-123456", app_secret="first-secret"),
        headers=admin_headers,
    )
    assert first.status_code == 200

    second = await client.put(
        "/admin/settings/instagram",
        json=ig_payload(app_id="ig-123456", app_secret=""),
        headers=admin_headers,
    )

    assert second.status_code == 200
    assert second.json()["app_secret_configured"] is True


async def test_instagram_settings_requires_permission(client, auth_headers):
    response = await client.get("/admin/settings/instagram", headers=auth_headers)
    assert response.status_code == 403

    response = await client.put("/admin/settings/instagram", json=ig_payload(), headers=auth_headers)
    assert response.status_code == 403

    response = await client.post("/admin/settings/instagram/test", headers=auth_headers)
    assert response.status_code == 403


# ============================================================
# Priorité base de données / variables d'environnement
# ============================================================

async def test_load_meta_values_prefers_db_over_env(client, admin_headers, monkeypatch):
    """La valeur enregistrée en base prime sur la variable d'environnement."""
    from app.services.sport_instagram import SportInstagramConnectService

    settings = get_settings()
    settings.INSTAGRAM_APP_ID = "env-app-id"

    await client.put(
        "/admin/settings/instagram",
        json=ig_payload(app_id="db-app-id"),
        headers=admin_headers,
    )

    response = await client.get("/admin/settings/instagram", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["app_id"] == "db-app-id"


# ============================================================
# Test de connexion Instagram (service mocké)
# ============================================================

class FakeConnection:
    """Connexion Instagram factice pour les tests de test_instagram_settings."""
    def __init__(self, connected, status, ig_user_id=None, username=None,
                 scopes="instagram_business_basic,instagram_business_content_publish",
                 encrypted_token="valid-token"):
        self.connected = connected
        self.status = status
        self.instagram_business_account_id = ig_user_id
        self.auth_type = "instagram_login"
        self.scopes = scopes
        self.encrypted_access_token = "encrypted"
        self.encrypted_long_lived_token = "encrypted"
        self.metadata_json = {"username": username} if username else {}


async def test_instagram_test_not_configured(client, admin_headers, monkeypatch):
    """Pas d'App ID configuré → erreur 400."""
    from app.services.sport_instagram import SportInstagramConnectService

    async def fake_load(self):
        return {"instagram_app_id": "", "instagram_app_secret": ""}

    monkeypatch.setattr(SportInstagramConnectService, "load_meta_values", fake_load)

    response = await client.post("/admin/settings/instagram/test", headers=admin_headers)
    assert response.status_code == 400
    assert "non configuré" in response.json()["detail"].lower()


async def test_instagram_test_secret_missing(client, admin_headers, monkeypatch):
    """App Secret manquant → erreur 400."""
    from app.services.sport_instagram import SportInstagramConnectService

    async def fake_load(self):
        return {"instagram_app_id": "ig-123456", "instagram_app_secret": ""}

    monkeypatch.setattr(SportInstagramConnectService, "load_meta_values", fake_load)

    response = await client.post("/admin/settings/instagram/test", headers=admin_headers)
    assert response.status_code == 400


async def test_instagram_test_no_account_connected(client, admin_headers, monkeypatch):
    """Configuré mais aucun compte Instagram connecté → disconnected."""
    from app.services.sport_instagram import SportInstagramConnectService

    async def fake_load(self):
        return {"instagram_app_id": "ig-123456", "instagram_app_secret": "secret",
                "instagram_api_version": "v26.0"}

    async def fake_get_connection(self, user_id):
        return None

    monkeypatch.setattr(SportInstagramConnectService, "load_meta_values", fake_load)
    monkeypatch.setattr(SportInstagramConnectService, "get_connection", fake_get_connection)

    response = await client.post("/admin/settings/instagram/test", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is False
    assert data["status"] == "disconnected"
    assert data["configured"] is True


async def test_instagram_test_operational(client, admin_headers, monkeypatch):
    """Compte connecté avec token valide → operational, pas de publication."""
    import httpx

    from app.services.sport_instagram import SportInstagramConnectService

    async def fake_load(self):
        return {"instagram_app_id": "ig-123456", "instagram_app_secret": "secret",
                "instagram_api_version": "v26.0"}

    fake_conn = FakeConnection(
        connected=True, status="active",
        ig_user_id="17841400000000000", username="testuser",
        scopes="instagram_business_basic,instagram_business_content_publish",
    )

    async def fake_get_connection(self, user_id):
        return fake_conn

    # Mock du décryptage de token
    def fake_decrypt(self, token):
        return "valid-token"

    # Mock de httpx pour l'appel /me
    seen_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen_urls.append(url)
        if "graph.instagram.com" in url and "/me" in url:
            return httpx.Response(200, json={"id": "17841400000000000", "username": "testuser"}, request=request)
        return httpx.Response(404, json={"error": "not found"}, request=request)

    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(SportInstagramConnectService, "load_meta_values", fake_load)
    monkeypatch.setattr(SportInstagramConnectService, "get_connection", fake_get_connection)
    monkeypatch.setattr(SportInstagramConnectService, "_decrypt", fake_decrypt)
    monkeypatch.setattr("app.api.admin.httpx.AsyncClient", factory)

    response = await client.post("/admin/settings/instagram/test", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["status"] == "operational"
    assert data["instagram_user_id"] == "17841400000000000"
    assert data["username"] == "testuser"
    assert data["publish_permission"] is True

    # Vérifier qu'aucun endpoint de publication n'a été appelé
    for url in seen_urls:
        assert "/media" not in url
        assert "/media_publish" not in url


async def test_instagram_test_token_expired(client, admin_headers, monkeypatch):
    """Token expiré → token_expired."""
    import httpx

    from app.services.sport_instagram import SportInstagramConnectService

    async def fake_load(self):
        return {"instagram_app_id": "ig-123456", "instagram_app_secret": "secret",
                "instagram_api_version": "v26.0"}

    fake_conn = FakeConnection(
        connected=True, status="active",
        ig_user_id="17841400000000000", username="testuser",
        encrypted_token="expired-token",
    )

    async def fake_get_connection(self, user_id):
        return fake_conn

    def fake_decrypt(self, token):
        return "expired-token"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Session has expired"}}, request=request)

    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(SportInstagramConnectService, "load_meta_values", fake_load)
    monkeypatch.setattr(SportInstagramConnectService, "get_connection", fake_get_connection)
    monkeypatch.setattr(SportInstagramConnectService, "_decrypt", fake_decrypt)
    monkeypatch.setattr("app.api.admin.httpx.AsyncClient", factory)

    response = await client.post("/admin/settings/instagram/test", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "token_expired"
    assert data["connected"] is False


async def test_instagram_test_token_invalid(client, admin_headers, monkeypatch):
    """Token invalide → token_invalid."""
    import httpx

    from app.services.sport_instagram import SportInstagramConnectService

    async def fake_load(self):
        return {"instagram_app_id": "ig-123456", "instagram_app_secret": "secret",
                "instagram_api_version": "v26.0"}

    fake_conn = FakeConnection(
        connected=True, status="active",
        ig_user_id="17841400000000000", username="testuser",
    )

    async def fake_get_connection(self, user_id):
        return fake_conn

    def fake_decrypt(self, token):
        return "bad-token"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Invalid token"}}, request=request)

    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(SportInstagramConnectService, "load_meta_values", fake_load)
    monkeypatch.setattr(SportInstagramConnectService, "get_connection", fake_get_connection)
    monkeypatch.setattr(SportInstagramConnectService, "_decrypt", fake_decrypt)
    monkeypatch.setattr("app.api.admin.httpx.AsyncClient", factory)

    response = await client.post("/admin/settings/instagram/test", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "token_invalid"
    assert data["connected"] is False


async def test_instagram_test_api_error(client, admin_headers, monkeypatch):
    """Erreur API Instagram → 502."""
    import httpx

    from app.services.sport_instagram import SportInstagramConnectService

    async def fake_load(self):
        return {"instagram_app_id": "ig-123456", "instagram_app_secret": "secret",
                "instagram_api_version": "v26.0"}

    fake_conn = FakeConnection(
        connected=True, status="active",
        ig_user_id="17841400000000000", username="testuser",
    )

    async def fake_get_connection(self, user_id):
        return fake_conn

    def fake_decrypt(self, token):
        return "valid-token"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "Internal error"}}, request=request)

    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(SportInstagramConnectService, "load_meta_values", fake_load)
    monkeypatch.setattr(SportInstagramConnectService, "get_connection", fake_get_connection)
    monkeypatch.setattr(SportInstagramConnectService, "_decrypt", fake_decrypt)
    monkeypatch.setattr("app.api.admin.httpx.AsyncClient", factory)

    response = await client.post("/admin/settings/instagram/test", headers=admin_headers)
    assert response.status_code == 502


async def test_instagram_test_no_publish_endpoint_called(client, admin_headers, monkeypatch):
    """Le test de connexion n'appelle jamais d'endpoint de publication."""
    import httpx

    from app.services.sport_instagram import SportInstagramConnectService

    async def fake_load(self):
        return {"instagram_app_id": "ig-123456", "instagram_app_secret": "secret",
                "instagram_api_version": "v26.0"}

    fake_conn = FakeConnection(
        connected=True, status="active",
        ig_user_id="17841400000000000", username="testuser",
    )

    async def fake_get_connection(self, user_id):
        return fake_conn

    def fake_decrypt(self, token):
        return "valid-token"

    seen_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen_urls.append(url)
        if "graph.instagram.com" in url and "/me" in url:
            return httpx.Response(200, json={"id": "17841400000000000", "username": "testuser"}, request=request)
        return httpx.Response(404, json={"error": "not found"}, request=request)

    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(SportInstagramConnectService, "load_meta_values", fake_load)
    monkeypatch.setattr(SportInstagramConnectService, "get_connection", fake_get_connection)
    monkeypatch.setattr(SportInstagramConnectService, "_decrypt", fake_decrypt)
    monkeypatch.setattr("app.api.admin.httpx.AsyncClient", factory)

    response = await client.post("/admin/settings/instagram/test", headers=admin_headers)
    assert response.status_code == 200

    # Vérifier qu'aucun endpoint de publication n'a été appelé
    for url in seen_urls:
        assert "/media" not in url
        assert "/media_publish" not in url
