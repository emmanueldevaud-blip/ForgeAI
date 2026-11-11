"""Tests du flux Instagram Login (voie B) — connexions par utilisateur.

Couvre : URL d'autorisation, states CSRF, callback public, echange POST
multipart sur api.instagram.com, isolation multi-utilisateurs, deconnexion,
statut, publication avec jeton de connexion, et garanties statiques
(absence totale de Facebook Login for Business).
"""

import pathlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.models.module import Module, ModuleConfig, ModuleStatus
from app.models.sport import SportInstagramConnection, SportInstagramOAuthState
from app.services.sport_instagram import SportInstagramConnectService, _decrypt_token
from app.services.sport_instagram_publish import MetaPublishService

IG_APP_ID = "2039163733413585"
IG_APP_SECRET = "instagram-app-secret-value"
IG_REDIRECT = "https://forgeai.design-ede.fr/sport/publications/meta/callback"
SHORT_TOKEN = "SHORT-IG-TOKEN"
LONG_TOKEN = "LONG-IG-TOKEN"
CONN_TOKEN = "USER-CONNECTION-TOKEN"
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


async def _save_instagram_config(db, **values):
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
                is_secret=key.endswith("secret"),
            ))
    await db.commit()


async def _save_meta_config(db, **values):
    """Configuration Meta centralisee (repli de publication)."""
    await _save_instagram_config(db, **values)


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


def _happy_handler(recorder: _Recorder):
    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        path = str(request.url).split("?")[0]
        if path == "https://api.instagram.com/oauth/access_token":
            return httpx.Response(
                200,
                json={"access_token": SHORT_TOKEN, "token_type": "bearer", "expires_in": 3600, "user_id": "111"},
                request=request,
            )
        if path.startswith("https://graph.instagram.com/") and path.endswith("/refresh_access_token"):
            return httpx.Response(
                200, json={"access_token": "RENEWED-TOKEN", "expires_in": 5184000}, request=request
            )
        if path.startswith("https://graph.instagram.com/") and path.endswith("/access_token"):
            return httpx.Response(
                200,
                json={"access_token": LONG_TOKEN, "token_type": "bearer", "expires_in": 5184000},
                request=request,
            )
        if path.startswith("https://graph.instagram.com/") and path.endswith("/me"):
            return httpx.Response(
                200, json={"id": IG_ACCOUNT_ID, "username": "trailrunner"}, request=request
            )
        if "graph.facebook.com" in path and path.endswith("/media"):
            return httpx.Response(200, json={"id": "CONTAINER-123"}, request=request)
        return httpx.Response(404, json={}, request=request)

    return handler


def _exchange_error_handler(recorder: _Recorder, message: str, status: int = 400):
    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        if str(request.url).startswith("https://api.instagram.com/"):
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


async def _connect_user(db, user_id, token=CONN_TOKEN, ig_id=IG_ACCOUNT_ID):
    service = SportInstagramConnectService(db)
    await service.save_connection(
        user_id,
        access_token=token,
        expires_in=5184000,
        instagram_business_account_id=ig_id,
        username="trailrunner",
    )
    return await service.get_connection(user_id)


# --------------------------------------------------------------------------- #
# URL d'autorisation
# --------------------------------------------------------------------------- #


class TestAuthorizeUrl:
    async def test_authorize_url_uses_instagram_dialog(self, client, db_session, admin_headers, admin_user):
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
        state, url = await _authorize(client, admin_headers)

        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "www.instagram.com"
        assert parsed.path == "/oauth/authorize"
        qs = parse_qs(parsed.query)
        assert qs["client_id"] == [IG_APP_ID]
        assert qs["redirect_uri"] == [IG_REDIRECT]
        assert qs["response_type"] == ["code"]
        assert "instagram_business_content_publish" in qs["scope"][0]
        assert qs["state"] == [state]
        # Aucun parametre Facebook Login for Business
        assert "config_id" not in qs

        row = (
            await db_session.execute(
                select(SportInstagramOAuthState).where(SportInstagramOAuthState.state == state)
            )
        ).scalar_one()
        assert row.user_id == admin_user.id
        assert row.consumed is False
        assert row.expires_at is not None

    async def test_authorize_requires_instagram_config(self, client, db_session, admin_headers):
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
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
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
# Echange du code (POST multipart api.instagram.com)
# --------------------------------------------------------------------------- #


