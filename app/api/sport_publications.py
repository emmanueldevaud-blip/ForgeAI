"""Routes API pour les publications Instagram (module Sport)."""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
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



@router.post("/meta/login")
async def meta_login_init(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Demarrage du parcours Facebook Login for Business (state OAuth)."""
    service = SportInstagramConnectService(db)
    return await service.initiate_meta_login()


@router.get("/meta/callback")
async def meta_oauth_callback(
    code: str = Query(..., description="Code OAuth de Facebook Login for Business"),
    state: str = Query(..., description="State OAuth"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Callback Facebook Login for Business : echange le code contre le jeton du
    Business Integration System User, recupere le contexte, enregistre le tout."""
    service = SportInstagramConnectService(db)
    if not await service.validate_meta_state(state):
        raise HTTPException(status_code=400, detail="State OAuth invalide")
    result = await service.exchange_business_code(code)
    accounts = result.get("instagram_accounts") or []
    instagram_user_id = ""
    for account in accounts:
        if account.get("id"):
            instagram_user_id = str(account.get("id"))
            break
    await service.save_meta_credentials(
        token=result.get("access_token") or "",
        client_business_id=result.get("client_business_id") or "",
        instagram_user_id=instagram_user_id,
    )
    return {
        "status": "ok",
        "client_business_id": result.get("client_business_id"),
        "instagram_accounts": accounts,
    }
