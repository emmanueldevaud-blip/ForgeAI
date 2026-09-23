import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
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

    async def dashboard(self, period_days: int = 28) -> dict:
        athlete = await self.get_or_create_athlete()
        period_days = period_days if period_days in {7, 28, 90, 365} else 28
        today = datetime.now(timezone.utc).date()
        period_start = today - timedelta(days=period_days - 1)
        previous_start = period_start - timedelta(days=period_days)
        calendar_start = today - timedelta(days=83)
        query_start = min(period_start, previous_start, calendar_start)
        columns = (
            SportActivity.id, SportActivity.sport_type, SportActivity.activity_name, SportActivity.started_at,
            SportActivity.duration_seconds, SportActivity.distance_m, SportActivity.elevation_gain_m,
            SportActivity.elevation_loss_m, SportActivity.avg_speed_m_s, SportActivity.avg_pace_sec_km,
            SportActivity.avg_heart_rate, SportActivity.max_heart_rate, SportActivity.avg_cadence,
            SportActivity.avg_power_w, SportActivity.calories, SportActivity.temperature_c,
            SportActivity.source_type, SportActivity.source_file_name, SportActivity.external_id,
        )
        result = await self.db.execute(
            select(SportActivity).options(load_only(*columns)).where(
                SportActivity.athlete_id == athlete.id,
                SportActivity.started_at >= datetime.combine(query_start, datetime.min.time()),
            ).order_by(SportActivity.started_at.desc())
        )
        activities = list(result.scalars().all())
        current = [item for item in activities if period_start <= item.started_at.date() <= today]
        previous = [item for item in activities if previous_start <= item.started_at.date() < period_start]
        goals_result = await self.db.execute(
            select(SportGoal).where(SportGoal.athlete_id == athlete.id).order_by(SportGoal.target_date.asc())
        )
        goals = list(goals_result.scalars().all())
        current_summary = self._summary(current)
        previous_summary = self._summary(previous)
        summary = {
            **current_summary,
            "previous": previous_summary,
        }
        return {
            "period_days": period_days,
            "period_start": period_start,
            "period_end": today,
            "summary": summary,
            "trends": self._trends(current_summary, previous_summary),
            "daily": self._daily(current, period_start, today),
            "weekly": self._weekly(activities, today),
            "sports": self._sports(current),
            "calendar": self._calendar(activities, calendar_start, today),
            "heart_rate": self._heart_rate(current),
            "elevation": self._elevation(activities, today),
            "latest_activity": activities[0] if activities else None,
            "recent_activities": activities[:6],
            "goals": goals,
            "ai": {"available": False},
        }

    @staticmethod
    def _summary(activities: list[SportActivity]) -> dict:
        def average(field: str) -> float | None:
            values = [getattr(item, field) for item in activities if getattr(item, field) is not None]
            return sum(values) / len(values) if values else None

        distance = [item.distance_m for item in activities if item.distance_m is not None]
        elevation = [item.elevation_gain_m for item in activities if item.elevation_gain_m is not None]
        return {
            "activity_count": len(activities),
            "distance_m": sum(distance) if distance else None,
            "duration_seconds": sum(item.duration_seconds or 0 for item in activities) if activities else None,
            "elevation_gain_m": sum(elevation) if elevation else None,
            "avg_speed_m_s": average("avg_speed_m_s"),
            "avg_pace_sec_km": average("avg_pace_sec_km"),
            "avg_heart_rate": average("avg_heart_rate"),
        }

    @staticmethod
    def _change(current: float | None, previous: float | None) -> float | None:
        if current is None or previous in (None, 0):
            return None
        return round((current - previous) / previous * 100, 1)

    def _trends(self, current: dict, previous: dict) -> list[dict]:
        values = (
            ("distance_m", "Distance", "m"),
            ("elevation_gain_m", "Dénivelé positif", "m"),
            ("duration_seconds", "Temps d’entraînement", "s"),
            ("activity_count", "Activités", "count"),
            ("avg_pace_sec_km", "Allure moyenne", "pace"),
            ("avg_heart_rate", "FC moyenne", "bpm"),
        )
        return [
            {"key": key, "label": label, "value": current.get(key), "unit": unit,
             "change_percent": self._change(current.get(key), previous.get(key))}
            for key, label, unit in values if current.get(key) is not None
        ]

    @staticmethod
    def _daily(activities: list[SportActivity], start: date, end: date) -> list[dict]:
        grouped = defaultdict(list)
        for item in activities:
            grouped[item.started_at.date()].append(item)
        return [
            {"date": day, **SportService._summary(grouped[day])}
            for offset in range((end - start).days + 1)
            for day in [start + timedelta(days=offset)]
        ]

    @staticmethod
    def _weekly(activities: list[SportActivity], end: date) -> list[dict]:
        start = end - timedelta(days=41)
        grouped = defaultdict(list)
        for item in activities:
            day = item.started_at.date()
            if start <= day <= end:
                week_start = day - timedelta(days=day.weekday())
                grouped[week_start].append(item)
        first_week = start - timedelta(days=start.weekday())
        last_week = end - timedelta(days=end.weekday())
        result = []
        cursor = first_week
        while cursor <= last_week:
            result.append({"start": cursor, "end": cursor + timedelta(days=6), **SportService._summary(grouped[cursor])})
            cursor += timedelta(days=7)
        return result

    @staticmethod
    def _sports(activities: list[SportActivity]) -> list[dict]:
        grouped = defaultdict(list)
        for item in activities:
            grouped[item.sport_type or "other"].append(item)
        result = []
        for sport_type, items in grouped.items():
            summary = SportService._summary(items)
            result.append({"sport_type": sport_type, **summary})
        return sorted(result, key=lambda item: item["activity_count"], reverse=True)

    @staticmethod
    def _calendar(activities: list[SportActivity], start: date, end: date) -> list[dict]:
        grouped = defaultdict(list)
        for item in activities:
            grouped[item.started_at.date()].append(item)
        return [
            {"date": day, "activity_count": len(grouped[day]),
             "duration_seconds": sum(item.duration_seconds or 0 for item in grouped[day]),
             "distance_m": sum(item.distance_m or 0 for item in grouped[day]) or None}
            for offset in range((end - start).days + 1)
            for day in [start + timedelta(days=offset)]
        ]

    @staticmethod
    def _heart_rate(activities: list[SportActivity]) -> dict | None:
        with_hr = [item for item in activities if item.avg_heart_rate is not None]
        if not with_hr:
            return None
        weekly = defaultdict(list)
        for item in with_hr:
            week_start = item.started_at.date() - timedelta(days=item.started_at.date().weekday())
            weekly[week_start].append(item.avg_heart_rate)
        return {
            "avg_bpm": sum(item.avg_heart_rate for item in with_hr) / len(with_hr),
            "max_bpm": max((item.max_heart_rate for item in with_hr if item.max_heart_rate is not None), default=None),
            "weekly": [{"start": start, "avg_bpm": sum(values) / len(values)} for start, values in sorted(weekly.items())],
            "zones": [],
        }

    @staticmethod
    def _elevation(activities: list[SportActivity], end: date) -> dict:
        recent = [item for item in activities if item.started_at.date() >= end - timedelta(days=27)]
        month = sum(item.elevation_gain_m or 0 for item in recent) if any(item.elevation_gain_m is not None for item in recent) else None
        weeks = SportService._weekly(activities, end)
        values = [item["elevation_gain_m"] for item in weeks if item["elevation_gain_m"] is not None]
        return {"month_m": month, "weekly_average_m": sum(values) / len(values) if values else None,
                "weekly": [{"start": item["start"], "elevation_gain_m": item["elevation_gain_m"]} for item in weeks]}

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
