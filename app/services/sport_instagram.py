"""Connexion Instagram Login (voie B) et configuration Meta.

Flux d'authentification : Instagram Login individuel — autorisation sur
www.instagram.com, echange du code sur api.instagram.com (POST multipart).
Les fonctionnalites Meta Graph (diagnostic, publication) lisent la
configuration Meta centralisee (meta_*) via load_meta_values().
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

DEFAULT_INSTAGRAM_SCOPES = "instagram_business_basic,instagram_business_content_publish"
STATE_TTL_MINUTES = 10


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
        """URL d'autorisation Instagram Login."""
        return "https://www.instagram.com/oauth/authorize"

    @property
    def _token_url(self) -> str:
        """URL d'echange code -> token (Instagram Login)."""
        return "https://api.instagram.com/oauth/access_token"

    @property
    def _graph_instagram_url(self) -> str:
        """URL de base Graph Instagram (token longue duree + profil)."""
        return "https://graph.instagram.com"

    async def load_instagram_login_values(self) -> dict[str, str]:
        """Identifiants Instagram Login : overlay DB (module administration) > environnement.

        Uniquement les cles instagram_* (aucun repli meta_* : le flux
        d'authentification est separe de la configuration Meta Graph).
        """
        from app.models.module import Module, ModuleConfig

        result = await self.db.execute(
            select(ModuleConfig)
            .join(Module)
            .where(
                Module.code == "administration",
                ModuleConfig.key.in_((
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
        app_id = configs.get("instagram_app_id") or settings.INSTAGRAM_APP_ID
        app_secret = configs.get("instagram_app_secret") or settings.INSTAGRAM_APP_SECRET
        redirect_uri = configs.get("instagram_redirect_uri") or settings.INSTAGRAM_REDIRECT_URI
        api_version = configs.get("instagram_api_version") or settings.INSTAGRAM_API_VERSION
        return {
            "app_id": app_id or "",
            "app_secret": app_secret or "",
            "redirect_uri": redirect_uri or "",
            "api_version": api_version or "v27.0",
            "scopes": DEFAULT_INSTAGRAM_SCOPES,
            "instagram_app_id": app_id or "",
            "instagram_app_secret": app_secret or "",
            "instagram_redirect_uri": redirect_uri or "",
            "instagram_api_version": api_version or "v27.0",
        }

    async def build_authorization_url(self, user_id: int) -> tuple[str, str]:
        """Construit l'URL d'autorisation Instagram Login et enregistre le state CSRF."""
        values = await self.load_instagram_login_values()
        if not values["app_id"] or not values["app_secret"] or not values["redirect_uri"]:
            raise HTTPException(
                status_code=503,
                detail="Instagram Login non configuré (App ID, App Secret ou callback manquant)",
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
            "redirect_uri": values["redirect_uri"],
            "response_type": "code",
            "state": state,
            "scope": values["scopes"],
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

    async def exchange_instagram_code(self, code: str) -> dict:
        """Echange le code OAuth Instagram Login contre un jeton (POST multipart).

        Etapes : echange sur api.instagram.com (multipart), conversion en jeton
        longue duree sur graph.instagram.com (best effort), lecture du profil
        Instagram (best effort). Le court terme n'est jamais abandonne si la
        conversion echoue (repli conservateur).
        """
        values = await self.load_instagram_login_values()
        if not values["app_id"] or not values["app_secret"] or not values["redirect_uri"]:
            raise HTTPException(
                status_code=503,
                detail="Instagram Login non configuré (App ID, App Secret ou callback manquant)",
            )

        files = {
            "grant_type": (None, "authorization_code"),
            "client_id": (None, values["app_id"]),
            "client_secret": (None, values["app_secret"]),
            "redirect_uri": (None, values["redirect_uri"]),
            "code": (None, code),
        }
        redact = (values["app_secret"], code)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self._token_url, files=files)
            _raise_oauth_http_error(response, "Echange du code OAuth Instagram", redact=redact)
            token_data = response.json()
            short_token = token_data.get("access_token")
            short_expires = token_data.get("expires_in")
            if not short_token:
                raise HTTPException(
                    status_code=502,
                    detail="Echange du code OAuth Instagram : jeton d'accès absent de la réponse",
                )

            # Conversion court terme -> longue duree (best effort).
            long_token = None
            long_expires = None
            try:
                long_response = await client.get(
                    f"{self._graph_instagram_url}/{values['api_version']}/access_token",
                    params={"grant_type": "ig_refresh_token", "access_token": short_token},
                )
                if long_response.status_code == 200:
                    long_data = long_response.json()
                    long_token = long_data.get("access_token")
                    long_expires = long_data.get("expires_in")
                else:
                    logger.warning(
                        "Conversion Instagram token longue duree refusée (HTTP %s)",
                        long_response.status_code,
                    )
            except httpx.HTTPError:
                logger.warning("Conversion Instagram token longue duree : erreur reseau")

            token = long_token or short_token
            expires_in = long_expires or short_expires

            # Profil Instagram (best effort).
            ig_account_id = None
            ig_username = None
            try:
                me_response = await client.get(
                    f"{self._graph_instagram_url}/{values['api_version']}/me",
                    params={"fields": "id,username", "access_token": token},
                )
                if me_response.status_code == 200:
                    me_data = me_response.json()
                    ig_account_id = str(me_data.get("id") or "") or None
                    ig_username = me_data.get("username")
            except httpx.HTTPError:
                logger.warning("Profil Instagram indisponible : erreur reseau")

        return {
            "access_token": token,
            "expires_in": expires_in,
            "instagram_business_account_id": ig_account_id,
            "username": ig_username,
        }

    async def save_connection(
        self,
        user_id: int,
        *,
        access_token: str,
        expires_in: int | None,
        instagram_business_account_id: str | None,
        username: str | None = None,
        scopes: str | None = None,
    ) -> None:
        """Cree ou met a jour la connexion Instagram active de l'utilisateur."""
        from app.models.sport import SportInstagramConnection

        result = await self.db.execute(
            select(SportInstagramConnection).where(SportInstagramConnection.user_id == user_id)
        )
        connection = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        encrypted = _encrypt_token(access_token)
        metadata = {"username": username} if username else {}

        if connection is not None:
            connection.instagram_business_account_id = (
                instagram_business_account_id or connection.instagram_business_account_id
            )
            connection.auth_type = "instagram_login"
            connection.encrypted_access_token = encrypted
            connection.encrypted_long_lived_token = encrypted
            connection.status = "active"
            connection.scopes = scopes or DEFAULT_INSTAGRAM_SCOPES
            connection.token_type = "bearer"
            connection.expires_in = expires_in
            connection.obtained_at = now
            connection.metadata_json = metadata
        else:
            self.db.add(SportInstagramConnection(
                user_id=user_id,
                instagram_business_account_id=instagram_business_account_id,
                auth_type="instagram_login",
                encrypted_access_token=encrypted,
                encrypted_long_lived_token=encrypted,
                status="active",
                scopes=scopes or DEFAULT_INSTAGRAM_SCOPES,
                token_type="bearer",
                expires_in=expires_in,
                obtained_at=now,
                metadata_json=metadata,
            ))
        await self.db.commit()

    async def get_connection(self, user_id: int):
        """Connexion Instagram de l'utilisateur (tous statuts)."""
        from app.models.sport import SportInstagramConnection

        result = await self.db.execute(
            select(SportInstagramConnection).where(SportInstagramConnection.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def disconnect(self, user_id: int) -> bool:
        """Desactive la connexion Instagram de l'utilisateur (isole par utilisateur)."""
        connection = await self.get_connection(user_id)
        if connection is None or connection.status != "active":
            return False
        connection.status = "disconnected"
        await self.db.commit()
        return True

    async def refresh_connection_token(self, connection) -> str | None:
        """Renouvelle le jeton longue duree d'une connexion Instagram Login."""
        token = _decrypt_token(
            getattr(connection, "encrypted_long_lived_token", None)
            or getattr(connection, "encrypted_access_token", None)
        )
        if not token:
            return None
        values = await self.load_instagram_login_values()
        version = values["api_version"]
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{self._graph_instagram_url}/{version}/refresh_access_token",
                    params={"grant_type": "ig_refresh_token", "access_token": token},
                )
        except httpx.HTTPError:
            logger.warning("Renouvellement du jeton Instagram : erreur reseau")
            return None
        if response.status_code != 200:
            logger.warning(
                "Renouvellement du jeton Instagram refuse (HTTP %s)", response.status_code
            )
            return None
        try:
            new_token = response.json().get("access_token")
            new_expires = response.json().get("expires_in")
        except ValueError:
            return None
        if not new_token:
            return None
        connection.encrypted_access_token = _encrypt_token(new_token)
        connection.encrypted_long_lived_token = _encrypt_token(new_token)
        connection.expires_in = new_expires or connection.expires_in
        connection.obtained_at = datetime.now(timezone.utc)
        await self.db.commit()
        return new_token

    async def load_meta_values(self) -> dict[str, str]:
        """Valeurs Meta : overlay DB (module administration) > environnement.

        L'onglet Meta est la source unique de configuration : les cles meta_*
        priment sur les cles instagram_* (heritees de l'ancien onglet).
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
