"""Outil notification — réutilise le service de notifications de ForgeAI."""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.services import coach_feed
from app.services.notification import NotificationService
from app.services.sport_agent.tool_registry import ToolContext, ToolSpec

_NOTIFICATION_URL = "/sport/analyses"
_COACH_TIP_URL = "/ai"


async def send_notification(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title") or "").strip()
    message = str(args.get("message") or "").strip()
    if not title or not message:
        raise ValueError("notification_incomplete")
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
            "Plafond COACH_TIP_DAILY_LIMIT par jour, refus quota_conseils_atteint."
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
