"""Assemblage du registre d'outils de l'Agent Sport.

Pour ajouter un outil : créer le spec dans le module concerné puis l'ajouter
à ``TOOL_MODULES``. L'outil est aussitôt exposé au modèle et soumis au RBAC.
"""

from __future__ import annotations

from app.services.sport_agent.tool_registry import SportToolRegistry, ToolSpec
from app.services.sport_agent.tools import (
    activities,
    analysis,
    garmin,
    history,
    notifications,
    objectives,
    recommendations,
    recovery,
    training,
    web_fetch,
    web_search,
)

TOOL_MODULES = (
    activities,
    garmin,
    objectives,
    recovery,
    history,
    training,
    recommendations,
    notifications,
    analysis,
    web_search,
    web_fetch,
)


def build_registry() -> SportToolRegistry:
    registry = SportToolRegistry()
    for module in TOOL_MODULES:
        for spec in module.SPECS:
            registry.register(spec)
    return registry


__all__ = ["TOOL_MODULES", "ToolSpec", "build_registry"]
