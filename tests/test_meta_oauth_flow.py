"""Tests du parcours OAuth Meta Unified Login (Instagram) — non-régression.

Couvre :
- Génération de l'URL d'autorisation (build_authorization_url)
- Validation et consommation du state CSRF
- Callback OAuth (succès, erreur Meta, paramètres manquants)
- Échange du code (exchange_business_code)
- Cohérence des redirect_uri
- Gestion des erreurs Meta spécifiques
- Pré-vérification (preflight)
- Non-régression des autres fonctionnalités de publication

Tous les appels Meta sont mockés (httpx.MockTransport). Aucun appel réel n'est effectué.
"""

import httpx
import pytest
from sqlalchemy import select
from unittest.mock import AsyncMock, patch

from app.models.module import Module, ModuleConfig, ModuleStatus


# ============================================================
# Fixtures
# ============================================================


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


async def _setup_meta_config(client, admin_headers, **overrides):
    """Configure les paramètres Meta dans la base de test."""
    body = {
        "app_id": "test-app-id-123",
        "app_secret": "test-app-secret",
        "redirect_uri": "https://forgeai.example.com/sport/publications/meta/callback",
        "config_id": "cfg-test-456",
    }
    body.update(overrides)
    resp = await client.put("/admin/settings/meta", json=body, headers=admin_headers)
    assert resp.status_code == 200
    return resp.json()


def _mock_httpx(monkeypatch, handler, module_path="app.services.sport_instagram.httpx.AsyncClient"):
    """Remplace httpx.AsyncClient par un client MockTransport (API factice)."""
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(module_path, factory)


# ============================================================
# Tests : Génération de l'URL d'autorisation
# ============================================================


class TestBuildAuthorizationUrl:
    async def test_auth_url_contains_required_params(self, client, admin_headers):
        """L'URL générée contient client_id, config_id, redirect_uri, response_type, state."""
        await _setup_meta_config(client, admin_headers)
        resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        assert resp.status_code == 200
        url = resp.json()["authorize_url"]
        assert "client_id=test-app-id-123" in url
        assert "config_id=cfg-test-456" in url
        assert "redirect_uri=" in url
        assert "response_type=code" in url
        assert "state=" in url
        assert "prompt=login" in url
        assert "www.facebook.com/dialog/oauth" in url

    async def test_auth_url_contains_override_default_response_type(self, client, admin_headers):
        """Le paramètre override_default_response_type=true est présent."""
        await _setup_meta_config(client, admin_headers)
        resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        assert resp.status_code == 200
        url = resp.json()["authorize_url"]
        assert "override_default_response_type=true" in url

    async def test_auth_url_fails_without_config(self, client, admin_headers):
        """Sans configuration Meta, retourne 503."""
        resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        assert resp.status_code == 503
        assert "manquant" in resp.json()["detail"]

    async def test_auth_url_fails_without_config_id(self, client, admin_headers):
        """Sans Config ID, retourne 503."""
        await _setup_meta_config(client, admin_headers, config_id="")
        resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        assert resp.status_code == 503
        assert "Config ID" in resp.json()["detail"]

    async def test_auth_url_fails_without_redirect_uri(self, client, admin_headers):
        """Sans redirect_uri, retourne 503."""
        await _setup_meta_config(client, admin_headers, redirect_uri="")
        resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        assert resp.status_code == 503
        assert "Redirect URI" in resp.json()["detail"]

    async def test_redirect_uri_consistency(self, client, admin_headers):
        """Le redirect_uri dans l'URL OAuth correspond à celui configuré."""
        redirect = "https://forgeai.example.com/sport/publications/meta/callback"
        await _setup_meta_config(client, admin_headers, redirect_uri=redirect)
        resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        assert resp.status_code == 200
        from urllib.parse import quote
        assert quote(redirect, safe="") in resp.json()["authorize_url"]

    async def test_state_is_unique_per_call(self, client, admin_headers):
        """Chaque appel génère un state unique."""
        await _setup_meta_config(client, admin_headers)
        resp1 = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        resp2 = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        url1 = resp1.json()["authorize_url"]
        url2 = resp2.json()["authorize_url"]
        # Extraire les states
        import re
        state1 = re.search(r"state=([^&]+)", url1).group(1)
        state2 = re.search(r"state=([^&]+)", url2).group(1)
        assert state1 != state2

    async def test_auth_requires_settings_update_permission(self, client, auth_headers):
        """Un utilisateur sans permission settings_update ne peut pas générer l'URL."""
        resp = await client.get("/sport/publications/meta/auth", headers=auth_headers)
        assert resp.status_code == 403


# ============================================================
# Tests : Callback OAuth
# ============================================================


