"""Outil d'état de l'intégration Garmin (connexion et fraîcheur des données)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.models.sport import SportGarminConnection, SportHealthDaily
from app.services.sport_agent.tool_registry import ToolContext, ToolSpec


async def get_garmin_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    connection = await ctx.db.scalar(
        select(SportGarminConnection).where(SportGarminConnection.athlete_id == ctx.athlete.id)
    )
    if connection is None:
        return {"connected": False, "reason": "aucune_connexion_garmin"}
    start = (datetime.now(timezone.utc).date() - timedelta(days=6)).isoformat()
    health_days = (
        await ctx.db.execute(
            select(func.count(SportHealthDaily.id)).where(
                SportHealthDaily.athlete_id == ctx.athlete.id,
                SportHealthDaily.day >= start,
            )
        )
    ).scalar() or 0
    return {
        "connected": connection.status == "connected",
        "status": connection.status,
        "last_sync_at": connection.last_sync_at.isoformat() if connection.last_sync_at else None,
        "last_sync_status": connection.last_sync_status,
        "last_error": (connection.last_error or "")[:200] or None,
        "health_days_last_7": health_days,
    }


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_garmin_status",
        description="État de la connexion Garmin : dernière synchronisation, erreurs, fraîcheur des données de santé.",
        input_schema={"type": "object", "properties": {}},
        handler=get_garmin_status,
        permission="sport.access",
        access="read",
    ),
]
