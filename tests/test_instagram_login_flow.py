"""Tests du flux Instagram Unified Login (Facebook Login for Business).

Couvre : URL d'autorisation (dialog facebook.com + config_id), states CSRF,
callback public, echange sur graph.facebook.com, stockage centralise du SUAT
(ModuleConfig), statut/deconnexion, suppression de l'ancien onglet Instagram,
publication via la configuration centrale, et garanties statiques (un seul
parcours d'authentification).
"""

import pathlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.models.module import Module, ModuleConfig, ModuleStatus
from app.models.sport import SportInstagramOAuthState
from app.services.sport_instagram import (
    SportInstagramConnectService,
    _decrypt_token,
)
from app.services.sport_instagram_publish import MetaPublishService

META_APP_ID = "1234567890123456"
META_APP_SECRET = "meta-app-secret-value"
META_REDIRECT = "https://forgeai.design-ede.fr/sport/publications/meta/callback"
CONFIG_ID = "3080005675680801"
SUAT_TOKEN = "SUAT-NEVER-EXPIRING-TOKEN"
BUSINESS_ID = "111222333444555666"
IG_ACCOUNT_ID = "17841463605067187"


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


async def _save_meta_config(db, **values):
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
                is_secret=key.endswith("secret") or key == "meta_access_token",
            ))
    await db.commit()


async def _save_full_meta_config(db):
    await _save_meta_config(
        db,
        meta_app_id=META_APP_ID,
        meta_app_secret=META_APP_SECRET,
        meta_redirect_uri=META_REDIRECT,
        meta_config_id=CONFIG_ID,
    )


def _mock_httpx_client(monkeypatch, handler):
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("app.services.sport_instagram.httpx.AsyncClient", factory)


class _Recorder:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    @property
    def urls(self) -> list[str]:
        return [str(r.url) for r in self.requests]


def _happy_handler(recorder: _Recorder, accounts: list | None = None):
    if accounts is None:
        accounts = [{"id": IG_ACCOUNT_ID, "username": "trailrunner"}]

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        path = str(request.url).split("?")[0]
        if path == "https://graph.facebook.com/v27.0/oauth/access_token":
            return httpx.Response(
                200,
                json={"access_token": SUAT_TOKEN, "token_type": "bearer", "expires_in": 0},
                request=request,
            )
        if path == "https://graph.facebook.com/v27.0/me":
            return httpx.Response(
                200,
                json={"id": "9007199254740993", "client_business_id": BUSINESS_ID},
                request=request,
            )
        if path == "https://graph.facebook.com/v27.0/me/assigned_instagram_accounts":
            return httpx.Response(200, json={"data": accounts}, request=request)
        if "graph.facebook.com" in path and path.endswith("/media"):
            return httpx.Response(200, json={"id": "CONTAINER-123"}, request=request)
        return httpx.Response(404, json={}, request=request)

    return handler


def _exchange_error_handler(recorder: _Recorder, message: str, status: int = 400):
    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        if str(request.url).startswith("https://graph.facebook.com/"):
            return httpx.Response(
                status,
                json={"error": {"message": message, "type": "OAuthException"}},
                request=request,
            )
        return httpx.Response(404, json={}, request=request)

    return handler


async def _authorize(client, headers) -> tuple[str, str]:
    """Lance /meta/auth et retourne (state, authorize_url)."""
    response = await client.get("/sport/publications/meta/auth", headers=headers)
    assert response.status_code == 200, response.text
    url = response.json()["authorize_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    return state, url


async def _insert_state(db, user_id, *, state, expired=False, consumed=False):
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=-5 if expired else 10)
    db.add(SportInstagramOAuthState(
        state=state,
        user_id=user_id,
        expires_at=expires_at,
        consumed=consumed,
    ))
    await db.commit()
    return state


async def _connect(db, token=SUAT_TOKEN, ig_id=IG_ACCOUNT_ID, username="trailrunner"):
    service = SportInstagramConnectService(db)
    await service.save_meta_credentials(token, BUSINESS_ID, ig_id, username)


async def _config_value(db, key):
    result = await db.execute(select(ModuleConfig).where(ModuleConfig.key == key))
    config = result.scalar_one_or_none()
    return config.value if config is not None else None


