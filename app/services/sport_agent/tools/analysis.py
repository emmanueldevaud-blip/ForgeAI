"""Outils d'analyse — réutilisent SportAnalysisService (idempotence + notification)."""

from __future__ import annotations

from typing import Any

from app.services.sport_agent.tool_registry import ToolContext, ToolSpec
from app.services.sport_analysis_service import SportAnalysisService

_DAILY_KINDS = ("morning", "evening")


async def generate_daily_analysis(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Produit l'analyse du matin ou du soir si elle n'existe pas encore."""
    kind = str(args.get("kind") or "").strip().lower()
    if kind not in _DAILY_KINDS:
        raise ValueError(f"kind_invalide:{kind or 'vide'}")
    # Chaque analyse notifie : règle commune au job historique et à l'agent.
    notify = True
    service = SportAnalysisService(ctx.db, ctx.user)
    created, analysis = (
        await service.analyze_morning(notify=notify)
        if kind == "morning"
        else await service.analyze_evening(notify=notify)
    )
    return {
        "kind": kind,
        "created": created,
        "already_existed": analysis is not None and not created,
        "analysis_id": analysis.id if analysis is not None else None,
        "notification": notify,
    }


async def generate_activity_analysis(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Produit le débrief d'une activité si il n'existe pas encore."""
    activity_id = int(args.get("activity_id") or 0)
    notify = True
    service = SportAnalysisService(ctx.db, ctx.user)
    created, analysis = await service.analyze_activity(activity_id, notify=notify)
    return {
        "activity_id": activity_id,
        "created": created,
        "already_existed": analysis is not None and not created,
        "analysis_id": analysis.id if analysis is not None else None,
        "notification": notify,
    }


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="generate_daily_analysis",
        description=(
            "Génère l'analyse du matin ou du soir (idempotente : une seule par jour) "
            "et notifie l'utilisateur."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "morning | evening"},
            },
            "required": ["kind"],
        },
        handler=generate_daily_analysis,
        permission="sport.analysis.read",
        access="write",
    ),
    ToolSpec(
        name="generate_activity_analysis",
        description=(
            "Génère le débrief d'une activité (idempotent : une seule fois par activité). "
            "Par défaut aucune notification ne part : l'agent doit décider explicitement de notifier en passant notify=true."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
                "notify": {"type": "boolean", "description": "Envoyer la notification (défaut false : décision explicite de l'agent)"},
            },
            "required": ["activity_id"],
        },
        handler=generate_activity_analysis,
        permission="sport.analysis.read",
        access="write",
    ),
]
