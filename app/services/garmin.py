import asyncio
import base64
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.sport import SportActivity, SportAthlete, SportGarminConnection, SportGarminSyncLog, SportTrackPoint
from app.services.sport_normalizer import SportNormalizer


class GarminMFARequired(Exception):
    pass


class GarminServiceError(Exception):
    pass


class SportGarminConnectService:
    """Garmin Connect integration owned exclusively by the Sport module."""

    _sync_lock = asyncio.Lock()

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _cipher() -> Fernet:
        secret = get_settings().SECRET_KEY.encode("utf-8")
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))

    @classmethod
    def _encrypt_tokens(cls, token_json: str) -> str:
        return cls._cipher().encrypt(token_json.encode("utf-8")).decode("ascii")

    @classmethod
    def _decrypt_tokens(cls, encrypted: str) -> str:
        try:
            return cls._cipher().decrypt(encrypted.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise GarminServiceError("La session Garmin enregistrée est invalide") from exc

    @staticmethod
    def _garmin_class():
        try:
            from garminconnect import Garmin
        except ImportError as exc:
            raise GarminServiceError("La dépendance Garmin n'est pas installée") from exc
        return Garmin

    async def get_connection(self, athlete: SportAthlete) -> SportGarminConnection | None:
        result = await self.db.execute(select(SportGarminConnection).where(SportGarminConnection.athlete_id == athlete.id))
        return result.scalar_one_or_none()

    async def connect(self, athlete: SportAthlete, email: str, password: str, mfa_code: str | None, initial_sync_days: int) -> dict:
        Garmin = self._garmin_class()

        def authenticate():
            client = Garmin(
                email=email,
                password=password,
                prompt_mfa=lambda: mfa_code or "",
                return_on_mfa=not bool(mfa_code),
            )
            mfa_status, _ = client.login()
            return client, mfa_status

        try:
            client, mfa_status = await asyncio.to_thread(authenticate)
        except Exception as exc:
            raise GarminServiceError(self._safe_auth_error(exc)) from exc
        if mfa_status:
            return {"status": "mfa_required", "message": "Un code MFA Garmin est requis"}

        connection = await self.get_connection(athlete)
        if not connection:
            connection = SportGarminConnection(athlete_id=athlete.id, garmin_email=email)
            self.db.add(connection)
        connection.garmin_email = email
        connection.encrypted_tokens = self._encrypt_tokens(client.client.dumps())
        connection.status = "connected"
        connection.initial_sync_days = max(1, min(initial_sync_days, 365))
        connection.last_error = None
        connection.last_sync_status = None
        await self.db.commit()
        return {"status": "connected", "initial_sync_days": connection.initial_sync_days}

    async def disconnect(self, athlete: SportAthlete) -> bool:
        connection = await self.get_connection(athlete)
        if not connection:
            return False
        await self.db.delete(connection)
        await self.db.commit()
        return True

    async def sync_for_athlete(self, athlete: SportAthlete) -> dict:
        async with self._sync_lock:
            connection = await self.get_connection(athlete)
            if not connection:
                raise GarminServiceError("Aucun compte Garmin n'est connecté")
            return await self._sync_connection(connection, athlete)

    async def sync_all_connections(self) -> None:
        async with self._sync_lock:
            result = await self.db.execute(
                select(SportGarminConnection).options(selectinload(SportGarminConnection.athlete)).where(SportGarminConnection.status == "connected")
            )
            for connection in result.scalars().all():
                try:
                    await self._sync_connection(connection, connection.athlete)
                except Exception:
                    # One unavailable Garmin account must never stop the scheduler.
                    continue

    async def _sync_connection(self, connection: SportGarminConnection, athlete: SportAthlete) -> dict:
        started = datetime.now(timezone.utc)
        connection.last_sync_started_at = started
        connection.last_sync_status = "running"
        connection.last_error = None
        log = SportGarminSyncLog(connection_id=connection.id, status="running")
        self.db.add(log)
        await self.db.flush()
        try:
            client = await self._client_from_connection(connection)
            start_date = (connection.last_sync_at or started - timedelta(days=connection.initial_sync_days)).date() - timedelta(days=2)
            activities = await asyncio.to_thread(client.get_activities_by_date, start_date.isoformat(), date.today().isoformat())
            imported = 0
            for summary in activities or []:
                external_id = str(summary.get("activityId")) if summary.get("activityId") is not None else None
                if not external_id or await self._activity_exists(athlete.id, external_id):
                    continue
                try:
                    async with self.db.begin_nested():
                        await self._import_summary(client, athlete, summary)
                    imported += 1
                except Exception:
                    # A malformed activity must not prevent the remaining activities from syncing.
                    continue
            connection.encrypted_tokens = self._encrypt_tokens(client.client.dumps())
            connection.last_sync_at = datetime.now(timezone.utc)
            connection.last_sync_status = "success"
            log.status = "success"
            log.imported_count = imported
            log.finished_at = datetime.now(timezone.utc)
            await self.db.commit()
            return {"status": "success", "imported_count": imported, "last_sync_at": connection.last_sync_at}
        except Exception as exc:
            message = self._safe_sync_error(exc)
            connection.last_sync_status = "error"
            connection.last_error = message
            if "session" in message.lower() or "auth" in message.lower() or "401" in message:
                connection.status = "expired"
            log.status = "error"
            log.error_message = message
            log.finished_at = datetime.now(timezone.utc)
            await self.db.commit()
            raise GarminServiceError(message) from exc

    async def _client_from_connection(self, connection: SportGarminConnection):
        Garmin = self._garmin_class()
        token_json = self._decrypt_tokens(connection.encrypted_tokens)
        client = Garmin()
        # garminconnect accepts an inline token JSON when its length exceeds 512.
        tokenstore = token_json if len(token_json) > 512 else token_json + (" " * (513 - len(token_json)))
        try:
            await asyncio.to_thread(client.login, tokenstore)
        except Exception as exc:
            raise GarminServiceError("La session Garmin a expiré ou est indisponible") from exc
        return client

    async def _activity_exists(self, athlete_id: int, external_id: str) -> bool:
        result = await self.db.execute(
            select(SportActivity.id).where(
                SportActivity.athlete_id == athlete_id,
                SportActivity.source_type == "garmin",
                SportActivity.external_id == external_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _import_summary(self, client, athlete: SportAthlete, summary: dict[str, Any]) -> SportActivity:
        activity_id = str(summary["activityId"])
        activity_type = summary.get("activityTypeDTO") or {}
        if not isinstance(activity_type, dict):
            activity_type = {}
        sport_type = activity_type.get("typeKey")
        if not isinstance(sport_type, str):
            raw_type = summary.get("activityType")
            sport_type = raw_type.get("typeKey") if isinstance(raw_type, dict) else raw_type
        if not isinstance(sport_type, str) or not sport_type:
            sport_type = "other"
        started_raw = summary.get("startTimeLocal") or summary.get("startTimeGMT")
        started_at = datetime.fromisoformat(started_raw.replace("Z", "+00:00")) if started_raw else datetime.now(timezone.utc)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        details = await self._safe_garmin_call(client.get_activity_details, activity_id)
        splits = await self._safe_garmin_call(client.get_activity_split_summaries, activity_id)
        gpx_points: list[dict[str, Any]] = []
        source_path = None
        try:
            gpx = await asyncio.to_thread(client.download_activity, activity_id, client.ActivityDownloadFormat.GPX)
            normalized_gpx = SportNormalizer.from_file(f"garmin_{activity_id}.gpx", gpx)
            gpx_points = normalized_gpx.track_points
        except Exception:
            pass
        try:
            original = await asyncio.to_thread(client.download_activity, activity_id, client.ActivityDownloadFormat.ORIGINAL)
            upload_dir = os.getenv("UPLOAD_DIR", "/app/uploads/sport")
            os.makedirs(upload_dir, exist_ok=True)
            source_path = os.path.join(upload_dir, f"garmin_{activity_id}_{uuid4().hex}.zip")
            with open(source_path, "wb") as handle:
                handle.write(original)
        except Exception:
            pass
        activity = SportActivity(
            athlete_id=athlete.id,
            sport_type=sport_type,
            activity_name=summary.get("activityName"),
            started_at=started_at,
            duration_seconds=int(summary.get("duration") or 0),
            distance_m=summary.get("distance"),
            elevation_gain_m=summary.get("elevationGain"),
            elevation_loss_m=summary.get("elevationLoss"),
            avg_speed_m_s=summary.get("averageSpeed"),
            avg_pace_sec_km=summary.get("averagePace"),
            avg_heart_rate=summary.get("averageHR"),
            max_heart_rate=summary.get("maxHR"),
            avg_cadence=summary.get("averageRunningCadenceInStepsPerMinute") or summary.get("averageCadence"),
            avg_power_w=summary.get("avgPower") or summary.get("averagePower"),
            calories=summary.get("calories"),
            temperature_c=summary.get("averageTemperature"),
            source_type="garmin",
            source_file_name=f"garmin_{activity_id}.zip" if source_path else None,
            source_file_path=source_path,
            external_id=activity_id,
            metadata_json={"garmin_summary": summary, "garmin_details": details, "garmin_splits": splits},
        )
        self.db.add(activity)
        await self.db.flush()
        for point in gpx_points:
            recorded_at = point.get("recorded_at")
            if isinstance(recorded_at, str):
                recorded_at = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
            self.db.add(SportTrackPoint(activity_id=activity.id, recorded_at=recorded_at, **{
                key: value for key, value in point.items() if key != "recorded_at"
            }))
        return activity

    @staticmethod
    async def _safe_garmin_call(call, *args):
        try:
            return await asyncio.to_thread(call, *args)
        except Exception:
            return {}

    @staticmethod
    def _safe_auth_error(exc: Exception) -> str:
        text = str(exc).lower()
        if "mfa" in text:
            return "Un code MFA Garmin est requis"
        if "401" in text or "unauthorized" in text or "authentication" in text:
            return "Identifiants Garmin invalides"
        if "429" in text or "rate" in text:
            return "Garmin limite temporairement les tentatives"
        return "Connexion Garmin impossible"

    @staticmethod
    def _safe_sync_error(exc: Exception) -> str:
        text = str(exc).lower()
        if "401" in text or "unauthorized" in text or "authentication" in text or "session" in text:
            return "La session Garmin a expiré"
        if "429" in text or "rate" in text:
            return "Garmin limite temporairement les synchronisations"
        return "Synchronisation Garmin impossible"