# --------------------------------------------------------------------------- #
# URL d'autorisation
# --------------------------------------------------------------------------- #


class TestAuthorizeUrl:
    async def test_authorize_url_uses_facebook_dialog_with_config_id(
        self, client, db_session, admin_headers, admin_user
    ):
        await _save_full_meta_config(db_session)
        state, url = await _authorize(client, admin_headers)

        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "www.facebook.com"
        assert parsed.path == "/dialog/oauth"
        qs = parse_qs(parsed.query)
        assert qs["client_id"] == [META_APP_ID]
        assert qs["config_id"] == [CONFIG_ID]
        assert qs["redirect_uri"] == [META_REDIRECT]
        assert qs["response_type"] == ["code"]
        assert qs["prompt"] == ["login"]
        assert qs["state"] == [state]
        # Le config_id remplace les scopes : aucun scope dans l'URL.
        assert "scope" not in qs
        # Aucun dialogue Instagram direct.
        assert "instagram.com" not in url

        row = (
            await db_session.execute(
                select(SportInstagramOAuthState).where(SportInstagramOAuthState.state == state)
            )
        ).scalar_one()
        assert row.user_id == admin_user.id
        assert row.consumed is False
        assert row.expires_at is not None

    async def test_authorize_requires_meta_config(self, client, db_session, admin_headers):
        response = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        assert response.status_code == 503

    async def test_authorize_requires_config_id(self, client, db_session, admin_headers):
        await _save_meta_config(
            db_session,
            meta_app_id=META_APP_ID,
            meta_app_secret=META_APP_SECRET,
            meta_redirect_uri=META_REDIRECT,
        )
        response = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        assert response.status_code == 503

    async def test_authorize_requires_settings_update(self, client, auth_headers):
        response = await client.get("/sport/publications/meta/auth", headers=auth_headers)
        assert response.status_code == 403


# --------------------------------------------------------------------------- #
# States CSRF
# --------------------------------------------------------------------------- #


class TestStateValidation:
    async def test_state_consumed_once_only(self, db_session, admin_user):
        await _save_full_meta_config(db_session)
        service = SportInstagramConnectService(db_session)
        url, state = await service.build_authorization_url(admin_user.id)
        assert parse_qs(urlparse(url).query)["state"] == [state]

        assert await service.consume_state(state) == admin_user.id
        assert await service.consume_state(state) is None

    async def test_expired_state_rejected(self, db_session, admin_user):
        await _insert_state(db_session, admin_user.id, state="expired-state", expired=True)
        service = SportInstagramConnectService(db_session)
        assert await service.consume_state("expired-state") is None

    async def test_consumed_state_rejected(self, db_session, admin_user):
        await _insert_state(db_session, admin_user.id, state="used-state", consumed=True)
        service = SportInstagramConnectService(db_session)
        assert await service.consume_state("used-state") is None

    async def test_unknown_state_rejected(self, db_session):
        service = SportInstagramConnectService(db_session)
        assert await service.consume_state("state-inexistante") is None

    async def test_empty_state_rejected(self, db_session):
        service = SportInstagramConnectService(db_session)
        assert await service.consume_state("") is None


# --------------------------------------------------------------------------- #
# Echange du code (GET graph.facebook.com)
# --------------------------------------------------------------------------- #


