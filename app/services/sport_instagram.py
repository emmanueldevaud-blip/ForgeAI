"""Service de connexion Meta (Instagram Business) pour les statistiques Insights."""

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

DEFAULT_META_SCOPES = "instagram_business_basic"

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
        return f"https://graph.facebook.com/{get_settings().META_API_VERSION}"

    @property
    def _dialog_url(self) -> str:
        return f"https://www.facebook.com/{get_settings().META_API_VERSION}/dialog/oauth"

    async def load_meta_values(self) -> dict[str, str]:
        """Valeurs Meta : overlay DB (module administration) > environnement."""
        from app.models.module import Module, ModuleConfig

        result = await self.db.execute(
            select(ModuleConfig)
            .join(Module)
            .where(
                Module.code == "administration",
                ModuleConfig.key.in_(("meta_app_id", "meta_app_secret", "meta_redirect_uri", "meta_config_id")),
            )
        )
        configs = {
            config.key: config.value
            for config in result.scalars().all()
            if config.value is not None
        }
        settings = get_settings()
        return {
            "app_id": configs.get("meta_app_id") or settings.META_APP_ID,
            "app_secret": configs.get("meta_app_secret") or settings.META_APP_SECRET,
            "redirect_uri": configs.get("meta_redirect_uri") or settings.META_REDIRECT_URI,
            "config_id": configs.get("meta_config_id") or settings.META_CONFIG_ID,
        }

    async def _app_credentials(self) -> tuple[str, str, str, str]:
        values = await self.load_meta_values()
        if not values["app_id"] or not values["app_secret"]:
            raise HTTPException(status_code=503, detail="Meta OAuth non configuré (App ID ou App Secret manquant)")
        redirect_uri = values["redirect_uri"] or "http://localhost:8000/sport/publications/meta/callback"
        return values["app_id"], values["app_secret"], redirect_uri, values["config_id"]

    async def build_authorization_url(self, athlete_id: int, user_id: int, scopes: str | None = None) -> tuple[str, str]:
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
        logger.debug(f"STATE_CREATED: state_hash={hashlib.sha256(state.encode()).hexdigest()[:16]}, expires_at={oauth_state.expires_at}, consumed={oauth_state.consumed}")
        from urllib.parse import urlencode

        params = {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
        if config_id:
            params["config_id"] = config_id
            params["override_default_response_type"] = "true"
        else:
            params["scope"] = scopes or DEFAULT_META_SCOPES
        return f"{self._dialog_url}?{urlencode(params)}", state

    async def exchange_code(self, code: str, redirect_uri: str | None, state: str) -> SportInstagramConnection:
        """Exchange OAuth code for Instagram connection.

        Two-phase atomic flow:
        1. Transaction A: Validate and consume state atomically (UPDATE + commit)
        2. External calls: Exchange code with Meta, fetch Instagram account
        3. Transaction B: Create/update connection (commit or rollback)
        """
        # 1. Transaction A: Validate and consume state atomically
        from sqlalchemy import update, func
        now = datetime.now(timezone.utc)

        # Atomic consumption: UPDATE with rowcount check
        stmt = (
            update(SportInstagramOAuthState)
            .where(
                SportInstagramOAuthState.state == state,
                SportInstagramOAuthState.consumed == False,
                SportInstagramOAuthState.expires_at >= func.utc_timestamp(),
            )
            .values(consumed=True)
        )
        result = await self.db.execute(stmt)
        state_hash = hashlib.sha256(state.encode()).hexdigest()[:16]
        logger.debug(f"STATE_VALIDATION: state_hash={state_hash}, rowcount={result.rowcount}, callback_at={now}, consumed_ok={SportInstagramOAuthState.consumed == False}, not_expired={SportInstagramOAuthState.expires_at >= func.utc_timestamp()}")
        if result.rowcount != 1:
            raise HTTPException(status_code=400, detail="Etat OAuth invalide ou expire")

        # Retrieve state data before it's deleted
        q = await self.db.execute(
            select(SportInstagramOAuthState).where(SportInstagramOAuthState.state == state)
        )
        oauth_state = q.scalar_one()
        athlete_id = oauth_state.athlete_id
        user_id = oauth_state.user_id
        logger.debug(f"STATE_FOUND: athlete_id={athlete_id}, user_id={user_id}, stored_consumed={oauth_state.consumed}, stored_expires_at={oauth_state.expires_at}")

        # Commit state consumption immediately (Transaction A)
        await self.db.delete(oauth_state)
        await self.db.flush()
        await self.db.commit()
        logger.debug(f"STATE_CONSUMED: state_hash={state_hash}, deleted_from_db=True")

        # 2. External calls: Exchange code with Meta (no DB lock held)
        app_id, app_secret, default_redirect, _ = await self._app_credentials()
        redirect_to = redirect_uri or default_redirect
        if not redirect_to:
            raise HTTPException(status_code=503, detail="Meta OAuth redirect_uri non configure")

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                token_response = await client.post(
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
            except HTTPStatusError as exc:
                raise HTTPException(
                    status_code=exc.response.status_code,
                    detail=f"Meta token exchange failed: {exc.response.text}"
                ) from exc

            long_token = None
            try:
                long_response = await client.get(
                    f"{self._base_url}/oauth/access_token",
                    params={
                        "grant_type": "fb_exchange_long_lived",
                        "client_id": app_id,
                        "client_secret": app_secret,
                        "redirect_uri": redirect_to,
                        "fb_exchange_long_lived_token": short_token,
                    },
                )
                long_response.raise_for_status()
                long_token = long_response.json().get("access_token")
            except HTTPStatusError as exc:
                logger.warning("Meta long-lived token exchange failed", status=exc.response.status_code)
                long_token = None
            except httpx.HTTPError as exc:
                logger.warning("Meta long-lived token exchange network error", error=str(exc))
                long_token = None

            if long_token:
                token_data = long_response.json()

        long_lived_token = long_token or short_token
        obtained_at = datetime.now(timezone.utc)

        # 4. Fetch Instagram Business account
        ig_account_id = None
        ig_username = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as fetch_client:
                assigned_resp = await fetch_client.get(
                    f"{self._base_url}/me/assigned_instagram_accounts",
                    params={
                        "fields": "id,username",
                        "access_token": long_lived_token,
                    },
                )
                if assigned_resp.status_code == 200:
                    for acct in assigned_resp.json().get("data", []):
                        if acct.get("id"):
                            ig_account_id = str(acct["id"])
                            ig_username = acct.get("username")
                            break
                if not ig_account_id:
                    acc_resp = await fetch_client.get(
                        f"{self._base_url}/me/accounts",
                        params={
                            "fields": "id,name,instagram_business_account{id,username}",
                            "access_token": long_lived_token,
                        },
                    )
                    if acc_resp.status_code == 200:
                        for page in acc_resp.json().get("data", []):
                            ig = page.get("instagram_business_account")
                            if ig and ig.get("id"):
                                ig_account_id = str(ig["id"])
                                ig_username = ig.get("username")
                                break
                if not ig_account_id:
                    me_resp = await fetch_client.get(
                        f"{self._base_url}/me",
                        params={"fields": "id,username", "access_token": long_lived_token},
                    )
                    if me_resp.status_code == 200:
                        me_data = me_resp.json()
                        ig_account_id = str(me_data.get("id") or "")
                        ig_username = me_data.get("username")
        except httpx.HTTPError as exc:
            logger.warning("Instagram account fetch failed", error=str(exc))
        except Exception as exc:
            logger.warning("Unexpected error fetching Instagram account", error=str(exc))

        # 4. Transaction B: Create/update connection
        try:
            existing = await self.get_connection(user_id)
            meta_dict = {"username": ig_username} if ig_username else {}
            long_lived_token = long_token or short_token

            if existing is not None:
                existing.instagram_business_account_id = ig_account_id or existing.instagram_business_account_id
                existing.encrypted_access_token = _encrypt_token(long_lived_token or short_token)
                existing.encrypted_long_lived_token = _encrypt_token(long_token or short_token)
                existing.status = "active"
                existing.token_type = token_data.get("token_type") or "bearer"
                existing.expires_in = token_data.get("expires_in")
                existing.obtained_at = datetime.now(timezone.utc)
                existing.metadata_json = meta_dict
                existing.updated_at = datetime.now(timezone.utc)
                connection = existing
            else:
                connection = SportInstagramConnection(
                    user_id=user_id,
                    athlete_id=athlete_id,
                    instagram_business_account_id=ig_account_id,
                    status="active",
                    encrypted_access_token=_encrypt_token(long_lived_token or short_token),
                    encrypted_long_lived_token=_encrypt_token(long_token or short_token),
                    token_type=token_data.get("token_type") or "bearer",
                    expires_in=token_data.get("expires_in"),
                    obtained_at=datetime.now(timezone.utc),
                    metadata_json=meta_dict,
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
