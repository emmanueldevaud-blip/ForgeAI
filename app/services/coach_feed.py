"""Fil « Coach & Analyses » de l'Assistant IA.

Les analyses automatiques (matin, soir, sortie) et les conseils ponctuels du
coach sont publiés comme messages dans une conversation permanente par
utilisateur (module ``coach``) : l'utilisateur retrouve tout dans la page
Assistant IA, en plus de la notification téléphone.

Deux règles :

* publication best-effort : un échec n'annule jamais une analyse ni une
  notification ;
* quota quotidien des conseils ponctuels : ``COACH_TIP_DAILY_LIMIT`` par jour,
  compté sur les notifications de catégorie ``coach_tip`` déjà émises.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.maintenance import AIConversation, AIMessage
from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger(__name__)

COACH_MODULE = "coach"
COACH_CONVERSATION_TITLE = "Coach & Analyses"
COACH_TIP_CATEGORY = "coach_tip"
COACH_FEED_MODEL = "coach"


async def publish(db: AsyncSession, user: User, *, content: str, model: str = COACH_FEED_MODEL) -> bool:
    """Ajoute un message du coach à la conversation dédiée de l'utilisateur."""
    text = (content or "").strip()
    if not text:
        return False
    try:
        conversation = await db.scalar(
            select(AIConversation)
            .where(AIConversation.user_id == user.id, AIConversation.module == COACH_MODULE)
            .order_by(AIConversation.id.desc())
            .limit(1)
        )
        if conversation is None:
            conversation = AIConversation(
                user_id=user.id,
                module=COACH_MODULE,
                title=COACH_CONVERSATION_TITLE,
            )
            db.add(conversation)
            await db.flush()
        db.add(
            AIMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=text,
                model=model,
            )
        )
        await db.commit()
        return True
    except Exception:
        # Best-effort : la publication ne doit jamais faire échouer l'appelant.
        await db.rollback()
        logger.exception("[COACH-FEED] Publication impossible (user %s)", user.id)
        return False


def _local_day_start(now: datetime | None = None) -> datetime:
    """Début du jour courant (fuseau des analyses) en UTC naïf (SQL)."""
    settings = get_settings()
    try:
        tz = ZoneInfo(settings.SPORT_ANALYSIS_TIMEZONE)
    except Exception:  # noqa: BLE001 - ZoneInfoNotFound
        tz = UTC
    local = (now or datetime.now(UTC)).astimezone(tz)
    start = datetime.combine(local.date(), time.min, tzinfo=tz)
    return start.astimezone(UTC).replace(tzinfo=None)


async def coach_tips_sent_today(db: AsyncSession, user: User, now: datetime | None = None) -> int:
    """Conseils ponctuels déjà envoyés à l'utilisateur aujourd'hui."""
    start = _local_day_start(now)
    count = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.category == COACH_TIP_CATEGORY,
            Notification.created_at >= start,
        )
    )
    return int(count or 0)


async def coach_tips_left(db: AsyncSession, user: User, now: datetime | None = None) -> int:
    """Conseils ponctuels encore disponibles aujourd'hui (jamais négatif)."""
    limit = max(0, get_settings().COACH_TIP_DAILY_LIMIT)
    sent = await coach_tips_sent_today(db, user, now)
    return max(0, limit - sent)
