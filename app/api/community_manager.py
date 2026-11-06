"""Routes API V1 pour le Community Manager IA."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_enabled, require_permission
from app.models.user import User
from app.schemas.sport import (
    CalendarGenerateRequest,
    CalendarGenerateResponse,
    CommunityManagerStrategyCreate,
    CommunityManagerStrategyResponse,
    CommunityManagerStrategyUpdate,
    EditorialCalendarEntryResponse,
    EditorialCalendarEntryUpdate,
)
from app.services.community_manager import CommunityManagerService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/community-manager",
    tags=["community-manager"],
    dependencies=[Depends(require_module_enabled("community_manager"))],
)


async def get_cm_service(
    current_user: User = Depends(require_permission("community_manager.strategy_view")),
    db: AsyncSession = Depends(get_db),
) -> CommunityManagerService:
    return CommunityManagerService(db, current_user)


async def get_cm_write_service(
    current_user: User = Depends(require_permission("community_manager.strategy_update")),
    db: AsyncSession = Depends(get_db),
) -> CommunityManagerService:
    return CommunityManagerService(db, current_user)


async def get_cm_calendar_service(
    current_user: User = Depends(require_permission("community_manager.calendar_view")),
    db: AsyncSession = Depends(get_db),
) -> CommunityManagerService:
    return CommunityManagerService(db, current_user)


async def get_cm_generate_service(
    current_user: User = Depends(require_permission("community_manager.calendar_generate")),
    db: AsyncSession = Depends(get_db),
) -> CommunityManagerService:
    return CommunityManagerService(db, current_user)


# ============================================================
# STRATÉGIE ÉDITORIALE
# ============================================================


@router.post("/strategy", response_model=CommunityManagerStrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    data: CommunityManagerStrategyCreate,
    service: CommunityManagerService = Depends(get_cm_write_service),
):
    """Créer la stratégie éditoriale."""
    try:
        strategy = await service.create_or_update_strategy(data)
        return CommunityManagerStrategyResponse.model_validate(strategy)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/strategy", response_model=CommunityManagerStrategyResponse)
async def get_strategy(
    service: CommunityManagerService = Depends(get_cm_service),
):
    """Récupérer la stratégie éditoriale actuelle."""
    strategy = await service.get_strategy()
    if not strategy:
        raise HTTPException(status_code=404, detail="Stratégie non configurée")
    return CommunityManagerStrategyResponse.model_validate(strategy)


@router.put("/strategy", response_model=CommunityManagerStrategyResponse)
async def update_strategy(
    data: CommunityManagerStrategyUpdate,
    service: CommunityManagerService = Depends(get_cm_write_service),
):
    """Mettre à jour la stratégie éditoriale."""
    try:
        strategy = await service.create_or_update_strategy(data)
        return CommunityManagerStrategyResponse.model_validate(strategy)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ============================================================
# CALENDRIER ÉDITORIAL
# ============================================================


@router.post("/generate-calendar", response_model=CalendarGenerateResponse)
async def generate_calendar(
    data: CalendarGenerateRequest,
    service: CommunityManagerService = Depends(get_cm_generate_service),
):
    """Générer un calendrier éditorial via l'IA."""
    try:
        return await service.generate_calendar(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[COMMUNITY-MANAGER] Erreur génération calendrier")
        raise HTTPException(status_code=503, detail="Génération IA impossible") from exc


@router.get("/calendar", response_model=list[EditorialCalendarEntryResponse])
async def get_calendar(
    service: CommunityManagerService = Depends(get_cm_calendar_service),
):
    """Récupérer le calendrier éditorial existant."""
    return await service.get_calendar()


@router.patch("/calendar/{entry_id}", response_model=EditorialCalendarEntryResponse)
async def update_calendar_entry(
    entry_id: int,
    data: EditorialCalendarEntryUpdate,
    service: CommunityManagerService = Depends(get_cm_generate_service),
):
    """Mettre à jour une entrée du calendrier (valider, refuser, modifier)."""
    entry = await service.update_calendar_entry(entry_id, data)
    if not entry:
        raise HTTPException(status_code=404, detail="Entrée de calendrier introuvable")
    return entry


@router.delete("/calendar/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_entry(
    entry_id: int,
    service: CommunityManagerService = Depends(get_cm_generate_service),
):
    """Supprimer une entrée du calendrier (refus définitif)."""
    deleted = await service.delete_calendar_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entrée de calendrier introuvable")


# ============================================================
# ROUTES SPORT PUBLICATIONS (pont vers V1)
# ============================================================

# Ces routes sont appelées depuis le frontend sport existant
# Elles redirigent vers les endpoints V1 ci-dessus

sport_router = APIRouter(prefix="/sport/publications", tags=["sport"])


async def get_sport_cm_service(
    current_user: User = Depends(require_permission("sport.publications.read")),
    db: AsyncSession = Depends(get_db),
) -> CommunityManagerService:
    return CommunityManagerService(db, current_user)


async def get_sport_cm_write_service(
    current_user: User = Depends(require_permission("sport.publications.write")),
    db: AsyncSession = Depends(get_db),
) -> CommunityManagerService:
    return CommunityManagerService(db, current_user)


@sport_router.get("/community-strategy")
async def get_community_strategy(
    athlete_id: int = Query(..., description="ID de l'athlète"),
    service: CommunityManagerService = Depends(get_sport_cm_service),
):
    """Récupérer la stratégie community manager pour un athlète (pont frontend sport)."""
    # Vérifier que l'athlète appartient à l'utilisateur
    from app.models.sport import SportAthlete
    result = await service.db.execute(
        select(SportAthlete).where(SportAthlete.id == athlete_id, SportAthlete.user_id == service.current_user.id)
    )
    athlete = result.scalar_one_or_none()
    if not athlete:
        raise HTTPException(status_code=403, detail="Athlète non autorisé")

    strategy = await service.get_strategy()
    if not strategy:
        return {"configured": False}
    return {"configured": True, "strategy": CommunityManagerStrategyResponse.model_validate(strategy)}


@sport_router.post("/community-generate")
async def generate_community_topics(
    count: int = Query(5, ge=1, le=20),
    service: CommunityManagerService = Depends(get_sport_cm_write_service),
):
    """Générer des sujets de publication via le Community Manager (pont frontend sport)."""
    # L'athlète est déterminé par l'utilisateur courant via le service
    try:
        response = await service.generate_calendar(CalendarGenerateRequest(count=count))
        return {"calendar": [entry.model_dump() for entry in response.calendar]}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[SPORT-CM] Erreur génération sujets")
        raise HTTPException(status_code=503, detail="Génération IA impossible") from exc


@sport_router.get("/community-calendar")
async def get_community_calendar(
    athlete_id: int = Query(..., description="ID de l'athlète"),
    service: CommunityManagerService = Depends(get_sport_cm_service),
):
    """Récupérer le calendrier éditorial pour un athlète (pont frontend sport)."""
    from app.models.sport import SportAthlete
    result = await service.db.execute(
        select(SportAthlete).where(SportAthlete.id == athlete_id, SportAthlete.user_id == service.current_user.id)
    )
    athlete = result.scalar_one_or_none()
    if not athlete:
        raise HTTPException(status_code=403, detail="Athlète non autorisé")

    calendar = await service.get_calendar()
    return {"calendar": [entry.model_dump() for entry in calendar]}