"""Service de mise à disposition des médias pour publication Meta.

Ce service gère la mise à disposition publique des médias (photos/vidéos)
depuis le stockage ForgeAI vers des URLs accessibles publiquement par Meta.

Sécurité :
- URLs signées (JWT) avec expiration courte
- Validation stricte du propriétaire du média
- Protection contre l'accès aux photos d'autres utilisateurs
- Révocation/invalidation après expiration
- Tokens stockés en base pour validation et révocation
"""

import hashlib
import base64
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import Photo
from app.models.sport import MediaPublishToken

logger = logging.getLogger(__name__)


class MediaPublishError(Exception):
    """Erreur lors de la préparation du média pour publication."""

    pass


class MediaPublishService:
    """Service pour préparer les médias à la publication Meta.

    Sécurité :
    - URLs signées (JWT HS256) avec expiration courte (configurable, défaut 1h)
    - Tokens stockés en base pour validation et révocation
    - Validation stricte du propriétaire du média
    - Protection contre l'accès aux photos d'autres utilisateurs
    - Révocation/invalidation après expiration ou utilisation
    - Protection contre l'accès aux photos d'autres utilisateurs
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def _get_signing_key(self) -> bytes:
        """Récupère la clé de signature pour les JWT."""
        from app.core.config import get_settings
        settings = get_settings()
        # Utilise une clé dérivée du SECRET_KEY pour les tokens média
        import hashlib
        import base64
        secret = f"{settings.SECRET_KEY}:media-publish".encode("utf-8")
        return base64.urlsafe_b64encode(hashlib.sha256(secret).digest())

    def _create_signed_token(self, photo_id: int, user_id: int, expires_in_seconds: int = 3600) -> str:
        """Crée un token JWT signé pour l'accès au média."""
        import jwt
        import hashlib
        import base64

        now = datetime.now(timezone.utc)
        exp = now + timedelta(seconds=expires_in_seconds)

        payload = {
            "photo_id": photo_id,
            "user_id": user_id,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "type": "media_publish",
        }

        signing_key = self._get_signing_key()
        token = jwt.encode(payload, signing_key, algorithm="HS256")
        return token

    def _verify_signed_token(self, token: str) -> Optional[dict]:
        """Vérifie et décode un token JWT signé."""
        import jwt
        import hashlib
        import base64

        try:
            signing_key = self._get_signing_key()
            payload = jwt.decode(token, signing_key, algorithms=["HS256"])
            if payload.get("type") != "media_publish":
                return None
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    async def _store_token(self, token: str, photo_id: int, user_id: int, expires_at: datetime) -> None:
        """Stocke le token en base pour validation et révocation."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        media_token = MediaPublishToken(
            token_hash=token_hash,
            photo_id=photo_id,
            user_id=user_id,
            expires_at=expires_at,
            consumed=False,
        )
        self.db.add(media_token)
        await self.db.flush()

    async def _validate_token(self, token: str) -> Optional[dict]:
        """Valide un token : vérifie signature, expiration, et existence en base non consommé."""
        payload = self._verify_signed_token(token)
        if not payload:
            return None

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        result = await self.db.execute(
            select(MediaPublishToken).where(
                MediaPublishToken.token_hash == token_hash,
                MediaPublishToken.consumed == False,
                MediaPublishToken.expires_at >= datetime.now(timezone.utc),
            )
        )
        token_record = result.scalar_one_or_none()
        if not token_record:
            return None

        return {
            "photo_id": payload["photo_id"],
            "user_id": payload["user_id"],
            "token_record": token_record,
        }

    async def _consume_token(self, token_record: MediaPublishToken) -> None:
        """Marque un token comme consommé (révocation)."""
        token_record.consumed = True
        await self.db.flush()

    async def prepare_media_for_publish(self, photo_id: int, user_id: int, expires_in_seconds: int = 3600) -> str:
        """Prépare un média pour publication Meta.

        Returns:
            URL signée accessible par Meta pour télécharger le média.
        """
        # Récupérer la photo et vérifier l'accès
        result = await self.db.execute(
            select(Photo).where(Photo.id == photo_id)
        )
        photo = result.scalar_one_or_none()
        if not photo:
            raise MediaPublishError("Photo introuvable")

        # Vérifier que l'utilisateur a accès à cette photo
        if photo.owner_id != user_id and not photo.is_public:
            # Vérifier si l'utilisateur a accès via un album partagé
            # Pour l'instant, on autorise si l'utilisateur est propriétaire
            raise MediaPublishError("Accès non autorisé à ce média")

        # Créer le token signé
        token = self._create_signed_token(photo_id, user_id, expires_in_seconds)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)

        # Stocker le token en base
        await self._store_token(token, photo_id, user_id, expires_at)

        # Construire l'URL signée
        from app.core.config import get_settings
        settings = get_settings()
        base_url = settings.PUBLIC_URL.rstrip('/') if settings.PUBLIC_URL else "https://forgeai.design-ede.fr"

        public_url = f"{base_url}/photos/{photo_id}/file?meta_token={token}"

        logger.info(f"Media prepared for publish: photo_id={photo_id}, user_id={user_id}, expires_in={expires_in_seconds}s")
        return public_url

    async def validate_media_token(self, token: str) -> Optional[dict]:
        """Valide un token d'accès média (appelé par l'endpoint /photos/{id}/file)."""
        validation = await self._validate_token(token)
        if not validation:
            return None

        # Marquer le token comme consommé (single-use pour la publication Meta)
        await self._consume_token(validation["token_record"])

        return {
            "photo_id": validation["photo_id"],
            "user_id": validation["user_id"],
        }


async def get_media_publish_service(db: AsyncSession):
    return MediaPublishService(db)