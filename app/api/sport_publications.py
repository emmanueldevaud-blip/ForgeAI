"""Routes API pour les publications Instagram (module Sport)."""

import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sport import SportActivity

from app.api.deps import get_db, require_module_enabled, require_permission
from app.models.user import User
from app.schemas.sport import (
    SportActivityResponse,
    SportPublicationGenerateRequest,
    SportPublicationListResponse,
    SportPublicationResponse,
    SportPublicationSettingsResponse,
    SportPublicationSettingsUpdate,
    SportPublicationUpdate,
)
from app.services.sport_publications import (
    SportPublicationService,
    fire_publication_notifications,
    schedule_publication_notifications,
    style_labels,
)
from app.services.sport_instagram import SportInstagramConnectService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sport/publications",
    tags=["sport"],
    dependencies=[Depends(require_module_enabled("sport"))],
)


async def get_pub_service(
    current_user: User = Depends(require_permission("sport.publications.read")),
    db: AsyncSession = Depends(get_db),
) -> SportPublicationService:
    return SportPublicationService(db, current_user)


async def get_pub_write_service(
    current_user: User = Depends(require_permission("sport.publications.write")),
    db: AsyncSession = Depends(get_db),
) -> SportPublicationService:
    return SportPublicationService(db, current_user)


async def get_meta_service(
    current_user: User = Depends(require_permission("sport.publications.read")),
    db: AsyncSession = Depends(get_db),
) -> SportInstagramConnectService:
    return SportInstagramConnectService(db)


async def get_meta_write_service(
    current_user: User = Depends(require_permission("sport.publications.write")),
    db: AsyncSession = Depends(get_db),
) -> SportInstagramConnectService:
    return SportInstagramConnectService(db)


@router.get("/styles")
async def list_publication_styles(
    service: SportPublicationService = Depends(get_pub_service),
):
    return {"styles": style_labels()}


@router.get("/settings", response_model=SportPublicationSettingsResponse)
async def get_publication_settings(
    service: SportPublicationService = Depends(get_pub_write_service),
):
    return await service.get_settings()


@router.put("/settings", response_model=SportPublicationSettingsResponse)
async def update_publication_settings(
    data: SportPublicationSettingsUpdate,
    service: SportPublicationService = Depends(get_pub_write_service),
):
    return await service.update_settings(data)


@router.get("", response_model=SportPublicationListResponse)
async def list_publications(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: SportPublicationService = Depends(get_pub_service),
):
    data = await service.list_publications(status=status, page=page, page_size=page_size)
    # attache activite aux items
    from app.models.sport import SportActivity

    for pub in data["items"]:
        if getattr(pub, "activity", None) is None:
            res = await service.db.execute(
                select(SportActivity).where(SportActivity.id == pub.activity_id)
            )
            pub.activity = res.scalar_one_or_none()
    return data


@router.get("/activities")
async def list_recent_activities(
    limit: int = Query(20, ge=1, le=100),
    service: SportPublicationService = Depends(get_pub_service),
):
    rows = await service.recent_activities_for_publication(limit=limit)
    return {"items": rows}


@router.get("/activity/{activity_id}")
async def get_publication_for_activity(
    activity_id: int,
    service: SportPublicationService = Depends(get_pub_service),
):
    pub = await service.get_for_activity(activity_id)
    if pub is None:
        raise HTTPException(status_code=404, detail="Aucune publication pour cette activite")
    activity = await service.get_activity(activity_id)
    pub.activity = activity
    return pub


