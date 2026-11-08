"""Service de connexion Instagram (Unified Login / Facebook Login for Business)."""

import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import httpx
from httpx import HTTPStatusError
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.sport import SportAthlete, SportInstagramConnection, SportInstagramOAuthState
from app.models.user import User

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

    async def get_connection(self, user_id: int) -> SportInstagramConnection | None:
        result = await self.db.execute(
            select(SportInstagramConnection).where(
                SportInstagramConnection.user_id == user_id,
                SportInstagramConnection.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def _get_athlete(self, user_id: int) -> SportAthlete | None:
        result = await self.db.execute(
            select(SportAthlete)
            .where(SportAthlete.user_id == user_id)
            .order_by(SportAthlete.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @property
    def _base_url(self) -> str:
        """URL de base Graph API (Meta) utilisée pour l'OAuth et la publication."""
        return f"https://graph.facebook.com/{get_settings().META_API_VERSION}"

    @property
    def _dialog_url(self) -> str:
        """URL d'autorisation Unified Login (Facebook Login for Business)."""
        return "https://www.facebook.com/dialog/oauth"

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

    async def _app_credentials(self) -> tuple[str, str, str]:
        """Identifiants Meta : app_id, app_secret, redirect_uri."""
        values = await self.load_meta_values()
        if not values["instagram_app_id"] or not values["instagram_app_secret"]:
            raise HTTPException(
                status_code=503,
                detail="Unified Login non configuré (App ID ou App Secret manquant)",
            )
        redirect_uri = values["instagram_redirect_uri"] or "http://localhost:8000/sport/publications/meta/callback"
        return values["instagram_app_id"], values["instagram_app_secret"], redirect_uri

    async def _config_id(self) -> str:
        """Configuration ID Facebook Login for Business (Unified Login)."""
        values = await self.load_meta_values()
        config_id = values.get("config_id")
        if not config_id:
            raise HTTPException(
                status_code=503,
                detail="Unified Login non configuré (Configuration ID manquant)",
            )
        return config_id

    async def build_authorization_url(
        self, athlete_id: int, user_id: int
    ) -> tuple[str, str]:
        """Construit l'URL d'autorisation Unified Login.

        Les permissions sont définies par la configuration (config_id) ;
        aucun paramètre scope n'est envoyé.
        """
        app_id, _, redirect_uri = await self._app_credentials()
        config_id = await self._config_id()
        import secrets

        state = secrets.token_urlsafe(32)
        oauth_state = SportInstagramOAuthState(
            state=state,
            user_id=user_id,
            athlete_id=athlete_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            consumed=False,
        )
        self.db.add(oauth_state)
        await self.db.flush()
        await self.db.commit()
        logger.debug(
            "STATE_CREATED: state_hash=%s, expires_at=%s, consumed=%s",
            hashlib.sha256(state.encode()).hexdigest()[:16],
            oauth_state.expires_at,
            oauth_state.consumed,
        )
        from urllib.parse import urlencode

        params = {
            "client_id": app_id,
            "config_id": config_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "display": "popup",
            "prompt": "login",
        }
        return f"{self._dialog_url}?{urlencode(params)}", state

    async def exchange_code(
        self, code: str, redirect_uri: str | None, state: str
    ) -> SportInstagramConnection:
        """Exchange OAuth code for Instagram connection (Unified Login flow).

        Two-phase atomic flow:
        1. Transaction A: Validate and consume state atomically (UPDATE + commit)
        2. External calls: Exchange code with Meta, resolve Instagram accounts
        3. Transaction B: Create/update connection (commit or rollback)
        """
        # 1. Transaction A: Validate and consume state atomically
        from sqlalchemy import update
        now = datetime.now(timezone.utc)

        stmt = (
            update(SportInstagramOAuthState)
            .where(
                SportInstagramOAuthState.state == state,
                SportInstagramOAuthState.consumed == False,
                SportInstagramOAuthState.expires_at >= now,
            )
            .values(consumed=True)
        )
        result = await self.db.execute(stmt)
        state_hash = hashlib.sha256(state.encode()).hexdigest()[:16]
        logger.debug(
            "STATE_VALIDATION: state_hash=%s, rowcount=%s, callback_at=%s",
            state_hash, result.rowcount, now,
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=400, detail="Etat OAuth invalide ou expire")

        # Retrieve state data before it's deleted
        q = await self.db.execute(
            select(SportInstagramOAuthState).where(SportInstagramOAuthState.state == state)
        )
        oauth_state = q.scalar_one()
        athlete_id = oauth_state.athlete_id
        user_id = oauth_state.user_id

        # Commit state consumption immediately (Transaction A)
        await self.db.delete(oauth_state)
        await self.db.flush()
        await self.db.commit()

        # 2. External calls: Exchange code with Meta (no DB lock held)
        app_id, app_secret, default_redirect = await self._app_credentials()
        config_id = await self._config_id()
        redirect_to = redirect_uri or default_redirect
        if not redirect_to:
            raise HTTPException(status_code=503, detail="Instagram redirect_uri non configure")

        granted_scopes = None
        async with httpx.AsyncClient(timeout=20.0) as client:
            # 2a. Échange code -> token court (Facebook Login for Business)
            try:
                token_response = await client.get(
                    f"{self._base_url}/oauth/access_token",
                    params={
                        "grant_type": "authorization_code",
                        "client_id": app_id,
                        "client_secret": app_secret,
                        "redirect_uri": redirect_to,
                        "code": code,
                    },
                )
                token_response.raise_for_status()
                token_data = token_response.json()
                short_token = token_data.get("access_token")
                granted_scopes = token_data.get("scope")
            except HTTPStatusError as exc:
                raise HTTPException(
                    status_code=exc.response.status_code,
                    detail=f"Meta token exchange failed: {exc.response.text}"
                ) from exc

            # 2b. Échange court terme -> token longue durée (60 jours)
            long_token = None
            try:
                long_response = await client.get(
                    f"{self._base_url}/oauth/access_token",
                    params={
                        "grant_type": "fb_exchange_long_lived",
                        "client_id": app_id,
                        "client_secret": app_secret,
                        "fb_exchange_long_lived_token": short_token,
                    },
                )
                long_response.raise_for_status()
                long_token_data = long_response.json()
                long_token = long_token_data.get("access_token")
                # Facebook retourne aussi expires_in pour le token long-lived
                long_expires_in = long_token_data.get("expires_in")
                granted_scopes = long_token_data.get("scope") or granted_scopes
            except HTTPStatusError as exc:
                logger.warning(
                    "Meta long-lived token exchange failed (HTTP %s)", exc.response.status_code
                )
                long_token = None
                long_expires_in = None
            except httpx.HTTPError as exc:
                logger.warning("Meta long-lived token exchange network error", error=str(exc))
                long_token = None
                long_expires_in = None

            if long_token:
                long_lived_token = long_token
                expires_in_value = long_expires_in
            else:
                # Ne JAMAIS utiliser le short-lived token comme solution de repli.
                long_lived_token = None
                short_token = None
                expires_in_value = None

            obtained_at = datetime.now(timezone.utc)

            # 2c. Comptes Instagram assignés au token.
            # Unified Login : /me retourne le system user, pas le compte Instagram.
            ig_account_id = None
            ig_username = None
            access_for_lookup = long_lived_token or short_token
            if access_for_lookup:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as fetch_client:
                        me_resp = await fetch_client.get(
                            f"{self._base_url}/me/assigned_instagram_accounts",
                            params={
                                "fields": "id,username",
                                "access_token": access_for_lookup,
                            },
                        )
                        if me_resp.status_code == 200:
                            accounts = me_resp.json().get("data") or []
                            if accounts:
                                ig_account_id = str(accounts[0].get("id") or "")
                                ig_username = accounts[0].get("username")
                                if len(accounts) > 1:
                                    logger.info(
                                        "Multiple Instagram accounts assigned, using first: %s",
                                        ig_account_id,
                                    )
                except httpx.HTTPError as exc:
                    logger.warning("Instagram accounts lookup failed", error=str(exc))
                except Exception as exc:
                    logger.warning("Unexpected error looking up Instagram accounts", error=str(exc))

        # 3. Transaction B: Create/update connection
        try:
            existing = await self.get_connection(user_id)
            meta_dict = {}
            if ig_username:
                meta_dict["username"] = ig_username
            meta_dict["config_id"] = config_id
            token_to_store = long_lived_token or short_token

            if existing is not None:
                existing.instagram_business_account_id = ig_account_id or existing.instagram_business_account_id
                existing.auth_type = "unified_login"
                existing.encrypted_access_token = _encrypt_token(token_to_store)
                existing.encrypted_long_lived_token = _encrypt_token(long_lived_token or short_token)
                existing.status = "active"
                existing.token_type = "bearer"
                existing.expires_in = expires_in_value
                existing.obtained_at = obtained_at
                existing.metadata_json = meta_dict
                if granted_scopes:
                    existing.scopes = granted_scopes
                existing.updated_at = datetime.now(timezone.utc)
                connection = existing
            else:
                connection = SportInstagramConnection(
                    user_id=user_id,
                    athlete_id=athlete_id,
                    instagram_business_account_id=ig_account_id,
                    auth_type="unified_login",
                    status="active",
                    encrypted_access_token=_encrypt_token(token_to_store),
                    encrypted_long_lived_token=_encrypt_token(long_lived_token or short_token),
                    token_type="bearer",
                    expires_in=expires_in_value,
                    obtained_at=obtained_at,
                    metadata_json=meta_dict,
                    scopes=granted_scopes,
                )
                self.db.add(connection)

            await self.db.flush()
            await self.db.commit()
            return connection
        except Exception:
            await self.db.rollback()
            raise

    async def disconnect(self, user_id: int) -> bool:
        connection = await self.get_connection(user_id)
        if connection is None:
            return False
        connection.status = "revoked"
        connection.encrypted_access_token = None
        connection.encrypted_long_lived_token = None
        connection.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True