class TestCodeExchange:
    async def test_exchange_gets_suat_from_graph_facebook(self, db_session, monkeypatch):
        await _save_full_meta_config(db_session)
        recorder = _Recorder()
        _mock_httpx_client(monkeypatch, _happy_handler(recorder))

        service = SportInstagramConnectService(db_session)
        result = await service.exchange_business_code("AUTH-CODE")

        assert result["access_token"] == SUAT_TOKEN
        assert result["client_business_id"] == BUSINESS_ID
        assert result["instagram_accounts"] == [
            {"id": IG_ACCOUNT_ID, "username": "trailrunner"}
        ]

        exchange_requests = [
            r for r in recorder.requests
            if str(r.url).split("?")[0] == "https://graph.facebook.com/v27.0/oauth/access_token"
        ]
        assert len(exchange_requests) == 1
        query = parse_qs(urlparse(str(exchange_requests[0].url)).query)
        assert query["grant_type"] == ["authorization_code"]
        assert query["client_id"] == [META_APP_ID]
        assert query["code"] == ["AUTH-CODE"]
        assert query["redirect_uri"] == [META_REDIRECT]
        # Le secret n'apparait que dans la requete, jamais dans les reponses de test.

        paths = [str(r.url).split("?")[0] for r in recorder.requests]
        assert "https://graph.facebook.com/v27.0/me" in paths
        assert "https://graph.facebook.com/v27.0/me/assigned_instagram_accounts" in paths

    async def test_exchange_never_calls_instagram_endpoints(self, db_session, monkeypatch):
        await _save_full_meta_config(db_session)
        recorder = _Recorder()
        _mock_httpx_client(monkeypatch, _happy_handler(recorder))

        service = SportInstagramConnectService(db_session)
        await service.exchange_business_code("AUTH-CODE")

        for url in recorder.urls:
            assert "api.instagram.com" not in url
            assert "graph.instagram.com" not in url
            assert "www.instagram.com" not in url

    async def test_exchange_error_is_sanitized(self, db_session, monkeypatch):
        await _save_full_meta_config(db_session)
        recorder = _Recorder()
        _mock_httpx_client(
            monkeypatch,
            _exchange_error_handler(
                recorder,
                f"Bad secret {META_APP_SECRET} and code AUTH-SECRET-CODE",
                status=400,
            ),
        )

        service = SportInstagramConnectService(db_session)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            await service.exchange_business_code("AUTH-SECRET-CODE")
        assert excinfo.value.status_code == 502
        detail = str(excinfo.value.detail)
        assert "Echange du code OAuth Meta" in detail
        assert META_APP_SECRET not in detail
        assert "AUTH-SECRET-CODE" not in detail

    async def test_exchange_requires_meta_config(self, db_session):
        service = SportInstagramConnectService(db_session)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            await service.exchange_business_code("AUTH-CODE")
        assert excinfo.value.status_code == 503


# --------------------------------------------------------------------------- #
# Callback
# --------------------------------------------------------------------------- #


