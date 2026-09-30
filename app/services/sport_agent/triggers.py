"""Réveils de l'Agent Sport : catalogue des triggers et exécution unique.

Un trigger décrit *quand* l'agent est réveillé ; l'agent décide lui-même
*quoi faire*. Le repli sur l'analyse historique est du ressort de l'appelant :
ce module renvoie un résultat structuré, jamais d'exception métier.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.sport import SportAgentExecution
from app.models.user import User
from app.services.sport_agent.agent import SportAgent
from app.services.sport_agent.tool_registry import SportToolRegistry

logger = logging.getLogger(__name__)

TRIGGERS = (
    "morning",
    "evening",
    "activity",
    "user_request",
    "objective_created",
    "objective_updated",
    "garmin_sync",
    "recovery_change",
    "training_completed",
    "training_missed",
    "anomaly_detected",
)

# Déclencheurs émis par un événement métier (voir ``sport_agent.events``.
# Ils sont protégés par le cooldown par athlète/déclencheur pour éviter
# qu'une même synchronisation ou un même événement ne réveille plusieurs
# fois l'agent. ``morning``/``evening``/``activity`` gardent la gestion du
# cycle planifié, ``user_request`` ne doit jamais être différé.
EVENT_TRIGGERS = (
    "objective_created",
    "objective_updated",
    "garmin_sync",
    "recovery_change",
    "training_completed",
    "training_missed",
    "anomaly_detected",
)


def agent_enabled() -> bool:
    return bool(get_settings().SPORT_AGENT_ENABLED)


async def agent_woken_recently(
    db: AsyncSession,
    athlete_id: int,
    trigger: str,
    now: datetime | None = None,
) -> bool:
    """True si l'agent a déjà été réveillé pour ce déclencheur depuis moins de
    ``AGENT_TRIGGER_COOLDOWN_MINUTES`` (idempotence des événements)."""
    from app.services.sport_analysis_service import AGENT_TRIGGER_COOLDOWN_MINUTES

    now = now or datetime.now(timezone.utc)
    started_at = await db.scalar(
        select(SportAgentExecution.started_at)
        .where(
            SportAgentExecution.athlete_id == athlete_id,
            SportAgentExecution.trigger == trigger,
        )
        .order_by(SportAgentExecution.started_at.desc())
        .limit(1)
    )
    if started_at is None:
        return False
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return now - started_at < timedelta(minutes=AGENT_TRIGGER_COOLDOWN_MINUTES)


async def run_agent_trigger(
    db: AsyncSession,
    user: User,
    trigger: str,
    payload: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
    registry: SportToolRegistry | None = None,
) -> dict[str, Any]:
    """Réveille l'Agent Sport. Renvoie ``{"status": ...}`` ; ``disabled``
    signifie que le drapeau est off, ``failed``/``fallback`` que l'appelant
    doit enchaîner sur le traitement historique."""
    from app.services.sport import SportService

    base: dict[str, Any] = {"trigger": trigger, "execution_id": None, "answer": ""}
    if not agent_enabled():
        return {**base, "status": "disabled"}
    if trigger not in TRIGGERS:
        logger.warning("[SPORT-AGENT] event=unknown_trigger trigger=%s", trigger)
        return {**base, "status": "unknown_trigger"}

    try:
        athlete = await SportService(db, user).get_or_create_athlete()
        if trigger in EVENT_TRIGGERS and await agent_woken_recently(db, athlete.id, trigger):
            logger.info(
                "[SPORT-AGENT] event=cooldown trigger=%s athlete=%s", trigger, athlete.id
            )
            return {**base, "status": "cooldown"}
        agent = SportAgent(
            db=db,
            user=user,
            athlete=athlete,
            trigger=trigger,
            payload=payload,
            history=history,
            registry=registry,
        )
        execution = await agent.run()
    except Exception:
        logger.exception("[SPORT-AGENT] event=run_failed trigger=%s", trigger)
        return {**base, "status": "failed"}

    result = execution.result_json if isinstance(execution.result_json, dict) else {}
    return {
        **base,
        "status": execution.status,
        "execution_id": execution.id,
        "summary": execution.summary or "",
        "answer": str(result.get("answer") or ""),
        "created_analyses": int(result.get("created_analyses") or 0),
        "actions": len(result.get("actions") or []),
        "objective_id": execution.objective_id,
        "provider": execution.provider,
        "model": execution.model,
        "error": execution.error,
    }
