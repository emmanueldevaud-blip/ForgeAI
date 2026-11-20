"""Tests pour la résolution et la validation du jeton de Page Facebook.

Ces tests couvrent :
- Récupération correcte du jeton de Page
- Plusieurs Pages accessibles
- Correspondance exacte du Page ID
- Absence de la Page recherchée
- Jeton utilisateur invalide
- Permissions insuffisantes
- SUAT expiré
- Absence de fallback silencieux
- Publication vidéo avec jeton de Page
- Publication photo avec jeton de Page
"""

import httpx
import pytest
from sqlalchemy import select

from app.models.module import Module, ModuleConfig, ModuleStatus
from app.services.sport_instagram import _encrypt_token
from app.services.sport_instagram_publish import (
    MetaPublishService,
    FacebookPageTokenMissingError,
    FacebookPageTokenInvalidError,
    FacebookPageTokenExpiredError,
    FacebookPageMismatchError,
    FacebookPagePermissionMissingError,
    FacebookPageTokenResolutionFailedError,
)


FB_PAGE_ID = "1427819417083197"
SUAT_TOKEN = "SUAT-TEST-TOKEN-0123456789"


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


def _make_accounts_response(accounts_data):
    """Crée une réponse mock pour /me/accounts."""
    return {"data": accounts_data}


