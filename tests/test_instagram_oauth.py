"""Tests d'integration Instagram OAuth (Unified Login).

Tous les appels Meta sont mockes (httpx.MockTransport). Aucun appel reel
n'est effectue. Aucune modification de production.
"""

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta, timezone
import httpx

from app.services.sport_instagram import (
    SportInstagramConnectService,
    _encrypt_token,
    _decrypt_token,
)
from app.services.sport_instagram_publish import MetaPublishService, MetaPublishError
from app.models.sport import SportInstagramConnection, SportInstagramOAuthState


def _patch_unified_credentials(
    monkeypatch,
    app_id="meta-app-id",
    app_secret="meta-app-secret",
    redirect_uri="https://forgeai.example.com/callback",
    config_id="cfg-123",
):
    """Remplace les identifiants unifies (App + Configuration ID)."""

    async def fake_app_credentials(self):
        return app_id, app_secret, redirect_uri

    async def fake_config_id(self):
        return config_id

    monkeypatch.setattr(SportInstagramConnectService, "_app_credentials", fake_app_credentials)
    monkeypatch.setattr(SportInstagramConnectService, "_config_id", fake_config_id)


# ============================================================
# Tests de chiffrement / dechiffrement
# ============================================================

class TestTokenEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        original = "super-secret-token-12345"
        encrypted = _encrypt_token(original)
        assert encrypted != original
        decrypted = _decrypt_token(encrypted)
        assert decrypted == original

    def test_decrypt_none(self):
        assert _decrypt_token(None) is None
        assert _encrypt_token(None) is None

    def test_decrypt_invalid(self):
        assert _decrypt_token("not-valid-encrypted-data!!!") is None


# ============================================================
# Tests de construction URL OAuth
# ============================================================

class TestBuildAuthorizationUrl:
    @pytest.fixture
    def mock_service(self, db_session):
        return SportInstagramConnectService(db_session)

    @pytest.mark.asyncio
    async def test_build_authorization_url_unified_login(self, mock_service, monkeypatch):
        """L'URL d'autorisation utilise Unified Login (config_id sur facebook.com)."""
        _patch_unified_credentials(monkeypatch)

        url, state = await mock_service.build_authorization_url(athlete_id=1, user_id=1)

        assert "www.facebook.com/dialog/oauth" in url
        assert "client_id=meta-app-id" in url
        assert "config_id=cfg-123" in url
        assert "response_type=code" in url
        assert f"state={state}" in url
        assert "display=popup" in url
        assert "prompt=login" in url
        # Unified Login : les permissions viennent de la configuration, pas de scope
        assert "scope=" not in url
        assert "www.instagram.com" not in url

    @pytest.mark.asyncio
    async def test_build_authorization_url_requires_config_id(self, mock_service, monkeypatch):
        """Sans Configuration ID, la connexion Unified Login est impossible (503)."""

        async def fake_app_credentials(self):
            return "meta-app-id", "meta-app-secret", "https://forgeai.example.com/callback"

        async def fake_load(self):
            return {"config_id": ""}

        monkeypatch.setattr(SportInstagramConnectService, "_app_credentials", fake_app_credentials)
        monkeypatch.setattr(SportInstagramConnectService, "load_meta_values", fake_load)

        with pytest.raises(HTTPException) as exc_info:
            await mock_service.build_authorization_url(athlete_id=1, user_id=1)
        assert exc_info.value.status_code == 503
        assert "Configuration ID" in exc_info.value.detail


# ============================================================
# Helper pour mock httpx
# ============================================================

def _mock_httpx_client(monkeypatch, handler):
    """Remplace httpx.AsyncClient par un client MockTransport (API factice)."""
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("app.services.sport_instagram_publish.httpx.AsyncClient", factory)
    monkeypatch.setattr("app.services.sport_instagram.httpx.AsyncClient", factory)


# ============================================================
# Tests d'echange de code
# ============================================================

