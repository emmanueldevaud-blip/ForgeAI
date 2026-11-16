"""Service de mise a disposition des medias pour publication Meta.

Ce service gere la mise a disposition publique des medias (photos/videos)
depuis le stockage ForgeAI vers des URLs accessibles publiquement par Meta.

Securite :
- URLs signees avec tokens hex aleatoires (32 octets = 64 chars hex) pour eviter les problemes d'encodage URL
- Expiration courte (configurable, defaut 1h)
- Validation stricte du proprietaire du media
- Protection contre l'acces aux photos d'autres utilisateurs
- Revocation/invalidation apres expiration ou utilisation unique
- Tokens stockes en base (hash SHA256) pour validation et revocation
- Controle du type MIME avant envoi a Meta (reject HTML, JSON, etc.)
- Conversion automatique HEIC/HEIF -> JPEG pour Instagram
"""

import hashlib
import logging
import os
import secrets
import tempfile
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import Photo
from app.models.sport import MediaPublishToken

logger = logging.getLogger(__name__)

# Lazy import de Pillow + pillow-heif pour la conversion HEIC->JPEG
try:
    from PIL import Image, ImageOps
    import pillow_heif

    pillow_heif.register_heif_opener()
    _HEIC_SUPPORT = True
except ImportError:  # pragma: no cover - dependance optionnelle en dev
    _HEIC_SUPPORT = False

# Types MIME acceptes par l'API Meta Instagram
SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}
SUPPORTED_VIDEO_MIME_TYPES = {"video/mp4", "video/quicktime"}
SUPPORTED_MIME_TYPES = SUPPORTED_IMAGE_MIME_TYPES | SUPPORTED_VIDEO_MIME_TYPES

# Extensions de fichiers a rejeter explicitement (non supportees par Meta)
# .heic/.heif sont désormais convertis en JPEG a la volee, donc non rejetes.
REJECTED_EXTENSIONS = {".avif", ".html", ".htm", ".json", ".txt", ".pdf"}

# Qualite JPEG pour la conversion HEIC/HEIF
HEIC_TO_JPEG_QUALITY = 90


class MediaPublishError(Exception):
    """Erreur lors de la preparation du media pour publication."""

    pass


class MediaInfo:
    """Informations sur un media prepare pour publication."""

    def __init__(self, url: str, mime_type: str, filename: str, is_video: bool):
        self.url = url
        self.mime_type = mime_type
        self.filename = filename
        self.is_video = is_video

    def __repr__(self) -> str:
        return f"MediaInfo(url={self.url[:60]}..., mime_type={self.mime_type}, is_video={self.is_video})"


