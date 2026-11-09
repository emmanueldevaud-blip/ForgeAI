"""Configuration Meta/Instagram et chiffrement des jetons.

L'ancien système de connexion OAuth (Unified Login) a été supprimé
(jalon 3) : la publication s'appuie uniquement sur la configuration
Meta centralisée (meta_access_token + instagram_user_id).
"""

import base64
import hashlib
import logging
import uuid

import httpx
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

    async def _get_administration_module(self):
        from app.models.module import Module

        result = await self.db.execute(
            select(Module).where(Module.code == "administration")
        )
        module = result.scalar_one_or_none()
        if module is None:
            raise RuntimeError("Module Administration non trouve")
        return module

    async def initiate_meta_login(self) -> dict:
        """Genere un state OAuth CSRF pour le parcours Facebook Login for Business."""
        state = uuid.uuid4().hex
        module = await self._get_administration_module()
        from app.models.module import ModuleConfig

        existing = await self.db.execute(
            select(ModuleConfig).where(
                ModuleConfig.module_id == module.id,
                ModuleConfig.key == "meta_oauth_state",
            )
        )
        config = existing.scalar_one_or_none()
        if config is not None:
            config.value = state
        else:
            self.db.add(ModuleConfig(
                module_id=module.id,
                key="meta_oauth_state",
                value=state,
                value_type="string",
                is_secret=False,
            ))
        await self.db.commit()
        values = await self.load_meta_values()
        return {
            "state": state,
            "app_id": values["app_id"],
            "config_id": values["config_id"],
            "redirect_uri": values["redirect_uri"],
        }

    async def validate_meta_state(self, state: str) -> bool:
        """Valide et consomme un state OAuth (CSRF) du parcours Facebook Login for Business."""
        from app.models.module import ModuleConfig

        module = await self._get_administration_module()
        result = await self.db.execute(
            select(ModuleConfig).where(
                ModuleConfig.module_id == module.id,
                ModuleConfig.key == "meta_oauth_state",
            )
        )
        config = result.scalar_one_or_none()
        if config is None or not state or (config.value or "") != state:
            return False
        config.value = ""
        await self.db.commit()
        return True

    async def exchange_business_code(self, code: str) -> dict:
        """Echange le code OAuth (Facebook Login for Business) contre le jeton du
        Business Integration System User, puis recupere le contexte Meta."""
        values = await self.load_meta_values()
        base_url = f"https://graph.facebook.com/{values['api_version']}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{base_url}/oauth/access_token",
                params={
                    "grant_type": "authorization_code",
                    "client_id": values["app_id"],
                    "client_secret": values["app_secret"],
                    "code": code,
                    "redirect_uri": values["redirect_uri"],
                },
            )
            response.raise_for_status()
            token = response.json().get("access_token")
            me = await client.get(
                f"{base_url}/me",
                params={"fields": "id,client_business_id", "access_token": token},
            )
            me.raise_for_status()
            me_data = me.json()
            client_business_id = str(me_data.get("client_business_id") or "")
            ig_resp = await client.get(
                f"{base_url}/me/assigned_instagram_accounts",
                params={"fields": "id,username", "access_token": token},
            )
            ig_resp.raise_for_status()
            accounts = ig_resp.json().get("data") or []
        return {
            "access_token": token,
            "client_business_id": client_business_id,
            "instagram_accounts": accounts,
        }

    async def save_meta_credentials(self, token: str, client_business_id: str, instagram_user_id: str) -> None:
        """Enregistre le jeton chiffré et les identifiants Meta (source unique)."""
        module = await self._get_administration_module()
        encrypted = self._encrypt(token)
        values = {
            "meta_access_token": encrypted or "",
            "meta_client_business_id": client_business_id or "",
            "instagram_user_id": instagram_user_id or "",
        }
        from app.models.module import ModuleConfig

        for key, value in values.items():
            existing = await self.db.execute(
                select(ModuleConfig).where(
                    ModuleConfig.module_id == module.id,
                    ModuleConfig.key == key,
                )
            )
            config = existing.scalar_one_or_none()
            if config is not None:
                config.value = value
            else:
                self.db.add(ModuleConfig(
                    module_id=module.id,
                    key=key,
                    value=value,
                    value_type="string",
                    is_secret=key == "meta_access_token",
                ))
        await self.db.commit()

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
