"""Outils récupération, sommeil et données physiologiques (Garmin)."""

from __future__ import annotations

from typing import Any

from app.services.sport_agent.tool_registry import ToolContext, ToolSpec


async def get_recovery(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """État de récupération : readiness, sommeil, HRV, FC repos, stress, Body Battery."""
    return await ctx.service.recovery_context()


async def get_sleep(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    recovery = await ctx.service.recovery_context()
    latest = recovery.get("latest") or {}
    averages = recovery.get("period_averages") or {}
    return {
        "available": recovery.get("available"),
        "reason": recovery.get("reason"),
        "reference_day": recovery.get("reference_day"),
        "latest": {key: value for key, value in latest.items() if "sleep" in key},
        "period_averages": {key: value for key, value in averages.items() if "sleep" in key},
    }


async def get_health_data(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Tableau compact des données de santé quotidiennes (sommeil, HRV, stress, pas)."""
    days = max(1, min(int(args.get("days") or 14), 90))
    return await ctx.service.health_context(days)


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_recovery",
        description="État de récupération actuel : training readiness, sommeil, HRV, FC repos, stress, Body Battery.",
        input_schema={"type": "object", "properties": {}},
        handler=get_recovery,
        permission="sport.access",
        access="read",
    ),
    ToolSpec(
        name="get_sleep",
        description="Dernières valeurs de sommeil et moyennes de la période.",
        input_schema={"type": "object", "properties": {}},
        handler=get_sleep,
        permission="sport.access",
        access="read",
    ),
    ToolSpec(
        name="get_health_data",
        description="Données de santé quotidiennes Garmin en tableau compact (fenêtre de jours).",
        input_schema={
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "Fenêtre en jours (défaut 14, max 90)"}},
        },
        handler=get_health_data,
        permission="sport.access",
        access="read",
    ),
]