class TestCodeExchange:
    async def test_exchange_posts_multipart_to_api_instagram(self, db_session, monkeypatch):
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
        recorder = _Recorder()
        _mock_httpx_client(monkeypatch, _happy_handler(recorder))

        service = SportInstagramConnectService(db_session)
        result = await service.exchange_instagram_code("AUTH-CODE-XYZ")

        assert result["access_token"] == LONG_TOKEN
        assert result["instagram_business_account_id"] == IG_ACCOUNT_ID
        assert result["username"] == "trailrunner"

        token_requests = [r for r in recorder.requests if "api.instagram.com" in str(r.url)]
        assert len(token_requests) == 1
        request = token_requests[0]
        assert request.method == "POST"
        assert str(request.url) == "https://api.instagram.com/oauth/access_token"
        content_type = request.headers.get("content-type", "")
        assert content_type.startswith("multipart/form-data")
        body = request.content
        for field in (b"grant_type", b"client_id", b"client_secret", b"redirect_uri", b"code"):
            assert field in body, f"champ {field!r} absent du multipart"

    async def test_exchange_never_calls_graph_facebook(self, db_session, monkeypatch):
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
        recorder = _Recorder()
        _mock_httpx_client(monkeypatch, _happy_handler(recorder))

        service = SportInstagramConnectService(db_session)
        await service.exchange_instagram_code("AUTH-CODE-XYZ")

        assert recorder.requests, "aucun appel reseau enregistre"
        for url in recorder.urls:
            assert "graph.facebook.com" not in url, f"appel d'authentification vers graph.facebook.com : {url}"
            assert url.startswith(
                ("https://api.instagram.com/", "https://graph.instagram.com/")
            ), url

    async def test_exchange_keeps_short_token_when_conversion_fails(self, db_session, monkeypatch):
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            path = str(request.url).split("?")[0]
            if path == "https://api.instagram.com/oauth/access_token":
                return httpx.Response(
                    200, json={"access_token": SHORT_TOKEN, "expires_in": 3600}, request=request
                )
            if "graph.instagram.com" in path and path.endswith("/access_token"):
                return httpx.Response(500, json={}, request=request)
            return httpx.Response(404, json={}, request=request)

        _mock_httpx_client(monkeypatch, handler)
        service = SportInstagramConnectService(db_session)
        result = await service.exchange_instagram_code("AUTH-CODE-XYZ")
        assert result["access_token"] == SHORT_TOKEN
        assert result["expires_in"] == 3600

    async def test_exchange_instagram_error_is_sanitized(self, db_session, monkeypatch):
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
        recorder = _Recorder()
        _mock_httpx_client(
            monkeypatch,
            _exchange_error_handler(
                recorder,
                "Error validating verification code: redirect_uri is identical for app and token",
            ),
        )
        service = SportInstagramConnectService(db_session)
        with pytest.raises(Exception) as excinfo:
            await service.exchange_instagram_code("SECRET-CODE-VALUE")
        message = str(excinfo.value)
        assert "redirect_uri" in message
        assert IG_APP_SECRET not in message
        assert "SECRET-CODE-VALUE" not in message


# --------------------------------------------------------------------------- #
# Callback public (redirection navigateur, sans session)
# --------------------------------------------------------------------------- #


