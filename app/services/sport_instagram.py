"""Connexion Instagram Unified Login (Facebook Login for Business) et configuration Meta.

Flux d'authentification : Instagram Unified Login — autorisation sur
www.facebook.com/dialog/oauth avec le config_id de la configuration Meta,
echange du code sur graph.facebook.com, puis lecture des comptes Instagram
assignes (/me/assigned_instagram_accounts). Le jeton obtenu est un System
User Access Token (SUAT) rattache au business portfolio : il est stocke une
seule fois dans la configuration Meta centralisee (ModuleConfig meta_*).
Les fonctionnalites Meta Graph (diagnostic, publication) lisent la meme
configuration via load_meta_values().
"""

import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger(__name__)

STATE_TTL_MINUTES = 10

_META_CONFIG_KEYS = (
    "meta_app_id",
    "meta_app_secret",
    "meta_redirect_uri",
    "meta_config_id",
)

_CONNECTION_KEYS = (
    "meta_access_token",
    "meta_client_business_id",
    "instagram_user_id",
    "instagram_username",
)


def _raise_oauth_http_error(response: httpx.Response, contexte: str, redact: tuple[str, ...] = ()) -> None:
    """Leve HTTPException 502 sans URL ni secrets dans le message (logs propres)."""
    if 200 <= response.status_code < 300:
        return
    try:
        detail = (response.json().get("error") or {}).get("message") or ""
    except ValueError:
        detail = ""
    for value in redact:
        if value and len(value) > 4 and value in detail:
            detail = detail.replace(value, "***")
    message = f"{contexte} : HTTP {response.status_code}"
    if detail:
        message = f"{message} - {detail}"
    raise HTTPException(status_code=502, detail=message)


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

    @property
    def _dialog_url(self) -> str:
        """URL d'autorisation Instagram Unified Login (Facebook Login for Business)."""
        return "https://www.facebook.com/dialog/oauth"

    async def _get_administration_module(self):
        from app.models.module import Module

        result = await self.db.execute(
            select(Module).where(Module.code == "administration")
        )
        module = result.scalar_one_or_none()
        if module is None:
            raise RuntimeError("Module Administration non trouve")
        return module

    async def _load_administration_values(self, keys: tuple[str, ...]) -> dict[str, str]:
        """Cles du module administration presentes en base (valeur non vide)."""
        from app.models.module import Module, ModuleConfig

        result = await self.db.execute(
            select(ModuleConfig)
            .join(Module)
            .where(
                Module.code == "administration",
                ModuleConfig.key.in_(keys),
            )
        )
        return {
            config.key: config.value
            for config in result.scalars().all()
            if config.value is not None
        }

    async def load_meta_values(self) -> dict[str, str]:
        """Valeurs Meta : overlay DB (module administration) > environnement.

        Source unique de configuration du flux Unified Login et des
        fonctionnalites Graph. Les anciennes cles instagram_* ne sont plus lues.
        """
        configs = await self._load_administration_values(_META_CONFIG_KEYS)
        settings = get_settings()
        app_id = configs.get("meta_app_id") or settings.META_APP_ID
        app_secret = configs.get("meta_app_secret") or settings.META_APP_SECRET
        redirect_uri = configs.get("meta_redirect_uri") or settings.META_REDIRECT_URI
        config_id = configs.get("meta_config_id") or settings.META_CONFIG_ID
        return {
            "app_id": app_id or "",
            "app_secret": app_secret or "",
            "redirect_uri": redirect_uri or "",
            "config_id": config_id or "",
            "api_version": settings.META_API_VERSION or "v27.0",
            # Alias conserves pour les appelants existants (diagnostics admin)
            "meta_app_id": app_id or "",
            "meta_app_secret": app_secret or "",
            "meta_redirect_uri": redirect_uri or "",
            "meta_config_id": config_id or "",
        }

    async def build_authorization_url(self, user_id: int) -> tuple[str, str]:
        """Construit l'URL d'autorisation Unified Login et enregistre le state CSRF."""
        values = await self.load_meta_values()
        if not values["app_id"] or not values["app_secret"] or not values["config_id"] or not values["redirect_uri"]:
            raise HTTPException(
                status_code=503,
                detail="Connexion Meta non configurée (App ID, App Secret, Config ID ou callback manquant)",
            )

        from app.models.sport import SportInstagramOAuthState

        now = datetime.now(timezone.utc)
        # Nettoyage des states expires (borne par l'index expires_at).
        await self.db.execute(
            delete(SportInstagramOAuthState)
            .where(SportInstagramOAuthState.expires_at < now)
            .execution_options(synchronize_session=False)
        )

        state = secrets.token_urlsafe(32)
        self.db.add(SportInstagramOAuthState(
            state=state,
            user_id=user_id,
            expires_at=now + timedelta(minutes=STATE_TTL_MINUTES),
            consumed=False,
        ))
        await self.db.commit()

        params = {
            "client_id": values["app_id"],
            "config_id": values["config_id"],
            "redirect_uri": values["redirect_uri"],
            "response_type": "code",
            "state": state,
            "prompt": "login",
        }
        return f"{self._dialog_url}?{urlencode(params)}", state

    async def consume_state(self, state: str) -> int | None:
        """Consomme atomiquement un state OAuth (CSRF) et retourne le user_id.

        L'UPDATE + commit est effectue AVANT tout appel reseau (echange du code).
        """
        if not state:
            return None
        from app.models.sport import SportInstagramOAuthState

        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(SportInstagramOAuthState)
            .where(
                SportInstagramOAuthState.state == state,
                SportInstagramOAuthState.consumed == False,
                SportInstagramOAuthState.expires_at >= now,
            )
            .values(consumed=True)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            await self.db.rollback()
            return None
        row = await self.db.execute(
            select(SportInstagramOAuthState).where(SportInstagramOAuthState.state == state)
        )
        oauth_state = row.scalar_one_or_none()
        user_id = oauth_state.user_id if oauth_state is not None else None
        if oauth_state is not None:
            await self.db.delete(oauth_state)
        await self.db.commit()
        return user_id

    async def exchange_business_code(self, code: str) -> dict:
        """Echange le code OAuth (Instagram Unified Login) contre le System User
        Access Token, puis lit le client business ID et les comptes Instagram
        assignes du jeton.

        Appel serveur sur graph.facebook.com avec les identifiants Meta de
        l'application (jamais les identifiants Instagram d'un autre onglet).
        """
        values = await self.load_meta_values()
        if not values["app_id"] or not values["app_secret"] or not values["redirect_uri"]:
            raise HTTPException(
                status_code=503,
                detail="Connexion Meta non configurée (App ID, App Secret ou callback manquant)",
            )
        base_url = f"https://graph.facebook.com/{values['api_version']}"
        redact = (values["app_secret"], code)

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
            _raise_oauth_http_error(response, "Echange du code OAuth Meta", redact=redact)
            token = response.json().get("access_token")
            if not token:
                raise HTTPException(
                    status_code=502,
                    detail="Echange du code OAuth Meta : jeton d'accès absent de la réponse",
                )

            me_response = await client.get(
                f"{base_url}/me",
                params={"fields": "id,client_business_id", "access_token": token},
            )
            _raise_oauth_http_error(me_response, "Lecture /me Meta", redact=(token,))
            me_data = me_response.json()
            client_business_id = str(me_data.get("client_business_id") or "")

            ig_response = await client.get(
                f"{base_url}/me/assigned_instagram_accounts",
                params={"fields": "id,username", "access_token": token},
            )
            _raise_oauth_http_error(ig_response, "Lecture des comptes Instagram assignes", redact=(token,))
            accounts = ig_response.json().get("data") or []

        return {
            "access_token": token,
            "client_business_id": client_business_id,
            "instagram_accounts": accounts,
        }

    async def save_meta_credentials(
        self,
        token: str,
        client_business_id: str,
        instagram_user_id: str,
        username: str | None = None,
    ) -> None:
        """Enregistre le jeton SUAT chiffre et le contexte Meta (source unique)."""
        module = await self._get_administration_module()
        from app.models.module import ModuleConfig

        values = {
            "meta_access_token": self._encrypt(token) or "",
            "meta_client_business_id": client_business_id or "",
            "instagram_user_id": instagram_user_id or "",
            "instagram_username": username or "",
        }
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

    async def clear_meta_credentials(self) -> bool:
        """Retire le jeton SUAT et le contexte de connexion (configuration conservee).

        Retourne True si un jeton etait enregistre avant la deconnexion.
        """
        module = await self._get_administration_module()
        from app.models.module import ModuleConfig

        result = await self.db.execute(
            select(ModuleConfig).where(
                ModuleConfig.module_id == module.id,
                ModuleConfig.key.in_(_CONNECTION_KEYS),
            )
        )
        configs = result.scalars().all()
        had_token = any(c.key == "meta_access_token" and c.value for c in configs)
        for config in configs:
            config.value = ""
        await self.db.commit()
        return had_token

    async def connection_status(self) -> dict:
        """Statut de la connexion Meta (configuration + jeton SUAT centralise)."""
        configs = await self._load_administration_values(_META_CONFIG_KEYS + _CONNECTION_KEYS)
        settings = get_settings()
        app_id = configs.get("meta_app_id") or settings.META_APP_ID
        app_secret = configs.get("meta_app_secret") or settings.META_APP_SECRET
        redirect_uri = configs.get("meta_redirect_uri") or settings.META_REDIRECT_URI
        config_id = configs.get("meta_config_id") or settings.META_CONFIG_ID
        token = configs.get("meta_access_token")
        instagram_user_id = configs.get("instagram_user_id")
        return {
            "configured": bool(app_id and app_secret and config_id and redirect_uri),
            "connected": bool(token and instagram_user_id),
            "instagram_user_id": instagram_user_id,
            "client_business_id": configs.get("meta_client_business_id"),
            "username": configs.get("instagram_username"),
        }