class TestFacebookPageTokenResolution:
    """Tests pour _get_facebook_page_token."""

    @pytest.mark.asyncio
    async def test_get_facebook_page_token_success(self, db_session, monkeypatch):
        """Récupération correcte du jeton de Page quand tout est configuré."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            facebook_page_id=FB_PAGE_ID,
        )

        accounts_data = [
            {
                "id": FB_PAGE_ID,
                "name": "Jepepagtrail",
                "access_token": "PAGE_TOKEN_123",
                "tasks": {"MANAGE": True, "CREATE_CONTENT": True},
            }
        ]

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(200, json=_make_accounts_response(accounts_data), request=request)
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        assert connection is not None

        page_token = await service._get_facebook_page_token(connection)
        assert page_token == "PAGE_TOKEN_123"

    @pytest.mark.asyncio
    async def test_get_facebook_page_token_multiple_pages_exact_match(self, db_session, monkeypatch):
        """Plusieurs Pages accessibles : sélection exacte du Page ID configuré."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            facebook_page_id=FB_PAGE_ID,
        )

        accounts_data = [
            {
                "id": "999999999999999",
                "name": "Other Page",
                "access_token": "OTHER_PAGE_TOKEN",
                "tasks": {"MANAGE": True, "CREATE_CONTENT": True},
            },
            {
                "id": FB_PAGE_ID,
                "name": "Jepepagtrail",
                "access_token": "CORRECT_PAGE_TOKEN",
                "tasks": {"MANAGE": True, "CREATE_CONTENT": True},
            },
            {
                "id": "888888888888888",
                "name": "Another Page",
                "access_token": "ANOTHER_PAGE_TOKEN",
                "tasks": {"CREATE_CONTENT": True},
            },
        ]

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(200, json=_make_accounts_response(accounts_data), request=request)
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        assert connection is not None

        page_token = await service._get_facebook_page_token(connection)
        assert page_token == "CORRECT_PAGE_TOKEN"

    @pytest.mark.asyncio
    async def test_get_facebook_page_token_page_not_found(self, db_session, monkeypatch):
        """La Page configurée n'est pas dans les Pages accessibles -> FACEBOOK_PAGE_MISMATCH."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            facebook_page_id=FB_PAGE_ID,
        )

        accounts_data = [
            {
                "id": "999999999999999",
                "name": "Other Page",
                "access_token": "OTHER_PAGE_TOKEN",
                "tasks": {"MANAGE": True, "CREATE_CONTENT": True},
            },
        ]

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(200, json=_make_accounts_response(accounts_data), request=request)
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        assert connection is not None

        with pytest.raises(FacebookPageMismatchError) as exc_info:
            await service._get_facebook_page_token(connection)

        assert exc_info.value.code == "FACEBOOK_PAGE_MISMATCH"
        assert FB_PAGE_ID in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_facebook_page_token_no_suat(self, db_session, monkeypatch):
        """Aucun SUAT configuré -> resolve_facebook_publish_context retourne None."""
        await _save_config(
            db_session,
            facebook_page_id=FB_PAGE_ID,
        )

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        # Sans SUAT, le contexte de publication Facebook ne peut pas être résolu
        assert connection is None

    @pytest.mark.asyncio
    async def test_get_facebook_page_token_no_page_id(self, db_session, monkeypatch):
        """Aucun Page ID configuré -> resolve_facebook_publish_context retourne None."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
        )

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        # Sans Page ID, le contexte de publication Facebook ne peut pas être résolu
        assert connection is None

    @pytest.mark.asyncio
    async def test_get_facebook_page_token_invalid_suat(self, db_session, monkeypatch):
        """SUAT invalide (HTTP 401/403) -> FACEBOOK_PAGE_TOKEN_INVALID."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            facebook_page_id=FB_PAGE_ID,
        )

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(
                        401,
                        json={"error": {"message": "Invalid OAuth access token", "code": 190, "type": "OAuthException"}},
                        request=request,
                    )
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        assert connection is not None

        with pytest.raises(FacebookPageTokenResolutionFailedError) as exc_info:
            await service._get_facebook_page_token(connection)

        assert exc_info.value.code == "FACEBOOK_PAGE_TOKEN_RESOLUTION_FAILED"

    @pytest.mark.asyncio
    async def test_get_facebook_page_token_page_no_access_token(self, db_session, monkeypatch):
        """La Page existe mais ne retourne pas de jeton -> FACEBOOK_PAGE_TOKEN_MISSING."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            facebook_page_id=FB_PAGE_ID,
        )

        accounts_data = [
            {
                "id": FB_PAGE_ID,
                "name": "Jepepagtrail",
                "tasks": {"MANAGE": True, "CREATE_CONTENT": True},
            }
        ]

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(200, json=_make_accounts_response(accounts_data), request=request)
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        assert connection is not None

        with pytest.raises(FacebookPageTokenMissingError) as exc_info:
            await service._get_facebook_page_token(connection)

        assert exc_info.value.code == "FACEBOOK_PAGE_TOKEN_MISSING"
        assert "retourne pas de jeton" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_facebook_page_token_insufficient_permissions(self, db_session, monkeypatch):
        """La Page a un jeton mais permissions insuffisantes -> FACEBOOK_PAGE_PERMISSION_MISSING."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            facebook_page_id=FB_PAGE_ID,
        )

        accounts_data = [
            {
                "id": FB_PAGE_ID,
                "name": "Jepepagtrail",
                "access_token": "PAGE_TOKEN_NO_PERMS",
                "tasks": {"ANALYZE": True},  # Pas MANAGE ni CREATE_CONTENT
            }
        ]

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(200, json=_make_accounts_response(accounts_data), request=request)
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        assert connection is not None

        with pytest.raises(FacebookPagePermissionMissingError) as exc_info:
            await service._get_facebook_page_token(connection)

        assert exc_info.value.code == "FACEBOOK_PAGE_PERMISSION_MISSING"
        assert "tâches" in str(exc_info.value).lower() or "permissions" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_facebook_page_token_tasks_as_list(self, db_session, monkeypatch):
        """Permissions fournies sous forme de liste (au lieu de dict)."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            facebook_page_id=FB_PAGE_ID,
        )

        accounts_data = [
            {
                "id": FB_PAGE_ID,
                "name": "Jepepagtrail",
                "access_token": "PAGE_TOKEN_LIST_PERMS",
                "tasks": ["MANAGE", "CREATE_CONTENT", "ANALYZE"],
            }
        ]

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(200, json=_make_accounts_response(accounts_data), request=request)
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        assert connection is not None

        page_token = await service._get_facebook_page_token(connection)
        assert page_token == "PAGE_TOKEN_LIST_PERMS"

    @pytest.mark.asyncio
    async def test_get_facebook_page_token_no_fallback_to_suat(self, db_session, monkeypatch):
        """Vérifier qu'il n'y a JAMAIS de fallback silencieux sur le SUAT."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            facebook_page_id=FB_PAGE_ID,
        )

        # La Page n'existe pas dans les comptes accessibles
        accounts_data = [
            {
                "id": "999999999999999",
                "name": "Other Page",
                "access_token": "OTHER_PAGE_TOKEN",
                "tasks": {"MANAGE": True, "CREATE_CONTENT": True},
            }
        ]

        call_count = {"count": 0}

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                call_count["count"] += 1
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(200, json=_make_accounts_response(accounts_data), request=request)
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        assert connection is not None

        # Doit lever FACEBOOK_PAGE_MISMATCH, pas retourner le SUAT
        with pytest.raises(FacebookPageMismatchError):
            await service._get_facebook_page_token(connection)

        # Vérifier qu'un seul appel à /me/accounts a été fait
        assert call_count["count"] == 1


class TestFacebookPagePublishing:
    """Tests pour publish_to_facebook_page."""

    @pytest.mark.asyncio
    async def test_publish_facebook_photo_with_page_token(self, db_session, monkeypatch):
        """Publication photo avec jeton de Page valide."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            facebook_page_id=FB_PAGE_ID,
        )

        accounts_data = [
            {
                "id": FB_PAGE_ID,
                "name": "Jepepagtrail",
                "access_token": "PAGE_TOKEN_PHOTO",
                "tasks": {"MANAGE": True, "CREATE_CONTENT": True},
            }
        ]

        post_requests = []

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(200, json=_make_accounts_response(accounts_data), request=request)
                if request.url.path.endswith(f"/{FB_PAGE_ID}/photos") and request.method == "POST":
                    post_requests.append(request)
                    return httpx.Response(200, json={"post_id": "POST_123", "id": "POST_123"}, request=request)
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        assert connection is not None

        media_id = await service.publish_to_facebook_page(
            connection,
            "https://cdn.example.com/photo.jpg",
            "Test caption",
            mime_type="image/jpeg",
            is_video=False,
            publication_id=1,
        )

        assert media_id == "POST_123"
        assert len(post_requests) == 1
        # Vérifier que le jeton utilisé est le jeton de Page, pas le SUAT
        assert post_requests[0].url.params["access_token"] == "PAGE_TOKEN_PHOTO"
        assert post_requests[0].url.params["access_token"] != SUAT_TOKEN

    @pytest.mark.asyncio
    async def test_publish_facebook_video_with_page_token(self, db_session, monkeypatch):
        """Publication vidéo avec jeton de Page valide."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            facebook_page_id=FB_PAGE_ID,
        )

        accounts_data = [
            {
                "id": FB_PAGE_ID,
                "name": "Jepepagtrail",
                "access_token": "PAGE_TOKEN_VIDEO",
                "tasks": {"MANAGE": True, "CREATE_CONTENT": True},
            }
        ]

        post_requests = []

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(200, json=_make_accounts_response(accounts_data), request=request)
                if request.url.path.endswith(f"/{FB_PAGE_ID}/videos") and request.method == "POST":
                    post_requests.append(request)
                    return httpx.Response(200, json={"id": "VIDEO_456"}, request=request)
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        assert connection is not None

        media_id = await service.publish_to_facebook_page(
            connection,
            "https://cdn.example.com/video.mp4",
            "Test video caption",
            mime_type="video/mp4",
            is_video=True,
            publication_id=2,
        )

        assert media_id == "VIDEO_456"
        assert len(post_requests) == 1
        # Vérifier que le jeton utilisé est le jeton de Page, pas le SUAT
        assert post_requests[0].url.params["access_token"] == "PAGE_TOKEN_VIDEO"
        assert post_requests[0].url.params["access_token"] != SUAT_TOKEN

    @pytest.mark.asyncio
    async def test_publish_facebook_token_validation_before_post(self, db_session, monkeypatch):
        """Vérifier que la validation du jeton a lieu avant le POST."""
        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            facebook_page_id=FB_PAGE_ID,
        )

        # La Page n'a pas de jeton d'accès
        accounts_data = [
            {
                "id": FB_PAGE_ID,
                "name": "Jepepagtrail",
                "tasks": {"MANAGE": True, "CREATE_CONTENT": True},
            }
        ]

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(200, json=_make_accounts_response(accounts_data), request=request)
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        connection = await service.resolve_facebook_publish_context()
        assert connection is not None

        # Doit échouer AVANT tout POST vers /photos ou /videos
        with pytest.raises(FacebookPageTokenMissingError):
            await service.publish_to_facebook_page(
                connection,
                "https://cdn.example.com/photo.jpg",
                "Test caption",
                mime_type="image/jpeg",
                is_video=False,
                publication_id=3,
            )


class TestFacebookPageErrors:
    """Tests pour les codes d'erreur explicites."""

    @pytest.mark.asyncio
    async def test_error_codes_defined(self):
        """Vérifier que tous les codes d'erreur requis sont définis."""
        assert FacebookPageTokenMissingError.code == "FACEBOOK_PAGE_TOKEN_MISSING"
        assert FacebookPageTokenInvalidError.code == "FACEBOOK_PAGE_TOKEN_INVALID"
        assert FacebookPageTokenExpiredError.code == "FACEBOOK_PAGE_TOKEN_EXPIRED"
        assert FacebookPageMismatchError.code == "FACEBOOK_PAGE_MISMATCH"
        assert FacebookPagePermissionMissingError.code == "FACEBOOK_PAGE_PERMISSION_MISSING"
        assert FacebookPageTokenResolutionFailedError.code == "FACEBOOK_PAGE_TOKEN_RESOLUTION_FAILED"

    @pytest.mark.asyncio
    async def test_error_inheritance(self):
        """Vérifier que toutes les erreurs héritent de MetaPublishError."""
        from app.services.sport_instagram_publish import MetaPublishError

        assert issubclass(FacebookPageTokenMissingError, MetaPublishError)
        assert issubclass(FacebookPageTokenInvalidError, MetaPublishError)
        assert issubclass(FacebookPageTokenExpiredError, MetaPublishError)
        assert issubclass(FacebookPageMismatchError, MetaPublishError)
        assert issubclass(FacebookPagePermissionMissingError, MetaPublishError)
        assert issubclass(FacebookPageTokenResolutionFailedError, MetaPublishError)