class TestOAuthCallback:
    async def test_callback_error_param_returns_error(self, client):
        """Le callback avec un paramètre error retourne une erreur 400."""
        resp = await client.get(
            "/sport/publications/meta/callback",
            params={"error": "access_denied", "error_reason": "user_denied"},
            headers={"accept": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["status"] == "error"
        assert "refusé" in data["detail"] or "annulé" in data["detail"]

    async def test_callback_missing_code_returns_error(self, client):
        """Le callback sans code ni state retourne une erreur 400."""
        resp = await client.get(
            "/sport/publications/meta/callback",
            headers={"accept": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["status"] == "error"
        assert "manquants" in data["detail"]

    async def test_callback_missing_state_returns_error(self, client):
        """Le callback avec code mais sans state retourne une erreur 400."""
        resp = await client.get(
            "/sport/publications/meta/callback",
            params={"code": "test-code"},
            headers={"accept": "application/json"},
        )
        assert resp.status_code == 400

    async def test_callback_invalid_state_returns_error(self, client):
        """Le callback avec un state invalide retourne une erreur 400."""
        resp = await client.get(
            "/sport/publications/meta/callback",
            params={"code": "test-code", "state": "invalid-state-xyz"},
            headers={"accept": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "invalide" in data["detail"] or "expiré" in data["detail"]

    async def test_callback_success_flow(self, client, admin_headers, monkeypatch):
        """Callback complet : state valide → échange code → enregistrement → connected."""
        await _setup_meta_config(client, admin_headers)
        # 1. Générer un state valide
        auth_resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        assert auth_resp.status_code == 200
        import re
        state = re.search(r"state=([^&]+)", auth_resp.json()["authorize_url"]).group(1)

        # 2. Mock des appels Meta pour l'échange
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "/oauth/access_token" in path:
                return httpx.Response(200, json={"access_token": "suat-token-test"}, request=request)
            if path.endswith("/me"):
                return httpx.Response(200, json={"id": "sys-user-1", "client_business_id": "bus-123"}, request=request)
            if "assigned_instagram_accounts" in path:
                return httpx.Response(200, json={"data": [{"id": "ig-456", "username": "testathlete"}]}, request=request)
            return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

        _mock_httpx(monkeypatch, handler)

        # 3. Appeler le callback
        resp = await client.get(
            "/sport/publications/meta/callback",
            params={"code": "test-auth-code", "state": state},
            headers={"accept": "application/json"},
            follow_redirects=False,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connected"

    async def test_callback_exchange_failure_returns_502(self, client, admin_headers, monkeypatch):
        """Si l'échange du code échoue, le callback retourne une erreur 502."""
        await _setup_meta_config(client, admin_headers)
        auth_resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        import re
        state = re.search(r"state=([^&]+)", auth_resp.json()["authorize_url"]).group(1)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={"error": {"message": "Invalid verification code", "code": 100}},
                request=request,
            )

        _mock_httpx(monkeypatch, handler)

        resp = await client.get(
            "/sport/publications/meta/callback",
            params={"code": "bad-code", "state": state},
            headers={"accept": "application/json"},
            follow_redirects=False,
        )
        assert resp.status_code == 502

    async def test_callback_redirect_on_success_for_browser(self, client, admin_headers, monkeypatch):
        """Sans Accept JSON, le callback redirige vers /settings?connected=1."""
        await _setup_meta_config(client, admin_headers)
        auth_resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        import re
        state = re.search(r"state=([^&]+)", auth_resp.json()["authorize_url"]).group(1)

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "/oauth/access_token" in path:
                return httpx.Response(200, json={"access_token": "suat-token-test"}, request=request)
            if path.endswith("/me"):
                return httpx.Response(200, json={"id": "sys-user-1", "client_business_id": "bus-123"}, request=request)
            if "assigned_instagram_accounts" in path:
                return httpx.Response(200, json={"data": [{"id": "ig-456", "username": "testathlete"}]}, request=request)
            return httpx.Response(404, request=request)

        _mock_httpx(monkeypatch, handler)

        resp = await client.get(
            "/sport/publications/meta/callback",
            params={"code": "test-auth-code", "state": state},
            headers={"accept": "text/html"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/settings?connected=1" in resp.headers.get("location", "")

    async def test_callback_redirect_on_error_for_browser(self, client):
        """Sans Accept JSON, une erreur redirige vers /settings?error=…."""
        resp = await client.get(
            "/sport/publications/meta/callback",
            params={"error": "access_denied", "error_reason": "user_denied"},
            headers={"accept": "text/html"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/settings?" in resp.headers.get("location", "")
        assert "error=" in resp.headers.get("location", "")

    async def test_state_cannot_be_reused(self, client, admin_headers, monkeypatch):
        """Un state OAuth consommé ne peut pas être réutilisé."""
        await _setup_meta_config(client, admin_headers)
        auth_resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        import re
        state = re.search(r"state=([^&]+)", auth_resp.json()["authorize_url"]).group(1)

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "/oauth/access_token" in path:
                return httpx.Response(200, json={"access_token": "suat-token-test"}, request=request)
            if path.endswith("/me"):
                return httpx.Response(200, json={"id": "sys-user-1", "client_business_id": "bus-123"}, request=request)
            if "assigned_instagram_accounts" in path:
                return httpx.Response(200, json={"data": [{"id": "ig-456", "username": "testathlete"}]}, request=request)
            return httpx.Response(404, request=request)

        _mock_httpx(monkeypatch, handler)

        # Premier appel : succès
        resp1 = await client.get(
            "/sport/publications/meta/callback",
            params={"code": "test-code", "state": state},
            headers={"accept": "application/json"},
        )
        assert resp1.json()["status"] == "connected"

        # Second appel avec le même state : échec
        resp2 = await client.get(
            "/sport/publications/meta/callback",
            params={"code": "test-code-2", "state": state},
            headers={"accept": "application/json"},
        )
        assert resp2.status_code == 400
        assert "invalide" in resp2.json()["detail"] or "expiré" in resp2.json()["detail"]


# ============================================================
# Tests : Échange du code (exchange_business_code)
# ============================================================


class TestExchangeBusinessCode:
    async def test_exchange_success(self, client, admin_headers, db_session, monkeypatch):
        """L'échange du code retourne access_token, client_business_id et comptes IG."""
        await _setup_meta_config(client, admin_headers)

        from app.services.sport_instagram import SportInstagramConnectService

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "/oauth/access_token" in path:
                return httpx.Response(200, json={"access_token": "suat-exchange-test"}, request=request)
            if path.endswith("/me"):
                return httpx.Response(200, json={"id": "sys-1", "client_business_id": "bus-xyz"}, request=request)
            if "assigned_instagram_accounts" in path:
                return httpx.Response(200, json={"data": [{"id": "ig-111", "username": "athlete_test"}]}, request=request)
            return httpx.Response(404, request=request)

        _mock_httpx(monkeypatch, handler)

        service = SportInstagramConnectService(db_session)
        result = await service.exchange_business_code("test-code-abc")

        assert result["access_token"] == "suat-exchange-test"
        assert result["client_business_id"] == "bus-xyz"
        assert len(result["instagram_accounts"]) == 1
        assert result["instagram_accounts"][0]["username"] == "athlete_test"

    async def test_exchange_invalid_code_raises(self, client, admin_headers, db_session, monkeypatch):
        """Un code invalide lève HTTPException."""
        await _setup_meta_config(client, admin_headers)

        from app.services.sport_instagram import SportInstagramConnectService
        from fastapi import HTTPException

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={"error": {"message": "Invalid verification code format", "code": 100}},
                request=request,
            )

        _mock_httpx(monkeypatch, handler)

        service = SportInstagramConnectService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.exchange_business_code("bad-code")
        assert exc_info.value.status_code == 502

    async def test_exchange_no_token_in_response_raises(self, client, admin_headers, db_session, monkeypatch):
        """Réponse 200 sans access_token lève HTTPException."""
        await _setup_meta_config(client, admin_headers)

        from app.services.sport_instagram import SportInstagramConnectService
        from fastapi import HTTPException

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"token_type": "bearer"}, request=request)

        _mock_httpx(monkeypatch, handler)

        service = SportInstagramConnectService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.exchange_business_code("code-no-token")
        assert exc_info.value.status_code == 502
        assert "absent" in str(exc_info.value.detail)


# ============================================================
# Tests : Cohérence redirect_uri
# ============================================================


class TestRedirectUriConsistency:
    async def test_redirect_uri_in_auth_matches_config(self, client, admin_headers):
        """Le redirect_uri dans l'URL d'auth correspond à la configuration."""
        redirect = "https://my.app.com/sport/publications/meta/callback"
        await _setup_meta_config(client, admin_headers, redirect_uri=redirect)
        resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        from urllib.parse import unquote
        url = resp.json()["authorize_url"]
        # Extraire le redirect_uri de l'URL
        import re
        match = re.search(r"redirect_uri=([^&]+)", url)
        assert match
        decoded = unquote(match.group(1))
        assert decoded == redirect


# ============================================================
# Tests : Gestion des erreurs Meta spécifiques
# ============================================================


class TestMetaErrorHandling:
    async def test_callback_access_denied_message(self, client):
        """Le message d'erreur 'access_denied' est explicite."""
        resp = await client.get(
            "/sport/publications/meta/callback",
            params={"error": "access_denied", "error_reason": "user_denied"},
            headers={"accept": "application/json"},
        )
        data = resp.json()
        assert "annulé" in data["detail"] or "refusé" in data["detail"]

    async def test_callback_generic_error(self, client):
        """Une erreur Meta générique est correctement rapportée."""
        resp = await client.get(
            "/sport/publications/meta/callback",
            params={"error": "server_error", "error_reason": "internal_failure"},
            headers={"accept": "application/json"},
        )
        data = resp.json()
        assert data["status"] == "error"
        assert "refusé" in data["detail"]


# ============================================================
# Tests : Preflight
# ============================================================


class TestPreflight:
    async def test_preflight_no_config_returns_not_ready(self, client, admin_headers):
        """Sans configuration, le preflight retourne ready=false."""
        resp = await client.get("/sport/publications/meta/preflight", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is False
        assert any(c["status"] == "error" for c in data["checks"])

    async def test_preflight_valid_config_returns_ready(self, client, admin_headers, monkeypatch):
        """Avec une configuration valide, le preflight retourne ready=true."""
        await _setup_meta_config(client, admin_headers)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"access_token": "app-token"}, request=request)

        # Mock httpx dans le module sport_publications (où le preflight fait l'appel)
        _mock_httpx(monkeypatch, handler, "app.api.sport_publications.httpx.AsyncClient")

        resp = await client.get("/sport/publications/meta/preflight", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True

    async def test_preflight_invalid_credentials(self, client, admin_headers, monkeypatch):
        """Avec des identifiants invalides, le preflight signale l'erreur."""
        await _setup_meta_config(client, admin_headers)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={"error": {"message": "Invalid client_id"}},
                request=request,
            )

        _mock_httpx(monkeypatch, handler, "app.api.sport_publications.httpx.AsyncClient")

        resp = await client.get("/sport/publications/meta/preflight", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is False
        assert any("rejeté" in c.get("detail", "") for c in data["checks"])

    async def test_preflight_requires_permission(self, client, auth_headers):
        """Un utilisateur sans permission ne peut pas accéder au preflight."""
        resp = await client.get("/sport/publications/meta/preflight", headers=auth_headers)
        assert resp.status_code == 403


# ============================================================
# Tests : Connexion/déconnexion status
# ============================================================


class TestConnectionStatus:
    async def test_status_not_configured(self, client, admin_headers):
        """Sans configuration, le statut retourne configured=false."""
        resp = await client.get("/sport/publications/meta/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False
        assert data["connected"] is False

    async def test_status_configured_not_connected(self, client, admin_headers):
        """Avec config mais sans token, le statut retourne configured=true, connected=false."""
        await _setup_meta_config(client, admin_headers)
        resp = await client.get("/sport/publications/meta/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["connected"] is False

    async def test_disconnect_clears_credentials(self, client, admin_headers, monkeypatch):
        """La déconnexion efface le token et le contexte."""
        await _setup_meta_config(client, admin_headers)

        # Simuler une connexion réussie d'abord
        auth_resp = await client.get("/sport/publications/meta/auth", headers=admin_headers)
        import re
        state = re.search(r"state=([^&]+)", auth_resp.json()["authorize_url"]).group(1)

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "/oauth/access_token" in path:
                return httpx.Response(200, json={"access_token": "suat-test"}, request=request)
            if path.endswith("/me"):
                return httpx.Response(200, json={"id": "sys-1", "client_business_id": "bus-1"}, request=request)
            if "assigned_instagram_accounts" in path:
                return httpx.Response(200, json={"data": [{"id": "ig-1", "username": "test"}]}, request=request)
            return httpx.Response(404, request=request)

        _mock_httpx(monkeypatch, handler)

        await client.get(
            "/sport/publications/meta/callback",
            params={"code": "test-code", "state": state},
            headers={"accept": "application/json"},
        )

        # Vérifier la connexion
        status_resp = await client.get("/sport/publications/meta/status", headers=admin_headers)
        assert status_resp.json()["connected"] is True

        # Déconnecter
        disc_resp = await client.delete("/sport/publications/meta", headers=admin_headers)
        assert disc_resp.status_code == 200
        assert disc_resp.json()["disconnected"] is True

        # Vérifier la déconnexion
        status_resp2 = await client.get("/sport/publications/meta/status", headers=admin_headers)
        assert status_resp2.json()["connected"] is False


# ============================================================
# Tests : Non-régression des publications
# ============================================================


class TestPublicationNonRegression:
    async def test_publications_list_still_works(self, client, admin_headers):
        """La liste des publications fonctionne toujours."""
        resp = await client.get("/sport/publications", headers=admin_headers)
        assert resp.status_code == 200

    async def test_publication_styles_still_works(self, client, admin_headers):
        """La liste des styles de publication fonctionne toujours."""
        resp = await client.get("/sport/publications/styles", headers=admin_headers)
        assert resp.status_code == 200

    async def test_settings_still_works(self, client, admin_headers):
        """Les paramètres de publication fonctionnent toujours."""
        resp = await client.get("/sport/publications/settings", headers=admin_headers)
        assert resp.status_code == 200
