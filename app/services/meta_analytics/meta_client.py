"""Client Meta Graph API centralise pour Meta Analytics.

Reutilise la configuration Meta existante (ModuleConfig administration >
variables d'environnement) et le jeton SUAT dejà chiffre, sans creer de
deuxieme gestionnaire de connexion ni dupliquer les tokens.

Aucune cle secrete n'est jamais loggee ni retournee.
"""

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.models.module import Module, ModuleConfig
from app.services.sport_instagram import _decrypt_token

logger = logging.getLogger(__name__)

META_GRAPH_HOST = "https://graph.facebook.com"


class MetaGraphError(Exception):
    """Erreur retourne par l'API Meta Graph (sans secret dans le message)."""

    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


class MetaGraphClient:
    """Client HTTP vers graph.facebook.com avec gestion des quotas et pagination."""

    def __init__(self, db, access_token: str, api_version: str | None = None):
        self.db = db
        self.access_token = access_token
        settings = get_settings()
        self.api_version = api_version or settings.META_API_VERSION or "v27.0"
        self.base_url = f"{META_GRAPH_HOST}/{self.api_version}"
        self._client = httpx.AsyncClient(timeout=30.0)

    @property
    def headers(self) -> dict[str, str]:
        return {"User-Agent": "ForgeAI-MetaAnalytics/1.0"}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        params["access_token"] = self.access_token
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = await self._client.request(method, url, params=params, headers=self.headers)
        except httpx.RequestError as exc:
            raise MetaGraphError(f"Erreur reseau vers Meta Graph: {exc}") from exc

        if response.status_code >= 400:
            error_code = None
            message = f"Meta Graph HTTP {response.status_code}"
            try:
                payload = response.json()
                meta_error = payload.get("error", {}) or {}
                message = meta_error.get("message") or message
                error_code = str(meta_error.get("code") or "")
                # Subcode utile pour diagnostiquer permissions/quotas sans le logger en clair
                subcode = meta_error.get("error_subcode")
                logger.warning(
                    "Meta Graph erreur (HTTP %s, code=%s, subcode=%s)",
                    response.status_code, error_code, subcode,
                )
            except ValueError:
                logger.warning("Meta Graph erreur (HTTP %s, reponse non-JSON)", response.status_code)
            raise MetaGraphError(message, status=response.status_code, code=error_code) from None

        try:
            return response.json()
        except ValueError:
            return {}

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, params)

    async def get_paginated(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Recupere toutes les pages d'un endpoint pagine (borne par limit)."""
        results: list[dict[str, Any]] = []
        next_url: str | None = None
        current_params = dict(params or {})
        pages = 0
        max_pages = 50  # garde-fou contre les boucles

        while pages < max_pages and (next_url or pages == 0) and len(results) < limit:
            pages += 1
            if next_url:
                # Pagination via curseur Meta : on recupere l'URL suivante telle quelle
                try:
                    response = await self._client.get(next_url, headers=self.headers, params={"access_token": self.access_token})
                except httpx.RequestError as exc:
                    raise MetaGraphError(f"Erreur reseau pagination Meta: {exc}") from exc
                if response.status_code >= 400:
                    raise MetaGraphError(f"Meta Graph pagination HTTP {response.status_code}", status=response.status_code) from None
                try:
                    payload = response.json()
                except ValueError:
                    break
            else:
                payload = await self.get(path, current_params)

            data = payload.get("data") or []
            results.extend(data)
            if len(results) >= limit:
                results = results[:limit]
                break

            paging = payload.get("paging") or {}
            next_url = paging.get("next")
            current_params = {}  # l'URL suivante est complete

        return results

    async def get_insights(
        self,
        object_id: str,
        metrics: list[str],
        period: str = "day",
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        """Recupere des insights pour un objet Meta (compte ou media)."""
        params: dict[str, Any] = {
            "metric": ",".join(metrics),
            "period": period,
        }
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        return await self.get(f"{object_id}/insights", params)


async def _load_meta_connection(db) -> dict[str, str]:
    """Charge la configuration Meta et le jeton deconnecte depuis la base.

    Retourne un dictionnaire avec : app_id, app_secret, api_version,
    access_token (dechiffre), instagram_user_id, client_business_id.
    Aucune valeur secrete n'est retournee en clair au-delà du jeton necessaire
    aux appels Graph (garde en memoire uniquement, jamais logge).
    """
    from app.services.sport_instagram import SportInstagramConnectService

    service = SportInstagramConnectService(db)
    configs = await service._load_administration_values(
        ("meta_app_id", "meta_app_secret", "meta_config_id", "meta_access_token", "meta_client_business_id", "instagram_user_id", "instagram_username")
    )
    settings = get_settings()
    return {
        "app_id": configs.get("meta_app_id") or settings.META_APP_ID or "",
        "app_secret": configs.get("meta_app_secret") or settings.META_APP_SECRET or "",
        "config_id": configs.get("meta_config_id") or settings.META_CONFIG_ID or "",
        "api_version": configs.get("api_version") or settings.META_API_VERSION or "v27.0",
        "access_token_encrypted": configs.get("meta_access_token") or "",
        "client_business_id": configs.get("meta_client_business_id") or "",
        "instagram_user_id": configs.get("instagram_user_id") or "",
        "instagram_username": configs.get("instagram_username") or "",
    }


async def build_client(db) -> tuple[MetaGraphClient, dict[str, str]]:
    """Construit un client Meta Graph pret a l'emploi a partir de la config centrale.

    Leve MetaGraphError si la configuration ou le jeton est absent/illisible.
    """
    connection = await _load_meta_connection(db)
    encrypted_token = connection["access_token_encrypted"]
    if not encrypted_token:
        raise MetaGraphError("Aucun jeton Meta configure. Connectez le compte Instagram dans Parametres > Meta.", status=403)
    token = _decrypt_token(encrypted_token)
    if not token:
        raise MetaGraphError("Jeton Meta illisible. Regenerer le jeton dans la configuration Meta.", status=403)
    client = MetaGraphClient(db, token, api_version=connection["api_version"])
    return client, connection
