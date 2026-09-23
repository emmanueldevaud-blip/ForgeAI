from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any, Iterable


class SportAnalysisEngine:
    """Deterministic sport metrics and context builder, independent from any LLM."""

    @staticmethod
    def _values(activities: Iterable[Any], field: str) -> list[float]:
        return [float(value) for item in activities if (value := getattr(item, field, None)) is not None]

    @classmethod
    def summarize(cls, activities: Iterable[Any]) -> dict[str, Any]:
        items = list(activities)
        distances = cls._values(items, "distance_m")
        elevations = cls._values(items, "elevation_gain_m")
        paces = cls._values(items, "avg_pace_sec_km")
        heart_rates = cls._values(items, "avg_heart_rate")
        days = {item.started_at.date() for item in items if getattr(item, "started_at", None)}
        sports: dict[str, int] = defaultdict(int)
        for item in items:
            sports[getattr(item, "sport_type", None) or "other"] += 1
        return {
            "activity_count": len(items),
            "distance_m": sum(distances) if distances else None,
            "duration_seconds": sum((getattr(item, "duration_seconds", 0) or 0) for item in items) if items else None,
            "elevation_gain_m": sum(elevations) if elevations else None,
            "avg_pace_sec_km": mean(paces) if paces else None,
            "avg_heart_rate": mean(heart_rates) if heart_rates else None,
            "max_heart_rate": max(cls._values(items, "max_heart_rate"), default=None),
            "days_trained": len(days),
            "long_activity_count": sum(1 for item in items if (getattr(item, "duration_seconds", 0) or 0) >= 90 * 60),
            "sports": dict(sports),
        }

    @staticmethod
    def percent_change(current: float | None, previous: float | None) -> float | None:
        if current is None or previous in (None, 0):
            return None
        return round((current - previous) / previous * 100, 1)

    @classmethod
    def compare(cls, current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
        keys = ("distance_m", "duration_seconds", "elevation_gain_m", "activity_count", "avg_pace_sec_km", "avg_heart_rate")
        return {key: cls.percent_change(current.get(key), previous.get(key)) for key in keys}

    @classmethod
    def heart_rate_zones(cls, activity: Any, zones: dict[str, Any] | None = None) -> dict[str, Any] | None:
        config = zones or {}
        max_hr = config.get("max_hr")
        rest_hr = config.get("rest_hr")
        if not max_hr:
            return None
        points = getattr(activity, "track_points", None) or []
        heart_rates = [float(point.heart_rate) for point in points if point.heart_rate is not None]
        if not heart_rates:
            return {"configured": True, "max_hr": max_hr, "rest_hr": rest_hr, "time_seconds": {}}
        boundaries = config.get("custom_zones")
        if boundaries and len(boundaries) == 5:
            limits = [float(value) for value in boundaries]
        elif rest_hr is not None:
            reserve = max_hr - rest_hr
            limits = [rest_hr + reserve * ratio for ratio in (0.6, 0.7, 0.8, 0.9, 1.0)]
        else:
            limits = [max_hr * ratio for ratio in (0.6, 0.7, 0.8, 0.9, 1.0)]
        durations = dict.fromkeys(("Z1", "Z2", "Z3", "Z4", "Z5"), 0.0)
        points = [point for point in points if point.heart_rate is not None]
        for index, point in enumerate(points):
            heart_rate = float(point.heart_rate)
            zone = next((index for index, limit in enumerate(limits) if heart_rate <= limit), 4)
            duration = cls._point_duration(points, index)
            durations[f"Z{zone + 1}"] += duration
        return {"configured": True, "max_hr": max_hr, "rest_hr": rest_hr, "time_seconds": durations}

    @staticmethod
    def _point_duration(points: list[Any], index: int) -> float:
        if index + 1 >= len(points):
            return 0.0
        current = getattr(points[index], "recorded_at", None)
        following = getattr(points[index + 1], "recorded_at", None)
        if not isinstance(current, datetime) or not isinstance(following, datetime):
            return 0.0
        seconds = (following - current).total_seconds()
        return min(max(seconds, 0.0), 60.0)

    @classmethod
    def cardiac_drift(cls, activity: Any) -> dict[str, Any] | None:
        points = getattr(activity, "track_points", None) or []
        valid = [point for point in points if point.heart_rate and point.speed_m_s and point.speed_m_s > 0]
        if len(valid) < 10 or not all(getattr(point, "recorded_at", None) for point in valid):
            return None
        middle = len(valid) // 2
        first, second = valid[:middle], valid[middle:]
        first_efficiency = mean(point.heart_rate / point.speed_m_s for point in first)
        second_efficiency = mean(point.heart_rate / point.speed_m_s for point in second)
        if first_efficiency <= 0:
            return None
        drift = round((second_efficiency - first_efficiency) / first_efficiency * 100, 1)
        return {"percent": drift, "first_avg_hr": round(mean(point.heart_rate for point in first), 1), "second_avg_hr": round(mean(point.heart_rate for point in second), 1), "sample_count": len(valid), "method": "heart_rate_to_speed"}

    @staticmethod
    def training_load(activity: Any, zones: dict[str, Any] | None = None) -> dict[str, Any]:
        """Calculate a transparent duration x HR-intensity score, never a medical metric."""
        duration = float(getattr(activity, "duration_seconds", 0) or 0)
        avg_hr = getattr(activity, "avg_heart_rate", None)
        max_hr = (zones or {}).get("max_hr")
        rest_hr = (zones or {}).get("rest_hr")
        if duration <= 0 or avg_hr is None or max_hr is None or rest_hr is None or max_hr <= rest_hr:
            return {"available": False, "reason": "Durée, FC moyenne, FC repos et FC max configurées requis"}
        intensity = min(1.2, max(0.0, (float(avg_hr) - rest_hr) / (max_hr - rest_hr)))
        return {"available": True, "score": round(duration / 60 * intensity * 100, 1),
                "method": "duration_minutes_x_hr_reserve_ratio_x_100", "intensity_factor": round(intensity, 3),
                "inputs": {"duration_seconds": duration, "avg_heart_rate": avg_hr, "rest_hr": rest_hr, "max_hr": max_hr}}

    @classmethod
    def period_training_load(cls, activities: Iterable[Any], zones: dict[str, Any] | None = None) -> dict[str, Any]:
        loads = [cls.training_load(item, zones) for item in activities]
        available = [item for item in loads if item["available"]]
        if not available:
            return {"available": False, "reason": "Aucune activité ne contient les données nécessaires"}
        return {"available": True, "score": round(sum(item["score"] for item in available), 1),
                "activity_count": len(available), "method": available[0]["method"]}

    @classmethod
    def analyze_period(cls, activities: Iterable[Any], start: date, end: date, previous_start: date | None = None, zones: dict[str, Any] | None = None) -> dict[str, Any]:
        items = list(activities)
        current = [item for item in items if start <= item.started_at.date() <= end]
        previous = []
        if previous_start is not None:
            previous_end = start - timedelta(days=1)
            previous = [item for item in items if previous_start <= item.started_at.date() <= previous_end]
        summary = cls.summarize(current)
        previous_summary = cls.summarize(previous)
        comparison = cls.compare(summary, previous_summary)
        observations = []
        findings = []
        if comparison["distance_m"] is not None:
            direction = "en hausse" if comparison["distance_m"] >= 0 else "en baisse"
            message = f"Distance {direction} de {abs(comparison['distance_m'])} % par rapport à la période précédente."
            observations.append(message)
            findings.append({"type": "comparison", "message": message, "evidence": {
                "metric": "distance_m", "current": summary["distance_m"], "previous": previous_summary["distance_m"],
                "change_percent": comparison["distance_m"], "current_period": {"start": start, "end": end},
                "previous_period": {"start": previous_start, "end": start - timedelta(days=1)} if previous_start else None,
            }})
        if summary["long_activity_count"]:
            message = f"{summary['long_activity_count']} sortie(s) longue(s) ont été enregistrées."
            observations.append(message)
            findings.append({"type": "volume", "message": message, "evidence": {
                "long_activity_count": summary["long_activity_count"], "threshold_duration_seconds": 90 * 60,
            }})
        if summary["activity_count"] == 0:
            message = "Aucune activité disponible sur cette période."
            observations.append(message)
            findings.append({"type": "data_quality", "message": message, "evidence": {"activity_count": 0}})
        return {"period": {"start": start, "end": end}, "comparison_period": {"start": previous_start, "end": start - timedelta(days=1)} if previous_start else None, "summary": summary, "previous": previous_summary, "comparison": comparison, "observations": observations, "findings": findings, "training_load": cls.period_training_load(current, zones)}

    @classmethod
    def analyze_activity(cls, activity: Any, similar_activities: Iterable[Any] = (), zones: dict[str, Any] | None = None) -> dict[str, Any]:
        summary = cls.summarize([activity])
        similar = cls.summarize(similar_activities)
        observations = []
        findings = []
        if summary["long_activity_count"]:
            message = "Sortie longue détectée."
            observations.append(message)
            findings.append({"type": "volume", "message": message, "evidence": {"duration_seconds": summary["duration_seconds"], "threshold_duration_seconds": 90 * 60}})
        if activity.elevation_gain_m is not None and activity.elevation_gain_m >= 1000:
            message = "Dénivelé positif important sur cette séance."
            observations.append(message)
            findings.append({"type": "elevation", "message": message, "evidence": {"elevation_gain_m": activity.elevation_gain_m, "threshold_m": 1000}})
        drift = cls.cardiac_drift(activity)
        if drift and drift["percent"] > 5:
            message = "Une dérive cardiaque a été calculée sur la seconde partie de l’activité."
            observations.append(message)
            findings.append({"type": "cardiac_drift", "message": message, "evidence": drift})
        return {"activity": summary, "comparison": {"similar_activity_count": similar["activity_count"], "similar": similar}, "heart_rate_zones": cls.heart_rate_zones(activity, zones), "cardiac_drift": drift, "training_load": cls.training_load(activity, zones), "observations": observations, "findings": findings}

    @classmethod
    def analyze_goals(cls, goals: Iterable[Any], activities: Iterable[Any], today: date | None = None) -> list[dict[str, Any]]:
        """Describe recent compatible training against configured targets without predicting outcomes."""
        target_day = today or date.today()
        items = list(activities)
        result = []
        for goal in goals:
            metadata = getattr(goal, "metadata_json", None) or (goal.get("metadata_json", {}) if isinstance(goal, dict) else {})
            target_date = getattr(goal, "target_date", None) if not isinstance(goal, dict) else goal.get("target_date")
            goal_type = getattr(goal, "goal_type", None) if not isinstance(goal, dict) else goal.get("goal_type")
            sport = metadata.get("sport_type") or metadata.get("sport")
            compatible = [item for item in items if not sport or getattr(item, "sport_type", None) == sport]
            recent = [item for item in compatible if target_day - timedelta(days=27) <= item.started_at.date() <= target_day]
            summary = cls.summarize(recent)
            target_value = getattr(goal, "target_value", None) if not isinstance(goal, dict) else goal.get("target_value")
            unit = getattr(goal, "unit", None) if not isinstance(goal, dict) else goal.get("unit")
            target = {
                "value": target_value, "unit": unit,
                "distance_m": metadata.get("distance_m"),
                "elevation_gain_m": metadata.get("elevation_gain_m"),
                "duration_seconds": metadata.get("target_duration_seconds"),
            }
            if target["distance_m"] is None and unit in {"km", "kilometre", "kilometers"} and target_value is not None:
                target["distance_m"] = target_value * 1000
            if target["elevation_gain_m"] is None and unit in {"m", "meters", "metres"} and goal_type == "elevation":
                target["elevation_gain_m"] = target_value
            result.append({
                "goal_id": getattr(goal, "id", None) if not isinstance(goal, dict) else goal.get("id"),
                "name": getattr(goal, "name", None) if not isinstance(goal, dict) else goal.get("name"),
                "sport_type": sport,
                "target_date": target_date,
                "days_remaining": (target_date - target_day).days if target_date else None,
                "target": target,
                "recent_28_days": summary,
                "compatible_activity_count": len(compatible),
                "interpretation": "Observation descriptive uniquement; aucune prédiction de réussite n'est calculée.",
            })
        return result

    @classmethod
    def athlete_profile(cls, activities: Iterable[Any], goals: Iterable[Any] = ()) -> dict[str, Any]:
        items = list(activities)
        summary = cls.summarize(items)
        weeks: dict[date, list[Any]] = defaultdict(list)
        for item in items:
            day = item.started_at.date()
            weeks[day - timedelta(days=day.weekday())].append(item)
        weekly = [cls.summarize(values) for values in weeks.values()]
        completed_weeks = weekly[-12:]

        def average(key: str) -> float | None:
            values = [week[key] for week in completed_weeks if week.get(key) is not None]
            return round(mean(values), 1) if values else None

        return {
            "sports": summary["sports"],
            "volume_habitual": {
                "distance_m_weekly": average("distance_m"),
                "elevation_gain_m_weekly": average("elevation_gain_m"),
                "duration_seconds_weekly": average("duration_seconds"),
                "activity_count_weekly": average("activity_count"),
            },
            "frequency": {
                "days_trained_total": summary["days_trained"],
                "activities_total": summary["activity_count"],
                "active_weeks": len(weeks),
            },
            "intensity": {
                "avg_pace_sec_km": summary["avg_pace_sec_km"],
                "avg_heart_rate": summary["avg_heart_rate"],
            },
            "long_activity_count": summary["long_activity_count"],
            "goals": list(goals),
            "data_period": {
                "start": min((item.started_at.date() for item in items), default=None),
                "end": max((item.started_at.date() for item in items), default=None),
            },
        }

    @classmethod
    def build_context(cls, athlete: dict[str, Any], recent: Iterable[Any], weekly: dict[str, Any], monthly: dict[str, Any], goals: list[Any]) -> dict[str, Any]:
        return {
            "athlete": athlete,
            "current_activity": None,
            "recent_activities": [cls.summarize([item]) for item in list(recent)[:10]],
            "weekly_summary": weekly,
            "monthly_summary": monthly,
            "trends": weekly.get("comparison", {}),
            "goals": goals,
            "heart_rate": {"available": weekly.get("summary", {}).get("avg_heart_rate") is not None},
            "training_load": weekly.get("training_load", {"available": False, "reason": "Aucune charge calculée"}),
            "recovery": {"available": False, "reason": "Aucune donnée de récupération disponible"},
        }
