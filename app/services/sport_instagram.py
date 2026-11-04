"""Service de connexion Meta (Instagram Business) pour les statistiques Insights."""

import base64
import hashlib
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.sport import SportAthlete, SportInstagramConnection
from app.models.user import User

DEFAULT_META_SCOPES = "instagram_business_basic"


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

    def _app_credentials(self) -> tuple[str, str, str]:
        settings = get_settings()
        if not settings.META_APP_ID or not settings.META_APP_SECRET:
            raise HTTPException(status_code=503, detail="Meta OAuth non configuré (META_APP_ID ou META_APP_SECRET manquant)")
        redirect_uri = settings.META_REDIRECT_URI or "http://localhost:8000/sport/publications/meta/callback"
        return settings.META_APP_ID, settings.META_APP_SECRET, redirect_uri

    def build_authorization_url(self, athlete_id: int, user_id: int, scopes: str | None = None) -> tuple[str, str]:
        app_id, _, redirect_uri = self._app_credentials()
        state = f"{athlete_id}:{user_id}"
        from urllib.parse import urlencode

        query = urlencode(
            {
                "client_id": app_id,
                "redirect_uri": redirect_uri,
                "scope": scopes or DEFAULT_META_SCOPES,
                "response_type": "code",
                "state": state,
            }
        )
        return f"{self._dialog_url}?{query}", state

    async def exchange_code(self, code: str, redirect_uri: str | None, state: str) -> SportInstagramConnection:
        app_id, app_secret, default_redirect = self._app_credentials()
        redirect_to = redirect_uri or default_redirect
        if not redirect_to:
            raise HTTPException(status_code=503, detail="Meta OAuth redirect_uri non configure")

        async with httpx.AsyncClient(timeout=20.0) as client:
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
            short_token = token_response.json().get("access_token")

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

        token_data = long_response.json()
        long_lived_token = long_token or short_token
        obtained_at = datetime.now(timezone.utc)

        parts = state.split(":")
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Etat OAuth invalide")
        try:
            athlete_id = int(parts[0])
            user_id = int(parts[1])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Etat OAuth invalide") from exc

        athlete = await self.db.get(SportAthlete, athlete_id)
        user = await self.db.get(User, user_id)

        if athlete is None or user is None:
            raise HTTPException(status_code=404, detail="Utilisateur ou athlete introuvable")

        # Détection du compte Instagram Business lié
        ig_account_id = None
        ig_username = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as fetch_client:
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
        except Exception:
            pass

        existing = await self.get_connection(user_id)
        now = datetime.now(timezone.utc)
        meta_dict = {"username": ig_username} if ig_username else {}
        if existing is not None:
            existing.instagram_business_account_id = ig_account_id or existing.instagram_business_account_id
            existing.encrypted_access_token = _encrypt_token(long_lived_token)
            existing.encrypted_long_lived_token = _encrypt_token(long_token)
            existing.status = "active"
            existing.token_type = token_data.get("token_type") or "bearer"
            existing.expires_in = token_data.get("expires_in")
            existing.obtained_at = obtained_at
            existing.metadata_json = meta_dict
            existing.updated_at = now
            await self.db.flush()
            return existing

        connection = SportInstagramConnection(
            user_id=user_id,
            athlete_id=athlete_id,
            instagram_business_account_id=ig_account_id,
            status="active",
            encrypted_access_token=_encrypt_token(long_lived_token),
            encrypted_long_lived_token=_encrypt_token(long_token),
            token_type=token_data.get("token_type") or "bearer",
            expires_in=token_data.get("expires_in"),
            obtained_at=obtained_at,
            metadata_json=meta_dict,
        )
        self.db.add(connection)
        await self.db.flush()
        return connection

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