class TestExchangeCode:
    @pytest.fixture
    def mock_service(self, db_session):
        return SportInstagramConnectService(db_session)

    @pytest.mark.asyncio
    async def test_exchange_code_success_unified_login(self, mock_service, db_session, monkeypatch):
        """Flux complet Unified Login : code -> token FB -> long-lived -> comptes IG."""
        from app.models.sport import SportInstagramOAuthState
        state_obj = SportInstagramOAuthState(
            state="valid-state-123",
            user_id=1,
            athlete_id=10,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            consumed=False,
        )
        db_session.add(state_obj)
        await db_session.commit()

        _patch_unified_credentials(monkeypatch)

        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            seen.append(url)
            if "graph.facebook.com" in url and "/oauth/access_token" in url:
                grant = request.url.params.get("grant_type")
                if grant == "authorization_code":
                    return httpx.Response(
                        200,
                        json={
                            "access_token": "short-lived-token",
                            "token_type": "bearer",
                            "scope": "instagram_basic,instagram_content_publish",
                        },
                        request=request,
                    )
                if grant == "fb_exchange_long_lived":
                    return httpx.Response(
                        200,
                        json={
                            "access_token": "long-lived-token-123",
                            "expires_in": 5184000,
                            "scope": "instagram_basic,instagram_content_publish",
                        },
                        request=request,
                    )
            if "/me/assigned_instagram_accounts" in url:
                return httpx.Response(
                    200,
                    json={"data": [{"id": "17841400000000000", "username": "testuser_ig"}]},
                    request=request,
                )
            return httpx.Response(404, json={"error": "not found"}, request=request)

        _mock_httpx_client(monkeypatch, handler)

        connection = await mock_service.exchange_code(
            code="auth-code-123",
            redirect_uri="https://forgeai.example.com/callback",
            state="valid-state-123",
        )

        assert connection is not None
        assert connection.instagram_business_account_id == "17841400000000000"
        assert connection.auth_type == "unified_login"
        assert connection.status == "active"
        assert _decrypt_token(connection.encrypted_long_lived_token) == "long-lived-token-123"
        # Les permissions accordees sont conservees pour detecter content_publish
        assert connection.scopes is not None
        assert "instagram_content_publish" in connection.scopes
        # Le compte IG est resolve via assigned_instagram_accounts, jamais via /me
        assert any("/me/assigned_instagram_accounts" in url for url in seen)
        # Aucun appel au flux Instagram Login natif
        assert not any("api.instagram.com" in url for url in seen)
        assert not any("graph.instagram.com" in url for url in seen)

    @pytest.mark.asyncio
    async def test_exchange_code_invalid_state(self, mock_service, db_session, monkeypatch):
        """Etat invalide -> HTTP 400."""
        with pytest.raises(HTTPException) as exc_info:
            await mock_service.exchange_code(
                code="any-code",
                redirect_uri=None,
                state="invalid-state",
            )
        assert exc_info.value.status_code == 400


# ============================================================
# Tests de rafraîchissement des tokens
# ============================================================

