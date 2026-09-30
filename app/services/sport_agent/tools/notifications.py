"""Outil notification — réutilise le service de notifications de ForgeAI."""

from __future__ import annotations

from typing import Any

from app.services.notification import NotificationService
from app.services.sport_agent.tool_registry import ToolContext, ToolSpec

_NOTIFICATION_URL = "/sport/analyses"


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


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="send_notification",
        description=(
            "Envoie une notification à l'utilisateur (BDD + Web Push téléphone). "
            "À n'utiliser que si la notification apporte vraiment quelque chose."
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
]
