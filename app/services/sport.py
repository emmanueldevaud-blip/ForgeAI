import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from app.models.sport import (SportActivity, SportActivityAnalysis, SportAthlete, SportAthleteObservation,
                               SportCoachConversation, SportCoachMessage, SportGoal, SportHealthDaily, SportTrackPoint)
from app.models.user import User
from app.schemas.sport import (SportActivityCreate, SportGoalCreate, SportNormalizedActivity,
                                SportHeartRateConfig, SportObservationCreate)
from app.services.sport_normalizer import SportNormalizer
from app.services.sport_analysis import SportAnalysisEngine
from app.services.sport_ai import get_sport_ai_provider

logger = logging.getLogger(__name__)


def _to_number(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _dig(value: Any, *paths: str) -> Any:
    """Retourne la première valeur atteignable parmi des chemins de clés ('a.b.c')."""
    if not isinstance(value, dict):
        return None
    for path in paths:
        node: Any = value
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if node is not None:
            return node
    return None


def _num(value: Any, *paths: str) -> float | None:
    return _to_number(_dig(value, *paths))


def _scalar(value: Any) -> Any:
    if isinstance(value, bool) or isinstance(value, (int, float, str)) or value is None:
        return value
    if isinstance(value, dict):
        for key in ("value", "status", "text", "label", "overall"):
            if key in value:
                return _scalar(value[key])
    return None


def _avg(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _minutes(seconds: float | None) -> int | None:
    return round(seconds / 60) if seconds else None

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
        await self._calculate_and_store_activity_analysis(activity.id)
        return await self.get_activity(activity.id)

    async def _calculate_and_store_activity_analysis(self, activity_id: int) -> None:
        try:
            analysis = await self._calculate_activity_analysis(activity_id)
            if not analysis:
                return
            stored = await self.db.scalar(select(SportActivityAnalysis).where(SportActivityAnalysis.activity_id == activity_id))
            if stored:
                stored.analysis_json = analysis
                stored.status = "calculated"
            else:
                self.db.add(SportActivityAnalysis(activity_id=activity_id, analysis_json=analysis, status="calculated"))
            await self.db.commit()
        except Exception:
            await self.db.rollback()

    async def build_activity_ai_context(self, activity_id: int, deterministic: dict | None = None) -> dict | None:
        """Contexte IA complet d'une activité (débrief ponctuel + analyse automatique).

        Regroupe analyse déterministe, historique, objectifs, récupération,
        détail Garmin minute par minute et santé récente.
        """
        if deterministic is None:
            deterministic = await self._calculate_activity_analysis(activity_id)
        if deterministic is None:
            return None
        athlete = await self.get_or_create_athlete()
        activity = await self.db.scalar(select(SportActivity).where(
            SportActivity.id == activity_id, SportActivity.athlete_id == athlete.id,
        ))
        if activity is None:
            return None
        reference_day = activity.started_at.date()
        result = await self.db.execute(select(SportActivity).where(
            SportActivity.athlete_id == athlete.id,
            SportActivity.started_at >= datetime.combine(reference_day - timedelta(days=179), datetime.min.time()),
            SportActivity.started_at <= datetime.combine(reference_day, datetime.max.time()),
        ).order_by(SportActivity.started_at.desc()))
        activities = list(result.scalars().all())
        zones = (athlete.metadata_json or {}).get("heart_rate_zones")
        weekly = SportAnalysisEngine.analyze_period(activities, reference_day - timedelta(days=27), reference_day, reference_day - timedelta(days=55), zones)
        goals_result = await self.db.execute(select(SportGoal).where(SportGoal.athlete_id == athlete.id))
        goals = list(goals_result.scalars().all())
        context = SportAnalysisEngine.build_context(
            {"display_name": athlete.display_name, "profile": SportAnalysisEngine.athlete_profile(activities, goals),
             "heart_rate": zones}, activities[:3], weekly, None, goals,
            recovery=await self.recovery_context(reference_day),
        )
        context["current_activity"] = deterministic
        detail = SportAnalysisEngine.activity_detail(activity, curve_points=20)
        if detail:
            context["current_activity"]["detail"] = detail
        context["health"] = await self.health_context(7, reference=reference_day)
        return context

    async def generate_activity_ai_analysis(self, activity_id: int) -> bool:
        """Generate the optional AI summary without affecting activity persistence."""
        try:
            deterministic = await self._calculate_activity_analysis(activity_id)
            if deterministic is None:
                return False
            await self._calculate_and_store_activity_analysis(activity_id)
            stored = await self.db.scalar(select(SportActivityAnalysis).where(SportActivityAnalysis.activity_id == activity_id))
            if stored is None:
                return False
            stored.ai_attempts = (stored.ai_attempts or 0) + 1
            stored.ai_status = "pending"
            stored.ai_error = None
            await self.db.commit()

            context = await self.build_activity_ai_context(activity_id, deterministic)
            if context is None:
                return False
            answer = await get_sport_ai_provider().answer(
                "Raconte-moi cette sortie comme si on la débriefait ensemble après la douche : "
                "ce que les chiffres racontent, ce qui a bien fonctionné, ce qui peut progresser, "
                "puis un conseil concret pour la suite. Appuie-toi sur toutes les données détaillées "
                "quand elles éclairent le propos : courbe minute par minute, segments kilométriques, "
                "cadence, puissance, dénivelé, FC. Ton naturel de coach complice : phrases courtes, "
                "vocabulaire simple, tutoiement, humour léger et décalé présent naturellement "
                "(~1 touche, 0 si fatigue, 2 si long), jamais forcé. Vocabulaire trail/endurance "
                "occasionnel bienvenu (D+, cailloux, sentiers, ravitaillement, mental, bâtons). "
                "Compare avec l'historique : tendances > donnée isolée. Pas de félicitations vides : "
                "félicite sur la base des données. Séance difficile = humour doux, explicatif, jamais "
                "culpabilisant. Fatigue = humour réduit, priorité récup. Structure libre mais claire : "
                "ce que je vois / ce que ça signifie / mon avis / petite touche coach. "
                "Termine sur un conseil applicable et une note motivante.",
                context,
            )
            stored.ai_analysis_json = {"answer": answer.get("answer"), "provider": answer.get("provider"), "sources": answer.get("sources", [])}
            stored.ai_status = "available" if answer.get("available") else "unavailable"
            stored.ai_generated_at = datetime.now(timezone.utc)
            stored.ai_error = None
            await self.db.commit()
            return True
        except Exception as exc:
            await self.db.rollback()
            logger.exception("Sport AI analysis failed for activity %s", activity_id)
            stored = await self.db.scalar(select(SportActivityAnalysis).where(SportActivityAnalysis.activity_id == activity_id))
            if stored:
                stored.ai_status = "failed"
                stored.ai_error = str(exc)[:1000]
                try:
                    await self.db.commit()
                except Exception:
                    await self.db.rollback()
            return False

    async def _calculate_activity_analysis(self, activity_id: int) -> dict | None:
        athlete = await self.get_or_create_athlete()
        result = await self.db.execute(
            select(SportActivity).options(selectinload(SportActivity.track_points)).where(
                SportActivity.id == activity_id,
                SportActivity.athlete_id == athlete.id,
            )
        )
        activity = result.scalar_one_or_none()
        if not activity:
            return None
        similar_result = await self.db.execute(
            select(SportActivity).where(
                SportActivity.athlete_id == athlete.id,
                SportActivity.id != activity_id,
                SportActivity.sport_type == activity.sport_type,
            ).order_by(SportActivity.started_at.desc()).limit(20)
        )
        zones = (athlete.metadata_json or {}).get("heart_rate_zones")
        return SportAnalysisEngine.analyze_activity(activity, similar_result.scalars().all(), zones)

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
        athlete_zones = (athlete.metadata_json or {}).get("heart_rate_zones")
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
            "goal_analysis": SportAnalysisEngine.analyze_goals(goals, activities, today),
            "ai": {"available": True, "provider": "local", "llm": False},
            "analysis": SportAnalysisEngine.analyze_period(
                activities,
                period_start,
                today,
                previous_start,
                athlete_zones,
            ),
        }

    async def health(self, period_days: int = 28, *, reference: date | None = None) -> dict:
        """Séries de santé quotidiennes (Garmin) sur la période demandée."""
        athlete = await self.get_or_create_athlete()
        period_days = period_days if period_days in {7, 14, 28, 90} else 28
        today = reference or datetime.now(timezone.utc).date()
        start = today - timedelta(days=period_days - 1)
        result = await self.db.execute(
            select(SportHealthDaily).where(
                SportHealthDaily.athlete_id == athlete.id,
                SportHealthDaily.day >= start,
                SportHealthDaily.day <= today,
            )
        )
        rows = sorted(result.scalars().all(), key=lambda row: row.day)

        series: dict[str, list[dict[str, Any]]] = {
            "heart_rate": [], "sleep": [], "hrv": [], "stress": [], "body_battery": [],
            "steps": [], "spo2": [], "respiration": [], "readiness": [],
        }

        def push(key: str, item: dict[str, Any]) -> None:
            if any(value is not None for name, value in item.items() if name != "date"):
                series[key].append(item)

        for row in rows:
            data = row.health_json or {}
            day = row.day.isoformat()

            heart_rates = data.get("heart_rates")
            resting_hr = data.get("resting_hr")
            resting = _num(resting_hr, "restingHR", "resting_hr", "rhr") or _num(heart_rates, "restingHeartRate", "restingHR", "resting_hr")
            if resting is None:
                summaries = _dig(resting_hr, "metricSummaries")
                if isinstance(summaries, list):
                    for entry in summaries:
                        candidate = _num(entry, "value")
                        if candidate is not None:
                            resting = candidate
                            break
            push("heart_rate", {
                "date": day,
                "resting": resting,
                "avg": _num(heart_rates, "avgHR", "averageHR", "avgHeartRate"),
                "max": _num(heart_rates, "maxHR", "max_hr", "maxHeartRate"),
            })

            sleep = data.get("sleep")
            if sleep:
                dto = _dig(sleep, "dailySleepDTO")
                total = _num(sleep, "sleepTimeSeconds", "totalSleepSeconds") or _num(dto, "sleepTimeSeconds", "totalSleepSeconds")
                score = (
                    _num(sleep, "sleepScore", "overallScore", "score.value", "sleepScores.value", "sleepScores.overall.value")
                    or _num(dto, "sleepScore", "score", "sleepScores.overall.value")
                )
                push("sleep", {
                    "date": day,
                    "total_minutes": round(total / 60) if total else None,
                    "score": score,
                    "deep_minutes": _minutes(_num(sleep, "deepSleepSeconds") or _num(dto, "deepSleepSeconds")),
                    "light_minutes": _minutes(_num(sleep, "lightSleepSeconds") or _num(dto, "lightSleepSeconds")),
                    "rem_minutes": _minutes(_num(sleep, "remSleepSeconds") or _num(dto, "remSleepSeconds")),
                    "awake_minutes": _minutes(_num(sleep, "awakeTimeSeconds", "awakeSleepSeconds") or _num(dto, "awakeTimeSeconds", "awakeSleepSeconds")),
                })

            hrv = data.get("hrv")
            if hrv:
                push("hrv", {
                    "date": day,
                    "value": _num(hrv, "hrv", "hrvValue", "avgHrv", "avg", "averageHRV", "hrvSummary.lastNightAvg", "hrvSummary.weeklyAvg"),
                    "status": _scalar(_dig(hrv, "status", "hrvStatus", "weeklyStatus", "hrvSummary.status")),
                })

            stress = data.get("stress")
            if stress:
                push("stress", {
                    "date": day,
                    "avg": _num(stress, "avgStressLevel", "averageStressLevel", "avgStress", "stressLevel"),
                    "max": _num(stress, "maxStressLevel", "maximumStressLevel", "maxStress"),
                })

            body_battery = data.get("body_battery")
            if body_battery:
                source = body_battery
                if isinstance(body_battery, list):
                    source = body_battery[0] if body_battery else {}
                values = source.get("bodyBatteryValuesArray") if isinstance(source, dict) else None
                numbers = []
                for entry in values if isinstance(values, list) else []:
                    raw = entry[1] if isinstance(entry, (list, tuple)) and len(entry) > 1 else entry
                    number = _to_number(raw)
                    if number is not None:
                        numbers.append(number)
                push("body_battery", {
                    "date": day,
                    "min": min(numbers) if numbers else _num(source, "bodyBattery", "value", "score"),
                    "max": max(numbers) if numbers else None,
                    "last": numbers[-1] if numbers else _num(source, "bodyBattery", "value", "score"),
                })

            daily_steps = data.get("daily_steps")
            if isinstance(daily_steps, list):
                daily_steps = daily_steps[0] if daily_steps else None
            daily_summary = data.get("daily_summary")
            push("steps", {
                "date": day,
                "steps": _num(daily_steps, "steps", "stepValue", "totalSteps") or _num(daily_summary, "steps", "stepValue", "totalSteps"),
                "calories": _num(daily_summary, "calories", "totalCalories", "activeKilocalories"),
                "moderate_minutes": _num(daily_summary, "moderateActivityMinutes"),
                "vigorous_minutes": _num(daily_summary, "vigorousActivityMinutes"),
            })

            spo2 = data.get("spo2")
            if spo2:
                push("spo2", {"date": day, "value": _num(spo2, "averageSpO2", "avgSpO2", "spo2Average", "averageSpo2", "spo2", "value")})

            respiration = data.get("respiration")
            if respiration:
                push("respiration", {"date": day, "value": _num(respiration, "avgWakingRespirationValue", "averageRespirationValue", "avgRespirationValue", "respirationValue", "avg", "value")})

            readiness = data.get("readiness")
            if isinstance(readiness, list):
                entries = [item for item in readiness if isinstance(item, dict)]
                matching = [item for item in entries if str(item.get("calendarDate") or "")[:10] == day]
                readiness = (matching or entries)[-1] if (matching or entries) else None
            if readiness:
                push("readiness", {
                    "date": day,
                    "score": _num(readiness, "score", "trainingReadinessScore", "readinessScore", "value"),
                    "status": _scalar(_dig(readiness, "status", "trainingStatus", "level")),
                })

        summary = {
            "days_with_data": len(rows),
            "resting_hr_avg": _avg([item.get("resting") for item in series["heart_rate"]]),
            "sleep_total_avg_minutes": _avg([item.get("total_minutes") for item in series["sleep"]]),
            "sleep_score_avg": _avg([item.get("score") for item in series["sleep"]]),
            "hrv_avg": _avg([item.get("value") for item in series["hrv"]]),
            "stress_avg": _avg([item.get("avg") for item in series["stress"]]),
            "body_battery_last": series["body_battery"][-1].get("last") if series["body_battery"] else None,
            "steps_avg": _avg([item.get("steps") for item in series["steps"]]),
            "spo2_avg": _avg([item.get("value") for item in series["spo2"]]),
            "respiration_avg": _avg([item.get("value") for item in series["respiration"]]),
            "readiness_last": series["readiness"][-1].get("score") if series["readiness"] else None,
        }
        return {
            "period_days": period_days,
            "period_start": start,
            "period_end": today,
            "days_available": len(rows),
            "summary": summary,
            "series": series,
        }

    async def recovery_context(self, reference: date | None = None) -> dict:
        """Données de récupération (readiness, sommeil, HRV, stress) pour l'IA."""
        data = await self.health(7, reference=reference)
        if not data["days_available"]:
            return {"available": False, "reason": "Aucune donnée de récupération disponible"}
        series = data["series"]
        summary = data["summary"]

        def latest(key: str, field: str) -> Any:
            items = series.get(key) or []
            return items[-1].get(field) if items else None

        return {
            "available": True,
            "days_with_data": data["days_available"],
            "reference_day": data["period_end"].isoformat(),
            "latest": {
                "readiness_score": latest("readiness", "score"),
                "readiness_status": latest("readiness", "status"),
                "sleep_score": latest("sleep", "score"),
                "sleep_total_minutes": latest("sleep", "total_minutes"),
                "hrv_ms": latest("hrv", "value"),
                "hrv_status": latest("hrv", "status"),
                "resting_hr": latest("heart_rate", "resting"),
                "stress_avg": latest("stress", "avg"),
                "body_battery": latest("body_battery", "last"),
                "spo2": latest("spo2", "value"),
            },
            "period_averages": {
                "sleep_score": summary.get("sleep_score_avg"),
                "sleep_total_minutes": summary.get("sleep_total_avg_minutes"),
                "hrv": summary.get("hrv_avg"),
                "resting_hr": summary.get("resting_hr_avg"),
                "stress": summary.get("stress_avg"),
                "steps": summary.get("steps_avg"),
            },
        }

    _HEALTH_CONTEXT_FIELDS: tuple[tuple[str, str, str, str], ...] = (
        ("heart_rate", "rhr", "resting", "fc_repos"),
        ("heart_rate", "avg", "avg", "fc_moy"),
        ("heart_rate", "hmax", "max", "fc_max"),
        ("sleep", "tmin", "total_minutes", "sommeil_min"),
        ("sleep", "ssc", "score", "score_sommeil"),
        ("sleep", "deep", "deep_minutes", "sommeil_profond_min"),
        ("sleep", "lt", "light_minutes", "sommeil_leger_min"),
        ("sleep", "rem", "rem_minutes", "rem_min"),
        ("sleep", "awk", "awake_minutes", "eveil_min"),
        ("hrv", "hrv", "value", "hrv_ms"),
        ("hrv", "hst", "status", "hrv_statut"),
        ("stress", "sta", "avg", "stress_moy"),
        ("stress", "stm", "max", "stress_max"),
        ("body_battery", "bbn", "min", "body_battery_min"),
        ("body_battery", "bbx", "max", "body_battery_max"),
        ("body_battery", "bbl", "last", "body_battery_fin"),
        ("steps", "stp", "steps", "pas"),
        ("steps", "kcal", "calories", "kcal"),
        ("steps", "mod", "moderate_minutes", "moderate_min"),
        ("steps", "vig", "vigorous_minutes", "vigoureux_min"),
        ("spo2", "o2", "value", "spo2"),
        ("respiration", "rsp", "value", "respiration"),
        ("readiness", "rds", "score", "readiness"),
        ("readiness", "rst", "status", "readiness_statut"),
    )

    async def health_context(self, period_days: int = 90, *, reference: date | None = None) -> dict:
        """Santé quotidienne en format tabulaire compact destiné au prompt IA.

        L'AI Gateway (tier gratuit) refuse les entrées au-delà d'une limite de
        tokens : le format brut de health() fait ~5 000 tokens, cette version
        compacte (~2 500 tokens) conserve toutes les séries et tous les jours.
        Les colonnes sans aucune valeur sont retirées.
        """
        data = await self.health(period_days, reference=reference)
        by_day: dict[str, dict[str, Any]] = {}
        for key, code, field, _ in self._HEALTH_CONTEXT_FIELDS:
            for item in data["series"].get(key) or []:
                value = item.get(field)
                if value is None:
                    continue
                if isinstance(value, float) and value.is_integer():
                    value = int(value)
                by_day.setdefault(item["date"], {})[code] = value
        used = [
            code for code in dict.fromkeys(code for _, code, _, _ in self._HEALTH_CONTEXT_FIELDS)
            if any(code in entry for entry in by_day.values())
        ]
        labels = {code: label for _, code, _, label in self._HEALTH_CONTEXT_FIELDS if code in used}
        summary = {
            key: (round(value, 1) if isinstance(value, float) else value)
            for key, value in data["summary"].items()
        }
        return {
            "period_days": data["period_days"],
            "period_end": data["period_end"].isoformat(),
            "days_with_data": data["days_available"],
            "columns": ["day", *used],
            "legend": "day=jour(MM-DD); " + "; ".join(f"{code}={label}" for code, label in labels.items()),
            "rows": [
                [day[5:]] + [by_day[day].get(code) for code in used]
                for day in sorted(by_day)
            ],
            "summary": summary,
        }

    async def analyze_period(self, period_days: int = 28) -> dict:
        athlete = await self.get_or_create_athlete()
        period_days = period_days if period_days in {7, 28, 90, 365} else 28
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=period_days - 1)
        query_start = start - timedelta(days=period_days)
        result = await self.db.execute(
            select(SportActivity).where(
                SportActivity.athlete_id == athlete.id,
                SportActivity.started_at >= datetime.combine(query_start, datetime.min.time()),
            ).order_by(SportActivity.started_at.desc())
        )
        return SportAnalysisEngine.analyze_period(
            list(result.scalars().all()), start, today, query_start,
            (athlete.metadata_json or {}).get("heart_rate_zones"),
        )

    async def analyze_activity(self, activity_id: int) -> dict:
        analysis = await self._calculate_activity_analysis(activity_id)
        if analysis is None:
            return {}
        await self._calculate_and_store_activity_analysis(activity_id)
        stored = await self.db.scalar(select(SportActivityAnalysis).where(SportActivityAnalysis.activity_id == activity_id))
        if stored:
            analysis["ai_analysis"] = {
                "status": stored.ai_status,
                "result": stored.ai_analysis_json,
                "generated_at": stored.ai_generated_at,
                "attempts": stored.ai_attempts,
                "error": stored.ai_error,
            }
        return analysis

    async def analyze_week(self) -> dict:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=today.weekday())
        return await self._analyze_range(start, today, 7)

    async def analyze_month(self) -> dict:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=29)
        return await self._analyze_range(start, today, 30)

    async def analyze_day(self, day: date | None = None) -> dict:
        athlete = await self.get_or_create_athlete()
        target = day or datetime.now(timezone.utc).date()
        previous = target - timedelta(days=1)
        result = await self.db.execute(select(SportActivity).where(
            SportActivity.athlete_id == athlete.id,
            SportActivity.started_at >= datetime.combine(previous, datetime.min.time()),
        ))
        return SportAnalysisEngine.analyze_period(
            list(result.scalars().all()), target, target, previous,
            (athlete.metadata_json or {}).get("heart_rate_zones"),
        )

    async def analyze_goals(self) -> list[dict]:
        athlete = await self.get_or_create_athlete()
        activities_result = await self.db.execute(select(SportActivity).where(SportActivity.athlete_id == athlete.id))
        goals_result = await self.db.execute(select(SportGoal).where(SportGoal.athlete_id == athlete.id))
        return SportAnalysisEngine.analyze_goals(
            goals_result.scalars().all(), activities_result.scalars().all(), datetime.now(timezone.utc).date(),
        )

    async def athlete_profile(self) -> dict:
        athlete = await self.get_or_create_athlete()
        result = await self.db.execute(
            select(SportActivity).where(SportActivity.athlete_id == athlete.id).order_by(SportActivity.started_at.asc())
        )
        goals_result = await self.db.execute(select(SportGoal).where(SportGoal.athlete_id == athlete.id))
        goals = [{"name": goal.name, "goal_type": goal.goal_type, "target_value": goal.target_value,
                  "unit": goal.unit, "target_date": goal.target_date} for goal in goals_result.scalars().all()]
        metadata = athlete.metadata_json or {}
        return {
            "athlete_id": athlete.id,
            "display_name": athlete.display_name,
            "heart_rate": metadata.get("heart_rate_zones"),
            "profile": SportAnalysisEngine.athlete_profile(result.scalars().all(), goals),
        }

    async def update_heart_rate_config(self, config: SportHeartRateConfig) -> dict:
        athlete = await self.get_or_create_athlete()
        values = config.model_dump(exclude_none=True)
        if values.get("custom_zones") and values["custom_zones"] != sorted(values["custom_zones"]):
            raise ValueError("Les limites des zones cardiaques doivent être croissantes")
        metadata = dict(athlete.metadata_json or {})
        if values:
            metadata["heart_rate_zones"] = values
        else:
            metadata.pop("heart_rate_zones", None)
        athlete.metadata_json = metadata
        await self.db.commit()
        return await self.athlete_profile()

    async def _analyze_range(self, start: date, end: date, period_days: int) -> dict:
        athlete = await self.get_or_create_athlete()
        previous_start = start - timedelta(days=period_days)
        result = await self.db.execute(select(SportActivity).where(
            SportActivity.athlete_id == athlete.id,
            SportActivity.started_at >= datetime.combine(previous_start, datetime.min.time()),
        ))
        return SportAnalysisEngine.analyze_period(
            list(result.scalars().all()), start, end, previous_start,
            (athlete.metadata_json or {}).get("heart_rate_zones"),
        )

    async def build_coach_context(self, athlete) -> dict:
        """Construit le contexte de données (activités, périsodes, objectifs) utilisé par le coach IA."""
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=27)
        result = await self.db.execute(
            select(SportActivity).where(
                SportActivity.athlete_id == athlete.id,
                SportActivity.started_at >= datetime.combine(today - timedelta(days=120), datetime.min.time()),
            ).order_by(SportActivity.started_at.desc())
        )
        activities = list(result.scalars().all())
        zones = (athlete.metadata_json or {}).get("heart_rate_zones")
        weekly = SportAnalysisEngine.analyze_period(activities, start, today, today - timedelta(days=55), zones)
        monthly = SportAnalysisEngine.analyze_period(activities, today - timedelta(days=89), today, today - timedelta(days=179), zones)
        goals_result = await self.db.execute(select(SportGoal).where(SportGoal.athlete_id == athlete.id))
        goals = [{"name": goal.name, "goal_type": goal.goal_type, "target_value": goal.target_value, "unit": goal.unit, "target_date": goal.target_date} for goal in goals_result.scalars().all()]
        profile = SportAnalysisEngine.athlete_profile(activities, goals)
        profile["goal_analysis"] = SportAnalysisEngine.analyze_goals(goals, activities, today)
        context = SportAnalysisEngine.build_context(
            {"display_name": athlete.display_name, "profile": profile, "heart_rate": (athlete.metadata_json or {}).get("heart_rate_zones")},
            activities[:5], weekly, monthly, goals,
            recovery=await self.recovery_context(),
        )
        context["health"] = await self.health_context(90)
        return context

    async def coach(self, question: str, conversation_id: int | None = None) -> dict:
        athlete = await self.get_or_create_athlete()
        conversation = None
        if conversation_id is not None:
            conversation = await self.db.scalar(select(SportCoachConversation).where(
                SportCoachConversation.id == conversation_id,
                SportCoachConversation.athlete_id == athlete.id,
            ))
            if conversation is None:
                raise ValueError("Conversation Sport introuvable")
        else:
            conversation = SportCoachConversation(athlete_id=athlete.id, title=question[:300])
            self.db.add(conversation)
            await self.db.flush()

        self.db.add(SportCoachMessage(conversation_id=conversation.id, role="user", content=question, sources_json=[]))
        await self.db.flush()
        context = await self.build_coach_context(athlete)
        result = await get_sport_ai_provider().answer(question, context)
        assistant_message = SportCoachMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=result["answer"],
            provider=result.get("provider"),
            sources_json=result.get("sources", []),
        )
        self.db.add(assistant_message)
        conversation.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(assistant_message)
        return {**result, "conversation_id": conversation.id, "message_id": assistant_message.id}

    async def list_coach_conversations(self) -> list[dict]:
        athlete = await self.get_or_create_athlete()
        result = await self.db.execute(select(SportCoachConversation).where(
            SportCoachConversation.athlete_id == athlete.id,
        ).order_by(SportCoachConversation.updated_at.desc()).limit(50))
        return [{"id": item.id, "title": item.title, "created_at": item.created_at, "updated_at": item.updated_at, "messages": []}
                for item in result.scalars().all()]

    async def get_coach_conversation(self, conversation_id: int) -> dict | None:
        athlete = await self.get_or_create_athlete()
        result = await self.db.execute(select(SportCoachConversation).options(selectinload(SportCoachConversation.messages)).where(
            SportCoachConversation.id == conversation_id,
            SportCoachConversation.athlete_id == athlete.id,
        ))
        conversation = result.scalar_one_or_none()
        if not conversation:
            return None
        return {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "messages": [{"id": message.id, "role": message.role, "content": message.content,
                           "provider": message.provider, "sources": message.sources_json,
                           "created_at": message.created_at} for message in conversation.messages],
        }

    async def create_observation(self, data: SportObservationCreate) -> SportAthleteObservation:
        athlete = await self.get_or_create_athlete()
        if data.activity_id:
            activity = await self.db.scalar(select(SportActivity).where(
                SportActivity.id == data.activity_id, SportActivity.athlete_id == athlete.id,
            ))
            if activity is None:
                raise ValueError("Activité Sport introuvable")
        observation = SportAthleteObservation(
            athlete_id=athlete.id, activity_id=data.activity_id, kind=data.kind,
            content=data.content, status="confirmed", sources_json={"source": "user"},
            confirmed_at=datetime.now(timezone.utc),
        )
        self.db.add(observation)
        await self.db.commit()
        await self.db.refresh(observation)
        return observation

    async def list_observations(self) -> list[SportAthleteObservation]:
        athlete = await self.get_or_create_athlete()
        result = await self.db.execute(select(SportAthleteObservation).where(
            SportAthleteObservation.athlete_id == athlete.id,
        ).order_by(SportAthleteObservation.created_at.desc()).limit(100))
        return list(result.scalars().all())

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
