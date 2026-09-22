import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from app.models.sport import SportActivity, SportAthlete, SportGoal, SportTrackPoint
from app.models.user import User
from app.schemas.sport import SportActivityCreate, SportGoalCreate, SportNormalizedActivity
from app.services.sport_normalizer import SportNormalizer


class SportService:
    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user

    async def get_or_create_athlete(self) -> SportAthlete:
        result = await self.db.execute(select(SportAthlete).where(SportAthlete.user_id == self.current_user.id))
        athlete = result.scalar_one_or_none()
        if athlete:
            return athlete
        athlete = SportAthlete(
            user_id=self.current_user.id,
            display_name=f"{self.current_user.first_name or ''} {self.current_user.last_name or ''}".strip() or self.current_user.username,
        )
        self.db.add(athlete)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            result = await self.db.execute(select(SportAthlete).where(SportAthlete.user_id == self.current_user.id))
            athlete = result.scalar_one()
        return athlete

    async def create_activity(self, data: SportActivityCreate) -> dict:
        athlete = await self.get_or_create_athlete()
        normalized = SportNormalizer.from_mapping(data.model_dump(), source_type="manual")
        return await self._persist_normalized(athlete, normalized)

    async def import_activity(self, file: UploadFile) -> dict:
        content = await file.read()
        normalized = SportNormalizer.from_file(file.filename or "activity", content)
        upload_dir = os.getenv("UPLOAD_DIR", "/app/uploads/sport")
        os.makedirs(upload_dir, exist_ok=True)
        safe_name = f"{uuid4().hex}_{Path(file.filename or 'activity').name}"
        source_path = os.path.join(upload_dir, safe_name)
        with open(source_path, "wb") as handle:
            handle.write(content)
        normalized.source_file_path = source_path
        athlete = await self.get_or_create_athlete()
        return await self._persist_normalized(athlete, normalized)

    async def _persist_normalized(self, athlete: SportAthlete, normalized: SportNormalizedActivity) -> dict:
        activity = SportActivity(
            athlete_id=athlete.id,
            **normalized.model_dump(exclude={"track_points"}),
        )
        self.db.add(activity)
        await self.db.flush()
        for point in normalized.track_points:
            recorded_at = point.get("recorded_at")
            if isinstance(recorded_at, str):
                recorded_at = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
            self.db.add(SportTrackPoint(activity_id=activity.id, recorded_at=recorded_at, **{
                key: value for key, value in point.items() if key != "recorded_at"
            }))
        await self.db.commit()
        return await self.get_activity(activity.id)

    async def list_activities(self, page: int, page_size: int) -> dict:
        athlete = await self.get_or_create_athlete()
        columns = [
            SportActivity.id, SportActivity.sport_type, SportActivity.activity_name, SportActivity.started_at,
            SportActivity.duration_seconds, SportActivity.distance_m, SportActivity.elevation_gain_m,
            SportActivity.elevation_loss_m, SportActivity.avg_speed_m_s, SportActivity.avg_pace_sec_km,
            SportActivity.avg_heart_rate, SportActivity.max_heart_rate, SportActivity.avg_cadence,
            SportActivity.avg_power_w, SportActivity.calories, SportActivity.temperature_c,
            SportActivity.source_type, SportActivity.source_file_name, SportActivity.external_id,
        ]
        query = select(SportActivity).options(load_only(*columns)).where(SportActivity.athlete_id == athlete.id).order_by(SportActivity.started_at.desc())
        total = (await self.db.execute(select(func.count(SportActivity.id)).where(SportActivity.athlete_id == athlete.id))).scalar() or 0
        result = await self.db.execute(query.offset((page - 1) * page_size).limit(page_size))
        items = [item for item in result.scalars().all()]
        return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": max(1, -(-total // page_size))}

    async def get_activity(self, activity_id: int) -> Optional[dict]:
        athlete = await self.get_or_create_athlete()
        result = await self.db.execute(
            select(SportActivity).where(SportActivity.id == activity_id, SportActivity.athlete_id == athlete.id)
        )
        return result.scalar_one_or_none()

    async def dashboard(self) -> dict:
        athlete = await self.get_or_create_athlete()
        since = datetime.now(timezone.utc) - timedelta(days=30)
        base = select(SportActivity).options(load_only(
            SportActivity.id, SportActivity.sport_type, SportActivity.activity_name, SportActivity.started_at,
            SportActivity.duration_seconds, SportActivity.distance_m, SportActivity.elevation_gain_m,
            SportActivity.elevation_loss_m, SportActivity.avg_speed_m_s, SportActivity.avg_pace_sec_km,
            SportActivity.avg_heart_rate, SportActivity.max_heart_rate, SportActivity.avg_cadence,
            SportActivity.avg_power_w, SportActivity.calories, SportActivity.temperature_c,
            SportActivity.source_type, SportActivity.source_file_name, SportActivity.external_id,
        )).where(SportActivity.athlete_id == athlete.id, SportActivity.started_at >= since)
        result = await self.db.execute(base.order_by(SportActivity.started_at.desc()))
        recent = list(result.scalars().all())
        count = (await self.db.execute(select(func.count(SportActivity.id)).where(SportActivity.athlete_id == athlete.id))).scalar() or 0
        return {
            "activity_count": count,
            "recent_distance_m": sum(item.distance_m or 0 for item in recent),
            "recent_duration_seconds": sum(item.duration_seconds or 0 for item in recent),
            "recent_elevation_gain_m": sum(item.elevation_gain_m or 0 for item in recent),
            "latest_activity": recent[0] if recent else None,
        }

    async def list_goals(self) -> list[SportGoal]:
        athlete = await self.get_or_create_athlete()
        result = await self.db.execute(select(SportGoal).where(SportGoal.athlete_id == athlete.id).order_by(SportGoal.target_date.asc()))
        return list(result.scalars().all())

    async def create_goal(self, data: SportGoalCreate) -> SportGoal:
        athlete = await self.get_or_create_athlete()
        goal = SportGoal(athlete_id=athlete.id, **data.model_dump())
        self.db.add(goal)
        await self.db.commit()
        await self.db.refresh(goal)
        return goal
