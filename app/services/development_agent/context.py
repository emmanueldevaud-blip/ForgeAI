"""Contexte d'exécution de l'Agent Développement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.user import User
from app.models.development import DevelopmentTask, DevelopmentAgentExecution
from app.services.development_agent.tool_registry import DevelopmentToolRegistry, ToolContext


@dataclass
class RunContext:
    """Tout ce dont l'Agent Développement a besoin pendant une exécution."""

    db: AsyncSession
    user: User
    task: DevelopmentTask
    registry: DevelopmentToolRegistry
    settings: Settings
    execution: DevelopmentAgentExecution
    payload: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, str]] = field(default_factory=list)

    def tool_context(self) -> ToolContext:
        payload = dict(self.payload)
        payload["execution_id"] = self.execution.id
        payload["task_id"] = self.task.id
        return ToolContext(
            db=self.db,
            user=self.user,
            task=self.task,
            settings=self.settings,
            payload=payload,
        )