class MediaPublishService:
    """Service pour preparer les medias a la publication Meta.

    Securite :
    - Tokens hex aleatoires (32 octets = 64 chars) pour eviter les problemes d'encodage URL
    - Expiration courte (configurable, defaut 1h)
    - Tokens stockes en base (hash SHA256) pour validation et revocation
    - Validation stricte du proprietaire du media
    - Protection contre l'acces aux photos d'autres utilisateurs
    - Revocation/invalidation apres expiration ou utilisation unique
    - Protection contre l'acces aux photos d'autres utilisateurs
    - Controle du type MIME avant envoi a Meta
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def _create_hex_token(self) -> str:
        """Cree un token hex aleatoire de 32 octets (64 chars)."""
        return secrets.token_hex(32)

    def _hash_token(self, token: str) -> str:
        """Calcule le hash SHA256 d'un token pour stockage en base."""
        return hashlib.sha256(token.encode()).hexdigest()

    async def _store_token(self, token: str, photo_id: int, user_id: int, expires_at: datetime) -> None:
        """Stocke le hash du token en base pour validation et revocation."""
        token_hash = self._hash_token(token)
        media_token = MediaPublishToken(
            token_hash=token_hash,
            photo_id=photo_id,
            user_id=user_id,
            expires_at=expires_at,
            consumed=False,
        )
        self.db.add(media_token)
        await self.db.flush()

    async def _validate_token(self, token: str, correlation_id: Optional[str] = None) -> Optional[dict]:
        """Valide un token : verifie hash, expiration, et existence en base non consomme."""
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())[:8]

        token_hash = self._hash_token(token)
        logger.info(
            "_validate_token: correlation_id=%s, token_hash_prefix=%s",
            correlation_id, token_hash[:16],
        )
        result = await self.db.execute(
            select(MediaPublishToken).where(
                MediaPublishToken.token_hash == token_hash,
                MediaPublishToken.consumed == False,
                MediaPublishToken.expires_at >= datetime.now(timezone.utc),
            )
        )
        token_record = result.scalar_one_or_none()
        if not token_record:
            logger.warning(
                "_validate_token: correlation_id=%s, NO MATCHING DB RECORD: hash_prefix=%s",
                correlation_id, token_hash[:16]
            )
            return None

        logger.info(
            "_validate_token: correlation_id=%s, token VALID: photo_id=%s, user_id=%s, consumed=%s, expires_at=%s",
            correlation_id, token_record.photo_id, token_record.user_id, token_record.consumed, token_record.expires_at.isoformat(),
        )

        return {
            "photo_id": token_record.photo_id,
            "user_id": token_record.user_id,
            "token_record": token_record,
        }

    async def _consume_token(self, token_record: MediaPublishToken, correlation_id: Optional[str] = None) -> None:
        """Marque un token comme consomme (revocation)."""
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())[:8]
        logger.info(
            "_consume_token: correlation_id=%s, marking token consumed: photo_id=%s, token_id=%s",
            correlation_id, token_record.photo_id, token_record.id,
        )
        token_record.consumed = True
        await self.db.flush()

    def _detect_rejected_extension(self, filename: str) -> bool:
        """Detecte si l'extension du fichier est explicitement rejetee."""
        import os
        ext = os.path.splitext(filename or "")[1].lower()
        return ext in REJECTED_EXTENSIONS

    async def convert_heic_to_jpeg_if_needed(self, original_path: Path) -> Path:
        """Convertit une image HEIC/HEIF en JPEG si necessaire.

        Lit le fichier original, detecte son veritable format (via Pillow,
        pas seulement l'extension), applique l'orientation EXIF, aplatit la
        transparence sur fond blanc, et sauvegarde en JPEG qualite 90.

        Returns:
            Chemin vers le fichier JPEG (original si deja JPEG/PNG, ou
            fichier temporaire si conversion HEIC->JPEG effectuee).
        """
        if not _HEIC_SUPPORT:
            return original_path

        # Detecter le format reel via Pillow (pas seulement l'extension)
        try:
            with Image.open(original_path) as img:
                fmt = img.format
                if fmt not in ("HEIF", "HEIC"):
                    return original_path
        except Exception:
            # Fichier illisible ou pas une image : retourner tel quel
            return original_path

        # Conversion HEIC->JPEG (executee dans un thread pour ne pas bloquer)
        return await asyncio.to_thread(self._do_convert_heic_to_jpeg, original_path)

    def _do_convert_heic_to_jpeg(self, original_path: Path) -> Path:
        """Conversion HEIC->JPEG synchrone (a executer dans un thread via
        asyncio.to_thread)."""
        import os
        import tempfile

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg", prefix="heic_convert_")
        os.close(tmp_fd)

        try:
            with Image.open(original_path) as img:
                # Appliquer l'orientation EXIF
                img = ImageOps.exif_transpose(img)

                # Aplatir la transparence sur fond blanc
                if img.mode in ("RGBA", "LA") or (
                    img.mode == "P" and "transparency" in img.info
                ):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "RGBA":
                        background.paste(img, mask=img.split()[-1])
                    else:
                        background.paste(img)
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                img.save(tmp_path, "JPEG", quality=HEIC_TO_JPEG_QUALITY, optimize=True)
        except Exception:
            # Nettoyer le fichier temp en cas d'echec
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return Path(tmp_path)

    async def prepare_media_for_publish(
        self,
        photo_id: int,
        user_id: int,
        expires_in_seconds: int = 3600,
        size: str = "original",
        correlation_id: Optional[str] = None,
    ) -> MediaInfo:
        """Prepare un media pour publication Meta.

        Returns:
            MediaInfo avec url, mime_type, filename, is_video.

        Raises:
            MediaPublishError: si le media n'est pas valide pour Instagram
                (fichier introuvable, acces refuse, type MIME non supporte,
                extension rejetee, etc.)
        """
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())[:8]

        logger.info(
            "prepare_media_for_publish START: correlation_id=%s, photo_id=%s, user_id=%s, size=%s",
            correlation_id, photo_id, user_id, size,
        )

        # Recuperer la photo et verifier l'acces
        result = await self.db.execute(
            select(Photo).where(Photo.id == photo_id)
        )
        photo = result.scalar_one_or_none()
        if not photo:
            logger.error("prepare_media_for_publish: correlation_id=%s, photo_id=%s NOT FOUND", correlation_id, photo_id)
            raise MediaPublishError("Photo introuvable")

        logger.info(
            "prepare_media_for_publish: correlation_id=%s, photo found: mime_type=%s, filename=%s, owner_id=%s, is_deleted=%s",
            correlation_id, photo.mime_type, photo.original_filename, photo.owner_id, photo.is_deleted,
        )

        # Verifier que l'utilisateur a acces a cette photo
        if photo.owner_id != user_id and not photo.is_public:
            logger.error("prepare_media_for_publish: correlation_id=%s, ACCESS DENIED: photo.owner_id=%s != user_id=%s", correlation_id, photo.owner_id, user_id)
            raise MediaPublishError("Acces non autorise a ce media")

        # Verifier que le fichier n'est pas supprime
        if photo.is_deleted:
            logger.error("prepare_media_for_publish: correlation_id=%s, photo IS_DELETED", correlation_id)
            raise MediaPublishError("Ce media a ete supprime")

        # Verifier le type MIME
        mime_type = (photo.mime_type or "").lower()
        if mime_type not in SUPPORTED_MIME_TYPES:
            logger.error("prepare_media_for_publish: correlation_id=%s, UNSUPPORTED MIME: %s", correlation_id, mime_type)
            raise MediaPublishError(
                f"Type de media non supporte par Instagram : {mime_type or 'inconnu'}. "
                f"Types acceptes : {', '.join(sorted(SUPPORTED_MIME_TYPES))}"
            )

        # Verifier l'extension de fichier (rejet explicite HEIC, etc.)
        if self._detect_rejected_extension(photo.original_filename):
            logger.error("prepare_media_for_publish: correlation_id=%s, REJECTED EXTENSION: %s", correlation_id, photo.original_filename)
            raise MediaPublishError(
                f"Format de fichier non supporte par Instagram : {photo.original_filename}. "
                f"Utilisez un fichier JPEG, PNG ou MP4."
            )

        # Creer le token hex aleatoire
        token = self._create_hex_token()
        token_hash = self._hash_token(token)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)

        logger.info(
            "prepare_media_for_publish: correlation_id=%s, token created: len=%d, hash_prefix=%s, expires_at=%s",
            correlation_id, len(token), token_hash[:16], expires_at.isoformat(),
        )

        # Stocker le token en base
        await self._store_token(token, photo_id, user_id, expires_at)
        await self.db.commit()

        logger.info(
            "prepare_media_for_publish: correlation_id=%s, token stored in DB, photo_id=%s, user_id=%s",
            correlation_id, photo_id, user_id,
        )

        # Construire l'URL signee (taille originale pour la meilleure qualite)
        from app.core.config import get_settings
        settings = get_settings()
        base_url = settings.PUBLIC_URL.rstrip('/') if settings.PUBLIC_URL else "https://forgeai.design-ede.fr"

        # Passer la taille demandee ; "original" pour le fichier complet
        public_url = f"{base_url}/photos/{photo_id}/file?size={size}&meta_token={token}"
        safe_url = public_url.replace(token, "<MASKED>")

        is_video = mime_type in SUPPORTED_VIDEO_MIME_TYPES

        logger.info(
            "prepare_media_for_publish SUCCESS: correlation_id=%s, photo_id=%s, user_id=%s, mime_type=%s, "
            "is_video=%s, size=%s, expires_in=%ss, url=%s",
            correlation_id, photo_id, user_id, mime_type, is_video, size, expires_in_seconds, safe_url,
        )

        return MediaInfo(
            url=public_url,
            mime_type=mime_type,
            filename=photo.original_filename or f"photo_{photo_id}",
            is_video=is_video,
        )

    async def validate_media_token(self, token: str, correlation_id: Optional[str] = None) -> Optional[dict]:
        """Valide un token d'acces media (appele par l'endpoint /photos/{id}/file)."""
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())[:8]

        logger.info("validate_media_token: correlation_id=%s, START", correlation_id)
        validation = await self._validate_token(token, correlation_id=correlation_id)
        if not validation:
            logger.warning("validate_media_token: correlation_id=%s, validation FAILED", correlation_id)
            return None

        # Marquer le token comme consomme (single-use pour la publication Meta)
        await self._consume_token(validation["token_record"], correlation_id=correlation_id)

        logger.info("validate_media_token: correlation_id=%s, SUCCESS: photo_id=%s, user_id=%s", correlation_id, validation["photo_id"], validation["user_id"])

        return {
            "photo_id": validation["photo_id"],
            "user_id": validation["user_id"],
        }


async def get_media_publish_service(db: AsyncSession):
    return MediaPublishService(db)