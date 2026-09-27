"""API Notifications (lecture + abonnement Web Push telephone).

Tout utilisateur authentifie gere ses propres notifications ; aucune
permission RBAC particuliere n'est requise au-dela de l'authentification.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    PushSubscriptionRequest,
    PushSubscriptionResponse,
    UnreadCountResponse,
    UnsubscribeRequest,
)
from app.services.notification import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _response(notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        title=notification.title,
        message=notification.message,
        category=notification.category,
        data=notification.data_json or {},
        is_read=notification.is_read,
        push_sent=notification.push_sent,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: bool = Query(False),
    category: str | None = Query(None, max_length=50),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = NotificationService(db)
    items = await service.list_for_user(
        current_user.id, unread_only=unread_only, category=category, limit=limit
    )
    return NotificationListResponse(
        items=[_response(item) for item in items],
        unread_count=await service.unread_count(current_user.id),
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return UnreadCountResponse(count=await NotificationService(db).unread_count(current_user.id))


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    notification = await NotificationService(db).mark_read(current_user.id, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification non trouvée")
    await db.commit()
    return _response(notification)


@router.post("/read-all", response_model=UnreadCountResponse)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    updated = await NotificationService(db).mark_all_read(current_user.id)
    await db.commit()
    return UnreadCountResponse(count=updated)


@router.get("/push/vapid-public-key")
async def vapid_public_key():
    """Cle publique VAPID (base64url) requise par le navigateur pour s'abonner."""
    return {"publicKey": NotificationService.vapid_public_key()}


@router.post("/push/subscribe", response_model=PushSubscriptionResponse)
async def push_subscribe(
    data: PushSubscriptionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = NotificationService(db)
    try:
        subscription = await service.subscribe(
            current_user.id, endpoint=data.endpoint, p256dh=data.p256dh, auth=data.auth
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return PushSubscriptionResponse(
        endpoint=subscription.endpoint, vapid_public_key=service.vapid_public_key()
    )


@router.post("/push/unsubscribe")
async def push_unsubscribe(
    data: UnsubscribeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    removed = await NotificationService(db).unsubscribe(current_user.id, data.endpoint)
    await db.commit()
    return {"removed": removed}


@router.post("/push/test")
async def push_test(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Envoie une notification de test a l'utilisateur connecte (push best-effort)."""
    service = NotificationService(db)
    notification = await service.send(
        user_id=current_user.id,
        title="Test ForgeAI",
        message="Notifications configurees : tout fonctionne.",
        category="system",
        data={"url": "/sport/analyses"},
    )
    await db.commit()
    return {"push_sent": notification.push_sent}
