"""Outils historique : volumes, tendances et analyses déjà produites."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.sport import SportAnalysis
from app.services.sport_agent.tool_registry import ToolContext, ToolSpec

_ALLOWED_PERIODS = {7, 28, 90, 365}

# Plafond de caractères de corps d'analyse ajouté au résultat (budget tokens) :
# ~2 200 tokens au total, quelle que soit la valeur de ``limit``.
_DETAIL_CONTENT_CHARS = 6_000


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
    """Analyses déjà produites par le coach (mémoire de lecture de l'agent).

    Le corps complet des analyses reste en base : il n'est ajouté au résultat
    que lorsque ``detail`` est demandé (tronqué), pour ne pas gonfler les
    prompts et les tours d'outils.
    """
    limit = max(1, min(int(args.get("limit") or 10), 30))
    detail = bool(args.get("detail"))
    result = await ctx.db.execute(
        select(SportAnalysis)
        .where(SportAnalysis.athlete_id == ctx.athlete.id)
        .order_by(SportAnalysis.generated_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    budget = _DETAIL_CONTENT_CHARS if detail else 0
    analyses: list[dict[str, Any]] = []
    for row in rows:
        entry: dict[str, Any] = {
            "id": row.id,
            "type": row.analysis_type,
            "day": row.analysis_day.isoformat() if row.analysis_day else None,
            "title": row.title,
            "summary": row.summary,
            "activity_id": row.activity_id,
            "notification_sent": row.notification_sent,
            "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        }
        if budget > 0:
            content = (row.content or "")[:min(2_000, budget)]
            entry["content"] = content
            budget -= len(content)
        analyses.append(entry)
    return {"count": len(rows), "analyses": analyses}


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
        description="Analyses du coach déjà générées (matin, soir, sortie) : mémoire de ce qui a été dit. detail=true ajoute le corps complet (tronqué).",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Nombre d'analyses (défaut 10, max 30)"},
                "detail": {"type": "boolean", "description": "Inclure le corps complet des analyses"},
            },
        },
        handler=list_previous_analyses,
        permission="sport.analysis.read",
        access="read",
    ),
]