@router.post("/activity/{activity_id}/generate", response_model=SportPublicationResponse)
async def generate_publication(
    activity_id: int,
    data: SportPublicationGenerateRequest,
    service: SportPublicationService = Depends(get_pub_write_service),
):
    try:
        pub = await service.generate(activity_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Generation publication impossible")
        raise HTTPException(status_code=503, detail="Generation IA impossible") from exc
    activity = await service.get_activity(activity_id)
    pub.activity = activity
    # memorise le dernier ton utilise
    try:
        await service.update_settings(
            SportPublicationSettingsUpdate(last_styles=data.styles, last_custom_instructions=data.custom_instructions)
        )
    except Exception:
        pass
    return pub


@router.get("/{publication_id}", response_model=SportPublicationResponse)
async def get_publication(
    publication_id: int,
    service: SportPublicationService = Depends(get_pub_service),
):
    pub = await service.get_publication(publication_id)
    if pub is None:
        raise HTTPException(status_code=404, detail="Publication introuvable")
    activity = await service.db.execute(
        select(SportActivity).where(SportActivity.id == pub.activity_id)
    )
    pub.activity = activity.scalar_one_or_none()
    return pub


@router.patch("/{publication_id}", response_model=SportPublicationResponse)
async def update_publication(
    publication_id: int,
    data: SportPublicationUpdate,
    service: SportPublicationService = Depends(get_pub_write_service),
):
    pub = await service.update(publication_id, data)
    if pub is None:
        raise HTTPException(status_code=404, detail="Publication introuvable")
    return pub


@router.post("/{publication_id}/validate", response_model=SportPublicationResponse)
async def validate_publication(
    publication_id: int,
    service: SportPublicationService = Depends(get_pub_write_service),
):
    try:
        pub = await service.validate(publication_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if pub is None:
        raise HTTPException(status_code=404, detail="Publication introuvable")
    return pub


@router.post("/{publication_id}/share", response_model=SportPublicationResponse)
async def mark_shared(
    publication_id: int,
    service: SportPublicationService = Depends(get_pub_write_service),
):
    pub = await service.mark_shared(publication_id)
    if pub is None:
        raise HTTPException(status_code=404, detail="Publication introuvable")
    return pub


@router.post("/{publication_id}/card")
async def generate_card(
    publication_id: int,
    service: SportPublicationService = Depends(get_pub_write_service),
):
    path = await service.generate_card(publication_id)
    if not path:
        raise HTTPException(status_code=503, detail="Generation de la carte impossible")
    return {"card_path": path}


@router.delete("/meta")
async def meta_disconnect(
    current_user: User = Depends(require_permission("sport.publications.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = SportInstagramConnectService(db)
    disconnected = await service.disconnect(current_user.id)
    return {"disconnected": disconnected}


@router.delete("/{publication_id}")
async def delete_publication(
    publication_id: int,
    service: SportPublicationService = Depends(get_pub_write_service),
):
    ok = await service.delete(publication_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Publication introuvable")
    return {"deleted": True}


@router.post("/notifications/run")
async def run_publication_notifications(
    background_tasks: BackgroundTasks,
    service: SportPublicationService = Depends(get_pub_write_service),
):
    count = await service.notify_new_activities()
    return {"sent": count}


@router.get("/meta/auth")
async def meta_authorize_url(
    athlete_id: Optional[int] = Query(None, description="ID de l'athlete lie a la connexion Meta"),
    current_user: User = Depends(require_permission("sport.publications.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = SportInstagramConnectService(db)
    if not athlete_id:
        pub_service = SportPublicationService(db, current_user)
        athlete = await pub_service.get_or_create_athlete()
        athlete_id = athlete.id
    authorize_url, state = await service.build_authorization_url(athlete_id=athlete_id, user_id=current_user.id)
    return {"authorize_url": authorize_url, "state": state}


@router.get("/meta/callback")
async def meta_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    redirect_uri: Optional[str] = Query(None),
    current_user: User = Depends(require_permission("sport.publications.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = SportInstagramConnectService(db)
    connection = await service.exchange_code(code=code, redirect_uri=redirect_uri, state=state)
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return {
            "status": connection.status,
            "instagram_business_account_id": connection.instagram_business_account_id,
        }
    return RedirectResponse(url="/settings?connected=1", status_code=status.HTTP_302_FOUND)


@router.get("/meta/status")
async def meta_status(
    current_user: User = Depends(require_permission("sport.publications.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = SportInstagramConnectService(db)
    values = await service.load_meta_values()
    is_configured = bool(values["app_id"] and values["app_secret"])
    connection = await service.get_connection(current_user.id)
    if not is_configured:
        return {
            "connected": False,
            "status": "not_configured",
            "configured": False,
            "message": "Meta App ID / App Secret non configurés",
        }
    if connection is None:
        return {
            "connected": False,
            "status": "disconnected",
            "configured": True,
        }
    return {
        "connected": True,
        "status": connection.status,
        "configured": True,
        "instagram_business_account_id": connection.instagram_business_account_id,
        "scopes": connection.scopes,
    }
