"""Outils objectifs — la page Objectifs est la source de vérité de l'agent."""

from __future__ import annotations

from typing import Any

from app.services.sport_agent.tool_registry import ToolContext, ToolSpec


def _goal_dict(goal) -> dict[str, Any]:
    return {
        "id": goal.id,
        "name": goal.name,
        "goal_type": goal.goal_type,
        "target_value": goal.target_value,
        "unit": goal.unit,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "status": goal.status,
        "metadata": goal.metadata_json or {},
    }


async def get_active_objectives(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    goals = await ctx.service.list_goals()
    active = [goal for goal in goals if (goal.status or "active") == "active"]
    return {
        "count": len(active),
        "objectives": [_goal_dict(goal) for goal in active],
    }


async def get_goal_analysis(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Écart entre l'objectif et l'entraînement des 28 derniers jours."""
    analysis = await ctx.service.analyze_goals()
    return {"count": len(analysis), "objectives": analysis}


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_active_objectives",
        description="Liste les objectifs sportifs actifs (page Objectifs) : cible, échéance, type.",
        input_schema={"type": "object", "properties": {}},
        handler=get_active_objectives,
        permission="sport.goals.read",
        access="read",
    ),
    ToolSpec(
        name="get_goal_analysis",
        description="Écart entre chaque objectif et l'entraînement des 28 derniers jours (volume, jours restants).",
        input_schema={"type": "object", "properties": {}},
        handler=get_goal_analysis,
        permission="sport.goals.read",
        access="read",
    ),
]
