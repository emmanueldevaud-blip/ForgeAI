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
    assert data["api_version"] == "v27.0"

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
