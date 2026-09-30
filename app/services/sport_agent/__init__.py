"""Agent Sport autonome de ForgeAI.

L'agent observe les données d'un athlète, décide via la passerelle IA en
appelant des outils contrôlés par RBAC, exécute ses actions, vérifie leur
résultat en base puis réévalue avant de conclure.

Entrées publiques :
* ``get_sport_tool_registry`` — registre partagé des outils ;
* ``run_agent_trigger`` — réveil unique (matin, soir, activité, utilisateur…) ;
* ``agent_enabled`` — drapeau ``SPORT_AGENT_ENABLED``.
"""

from __future__ import annotations

from functools import lru_cache

from app.services.sport_agent.tool_registry import (
    SportToolRegistry,
    ToolContext,
    ToolResult,
    ToolSpec,
)
from app.services.sport_agent.tools import build_registry
from app.services.sport_agent.triggers import TRIGGERS, agent_enabled, run_agent_trigger

__all__ = [
    "TRIGGERS",
    "SportToolRegistry",
    "ToolContext",
    "ToolResult",
    "ToolSpec",
    "agent_enabled",
    "get_sport_tool_registry",
    "run_agent_trigger",
]


@lru_cache(maxsize=1)
def get_sport_tool_registry() -> SportToolRegistry:
    """Registre d'outils unique construit une seule fois par processus."""
    return build_registry()
