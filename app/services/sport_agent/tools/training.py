"""Outil charge d'entraînement."""

from __future__ import annotations

from typing import Any

from app.services.sport_agent.tool_registry import ToolContext, ToolSpec
from app.services.sport_agent.tools.history import _period_days


async def get_training_load(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Charge d'entraînement calculée sur la période demandée."""
    days = _period_days(args, default=28)
    period = await ctx.service.analyze_period(days)
    return {
        "days": days,
        "training_load": period.get("training_load"),
        "summary": period.get("summary"),
        "comparison": period.get("comparison"),
    }


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_training_load",
        description="Charge d'entraînement de la période (durée, distance, tendance vs période précédente).",
        input_schema={
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "7, 28, 90 ou 365 (défaut 28)"}},
        },
        handler=get_training_load,
        permission="sport.analysis.read",
        access="read",
    ),
]