class TestTokenRefresh:
    @pytest.fixture
    def mock_connection(self):
        conn = MagicMock(spec=SportInstagramConnection)
        conn.id = 1
        conn.user_id = 1
        conn.instagram_business_account_id = "17841400000000000"
        conn.auth_type = "instagram_login"
        conn.status = "active"
        conn.obtained_at = datetime.now(timezone.utc)
        conn.expires_in = 5184000
        conn.encrypted_long_lived_token = _encrypt_token("valid-long-token")
        return conn

    @pytest.mark.asyncio
    async def test_refresh_uses_ig_refresh_token_for_instagram_login(self, mock_connection, db_session, monkeypatch):
        """Les tokens Instagram Login utilisent ig_refresh_token (jamais fb_exchange_long_lived)."""
        service = MetaPublishService(db_session)
        service.db = db_session

        monkeypatch.setattr(service, "_get_long_lived_token", lambda c: "valid-long-token")

        async def fake_app_credentials(self):
            return "insta-app-id", "insta-app-secret", "https://forgeai.example.com/callback"
        monkeypatch.setattr(
            SportInstagramConnectService, "_app_credentials", fake_app_credentials
        )

        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            seen["url"] = url
            if "graph.instagram.com/v26.0/refresh_access_token" in url:
                return httpx.Response(200, json={"access_token": "refreshed-long-token"}, request=request)
            return httpx.Response(404, json={"error": "not found"}, request=request)

        _mock_httpx_client(monkeypatch, handler)

        class FakeResult:
            def scalar_one_or_none(self):
                return mock_connection
        monkeypatch.setattr(db_session, "execute", AsyncMock(return_value=FakeResult()))
        monkeypatch.setattr(db_session, "commit", AsyncMock())

        new_token = await service._refresh_long_lived_token(mock_connection)
        assert new_token == "refreshed-long-token"
        # Verifier que l'endpoint Instagram est appele (pas Facebook)
        assert "graph.instagram.com" in seen.get("url", "")
        assert "fb_exchange_long_lived" not in seen.get("url", "")

    @pytest.mark.asyncio
    async def test_refresh_uses_fb_exchange_for_unified_login(self, mock_connection, db_session, monkeypatch):
        """Unified Login : le refresh utilise fb_exchange_long_lived sur graph.facebook.com."""
        mock_connection.auth_type = "unified_login"
        service = MetaPublishService(db_session)
        service.db = db_session

        monkeypatch.setattr(service, "_get_long_lived_token", lambda c: "unified-long-token")

        async def fake_app_credentials(self):
            return "meta-app-id", "meta-app-secret", "https://forgeai.example.com/callback"
        monkeypatch.setattr(
            SportInstagramConnectService, "_app_credentials", fake_app_credentials
        )

        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            seen["url"] = url
            if "graph.facebook.com/v26.0/oauth/access_token" in url:
                return httpx.Response(200, json={"access_token": "refreshed-unified-token"}, request=request)
            return httpx.Response(404, json={"error": "not found"}, request=request)

        _mock_httpx_client(monkeypatch, handler)

        class FakeResult:
            def scalar_one_or_none(self):
                return mock_connection
        monkeypatch.setattr(db_session, "execute", AsyncMock(return_value=FakeResult()))
        monkeypatch.setattr(db_session, "commit", AsyncMock())

        new_token = await service._refresh_long_lived_token(mock_connection)
        assert new_token == "refreshed-unified-token"
        assert "graph.facebook.com" in seen.get("url", "")
        assert "fb_exchange_long_lived" in seen.get("url", "")
        assert "graph.instagram.com" not in seen.get("url", "")

    @pytest.mark.asyncio
    async def test_refresh_uses_fb_exchange_for_facebook_login(self, mock_connection, db_session, monkeypatch):
        """Les anciens tokens Facebook Login utilisent encore fb_exchange_long_lived (retrocompat)."""
        mock_connection.auth_type = "facebook_login"
        service = MetaPublishService(db_session)
        service.db = db_session

        monkeypatch.setattr(service, "_get_long_lived_token", lambda c: "old-fb-token")

        async def fake_app_credentials(self):
            return "fb-app-id", "fb-app-secret", "https://forgeai.example.com/callback"
        monkeypatch.setattr(
            SportInstagramConnectService, "_app_credentials", fake_app_credentials
        )

        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            seen["url"] = url
            if "graph.facebook.com/v26.0/oauth/access_token" in url:
                return httpx.Response(200, json={"access_token": "refreshed-fb-token"}, request=request)
            return httpx.Response(404, json={"error": "not found"}, request=request)

        _mock_httpx_client(monkeypatch, handler)

        class FakeResult:
            def scalar_one_or_none(self):
                return mock_connection
        monkeypatch.setattr(db_session, "execute", AsyncMock(return_value=FakeResult()))
        monkeypatch.setattr(db_session, "commit", AsyncMock())

        new_token = await service._refresh_long_lived_token(mock_connection)
        assert new_token == "refreshed-fb-token"
        # Verifier que l'endpoint Facebook est appele pour ce vieux token
        assert "graph.facebook.com" in seen.get("url", "")
        assert "fb_exchange_long_lived" in seen.get("url", "")


# ============================================================
# Tests de protection contre le melange des tokens
# ============================================================

class TestTokenTypeProtection:
    def test_instagram_token_never_uses_fb_exchange(self):
        """Un token Instagram Login ne doit jamais etre rafraichi avec fb_exchange_long_lived."""
        import inspect
        source = inspect.getsource(MetaPublishService._refresh_long_lived_token)
        assert "ig_refresh_token" in source
        assert "instagram_login" in source

    def test_facebook_token_still_supported(self):
        """Un ancien token Facebook Login reste supporte pour retrocompatibilite."""
        import inspect
        source = inspect.getsource(MetaPublishService._refresh_long_lived_token)
        assert "fb_exchange_long_lived" in source


# ============================================================
# Tests de publication
# ============================================================

class TestPublish:
    @pytest.mark.asyncio
    async def test_create_media_container_uses_ig_account_id(self, db_session, monkeypatch):
        """La publication utilise instagram_business_account_id (IG ID, pas Page FB)."""
        service = MetaPublishService(db_session)

        connection = MagicMock(spec=SportInstagramConnection)
        connection.id = 1
        connection.instagram_business_account_id = "17841400000000000"
        connection.auth_type = "instagram_login"

        monkeypatch.setattr(service, "_get_valid_token", AsyncMock(return_value="valid-token"))

        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            seen["url"] = url
            assert "/17841400000000000/media" in url
            return httpx.Response(200, json={"id": "container_123"}, request=request)

        _mock_httpx_client(monkeypatch, handler)

        container_id = await service.create_media_container(
            connection, "https://example.com/photo.jpg", "Test caption"
        )
        assert container_id == "container_123"
