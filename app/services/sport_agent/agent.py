"""Exécution d'un réveil de l'Agent Sport.

Une exécution = un trigger (matin, soir, activité, demande utilisateur, …).
L'Agent crée la trace en base, puis délègue la boucle décisionnelle à
l'orchestrateur.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.sport import SportAgentExecution, SportAthlete
from app.models.user import User
from app.services.sport_agent.context import RunContext
from app.services.sport_agent.orchestrator import AgentOrchestrator
from app.services.sport_agent.tool_registry import SportToolRegistry

logger = logging.getLogger(__name__)


class SportAgent:
    def __init__(
        self,
        db: AsyncSession,
        user: User,
        athlete: SportAthlete,
        trigger: str,
        payload: dict[str, Any] | None = None,
        history: list[dict[str, str]] | None = None,
        registry: SportToolRegistry | None = None,
        settings: Settings | None = None,
    ):
        self.db = db
        self.user = user
        self.athlete = athlete
        self.trigger = trigger
        self.payload = payload or {}
        self.history = history or []
        self.settings = settings or get_settings()
        if registry is None:
            from app.services.sport_agent import get_sport_tool_registry

            registry = get_sport_tool_registry()
        self.registry = registry

    async def run(self) -> SportAgentExecution:
        execution = SportAgentExecution(
            user_id=self.user.id,
            athlete_id=self.athlete.id,
            trigger=self.trigger,
            status="running",
            summary="",
            steps_json=[],
            result_json={},
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(execution)
        await self.db.flush()
        # Trace durable avant toute action : une action annulée ne doit pas
        # effacer le journal de l'exécution.
        await self.db.commit()

        ctx = RunContext(
            db=self.db,
            user=self.user,
            athlete=self.athlete,
            trigger=self.trigger,
            registry=self.registry,
            settings=self.settings,
            execution=execution,
            payload=dict(self.payload),
            history=list(self.history),
        )
        return await AgentOrchestrator(ctx).execute()
