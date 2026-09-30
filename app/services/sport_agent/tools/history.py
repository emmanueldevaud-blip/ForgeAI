"""Outils historique : volumes, tendances et analyses déjà produites."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.sport import SportAnalysis
from app.services.sport_agent.tool_registry import ToolContext, ToolSpec

_ALLOWED_PERIODS = {7, 28, 90, 365}


def _period_days(args: dict[str, Any], default: int = 28) -> int:
    try:
        days = int(args.get("days") or default)
    except (TypeError, ValueError):
        return default
    return days if days in _ALLOWED_PERIODS else default


async def get_training_history(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Volumes, comparaison de période et charge d'entraînement."""
    return await ctx.service.analyze_period(_period_days(args))


async def list_previous_analyses(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Analyses déjà produites par le coach (mémoire de lecture de l'agent)."""
    limit = max(1, min(int(args.get("limit") or 10), 30))
    result = await ctx.db.execute(
        select(SportAnalysis)
        .where(SportAnalysis.athlete_id == ctx.athlete.id)
        .order_by(SportAnalysis.generated_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    return {
        "count": len(rows),
        "analyses": [
            {
                "id": row.id,
                "type": row.analysis_type,
                "day": row.analysis_day.isoformat() if row.analysis_day else None,
                "title": row.title,
                "summary": row.summary,
                "activity_id": row.activity_id,
                "notification_sent": row.notification_sent,
                "generated_at": row.generated_at.isoformat() if row.generated_at else None,
            }
            for row in rows
        ],
    }


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_training_history",
        description="Synthèse d'entraînement sur une période (7, 28, 90 ou 365 jours) : volumes, comparaison, charge.",
        input_schema={
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "7, 28, 90 ou 365 (défaut 28)"}},
        },
        handler=get_training_history,
        permission="sport.analysis.read",
        access="read",
    ),
    ToolSpec(
        name="list_previous_analyses",
        description="Analyses du coach déjà générées (matin, soir, sortie) : mémoire de ce qui a été dit.",
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Nombre d'analyses (défaut 10, max 30)"}},
        },
        handler=list_previous_analyses,
        permission="sport.analysis.read",
        access="read",
    ),
]