class TestCallback:
    async def test_callback_success_redirects_and_connects(
        self, client, db_session, admin_headers, admin_user, monkeypatch
    ):
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
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

        connection = (
            await db_session.execute(
                select(SportInstagramConnection).where(
                    SportInstagramConnection.user_id == admin_user.id
                )
            )
        ).scalar_one()
        assert connection.status == "active"
        assert connection.auth_type == "instagram_login"
        assert connection.instagram_business_account_id == IG_ACCOUNT_ID
        assert _decrypt_token(connection.encrypted_long_lived_token) == LONG_TOKEN
        assert (connection.metadata_json or {}).get("username") == "trailrunner"

    async def test_callback_success_with_json_accept(
        self, client, db_session, admin_headers, admin_user, monkeypatch
    ):
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
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
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
        recorder = _Recorder()
        _mock_httpx_client(monkeypatch, _happy_handler(recorder))

        response = await client.get(
            "/sport/publications/meta/callback?code=AUTH-CODE&state=etat-invalide"
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("/settings?error=")
        assert "invalide" in location
        assert recorder.requests == [], "aucun echange réseau avec un state invalide"
        rows = (await db_session.execute(select(SportInstagramConnection))).scalars().all()
        assert rows == []

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

    async def test_callback_instagram_refusal_reports_error(self, client):
        response = await client.get(
            "/sport/publications/meta/callback?error=access_denied&error_reason=user_denied"
        )
        assert response.status_code == 302
        assert response.headers["location"].startswith("/settings?error=")
        assert "user_denied" in response.headers["location"]

    async def test_callback_exchange_error_sanitized_in_redirect(
        self, client, db_session, admin_headers, monkeypatch
    ):
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
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
        assert IG_APP_SECRET not in location
        assert "SECRET-CODE-VALUE" not in location
        rows = (await db_session.execute(select(SportInstagramConnection))).scalars().all()
        assert rows == []

    async def test_callback_route_removed_from_authenticated_flow(self, client, db_session, admin_headers):
        """L'ancien POST /meta/callback (Facebook Login for Business) n'existe plus."""
        response = await client.post(
            "/sport/publications/meta/callback", json={"code": "x", "state": "y"}, headers=admin_headers
        )
        assert response.status_code == 405  # seul GET existe (route publique)

        response = await client.post("/sport/publications/meta/login", headers=admin_headers)
        # Route supprimee : seul le catch-all GET repond (405 method not allowed).
        assert response.status_code in (404, 405)


# --------------------------------------------------------------------------- #
# Isolation multi-utilisateurs + statut + deconnexion
# --------------------------------------------------------------------------- #


class TestConnectionsPerUser:
    async def test_two_users_have_separate_connections(
        self, client, db_session, admin_headers, admin_user, auth_user, monkeypatch
    ):
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
        _mock_httpx_client(monkeypatch, _happy_handler(_Recorder()))
        service = SportInstagramConnectService(db_session)

        state_a, _ = await _authorize(client, admin_headers)
        user_a = await service.consume_state(state_a)
        assert user_a == admin_user.id
        result = await service.exchange_instagram_code("CODE-A")
        await service.save_connection(
            user_a,
            access_token=result["access_token"],
            expires_in=result["expires_in"],
            instagram_business_account_id=result["instagram_business_account_id"],
            username=result.get("username"),
        )

        _, state_b = await service.build_authorization_url(auth_user.id)
        user_b = await service.consume_state(state_b)
        assert user_b == auth_user.id
        result_b = await service.exchange_instagram_code("CODE-B")
        await service.save_connection(
            user_b,
            access_token=result_b["access_token"],
            expires_in=result_b["expires_in"],
            instagram_business_account_id="99999999999999999",
            username="autre",
        )

        conn_a = await service.get_connection(admin_user.id)
        conn_b = await service.get_connection(auth_user.id)
        assert conn_a.instagram_business_account_id == IG_ACCOUNT_ID
        assert conn_b.instagram_business_account_id == "99999999999999999"
        assert conn_a.id != conn_b.id

        # Deconnexion isolee : B reste actif.
        assert await service.disconnect(admin_user.id) is True
        assert (await service.get_connection(admin_user.id)).status == "disconnected"
        assert (await service.get_connection(auth_user.id)).status == "active"

    async def test_status_endpoint(self, client, db_session, admin_headers, admin_user):
        # Non configure
        response = await client.get("/sport/publications/meta/status", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["configured"] is False
        assert response.json()["connected"] is False

        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
        response = await client.get("/sport/publications/meta/status", headers=admin_headers)
        assert response.json()["configured"] is True
        assert response.json()["connected"] is False

        await _connect_user(db_session, admin_user.id)
        response = await client.get("/sport/publications/meta/status", headers=admin_headers)
        data = response.json()
        assert data["connected"] is True
        assert data["instagram_business_account_id"] == IG_ACCOUNT_ID
        assert data["username"] == "trailrunner"
        assert data["status"] == "active"

    async def test_status_requires_settings_view(self, client, auth_headers):
        response = await client.get("/sport/publications/meta/status", headers=auth_headers)
        assert response.status_code == 403

    async def test_disconnect_endpoint(self, client, db_session, admin_headers, admin_user):
        await _save_instagram_config(
            db_session,
            instagram_app_id=IG_APP_ID,
            instagram_app_secret=IG_APP_SECRET,
            instagram_redirect_uri=IG_REDIRECT,
        )
        await _connect_user(db_session, admin_user.id)

        response = await client.delete("/sport/publications/meta", headers=admin_headers)
        assert response.status_code == 200
        assert response.json() == {"disconnected": True}

        status = await client.get("/sport/publications/meta/status", headers=admin_headers)
        assert status.json()["connected"] is False

        # Second appel : rien a deconnecter
        response = await client.delete("/sport/publications/meta", headers=admin_headers)
        assert response.json() == {"disconnected": False}

    async def test_disconnect_requires_settings_update(self, client, auth_headers):
        response = await client.delete("/sport/publications/meta", headers=auth_headers)
        assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Publication avec jeton de connexion
# --------------------------------------------------------------------------- #


class TestPublishWithConnection:
    async def test_publish_uses_user_connection_token(
        self, db_session, admin_user, monkeypatch
    ):
        await _connect_user(db_session, admin_user.id, token=CONN_TOKEN)
        # Repli de config present mais ignore : la connexion prime.
        await _save_meta_config(
            db_session,
            meta_access_token="should-not-be-used",
            instagram_user_id="00000000000000000",
        )

        recorder = _Recorder()
        _mock_httpx_client(monkeypatch, _happy_handler(recorder))

        publish_service = MetaPublishService(db_session)
        context = await publish_service.resolve_publish_context(admin_user.id)
        assert context is not None
        assert getattr(context, "auth_type", None) == "instagram_login"

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
        assert query["access_token"] == [CONN_TOKEN]

    async def test_resolve_falls_back_to_config_without_connection(
        self, db_session, admin_user
    ):
        from app.services.sport_instagram import _encrypt_token

        await _save_meta_config(
            db_session,
            meta_access_token=_encrypt_token("CONFIG-TOKEN") or "",
            instagram_user_id=IG_ACCOUNT_ID,
        )

        publish_service = MetaPublishService(db_session)
        context = await publish_service.resolve_publish_context(admin_user.id)
        assert context is not None
        assert getattr(context, "auth_type", None) == "meta_config"


# --------------------------------------------------------------------------- #
# Garanties statiques (frontend + cache-busting)
# --------------------------------------------------------------------------- #


class TestStaticGuarantees:
    def test_frontend_has_no_facebook_login(self):
        settings_page = pathlib.Path("src/public/js/pages/UserSettingsPage.js").read_text(
            encoding="utf-8"
        )
        index = pathlib.Path("src/public/index.html").read_text(encoding="utf-8")
        sport_api = pathlib.Path("src/public/js/services/sportApi.js").read_text(encoding="utf-8")

        for source, name in (
            (settings_page, "UserSettingsPage.js"),
            (index, "index.html"),
            (sport_api, "sportApi.js"),
        ):
            assert "window.FB" not in source, f"window.FB residuel dans {name}"
            assert "FB.login" not in source, f"FB.login residuel dans {name}"
            assert "connect.facebook.net" not in source, f"SDK FB residuel dans {name}"
            assert "initMetaLogin" not in source, f"initMetaLogin residuel dans {name}"
            assert "meta/login" not in source, f"meta/login residuel dans {name}"

        assert "config_id" not in settings_page
        assert "getInstagramAuthUrl" in settings_page
        assert "disconnectInstagram" in settings_page
        assert "window.location.assign" in settings_page
        assert "https://www.instagram.com/oauth/authorize" not in settings_page  # URL construite cote backend

    def test_backend_has_no_facebook_login_flow(self):
        source = pathlib.Path("app/services/sport_instagram.py").read_text(encoding="utf-8")
        assert "graph.facebook.com" not in source
        assert "FB.login" not in source
        assert "initiate_meta_login" not in source
        assert "api.instagram.com/oauth/access_token" in source

    def test_cache_bust_versions_are_bumped(self):
        app_erp = pathlib.Path("src/public/js/app-erp.js").read_text(encoding="utf-8")
        index = pathlib.Path("src/public/index.html").read_text(encoding="utf-8")
        settings_page = pathlib.Path("src/public/js/pages/UserSettingsPage.js").read_text(
            encoding="utf-8"
        )

        page_version = int(re.search(r"UserSettingsPage\.js\?v=(\d+)", app_erp).group(1))
        bundle_version = int(re.search(r"app-erp\.js\?v=(\d+)", index).group(1))
        sport_version = int(re.search(r"sportApi\.js\?v=(\d+)", settings_page).group(1))
        assert page_version >= 18, "cache-bust UserSettingsPage.js doit etre augmente"
        assert bundle_version >= 132, "cache-bust app-erp.js doit etre augmente"
        assert sport_version >= 3, "cache-bust sportApi.js doit etre augmente"
