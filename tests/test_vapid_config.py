"""Tests de la configuration VAPID depuis le module Sport.

Endpoints : GET/PUT /sport/notifications/config et
POST /sport/notifications/config/generate
"""

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.module import Module, ModuleConfig, ModuleStatus
from app.services.ai_gateway.config_store import db_key
from app.services.notifications.config_store import (
    VAPID_SETTINGS_FIELDS,
    derive_public_key,
    generate_vapid_keys,
)
from app.services.notification import NotificationService


@pytest.fixture(autouse=True)
async def sport_module(db_session):
    """Ligne module « sport » requise pour stocker les configs."""
    result = await db_session.execute(select(Module).where(Module.code == "sport"))
    module = result.scalar_one_or_none()
    if module is None:
        module = Module(
            code="sport",
            name="Sport",
            description="Sport et activités physiques",
            icon="activity",
            order=60,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/sport",
            component_path="Sport",
            is_core=False,
        )
        db_session.add(module)
        await db_session.commit()
    return module


@pytest.fixture(autouse=True)
def restore_vapid_settings():
    """Les écritures portent sur l'instance Settings partagée : restaure après test."""
    settings = get_settings()
    snapshot = {field: getattr(settings, field) for field in VAPID_SETTINGS_FIELDS}
    yield
    for field, value in snapshot.items():
        setattr(settings, field, value)


@pytest.fixture(autouse=True)
def empty_vapid_env():
    """Simule un déploiement sans clé VAPID dans l'environnement."""
    settings = get_settings()
    for field in ("NOTIFICATION_VAPID_PUBLIC_KEY", "NOTIFICATION_VAPID_PRIVATE_KEY"):
        setattr(settings, field, "")
    return settings


async def test_config_requires_permission(client, auth_headers):
    response = await client.get("/sport/notifications/config")
    assert response.status_code == 403


async def test_config_not_configured_by_default(client, admin_headers):
    response = await client.get("/sport/notifications/config")
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is False
    assert data["public_key"] == ""


async def test_generate_keys_persists_and_applies(client, admin_headers, db_session):
    response = await client.post("/sport/notifications/config/generate")
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is True
    assert len(data["public_key"]) > 40

    # Overlay à chaud sur l'instance Settings partagée (sans redémarrage).
    settings = get_settings()
    assert settings.NOTIFICATION_VAPID_PRIVATE_KEY
    assert NotificationService.vapid_public_key() == data["public_key"]

    # Persisté en DB, clé privée marquée secrète.
    configs = {
        config.key: config
        for config in (
            await db_session.execute(
                select(ModuleConfig).join(Module).where(Module.code == "sport")
            )
        ).scalars()
    }
    private = configs[db_key("NOTIFICATION_VAPID_PRIVATE_KEY")]
    assert private.value == settings.NOTIFICATION_VAPID_PRIVATE_KEY
    assert private.is_secret is True


async def test_generated_pair_is_consistent(client, admin_headers):
    response = await client.post("/sport/notifications/config/generate")
    data = response.json()
    settings = get_settings()
    assert derive_public_key(settings.NOTIFICATION_VAPID_PRIVATE_KEY) == data["public_key"]


async def test_private_key_never_returned(client, admin_headers):
    generated = (await client.post("/sport/notifications/config/generate")).json()
    state = (await client.get("/sport/notifications/config")).json()
    for payload in (generated, state):
        assert "private_key" not in payload
        assert get_settings().NOTIFICATION_VAPID_PRIVATE_KEY not in str(payload)


async def test_save_existing_private_key(client, admin_headers):
    public, private = generate_vapid_keys()
    response = await client.put(
        "/sport/notifications/config",
        json={"private_key": private, "subject": "mailto:admin@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is True
    assert data["public_key"] == public
    assert data["subject"] == "mailto:admin@example.com"


async def test_save_invalid_subject_rejected(client, admin_headers):
    response = await client.put(
        "/sport/notifications/config", json={"subject": "admin@example.com"}
    )
    assert response.status_code == 422
    assert "mailto" in response.json()["detail"]
