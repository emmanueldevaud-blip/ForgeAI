"""Contexte d'exécution d'un réveil de l'Agent Sport."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.sport import SportAgentExecution, SportAthlete
from app.models.user import User
from app.services.sport_agent.tool_registry import SportToolRegistry, ToolContext


@dataclass
class RunContext:
    """Tout ce dont l'agent a besoin pendant une exécution."""

    db: AsyncSession
    user: User
    athlete: SportAthlete
    trigger: str
    registry: SportToolRegistry
    settings: Settings
    execution: SportAgentExecution
    payload: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, str]] = field(default_factory=list)

    def tool_context(self) -> ToolContext:
        payload = dict(self.payload)
        payload["execution_id"] = self.execution.id
        payload["trigger"] = self.trigger
        return ToolContext(db=self.db, user=self.user, athlete=self.athlete, payload=payload)