class TestCallback:
    async def test_callback_success_redirects_and_stores_suat(
        self, client, db_session, admin_headers, admin_user, monkeypatch
    ):
        await _save_full_meta_config(db_session)
        recorder = _Recorder()
        _mock_httpx_client(monkeypatch, _happy_handler(recorder))

        state, _ = await _authorize(client, admin_headers)
        # Pas d'en-tete d'authentification : la route est publique.
        response = await client.get(
            f"/sport/publications/meta/callback?code=AUTH-CODE&state={state}"
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("/settings?connected=1")
        assert response.headers.get("cache-control") == "no-store"

        # SUAT chiffre dans la configuration centrale (ModuleConfig).
        raw_token = await _config_value(db_session, "meta_access_token")
        assert raw_token and raw_token != SUAT_TOKEN
        assert _decrypt_token(raw_token) == SUAT_TOKEN
        assert await _config_value(db_session, "meta_client_business_id") == BUSINESS_ID
        assert await _config_value(db_session, "instagram_user_id") == IG_ACCOUNT_ID
        assert await _config_value(db_session, "instagram_username") == "trailrunner"

        # Le state est consomme et supprime.
        rows = (
            await db_session.execute(
                select(SportInstagramOAuthState).where(SportInstagramOAuthState.state == state)
            )
        ).scalars().all()
        assert rows == []

        # Aucun appel aux API Instagram directes.
        for url in recorder.urls:
            assert "api.instagram.com" not in url
            assert "graph.instagram.com" not in url

    async def test_callback_success_with_json_accept(
        self, client, db_session, admin_headers, admin_user, monkeypatch
    ):
        await _save_full_meta_config(db_session)
        _mock_httpx_client(monkeypatch, _happy_handler(_Recorder()))
        state, _ = await _authorize(client, admin_headers)

        response = await client.get(
            f"/sport/publications/meta/callback?code=AUTH-CODE&state={state}",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "connected"}

    async def test_callback_invalid_state_redirects_error(
        self, client, db_session, admin_headers, monkeypatch
    ):
        await _save_full_meta_config(db_session)
        recorder = _Recorder()
        _mock_httpx_client(monkeypatch, _happy_handler(recorder))

        response = await client.get(
            "/sport/publications/meta/callback?code=AUTH-CODE&state=etat-invalide"
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("/settings?error=")
        assert "invalide" in location
        assert recorder.requests == [], "aucun echange reseau avec un state invalide"
        assert await _config_value(db_session, "meta_access_token") is None

    async def test_callback_missing_params_reports_error(self, client, monkeypatch):
        recorder = _Recorder()
        _mock_httpx_client(monkeypatch, _happy_handler(recorder))
        response = await client.get(
            "/sport/publications/meta/callback",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 400
        assert response.json()["status"] == "error"
        assert recorder.requests == []

    async def test_callback_refusal_reports_error(self, client):
        response = await client.get(
            "/sport/publications/meta/callback?error=access_denied&error_reason=user_denied"
        )
        assert response.status_code == 302
        assert response.headers["location"].startswith("/settings?error=")
        assert "user_denied" in response.headers["location"]

    async def test_callback_exchange_error_sanitized_in_redirect(
        self, client, db_session, admin_headers, monkeypatch
    ):
        await _save_full_meta_config(db_session)
        recorder = _Recorder()
        _mock_httpx_client(
            monkeypatch,
            _exchange_error_handler(
                recorder,
                "Error validating verification code: redirect_uri is identical for app and token",
            ),
        )
        state, _ = await _authorize(client, admin_headers)

        response = await client.get(
            f"/sport/publications/meta/callback?code=SECRET-CODE-VALUE&state={state}"
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("/settings?error=")
        assert "redirect_uri" in location
        assert META_APP_SECRET not in location
        assert "SECRET-CODE-VALUE" not in location
        assert await _config_value(db_session, "meta_access_token") is None

    async def test_callback_without_instagram_account_fails(
        self, client, db_session, admin_headers, monkeypatch
    ):
        await _save_full_meta_config(db_session)
        recorder = _Recorder()
        _mock_httpx_client(monkeypatch, _happy_handler(recorder, accounts=[]))
        state, _ = await _authorize(client, admin_headers)

        response = await client.get(
            f"/sport/publications/meta/callback?code=AUTH-CODE&state={state}",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 502
        payload = response.json()
        assert payload["status"] == "error"
        assert "Aucun compte Instagram assign" in payload["detail"]
        # Le jeton sans compte n'est pas enregistre.
        assert await _config_value(db_session, "meta_access_token") is None

    async def test_legacy_callback_and_login_routes_gone(self, client, db_session, admin_headers):
        """L'ancien POST /meta/callback et POST /meta/login n'existent plus."""
        response = await client.post(
            "/sport/publications/meta/callback", json={"code": "x", "state": "y"}, headers=admin_headers
        )
        assert response.status_code == 405  # seul GET existe (route publique)

        response = await client.post("/sport/publications/meta/login", headers=admin_headers)
        assert response.status_code in (404, 405)


# --------------------------------------------------------------------------- #
# Connexion centrale : statut, deconnexion, ancien onglet supprime
# --------------------------------------------------------------------------- #


class TestCentralConnection:
    async def test_status_endpoint_reports_configured_and_connected(
        self, client, db_session, admin_headers
    ):
        await _save_full_meta_config(db_session)
        await _connect(db_session)

        response = await client.get("/sport/publications/meta/status", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["configured"] is True
        assert data["connected"] is True
        assert data["instagram_user_id"] == IG_ACCOUNT_ID
        assert data["client_business_id"] == BUSINESS_ID
        assert data["username"] == "trailrunner"

    async def test_status_endpoint_default_not_configured(self, client, db_session, admin_headers):
        response = await client.get("/sport/publications/meta/status", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["configured"] is False
        assert data["connected"] is False
        assert data["instagram_user_id"] is None

    async def test_status_requires_settings_view(self, client, auth_headers):
        response = await client.get("/sport/publications/meta/status", headers=auth_headers)
        assert response.status_code == 403

    async def test_disconnect_clears_credentials(
        self, client, db_session, admin_headers
    ):
        await _save_full_meta_config(db_session)
        await _connect(db_session)

        response = await client.delete("/sport/publications/meta", headers=admin_headers)
        assert response.status_code == 200
        assert response.json() == {"disconnected": True}

        assert await _config_value(db_session, "meta_access_token") == ""
        assert await _config_value(db_session, "meta_client_business_id") == ""
        assert await _config_value(db_session, "instagram_user_id") == ""
        assert await _config_value(db_session, "instagram_username") == ""

        status = (
            await client.get("/sport/publications/meta/status", headers=admin_headers)
        ).json()
        assert status["connected"] is False

        # Configuration Meta conservee (app, secret, callback, config_id).
        assert await _config_value(db_session, "meta_app_id") == META_APP_ID
        assert await _config_value(db_session, "meta_config_id") == CONFIG_ID

        # Second appel : rien a deconnecter.
        response = await client.delete("/sport/publications/meta", headers=admin_headers)
        assert response.json() == {"disconnected": False}

    async def test_disconnect_requires_settings_update(self, client, auth_headers):
        response = await client.delete("/sport/publications/meta", headers=auth_headers)
        assert response.status_code == 403

    async def test_legacy_instagram_settings_routes_removed(
        self, client, db_session, admin_headers, auth_headers
    ):
        """L'ancien onglet /admin/settings/instagram n'existe plus (pas de route API)."""
        response = await client.get("/admin/settings/instagram", headers=admin_headers)
        # Sans route FastAPI -> le catch-all SPA renvoie l'index HTML (200 text/html).
        # Le fait qu'une API Meta JSON ne reponde plus prouve l'absence de route.
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        response = await client.put(
            "/admin/settings/instagram",
            json={"app_id": "x", "app_secret": "", "redirect_uri": ""},
            headers=admin_headers,
        )
        # PUT inconnu -> 405 (method not allowed sur le catch-all qui ne supporte que GET).
        assert response.status_code in (404, 405)

        # Sans droits : la route est absente, donc pas de 403 meta.
        response = await client.get("/admin/settings/instagram", headers=auth_headers)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


# --------------------------------------------------------------------------- #
# Publication via la configuration centrale
# --------------------------------------------------------------------------- #


class TestPublishWithCentralConfig:
    async def test_publish_uses_config_token(self, db_session, monkeypatch):
        await _save_full_meta_config(db_session)
        await _connect(db_session)

        recorder = _Recorder()
        _mock_httpx_client(monkeypatch, _happy_handler(recorder))

        publish_service = MetaPublishService(db_session)
        context = await publish_service.resolve_publish_context()
        assert context is not None
        assert getattr(context, "auth_type", None) == "meta_config"

        container_id = await publish_service.create_media_container(
            context, "https://example.com/photo.jpg", "caption"
        )
        assert container_id == "CONTAINER-123"

        media_requests = [
            r
            for r in recorder.requests
            if "graph.facebook.com" in str(r.url) and str(r.url).split("?")[0].endswith("/media")
        ]
        assert len(media_requests) == 1
        query = parse_qs(urlparse(str(media_requests[0].url)).query)
        assert query["access_token"] == [SUAT_TOKEN]

    async def test_resolve_returns_none_without_config(self, db_session):
        publish_service = MetaPublishService(db_session)
        context = await publish_service.resolve_publish_context()
        assert context is None

    async def test_resolve_ignores_missing_token(self, db_session):
        await _save_full_meta_config(db_session)
        await _save_meta_config(db_session, instagram_user_id=IG_ACCOUNT_ID)

        publish_service = MetaPublishService(db_session)
        context = await publish_service.resolve_publish_context()
        assert context is None


# --------------------------------------------------------------------------- #
# Garanties statiques (un seul parcours d'authentification + cache-busting)
# --------------------------------------------------------------------------- #


class TestStaticGuarantees:
    def test_frontend_has_single_meta_auth_path(self):
        settings_page = pathlib.Path("src/public/js/pages/UserSettingsPage.js").read_text(
            encoding="utf-8"
        )
        index = pathlib.Path("src/public/index.html").read_text(encoding="utf-8")
        sport_api = pathlib.Path("src/public/js/services/sportApi.js").read_text(encoding="utf-8")
        admin_api = pathlib.Path("src/public/js/services/adminApi.js").read_text(encoding="utf-8")

        for source, name in (
            (settings_page, "UserSettingsPage.js"),
            (index, "index.html"),
            (sport_api, "sportApi.js"),
            (admin_api, "adminApi.js"),
        ):
            assert "window.FB" not in source, f"window.FB residuel dans {name}"
            assert "FB.login" not in source, f"FB.login residuel dans {name}"
            assert "connect.facebook.net" not in source, f"SDK FB residuel dans {name}"
            assert "initMetaLogin" not in source, f"initMetaLogin residuel dans {name}"
            assert "meta/login" not in source, f"meta/login residuel dans {name}"

        # Carte Meta unique avec Config ID et connexion/dieconnexion.
        assert "config_id" in settings_page
        assert "getInstagramAuthUrl" in settings_page
        assert "disconnectInstagram" in settings_page
        assert "window.location.assign" in settings_page
        assert "data-role=\"meta-connection\"" in settings_page

        # L'ancien onglet Instagram individuel a disparu.
        assert "data-form=\"instagram-settings\"" not in settings_page
        assert "getInstagramSettings" not in settings_page
        assert "updateInstagramSettings" not in settings_page
        assert "instagram_app_id" not in settings_page
        assert "settings/instagram" not in admin_api

    def test_backend_uses_unified_login_only(self):
        service = pathlib.Path("app/services/sport_instagram.py").read_text(encoding="utf-8")
        assert "www.facebook.com/dialog/oauth" in service
        assert "graph.facebook.com" in service
        assert "\"config_id\"" in service
        assert "prompt" in service
        # Plus aucune API Instagram directe.
        assert "api.instagram.com" not in service
        assert "graph.instagram.com" not in service
        assert "www.instagram.com" not in service

        publications = pathlib.Path("app/api/sport_publications.py").read_text(encoding="utf-8")
        assert "instagram.com" not in publications
        assert "exchange_business_code" in publications
        assert "save_meta_credentials" in publications

        config = pathlib.Path("app/core/config.py").read_text(encoding="utf-8")
        assert "INSTAGRAM_APP_ID" not in config
        assert "INSTAGRAM_API_VERSION" not in config

        admin = pathlib.Path("app/api/admin.py").read_text(encoding="utf-8")
        assert "/settings/instagram" not in admin
        assert "InstagramSettings" not in admin
        # Les routes conservees restent presentes.
        assert '@settings_router.get("/meta"' in admin
        assert '@settings_router.put("/meta"' in admin
        assert "/meta/test" in admin
        assert "/meta/debug-token" in admin

        model = pathlib.Path("app/models/sport.py").read_text(encoding="utf-8")
        assert "SportInstagramConnection" not in model
        assert "SportInstagramOAuthState" in model

        migration = pathlib.Path(
            "alembic/versions/20261111_0001_drop_instagram_connections.py"
        ).read_text(encoding="utf-8")
        assert "drop_table" in migration
        assert "sport_instagram_connections" in migration

    def test_cache_bust_versions_are_bumped(self):
        app_erp = pathlib.Path("src/public/js/app-erp.js").read_text(encoding="utf-8")
        index = pathlib.Path("src/public/index.html").read_text(encoding="utf-8")
        settings_page = pathlib.Path("src/public/js/pages/UserSettingsPage.js").read_text(
            encoding="utf-8"
        )

        page_version = int(re.search(r"UserSettingsPage\.js\?v=(\d+)", app_erp).group(1))
        bundle_version = int(re.search(r"app-erp\.js\?v=(\d+)", index).group(1))
        sport_version = int(re.search(r"sportApi\.js\?v=(\d+)", settings_page).group(1))
        admin_version = int(re.search(r"adminApi\.js\?v=(\d+)", settings_page).group(1))
        assert page_version >= 19, "cache-bust UserSettingsPage.js doit etre augmente"
        assert bundle_version >= 133, "cache-bust app-erp.js doit etre augmente"
        assert sport_version >= 3, "cache-bust sportApi.js doit etre augmente"
        assert admin_version >= 7, "cache-bust adminApi.js doit etre augmente"
