"""Service de publication Meta (Instagram Business) - Publication effective."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from httpx import HTTPStatusError
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.sport import SportAthlete, SportInstagramConnection, SportPublication
from app.models.user import User

logger = logging.getLogger(__name__)


class MetaPublishError(Exception):
    """Erreur lors de la publication sur Meta."""

    def __init__(self, message: str, meta_error_code: Optional[str] = None, meta_error_subcode: Optional[str] = None):
        super().__init__(message)
        self.meta_error_code = meta_error_code
        self.meta_error_subcode = meta_error_subcode


class MetaPublishService:
    """Service pour publier du contenu sur Instagram via l'API Meta Graph."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def _base_url(self) -> str:
        return f"https://graph.facebook.com/{get_settings().META_API_VERSION}"

    async def _get_active_connection(self, user_id: int) -> Optional[SportInstagramConnection]:
        """Récupère la connexion Instagram active de l'utilisateur."""
        from app.models.sport import SportInstagramConnection
        result = await self.db.execute(
            select(SportInstagramConnection).where(
                SportInstagramConnection.user_id == user_id,
                SportInstagramConnection.status == "active",
            )
        )
        return result.scalar_one_or_none()

    def _get_long_lived_token(self, connection) -> Optional[str]:
        """Déchiffre le token long-lived depuis la connexion."""
        from app.services.sport_instagram import _decrypt_token
        return _decrypt_token(connection.encrypted_long_lived_token or connection.encrypted_access_token)

    async def _get_app_credentials(self) -> tuple[str, str]:
        """Récupère les identifiants de l'application Meta."""
        from app.services.sport_instagram import SportInstagramConnectService
        service = SportInstagramConnectService(self.db)
        app_id, app_secret, _, _ = await service._app_credentials()
        return app_id, app_secret

    async def _refresh_long_lived_token(self, connection) -> Optional[str]:
        """Rafraîchit le token long-lived via l'API Instagram (ig_refresh_token).

        Ne JAMAIS utiliser fb_exchange_long_lived (réservé au flux Facebook Login).
        Le flux Instagram Login utilise grant_type=ig_refresh_token sur
        https://graph.instagram.com/refresh_access_token.
        """
        from app.services.sport_instagram import SportInstagramConnectService, _decrypt_token, _encrypt_token

        # Vérifier si le token expire bientôt (moins de 24h)
        if connection.expires_in and connection.obtained_at:
            from datetime import timedelta
            expiry = connection.obtained_at + timedelta(seconds=connection.expires_in)
            if (expiry - datetime.now(timezone.utc)).total_seconds() < 86400:  # 24h
                logger.info(f"Token expires soon, refreshing for user {connection.user_id}")

        service = SportInstagramConnectService(self.db)
        app_id, app_secret, _ = await service._app_credentials()

        long_token = self._get_long_lived_token(connection)
        if not long_token:
            return None

        # Déterminer le type d'authentification pour choisir le bon endpoint de refresh
        auth_type = getattr(connection, "auth_type", None) or "facebook_login"

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                if auth_type == "instagram_login":
                    # Instagram Login : ig_refresh_token sur graph.instagram.com
                    response = await client.get(
                        f"https://graph.instagram.com/{get_settings().INSTAGRAM_API_VERSION}/refresh_access_token",
                        params={
                            "grant_type": "ig_refresh_token",
                            "access_token": long_token,
                        },
                    )
                else:
                    # Facebook Login (rétrocompatibilité anciens tokens) : fb_exchange_long_lived
                    response = await client.get(
                        f"{self._base_url}/oauth/access_token",
                        params={
                            "grant_type": "fb_exchange_long_lived",
                            "client_id": app_id,
                            "client_secret": app_secret,
                            "fb_exchange_long_lived_token": long_token,
                        },
                    )
                response.raise_for_status()
                new_token = response.json().get("access_token")
                if new_token:
                    # Mettre à jour la connexion
                    from app.models.sport import SportInstagramConnection
                    result = await self.db.execute(
                        select(SportInstagramConnection).where(
                            SportInstagramConnection.id == connection.id
                        )
                    )
                    conn = result.scalar_one_or_none()
                    if conn:
                        conn.encrypted_long_lived_token = self._fernet_encrypt(new_token)
                        conn.encrypted_access_token = self._fernet_encrypt(new_token)
                        conn.obtained_at = datetime.now(timezone.utc)
                        conn.expires_in = 5184000  # 60 jours
                        await self.db.commit()
                    logger.info("Long-lived token refreshed successfully")
                    return new_token
        except Exception as e:
            logger.warning(f"Failed to refresh long-lived token: {e}")
        return None

    def _fernet_encrypt(self, token: str) -> str:
        from app.services.sport_instagram import _fernet
        return _fernet().encrypt(token.encode("utf-8")).decode("ascii")

    async def _get_valid_token(self, connection) -> Optional[str]:
        """Récupère un token valide, le rafraîchit si nécessaire."""
        token = self._get_long_lived_token(connection)
        if not token:
            return None

        # Vérifier si le token est proche de l'expiration
        if connection.expires_in and connection.obtained_at:
            from datetime import timedelta
            expiry = connection.obtained_at + timedelta(seconds=connection.expires_in)
            if (expiry - datetime.now(timezone.utc)).total_seconds() < 86400:  # 24h
                refreshed = await self._refresh_long_lived_token(connection)
                if refreshed:
                    return refreshed
        return token

    async def create_media_container(
        self,
        connection,
        image_url: str,
        caption: str,
        is_video: bool = False,
    ) -> str:
        """Crée un conteneur média sur Instagram (étape 1 de la publication)."""
        token = await self._get_valid_token(connection)
        if not token:
            raise MetaPublishError("Aucun token valide disponible pour la publication")

        ig_account_id = connection.instagram_business_account_id
        if not ig_account_id:
            raise MetaPublishError("Aucun compte Instagram Business associé")

        url = f"{self._base_url}/{ig_account_id}/media"
        params = {
            "access_token": token,
            "caption": caption,
        }

        if is_video:
            params["media_type"] = "VIDEO"
            params["video_url"] = image_url
        else:
            params["image_url"] = image_url

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, params=params)
                response.raise_for_status()
                data = response.json()
                container_id = data.get("id")
                if not container_id:
                    raise MetaPublishError("Meta n'a pas retourné d'ID de conteneur média")
                logger.info(f"Media container created: {container_id}")
                return container_id
            except HTTPStatusError as exc:
                error_data = exc.response.json() if exc.response.content else {}
                error = error_data.get("error", {})
                raise MetaPublishError(
                    f"Erreur création conteneur: {error.get('message', str(exc))}",
                    meta_error_code=error.get("code"),
                    meta_error_subcode=error.get("error_subcode"),
                ) from exc
            except httpx.RequestError as exc:
                raise MetaPublishError(f"Erreur réseau: {str(exc)}") from exc

    async def publish_media_container(
        self,
        connection,
        container_id: str,
    ) -> str:
        """Publie un conteneur média précédemment créé (étape 2 de la publication)."""
        token = await self._get_valid_token(connection)
        if not token:
            raise MetaPublishError("Aucun token valide disponible pour la publication")

        ig_account_id = connection.instagram_business_account_id
        if not ig_account_id:
            raise MetaPublishError("Aucun compte Instagram Business associé")

        url = f"{self._base_url}/{ig_account_id}/media_publish"
        params = {
            "access_token": token,
            "creation_id": container_id,
        }

        # Polling pour vérifier le statut du conteneur
        max_attempts = 30
        for attempt in range(max_attempts):
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    status_resp = await client.get(
                        f"{self._base_url}/{container_id}",
                        params={"fields": "status_code", "access_token": token},
                    )
                    if status_resp.status_code == 200:
                        status_data = status_resp.json()
                        status_code = status_data.get("status_code")
                        if status_code == "FINISHED":
                            break
                        elif status_code in ("ERROR", "EXPIRED"):
                            raise MetaPublishError(f"Conteneur média invalide: {status_code}")
                        # IN_PROGRESS -> continuer le polling
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.warning(f"Erreur polling conteneur: {e}")
                    await asyncio.sleep(2)
        else:
            raise MetaPublishError("Timeout: le conteneur média n'est pas prêt après 60 secondes")

        # Publier le conteneur
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    url,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                media_id = data.get("id")
                if not media_id:
                    raise MetaPublishError("Meta n'a pas retourné d'ID de média publié")
                logger.info(f"Media published successfully: {media_id}")
                return media_id
            except HTTPStatusError as exc:
                error_data = exc.response.json() if exc.response.content else {}
                error = error_data.get("error", {})
                raise MetaPublishError(
                    f"Erreur publication: {error.get('message', str(exc))}",
                    meta_error_code=error.get("code"),
                    meta_error_subcode=error.get("error_subcode"),
                ) from exc
            except httpx.RequestError as exc:
                raise MetaPublishError(f"Erreur réseau: {str(exc)}") from exc

    async def publish_photo(
        self,
        connection,
        image_url: str,
        caption: str,
    ) -> str:
        """Publie une photo sur Instagram (workflow complet: container + publish)."""
        container_id = await self.create_media_container(connection, image_url, caption, is_video=False)
        media_id = await self.publish_media_container(connection, container_id)
        return media_id

    async def publish_video(
        self,
        connection,
        video_url: str,
        caption: str,
    ) -> str:
        """Publie une vidéo sur Instagram (workflow complet: container + publish)."""
        container_id = await self.create_media_container(connection, video_url, caption, is_video=True)
        media_id = await self.publish_media_container(connection, container_id)
        return media_id

    async def get_media_permalink(self, connection, media_id: str) -> Optional[str]:
        """Récupère le permalink d'un média publié."""
        token = await self._get_valid_token(connection)
        if not token:
            return None

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    f"{self._base_url}/{media_id}",
                    params={"fields": "permalink", "access_token": token},
                )
                response.raise_for_status()
                data = response.json()
                return data.get("permalink")
            except Exception as e:
                logger.warning(f"Failed to get permalink: {e}")
                return None


# Fonction helper pour récupérer le service
async def get_meta_publish_service(db: AsyncSession) -> MetaPublishService:
    return MetaPublishService(db)