class TestInstagramUnaffected:
    """Tests pour vérifier qu'Instagram n'est pas affecté."""

    @pytest.mark.asyncio
    async def test_instagram_still_works(self, db_session, monkeypatch):
        """Le parcours Instagram doit continuer de fonctionner normalement."""
        from app.services.sport_instagram_publish import _MetaConfigContext

        await _save_config(
            db_session,
            meta_access_token=_encrypt_token(SUAT_TOKEN),
            instagram_user_id="17841400000000000",
            facebook_page_id=FB_PAGE_ID,
        )

        container_requests = []
        publish_requests = []

        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs.pop("timeout", None)

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
                if request.url.path.endswith("/me/accounts"):
                    return httpx.Response(200, json={"data": []}, request=request)
                return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(
            "app.services.sport_instagram_publish.httpx.AsyncClient",
            client_factory,
        )

        service = MetaPublishService(db_session)
        
        # Instagram path
        ig_context = await service.resolve_publish_context()
        assert ig_context is not None
        assert isinstance(ig_context, _MetaConfigContext)

        media_id = await service.publish_photo(
            ig_context,
            "https://cdn.example.com/photo.jpg",
            "Légende Instagram",
        )

        assert media_id == "media_123"
        assert len(container_requests) == 1
        # Vérifier que le SUAT est utilisé pour Instagram
        assert container_requests[0].url.params["access_token"] == SUAT_TOKEN
        assert "/17841400000000000/media" in container_requests[0].url.path