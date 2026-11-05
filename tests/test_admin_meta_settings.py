"""Tests de l'API de configuration Meta (/admin/settings/meta)."""

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
        json=payload(app_id="db-app-id", app_secret="db-secret", redirect_uri="https://example.com/cb"),
        headers=admin_headers,
    )
    assert saved.status_code == 200

    settings = get_settings()
    monkeypatch.setattr(settings, "META_APP_ID", "", raising=False)
    monkeypatch.setattr(settings, "META_APP_SECRET", "", raising=False)

    response = await client.get("/sport/publications/meta/status", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["configured"] is True


async def test_meta_auth_builds_url_from_db_values(client, admin_headers, monkeypatch):
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

    response = await client.get("/sport/publications/meta/auth?athlete_id=1", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert "client_id=db-app-id" in body["authorize_url"]
    assert "redirect_uri=https%3A%2F%2Fexample.com%2Fcb" in body["authorize_url"]


async def test_meta_status_falls_back_to_env_when_db_empty(client, admin_headers, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "META_APP_ID", "env-app-id", raising=False)
    monkeypatch.setattr(settings, "META_APP_SECRET", "env-secret", raising=False)

    response = await client.get("/sport/publications/meta/status", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["configured"] is True
