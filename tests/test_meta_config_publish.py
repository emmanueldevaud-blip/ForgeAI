"""Tests de la publication via la configuration Meta centralisée.

La configuration globale (meta_access_token + instagram_user_id) est
l'unique source de publication depuis la suppression du flux OAuth (jalon 3).
"""

import httpx
import pytest
from sqlalchemy import select

from app.models.module import Module, ModuleConfig, ModuleStatus
from app.services.sport_instagram import _decrypt_token, _encrypt_token
from app.services.sport_instagram_publish import MetaPublishService, _MetaConfigContext

IG_USER_ID = "17841400000000000"
PLAIN_TOKEN = "SUAT-TEST-TOKEN-0123456789"


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


async def _save_config(db, **values):
    """Enregistre des clés dans la configuration Meta (module administration)."""
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


async def test_resolve_context_none_without_config(db_session):
    """Sans configuration Meta, aucune source de publication n'est disponible."""
    service = MetaPublishService(db_session)
    context = await service.resolve_publish_context()

    assert context is None


async def test_resolve_context_requires_instagram_user_id(db_session):
    """Un jeton sans Instagram User ID est incomplet : aucune source."""
    await _save_config(db_session, meta_access_token=_encrypt_token(PLAIN_TOKEN))

    service = MetaPublishService(db_session)
    context = await service.resolve_publish_context()

    assert context is None


async def test_resolve_context_unreadable_config_token_returns_none(db_session):
    """Un jeton illisible en base bloque la publication (régénération requise)."""
    await _save_config(
        db_session,
        meta_access_token="not-a-fernet-token",
        instagram_user_id=IG_USER_ID,
    )

    service = MetaPublishService(db_session)
    context = await service.resolve_publish_context()

    assert context is None


async def test_resolve_context_returns_none_when_no_source(db_session):
    """Ni configuration ni connexion : aucune source de publication."""
    service = MetaPublishService(db_session)
    context = await service.resolve_publish_context()

    assert context is None


async def test_publish_photo_uses_centralized_token(db_session, monkeypatch):
    """Bout-en-bout : le conteneur et la publication utilisent le jeton SUAT."""
    await _save_config(
        db_session,
        meta_access_token=_encrypt_token(PLAIN_TOKEN),
        instagram_user_id=IG_USER_ID,
    )

    container_requests = []
    publish_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path.endswith("/media_publish"):
            publish_requests.append(request)
            return httpx.Response(200, json={"id": "media_123"}, request=request)
        if request.method == "POST" and path.endswith("/media"):
            container_requests.append(request)
            return httpx.Response(200, json={"id": "container_1"}, request=request)
        if request.method == "GET" and path.endswith("/container_1"):
            return httpx.Response(200, json={"status_code": "FINISHED"}, request=request)
        return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

    # La vraie classe est capturée AVANT le patch : app.services...httpx est
    # le module httpx lui-même, remplacer AsyncClient dessus rendrait la
    # factory récursive.
    real_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(
        "app.services.sport_instagram_publish.httpx.AsyncClient",
        client_factory,
    )

    service = MetaPublishService(db_session)
    context = await service.resolve_publish_context()
    assert isinstance(context, _MetaConfigContext)

    media_id = await service.publish_photo(
        context,
        "https://cdn.example.com/photo.jpg",
        "Légende du post",
    )

    assert media_id == "media_123"
    assert len(container_requests) == 1
    container = container_requests[0]
    assert f"/{IG_USER_ID}/media" in container.url.path
    assert container.url.params["access_token"] == PLAIN_TOKEN
    assert container.url.params["image_url"] == "https://cdn.example.com/photo.jpg"
    assert container.url.params["caption"] == "Légende du post"
    assert "media_type" not in container.url.params

    assert len(publish_requests) == 1
    publish = publish_requests[0]
    assert publish.url.params["creation_id"] == "container_1"
    assert publish.url.params["access_token"] == PLAIN_TOKEN
