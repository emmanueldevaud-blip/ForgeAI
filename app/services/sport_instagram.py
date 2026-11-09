"""Configuration Meta/Instagram et chiffrement des jetons.

L'ancien système de connexion OAuth (Unified Login) a été supprimé
(jalon 3) : la publication s'appuie uniquement sur la configuration
Meta centralisée (meta_access_token + instagram_user_id).
"""

import base64
import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _fernet():
    from cryptography.fernet import Fernet

    secret = get_settings().SECRET_KEY.encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))


def _encrypt_token(token: str | None) -> str | None:
    if not token:
        return None
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def _decrypt_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        from cryptography.fernet import InvalidToken

        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except Exception:
        return None


class SportInstagramConnectService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _encrypt(self, token: str | None) -> str | None:
        return _encrypt_token(token)

    def _decrypt(self, token: str | None) -> str | None:
        return _decrypt_token(token)

    async def load_meta_values(self) -> dict[str, str]:
        """Valeurs Meta : overlay DB (module administration) > environnement.

        L'onglet Meta est la source unique de configuration : les clés meta_*
        priment sur les clés instagram_* (héritées de l'ancien onglet).
        """
        from app.models.module import Module, ModuleConfig

        result = await self.db.execute(
            select(ModuleConfig)
            .join(Module)
            .where(
                Module.code == "administration",
                ModuleConfig.key.in_((
                    "meta_app_id",
                    "meta_app_secret",
                    "meta_redirect_uri",
                    "meta_config_id",
                    "instagram_app_id",
                    "instagram_app_secret",
                    "instagram_redirect_uri",
                    "instagram_api_version",
                )),
            )
        )
        configs = {
            config.key: config.value
            for config in result.scalars().all()
            if config.value is not None
        }
        settings = get_settings()
        app_id = (
            configs.get("meta_app_id")
            or configs.get("instagram_app_id")
            or settings.META_APP_ID
            or settings.INSTAGRAM_APP_ID
        )
        app_secret = (
            configs.get("meta_app_secret")
            or configs.get("instagram_app_secret")
            or settings.META_APP_SECRET
            or settings.INSTAGRAM_APP_SECRET
        )
        redirect_uri = (
            configs.get("meta_redirect_uri")
            or configs.get("instagram_redirect_uri")
            or settings.META_REDIRECT_URI
            or settings.INSTAGRAM_REDIRECT_URI
        )
        config_id = configs.get("meta_config_id") or settings.META_CONFIG_ID
        api_version = configs.get("instagram_api_version") or settings.INSTAGRAM_API_VERSION
        return {
            "app_id": app_id,
            "app_secret": app_secret,
            "redirect_uri": redirect_uri,
            "config_id": config_id,
            "api_version": api_version,
            # Alias conservés pour les appelants existants
            "meta_app_id": configs.get("meta_app_id") or settings.META_APP_ID,
            "meta_app_secret": configs.get("meta_app_secret") or settings.META_APP_SECRET,
            "meta_redirect_uri": configs.get("meta_redirect_uri") or settings.META_REDIRECT_URI,
            "instagram_app_id": app_id,
            "instagram_app_secret": app_secret,
            "instagram_redirect_uri": redirect_uri,
            "instagram_api_version": api_version,
        }
