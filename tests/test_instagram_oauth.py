"""Tests du chiffrement des jetons Meta et de la publication Instagram.

L'ancien flux OAuth (Unified Login) a ete supprime (jalon 3) : seules restent
les fonctions de chiffrement et la publication via la configuration centralisee.
Tous les appels Meta sont mockes (httpx.MockTransport). Aucun appel reel
n'est effectue.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

import httpx

from app.services.sport_instagram import _decrypt_token, _encrypt_token
from app.services.sport_instagram_publish import MetaPublishService, _MetaConfigContext


def _mock_httpx_client(monkeypatch, handler):
    """Remplace httpx.AsyncClient par un client MockTransport (API factice)."""
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("app.services.sport_instagram_publish.httpx.AsyncClient", factory)


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
# Tests de publication
# ============================================================

class TestPublish:
    @pytest.mark.asyncio
    async def test_create_media_container_uses_ig_account_id(self, db_session, monkeypatch):
        """La publication utilise instagram_business_account_id (IG ID, pas Page FB)."""
        service = MetaPublishService(db_session)

        connection = _MetaConfigContext(
            encrypted_token="encrypted-token",
            instagram_business_account_id="17841400000000000",
        )

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
