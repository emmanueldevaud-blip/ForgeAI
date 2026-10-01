"""Service de l'Agent Développement."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, Settings
from app.models.user import User
from app.models.development import DevelopmentTask, DevelopmentTaskStatus, DevelopmentAgentExecution
from app.services.development_agent.orchestrator import DevelopmentOrchestrator
from app.services.development_agent.opencode import get_opencode_client
from app.services.development_agent.tools import build_registry

logger = logging.getLogger(__name__)


class DevelopmentService:
    """Service principal de l'Agent Développement."""

    def __init__(self, db: AsyncSession, user: User, settings: Settings | None = None):
        self.db = db
        self.user = user
        self.settings = settings or get_settings()
        self.registry = build_registry()

    async def create_task(
        self,
        title: str,
        request: str,
        repository: str = ".",
        payload: dict[str, Any] | None = None,
    ) -> DevelopmentTask:
        """Crée une nouvelle tâche de développement."""
        task = DevelopmentTask(
            user_id=self.user.id,
            title=title,
            request=request,
            repository=repository,
            status="pending",
            context=payload or {},
        )
        self.db.add(task)
        await self.db.flush()

        execution = DevelopmentAgentExecution(
            task_id=task.id,
            trigger="created",
            status="pending",
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(task)

        logger.info("[DEV-AGENT] task=%s created user=%s", task.id, self.user.id)
        return task

    async def get_task(self, task_id: str) -> DevelopmentTask | None:
        result = await self.db.execute(
            select(DevelopmentTask).where(
                DevelopmentTask.id == task_id,
                DevelopmentTask.user_id == self.user.id,
            )
        )
        return result.scalar_one_or_none()

    async def list_tasks(self, status: str | None = None, limit: int = 20) -> list[DevelopmentTask]:
        query = select(DevelopmentTask).where(DevelopmentTask.user_id == self.user.id)
        if status:
            query = query.where(DevelopmentTask.status == status)
        query = query.order_by(DevelopmentTask.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def run_task(self, task_id: str, trigger: str = "user_request", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Exécute une tâche de développement."""
        task = await self.get_task(task_id)
        if not task:
            return {"status": "not_found", "error": "Tâche non trouvée"}

        # Vérifier feature flag
        if not self.settings.DEVELOPMENT_AGENT_ENABLED:
            return {"status": "disabled", "error": "Agent Développement désactivé"}

        # Vérifier que la tâche n'est pas déjà en cours
        if task.status in ("analyzing", "planning", "developing", "testing", "fixing"):
            return {"status": "busy", "error": "Tâche déjà en cours"}

        # Créer l'exécution
        execution = DevelopmentAgentExecution(
            task_id=task.id,
            trigger=trigger,
            status="running",
        )
        self.db.add(execution)
        await self.db.commit()

        # Mettre à jour le statut de la tâche
        task.status = "analyzing"
        task.updated_at = datetime.now(timezone.utc)
        await self.db.commit()

        # Préparer le contexte
        from app.core.config import get_settings
        from app.services.development_agent.context import RunContext as RunContextModel

        run_ctx = RunContextModel(
            db=self.db,
            user=self.user,
            task=task,
            registry=build_registry(),
            settings=self.settings,
            execution=execution,
            payload=payload or {},
        )

        # Exécuter l'orchestrateur
        orchestrator = DevelopmentOrchestrator(run_ctx)
        try:
            status = await orchestrator.run()
            task.status = "ready_for_review" if status == "completed" else status
        except Exception as exc:
            logger.exception("[DEV-AGENT] task=%s execution failed", task.id)
            task.status = "failed"
            task.error = str(exc)
        finally:
            task.updated_at = datetime.now(timezone.utc)
            await self.db.commit()

        result_json = execution.result_json or {}
        return {
            "status": task.status,
            "task_id": task.id,
            "execution_id": execution.id,
            "answer": result_json.get("answer"),
            "summary": result_json.get("summary"),
        }


async def run_development_trigger(
    db: AsyncSession,
    user: User,
    trigger: str,
    payload: dict[str, Any] | None = None,
    title: str | None = None,
    request: str | None = None,
) -> dict[str, Any]:
    """Point d'entrée pour réveiller l'Agent Développement (depuis API, scheduler, etc.)."""
    settings = get_settings()

    if not settings.DEVELOPMENT_AGENT_ENABLED:
        return {"status": "disabled", "trigger": trigger}

    service = DevelopmentService(db, user)

    # Si trigger est "user_request", créer une nouvelle tâche
    if trigger == "user_request":
        if not request:
            return {"status": "error", "error": "Request requis pour user_request"}
        task = await service.create_task(
            title=title or request[:100],
            request=request,
            repository=settings.OPENCODE_WORK_DIR or ".",
            payload=payload,
        )
        return await service.run_task(task.id, trigger, payload)

    return {"status": "unknown_trigger", "trigger": trigger}