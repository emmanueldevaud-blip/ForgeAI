"""Registre complet des outils de l'Agent Développement."""

from __future__ import annotations

from app.services.development_agent.tool_registry import DevelopmentToolRegistry, ToolSpec
from app.services.development_agent.tools.development import DEVELOPMENT_SPECS
from app.services.development_agent.tools.git import GIT_SPECS
from app.services.development_agent.tools.production import PRODUCTION_SPECS
from app.services.development_agent.tools.reading import READ_SPECS


def build_registry() -> DevelopmentToolRegistry:
    """Construit le registre complet des outils de l'Agent Développement."""
    registry = DevelopmentToolRegistry()

    # Outils de lecture
    for spec in READ_SPECS:
        registry.register(spec)

    # Outils de développement
    for spec in DEVELOPMENT_SPECS:
        registry.register(spec)

    # Outils Git
    for spec in GIT_SPECS:
        registry.register(spec)

    # Outils Production
    for spec in PRODUCTION_SPECS:
        registry.register(spec)

    return registry


__all__ = ["build_registry", "DevelopmentToolRegistry", "ToolSpec"]