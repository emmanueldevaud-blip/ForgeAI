"""Outil notification — réutilise le service de notifications de ForgeAI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.models.notification import Notification
from app.services import coach_feed
from app.services.notification import NotificationService, is_notification_quiet_time
from app.services.sport_agent.tool_registry import ToolContext, ToolSpec

_NOTIFICATION_URL = "/sport/analyses"
_COACH_TIP_URL = "/ai"


async def _notification_suppression(ctx: ToolContext) -> str | None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if is_notification_quiet_time(now):
        return "quiet_hours"

    cooldown_hours = max(1, settings.SPORT_AGENT_NOTIFICATION_COOLDOWN_HOURS)
    cutoff = (now - timedelta(hours=cooldown_hours)).replace(tzinfo=None)
    recent = await ctx.db.scalar(
        select(Notification.id)
        .where(
            Notification.user_id == ctx.user.id,
            Notification.category.in_(("sport_agent", coach_feed.COACH_TIP_CATEGORY, "sport_analysis")),
            Notification.created_at >= cutoff,
        )
        .order_by(Notification.created_at.desc())
        .limit(1)
    )
    return "cooldown" if recent is not None else None


async def send_notification(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title") or "").strip()
    message = str(args.get("message") or "").strip()
    if not title or not message:
        raise ValueError("notification_incomplete")
    suppression = await _notification_suppression(ctx)
    if suppression:
        return {"user_id": ctx.user.id, "suppressed": suppression, "push_sent": False}
    notification = await NotificationService(ctx.db).send(
        user_id=ctx.user.id,
        title=title[:200],
        message=message,
        category="sport_agent",
        data={"url": _NOTIFICATION_URL, "source": "sport_agent"},
    )
    return {
        "notification_id": notification.id,
        "user_id": ctx.user.id,
        "push_sent": notification.push_sent,
    }


async def send_coach_tip(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Conseil personnalisé du coach : notification + message dans l'assistant.

    Plafonné à ``COACH_TIP_DAILY_LIMIT`` par jour ; au-delà, l'outil refuse
    (le modèle voit l'erreur et termine sans forcer).
    """
    title = str(args.get("title") or "").strip()
    message = str(args.get("message") or "").strip()
    if not title or not message:
        raise ValueError("conseil_incomplet")
    suppression = await _notification_suppression(ctx)
    if suppression:
        return {"user_id": ctx.user.id, "suppressed": suppression, "push_sent": False}
    limit = max(0, get_settings().COACH_TIP_DAILY_LIMIT)
    left = await coach_feed.coach_tips_left(ctx.db, ctx.user)
    if left <= 0:
        raise ValueError(f"quota_conseils_atteint:{limit}")
    notification = await NotificationService(ctx.db).send(
        user_id=ctx.user.id,
        title=title[:200],
        message=message,
        category=coach_feed.COACH_TIP_CATEGORY,
        data={"url": _COACH_TIP_URL, "source": "sport_agent"},
    )
    await coach_feed.publish(
        ctx.db, ctx.user, content=f"{title}\n\n{message}", model="coach"
    )
    return {
        "notification_id": notification.id,
        "user_id": ctx.user.id,
        "push_sent": notification.push_sent,
        "tips_left_today": left - 1,
        "daily_limit": limit,
    }


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="send_notification",
        description=(
            "Envoie une notification à l'utilisateur (BDD + Web Push téléphone). "
            "À n'utiliser que si la notification apporte vraiment quelque chose. "
            "Conseil d'entraînement/récupération → send_coach_tip."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "message": {"type": "string", "description": "4 à 6 lignes, lisible sur montre"},
            },
            "required": ["title", "message"],
        },
        handler=send_notification,
        permission="sport.access",
        access="write",
    ),
    ToolSpec(
        name="send_coach_tip",
        description=(
            "Conseil du coach : notification + publication dans l'Assistant IA. "
            "Plafond coach_tip_daily_limit par jour, refus quota_conseils_atteint. "
            "Vérifier coach_tips_left dans le brief AVANT d'appeler : si 0, NE PAS appeler."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "message": {"type": "string", "description": "Conseil personnalisé, 4 à 6 lignes"},
            },
            "required": ["title", "message"],
        },
        handler=send_coach_tip,
        permission="sport.access",
        access="write",
    ),
]
