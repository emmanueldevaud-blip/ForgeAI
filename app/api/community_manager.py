"""Routes API V1 pour le Community Manager IA."""

import logging
from datetime import datetime
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
    PublicationDraftUpdate,
    PublicationDraftResponse,
    PublicationGenerateFromCalendarRequest,
    PublicationGenerateFromCalendarResponse,
    PublicationPreviewRequest,
    PublicationPreviewResponse,
    PublicationValidateRequest,
    PublicationValidateResponse,
    PublicationVariantsRequest,
    PublicationVariantsResponse,
)
from app.services.ai_gateway import AIGatewayError
from app.services.community_manager import CommunityManagerService, CommunityManagerStudioService

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


async def get_cm_studio_service(
    current_user: User = Depends(require_permission("community_manager.calendar_generate")),
    db: AsyncSession = Depends(get_db),
) -> CommunityManagerStudioService:
    return CommunityManagerStudioService(db, current_user)


async def get_cm_studio_write_service(
    current_user: User = Depends(require_permission("community_manager.calendar_generate")),
    db: AsyncSession = Depends(get_db),
) -> CommunityManagerStudioService:
    return CommunityManagerStudioService(db, current_user)


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
# STUDIO DE CRÉATION V2
# ============================================================


@router.post("/studio/from-calendar", response_model=PublicationGenerateFromCalendarResponse)
async def create_studio_draft(
    data: PublicationGenerateFromCalendarRequest,
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Créer un brouillon de publication depuis une entrée de calendrier validée."""
    try:
        publication = await service.create_draft_from_calendar(data)
        return PublicationGenerateFromCalendarResponse(
            publication_id=publication.id,
            status=publication.status,
            proposals=publication.proposals or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIGatewayError as exc:
        raise HTTPException(status_code=503, detail="Génération IA impossible") from exc
    except Exception as exc:
        logger.exception("[CM-STUDIO] Erreur création brouillon")
        raise HTTPException(status_code=503, detail="Création impossible") from exc


@router.get("/studio/draft/{publication_id}", response_model=PublicationDraftResponse)
async def get_studio_draft(
    publication_id: int,
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    """Récupérer un brouillon de publication en cours de création."""
    publication = await service.get_draft(publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Brouillon introuvable")
    return PublicationDraftResponse.model_validate(publication)


@router.patch("/studio/draft/{publication_id}", response_model=PublicationDraftResponse)
async def update_studio_draft(
    publication_id: int,
    data: PublicationDraftUpdate,
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Mettre à jour un brouillon (texte, hashtags, visuel, ton, propositions)."""
    publication = await service.update_draft(publication_id, data)
    if not publication:
        raise HTTPException(status_code=404, detail="Brouillon introuvable")
    return PublicationDraftResponse.model_validate(publication)


@router.post("/studio/draft/{publication_id}/variants", response_model=PublicationVariantsResponse)
async def generate_text_variants(
    publication_id: int,
    data: PublicationVariantsRequest,
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Générer des variantes de texte pour un brouillon."""
    try:
        variants = await service.generate_text_variants(
            publication_id=publication_id,
            tone=data.tone,
            styles=data.styles,
            custom_instructions=data.custom_instructions,
            count=data.count,
        )
        return PublicationVariantsResponse(publication_id=publication_id, variants=variants)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIGatewayError as exc:
        raise HTTPException(status_code=503, detail="Génération IA impossible") from exc
    except Exception as exc:
        logger.exception("[CM-STUDIO] Erreur génération variantes")
        raise HTTPException(status_code=503, detail="Génération impossible") from exc


@router.post("/studio/draft/{publication_id}/validate", response_model=PublicationValidateResponse)
async def validate_draft_for_publication(
    publication_id: int,
    data: PublicationValidateRequest,
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Valider un brouillon pour publication (passe en 'validated')."""
    try:
        publication = await service.validate_for_publication(publication_id, data)
        if not publication:
            raise HTTPException(status_code=404, detail="Brouillon introuvable")
        return PublicationValidateResponse(
            publication_id=publication.id,
            status=publication.status,
            validated_at=publication.validated_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/studio/draft/{publication_id}/schedule")
async def schedule_draft(
    publication_id: int,
    scheduled_at: datetime = Query(..., description="Date/heure de publication planifiée"),
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Planifier une publication validée."""
    try:
        publication = await service.schedule_publication(publication_id, scheduled_at)
        if not publication:
            raise HTTPException(status_code=404, detail="Publication introuvable")
        return {"publication_id": publication.id, "status": publication.status, "scheduled_at": publication.scheduled_at}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/studio/draft/{publication_id}/preview", response_model=PublicationPreviewResponse)
async def preview_draft(
    publication_id: int,
    data: PublicationPreviewRequest,
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    """Prévisualiser le rendu Instagram d'une publication."""
    try:
        preview = await service.get_preview(publication_id, data.format)
        return PublicationPreviewResponse(**preview)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


# ============================================================
# ROUTES SPORT PUBLICATIONS V2 (pont vers Studio)
# ============================================================


async def get_sport_studio_write_service(
    current_user: User = Depends(require_permission("sport.publications.write")),
    db: AsyncSession = Depends(get_db),
) -> CommunityManagerStudioService:
    return CommunityManagerStudioService(db, current_user)


@sport_router.post("/studio/from-calendar", response_model=PublicationGenerateFromCalendarResponse)
async def create_studio_draft_from_sport(
    data: PublicationGenerateFromCalendarRequest,
    service: CommunityManagerStudioService = Depends(get_sport_studio_write_service),
):
    """Créer un brouillon de publication depuis une entrée de calendrier validée (pont frontend sport)."""
    try:
        publication = await service.create_draft_from_calendar(data)
        return PublicationGenerateFromCalendarResponse(
            publication_id=publication.id,
            status=publication.status,
            proposals=publication.proposals or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIGatewayError as exc:
        raise HTTPException(status_code=503, detail="Génération IA impossible") from exc
    except Exception as exc:
        logger.exception("[SPORT-STUDIO] Erreur création brouillon")
        raise HTTPException(status_code=503, detail="Création impossible") from exc