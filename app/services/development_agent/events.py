"""Événements de l'Agent Développement."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.development import DevelopmentTask, DevelopmentTaskStatus
from app.models.user import User


async def schedule_development_event(
    db: AsyncSession,
    user: User,
    trigger: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Planifie un événement pour l'Agent Développement (BackgroundTasks)."""
    settings = get_settings()
    if not settings.DEVELOPMENT_AGENT_ENABLED:
        return

    task = DevelopmentTask(
        user_id=user.id,
        title=payload.get("title") or trigger,
        request=payload.get("request") or "",
        repository=payload.get("repository") or ".",
        status="pending",
        context=payload or {},
    )
    db.add(task)
    await db.commit()


async def emit_development_event(
    db: AsyncSession,
    user: User,
    trigger: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Réveil immédiat de l'Agent Développement sur la session fournie."""
    from app.services.development_agent.service import run_development_trigger
    return await run_development_trigger(db, user, trigger, payload)