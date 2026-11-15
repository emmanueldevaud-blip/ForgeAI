"""Service de publication Meta (Instagram Business) - Publication effective."""

import asyncio
import logging
import os
from typing import Optional

import httpx
from httpx import HTTPStatusError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.sport import SportPublication

logger = logging.getLogger(__name__)


class MetaPublishError(Exception):
    """Erreur lors de la publication sur Meta."""

    def __init__(self, message: str, meta_error_code: Optional[str] = None, meta_error_subcode: Optional[str] = None):
        super().__init__(message)
        self.meta_error_code = meta_error_code
        self.meta_error_subcode = meta_error_subcode


# Extensions de fichiers vidéo acceptées par Meta
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
# Extensions de fichiers photo acceptées par Meta
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class _MetaConfigContext:
    """Contexte de publication tiré de la configuration Meta centralisée.

    Contrat attendu par MetaPublishService : jeton chiffré Fernet +
    compte Instagram. Pas d'expiration gérée (renouvellement manuel via
    la configuration Meta, donc aucun refresh auto).
    """

    def __init__(self, encrypted_token: str, instagram_business_account_id: str) -> None:
        self.encrypted_long_lived_token = encrypted_token
        self.encrypted_access_token = encrypted_token
        self.instagram_business_account_id = instagram_business_account_id
        self.expires_in = None
        self.obtained_at = None
        self.auth_type = "meta_config"
        self.status = "active"
        self.scopes = ""
        self.metadata_json = {"source": "meta_config"}


class MetaPublishService:
    """Service pour publier du contenu sur Instagram via l'API Meta Graph."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def _base_url(self) -> str:
        return f"https://graph.facebook.com/{get_settings().META_API_VERSION}"

    async def resolve_publish_context(self):
        """Source de la publication Instagram : la configuration Meta centralisée
        (jeton SUAT partagé, stocké une seule fois)."""
        return await self._config_publish_context()

    async def _config_publish_context(self) -> Optional[_MetaConfigContext]:
        """Construit le contexte depuis la config Meta si le jeton est exploitable."""
        from app.models.module import Module, ModuleConfig

        result = await self.db.execute(
            select(ModuleConfig)
            .join(Module)
            .where(
                Module.code == "administration",
                ModuleConfig.key.in_(("meta_access_token", "instagram_user_id")),
            )
        )
        configs = {
            config.key: config.value
            for config in result.scalars().all()
            if config.value is not None
        }
        raw_token = configs.get("meta_access_token")
        ig_user_id = configs.get("instagram_user_id")
        if not raw_token or not ig_user_id:
            return None

        from app.services.sport_instagram import _decrypt_token

        if not _decrypt_token(raw_token):
            logger.warning(
                "meta_access_token illisible — publication impossible tant que le jeton "
                "n'est pas régénéré dans la configuration Meta"
            )
            return None

        return _MetaConfigContext(
            encrypted_token=raw_token,
            instagram_business_account_id=str(ig_user_id),
        )

    def _get_long_lived_token(self, connection) -> Optional[str]:
        """Déchiffre le token de publication du contexte de publication."""
        from app.services.sport_instagram import _decrypt_token
        return _decrypt_token(connection.encrypted_long_lived_token or connection.encrypted_access_token)

    async def _get_valid_token(self, connection) -> Optional[str]:
        """Jeton de publication (le SUAT n'est pas renouvelé automatiquement :
        expiration choisie à la création de la configuration Meta)."""
        return self._get_long_lived_token(connection)

    def _detect_media_type_from_url(self, url: str) -> str:
        """Détecte le type de média à partir de l'extension du fichier dans l'URL.

        Retourne "video" ou "photo".
        """
        import os
        ext = os.path.splitext(url.split("?")[0])[1].lower()
        if ext in VIDEO_EXTENSIONS:
            return "video"
        if ext in PHOTO_EXTENSIONS:
            return "photo"
        # Par défaut, on considère que c'est une photo (cas des URLs sans extension
        # explicite mais qui servent une image via Content-Type)
        return "photo"

    def _validate_media_type_consistency(self, is_video_expected: bool, url: str, mime_type: str) -> None:
        """Vérifie que le type de média attendu (photo/vidéo) est cohérent
        avec le type MIME et l'extension du fichier.

        Raises:
            MetaPublishError: si une incohérence est détectée.
        """
        detected_type = self._detect_media_type_from_url(url)
        mime_is_video = mime_type in {"video/mp4", "video/quicktime"}

        # Si l'extension suggère une vidéo mais qu'on attend une photo (ou vice versa)
        if is_video_expected and not mime_is_video and detected_type != "video":
            raise MetaPublishError(
                f"Incohérence de type de média : publication vidéo demandée mais "
                f"le fichier semble être une image (MIME: {mime_type}, extension détectée: {detected_type}). "
                f"Vérifiez le visuel associé à la publication."
            )
        if not is_video_expected and mime_is_video:
            raise MetaPublishError(
                f"Incohérence de type de média : publication photo demandée mais "
                f"le fichier est une vidéo (MIME: {mime_type}). "
                f"Sélectionnez 'Reel' ou 'Vidéo' comme type de visuel, ou choisissez une photo."
            )

    async def create_media_container(
        self,
        connection,
        image_url: str,
        caption: str,
        is_video: bool = False,
        mime_type: Optional[str] = None,
    ) -> str:
        """Crée un conteneur média sur Instagram (étape 1 de la publication).

        Args:
            connection: Contexte de publication Meta (jeton + compte).
            image_url: URL publique du média (photo ou vidéo).
            caption: Légende de la publication.
            is_video: True si le média est une vidéo/Reel, False pour une photo.
            mime_type: Type MIME du média (pour validation et logs).
        """
        # Validation de cohérence du type de média
        if mime_type:
            self._validate_media_type_consistency(is_video, image_url, mime_type)

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

        # Log de diagnostic (sans le token)
        safe_url = image_url.split("?")[0] if "?" in image_url else image_url
        logger.info(
            "Creating Meta media container: is_video=%s, mime_type=%s, url=%s",
            is_video, mime_type or "unknown", safe_url,
        )

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
        mime_type: Optional[str] = None,
    ) -> str:
        """Publie une photo sur Instagram (workflow complet: container + publish)."""
        container_id = await self.create_media_container(connection, image_url, caption, is_video=False, mime_type=mime_type)
        media_id = await self.publish_media_container(connection, container_id)
        return media_id

    async def publish_video(
        self,
        connection,
        video_url: str,
        caption: str,
        mime_type: Optional[str] = None,
    ) -> str:
        """Publie une vidéo sur Instagram (workflow complet: container + publish)."""
        container_id = await self.create_media_container(connection, video_url, caption, is_video=True, mime_type=mime_type)
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