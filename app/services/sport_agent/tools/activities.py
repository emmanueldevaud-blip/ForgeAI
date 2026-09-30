"""Outils lecture d'activités sportives pour l'Agent Sport."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.models.sport import SportActivity
from app.services.sport_agent.tool_registry import ToolContext, ToolSpec


def activity_summary(item: SportActivity) -> dict[str, Any]:
    return {
        "id": item.id,
        "sport_type": item.sport_type,
        "name": item.activity_name,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "duration_minutes": round((item.duration_seconds or 0) / 60, 1),
        "distance_km": round(item.distance_m / 1000, 2) if item.distance_m is not None else None,
        "elevation_gain_m": item.elevation_gain_m,
        "avg_heart_rate": item.avg_heart_rate,
        "max_heart_rate": item.max_heart_rate,
        "avg_pace_sec_km": item.avg_pace_sec_km,
        "source_type": item.source_type,
    }


async def get_recent_activities(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    days = max(1, min(int(args.get("days") or 14), 365))
    limit = max(1, min(int(args.get("limit") or 10), 50))
    sport = str(args.get("sport_type") or "").strip()
    start = datetime.combine(
        datetime.now(timezone.utc).date() - timedelta(days=days - 1), datetime.min.time()
    )
    query = select(SportActivity).where(
        SportActivity.athlete_id == ctx.athlete.id,
        SportActivity.started_at >= start,
    )
    if sport:
        query = query.where(SportActivity.sport_type == sport)
    query = query.order_by(SportActivity.started_at.desc()).limit(limit)
    items = list((await ctx.db.execute(query)).scalars().all())
    return {
        "days": days,
        "count": len(items),
        "activities": [activity_summary(item) for item in items],
    }


async def get_activity(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    activity_id = int(args.get("activity_id") or 0)
    activity = await ctx.service.get_activity(activity_id)
    if activity is None:
        return {"found": False, "activity_id": activity_id}
    analysis = await ctx.service.analyze_activity(activity_id) or {}
    return {
        "found": True,
        "activity": activity_summary(activity),
        "analysis": {
            "comparison": analysis.get("comparison"),
            "heart_rate_zones": analysis.get("heart_rate_zones"),
            "cardiac_drift": analysis.get("cardiac_drift"),
            "training_load": analysis.get("training_load"),
            "observations": analysis.get("observations"),
        },
        "ai_analysis": analysis.get("ai_analysis"),
    }


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_recent_activities",
        description="Liste les activités sportives récentes de l'athlète (filtrables par sport).",
        input_schema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Fenêtre en jours (défaut 14)"},
                "limit": {"type": "integer", "description": "Nombre maximal d'activités (défaut 10, max 50)"},
                "sport_type": {"type": "string", "description": "Filtrer par sport (running, trail, ...)"},
            },
        },
        handler=get_recent_activities,
        permission="sport.activities.read",
        access="read",
    ),
    ToolSpec(
        name="get_activity",
        description="Détaille une activité : analyse déterministe, zones, charge et résultat de l'analyse IA.",
        input_schema={
            "type": "object",
            "properties": {"activity_id": {"type": "integer"}},
            "required": ["activity_id"],
        },
        handler=get_activity,
        permission="sport.activities.read",
        access="read",
    ),
]
