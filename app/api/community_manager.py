"""Routes API V1 pour le Community Manager IA."""

import logging
from datetime import datetime, date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_enabled, require_permission
from app.models.user import User
from app.models.sport import EditorialCalendarEntry, SportAthlete, SportPublication
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
    PublicationPublishRequest,
    PublicationPublishResponse,
    PublicationGenerateTextRequest,
    PublicationGenerateTextResponse,
)
from app.services.ai_gateway import AIGatewayError
from app.services.community_manager import CommunityManagerService, CommunityManagerStudioService
from app.services.community_manager.suggestions import EditorialSuggestionService
from app.services.garmin import SportGarminConnectService
from pydantic import BaseModel
from datetime import date
from typing import Optional

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


@router.get("/studio/draft/{publication_id}/suggested-photos")
async def get_suggested_photos(
    publication_id: int,
    limit: int = Query(15, ge=1, le=50),
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    """Récupérer les photos suggérées en liaison avec les activités sportives."""
    try:
        return await service.get_suggested_photos(publication_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/studio/draft/{publication_id}/lock/title", response_model=PublicationDraftResponse)
async def toggle_title_lock(
    publication_id: int,
    locked: bool = Query(...),
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Verrouiller ou déverrouiller le titre."""
    publication = await service.update_draft(publication_id, PublicationDraftUpdate(title_locked=locked))
    if not publication:
        raise HTTPException(status_code=404, detail="Brouillon introuvable")
    return PublicationDraftResponse.model_validate(publication)


@router.patch("/studio/draft/{publication_id}/lock/content", response_model=PublicationDraftResponse)
async def toggle_content_lock(
    publication_id: int,
    locked: bool = Query(...),
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Verrouiller ou déverrouiller le contenu."""
    publication = await service.update_draft(publication_id, PublicationDraftUpdate(content_locked=locked))
    if not publication:
        raise HTTPException(status_code=404, detail="Brouillon introuvable")
    return PublicationDraftResponse.model_validate(publication)


@router.patch("/studio/draft/{publication_id}/lock/photo", response_model=PublicationDraftResponse)
async def toggle_photo_lock(
    publication_id: int,
    locked: bool = Query(...),
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Verrouiller ou déverrouiller le visuel."""
    publication = await service.update_draft(publication_id, PublicationDraftUpdate(photo_locked=locked))
    if not publication:
        raise HTTPException(status_code=404, detail="Brouillon introuvable")
    return PublicationDraftResponse.model_validate(publication)


@router.post("/studio/draft/{publication_id}/generate-text", response_model=PublicationGenerateTextResponse)
async def generate_text(
    publication_id: int,
    data: PublicationGenerateTextRequest,
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Générer un texte court ou long selon le ton."""
    try:
        publication = await service.generate_text(publication_id, data)
        if not publication:
            raise HTTPException(status_code=404, detail="Brouillon introuvable")
        return PublicationGenerateTextResponse(
            publication_id=publication.id,
            title=publication.title,
            content=publication.content,
            hashtags=publication.hashtags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIGatewayError as exc:
        raise HTTPException(status_code=503, detail="Génération IA impossible") from exc
    except Exception as exc:
        logger.exception("[CM-STUDIO] Erreur génération texte")
        raise HTTPException(status_code=503, detail="Génération impossible") from exc


@router.post("/studio/draft/{publication_id}/publish", response_model=PublicationPublishResponse)
async def publish_draft(
    publication_id: int,
    data: PublicationPublishRequest,
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Publier une publication validée sur Instagram."""
    try:
        publication = await service.publish_to_instagram(publication_id, data)
        if not publication:
            raise HTTPException(status_code=404, detail="Publication introuvable")
        return PublicationPublishResponse(
            publication_id=publication.id,
            status=publication.status,
            instagram_media_id=getattr(publication, 'instagram_media_id', None),
            instagram_permalink=getattr(publication, 'instagram_permalink', None),
            shared_at=publication.shared_at,
            error_message=publication.error_message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[CM-STUDIO] Erreur publication Instagram")
        raise HTTPException(status_code=503, detail="Publication impossible") from exc


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


# ============================================================
# NOUVELLES ROUTES : Calendrier mensuel/hebdomadaire + Suggestions
# ============================================================

class MonthCalendarResponse(BaseModel):
    year: int
    month: int
    days: dict[str, list[dict]]


class WeekCalendarResponse(BaseModel):
    monday: str
    sunday: str
    days: dict[str, list[dict]]


class SuggestionGenerateResponse(BaseModel):
    week_monday: str
    week_sunday: str
    suggestions: list[dict]


class SuggestionActionResponse(BaseModel):
    id: int
    date: str
    topic: str
    content_type: str
    status: str


class RegenerateResponse(BaseModel):
    publication_id: int
    status: str
    error_message: Optional[str] = None


async def get_suggestion_service(
    current_user: User = Depends(require_permission("community_manager.calendar_generate")),
    db: AsyncSession = Depends(get_db),
) -> EditorialSuggestionService:
    return EditorialSuggestionService(db, current_user)


@router.get("/calendar/month", response_model=MonthCalendarResponse)
async def get_month_calendar(
    year: int = Query(..., description="Année"),
    month: int = Query(..., ge=1, le=12, description="Mois"),
    service: CommunityManagerService = Depends(get_cm_calendar_service),
    suggestion_service: EditorialSuggestionService = Depends(get_suggestion_service),
):
    """Calendrier mensuel : toutes les entrées groupées par jour.

    Déclenche automatiquement la génération idempotente des 3 suggestions
    hebdomadaires (Europe/Paris) à l'ouverture du calendrier.
    """
    from calendar import monthrange

    # Génération automatique des suggestions hebdomadaires (idempotente)
    try:
        await suggestion_service.generate_weekly_suggestions()
    except Exception:
        # Ne jamais bloquer l'affichage du calendrier si la génération échoue
        pass

    strategy = await service.get_strategy()
    if not strategy:
        return MonthCalendarResponse(year=year, month=month, days={})

    _, last_day = monthrange(year, month)
    first = date(year, month, 1)
    last = date(year, month, last_day)

    result = await service.db.execute(
        select(EditorialCalendarEntry)
        .where(
            EditorialCalendarEntry.strategy_id == strategy.id,
            EditorialCalendarEntry.date >= first,
            EditorialCalendarEntry.date <= last,
        )
        .order_by(EditorialCalendarEntry.date.asc())
    )
    entries = result.scalars().all()

    # Récupérer les publications liées
    entry_ids = [e.id for e in entries]
    pubs = {}
    if entry_ids:
        pubs_result = await service.db.execute(
            select(
                EditorialCalendarEntry.id.label("entry_id"),
                EditorialCalendarEntry.status.label("entry_status"),
                EditorialCalendarEntry.content_type.label("entry_content_type"),
                EditorialCalendarEntry.source.label("entry_source"),
                EditorialCalendarEntry.topic.label("entry_topic"),
                EditorialCalendarEntry.date.label("entry_date"),
                EditorialCalendarEntry.photo_id.label("entry_photo_id"),
                SportPublication.id.label("pub_id"),
                SportPublication.status.label("pub_status"),
                SportPublication.title.label("pub_title"),
                SportPublication.content.label("pub_content"),
                SportPublication.hashtags.label("pub_hashtags"),
                SportPublication.photo_id.label("pub_photo_id"),
            )
            .select_from(EditorialCalendarEntry)
            .outerjoin(
                SportPublication,
                SportPublication.calendar_entry_id == EditorialCalendarEntry.id,
            )
            .where(EditorialCalendarEntry.id.in_(entry_ids))
        )
        for row in pubs_result.all():
            pubs[row.entry_id] = {
                "entry_status": row.entry_status,
                "entry_content_type": row.entry_content_type,
                "entry_source": row.entry_source,
                "entry_topic": row.entry_topic,
                "entry_date": row.entry_date.isoformat() if row.entry_date else None,
                "entry_photo_id": row.entry_photo_id,
                "pub_id": row.pub_id,
                "pub_status": row.pub_status,
                "pub_title": row.pub_title,
                "pub_content": row.pub_content,
                "pub_hashtags": row.pub_hashtags,
                "pub_photo_id": row.pub_photo_id,
            }

    days: dict[str, list[dict]] = {}
    for e in entries:
        day_key = e.date.isoformat()
        info = pubs.get(e.id, {})
        days.setdefault(day_key, []).append({
            "entry_id": e.id,
            "topic": info.get("entry_topic", e.topic),
            "content_type": info.get("entry_content_type", e.content_type),
            "source": info.get("entry_source", e.source),
            "status": info.get("entry_status", e.status),
            "pub_id": info.get("pub_id"),
            "pub_status": info.get("pub_status"),
            "pub_title": info.get("pub_title"),
            "pub_hashtags": info.get("pub_hashtags"),
            "photo_id": info.get("pub_photo_id", info.get("entry_photo_id")),
        })

    return MonthCalendarResponse(year=year, month=month, days=days)


@router.get("/calendar/week", response_model=WeekCalendarResponse)
async def get_week_calendar(
    monday: str = Query(..., description="Lundi de la semaine (YYYY-MM-DD)"),
    service: CommunityManagerService = Depends(get_cm_calendar_service),
    suggestion_service: EditorialSuggestionService = Depends(get_suggestion_service),
):
    """Calendrier hebdomadaire.

    Déclenche automatiquement la génération idempotente des 3 suggestions
    hebdomadaires (Europe/Paris) à l'ouverture du calendrier.
    """
    from datetime import datetime as _dt

    # Génération automatique des suggestions hebdomadaires (idempotente)
    try:
        await suggestion_service.generate_weekly_suggestions()
    except Exception:
        # Ne jamais bloquer l'affichage du calendrier si la génération échoue
        pass

    try:
        monday_date = _dt.strptime(monday, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Format de date invalide (YYYY-MM-DD)")

    sunday_date = monday_date + timedelta(days=6)

    strategy = await service.get_strategy()
    if not strategy:
        return WeekCalendarResponse(monday=monday, sunday=sunday_date.isoformat(), days={})

    result = await service.db.execute(
        select(EditorialCalendarEntry)
        .where(
            EditorialCalendarEntry.strategy_id == strategy.id,
            EditorialCalendarEntry.date >= monday_date,
            EditorialCalendarEntry.date <= sunday_date,
        )
        .order_by(EditorialCalendarEntry.date.asc())
    )
    entries = result.scalars().all()

    entry_ids = [e.id for e in entries]
    pubs = {}
    if entry_ids:
        pubs_result = await service.db.execute(
            select(
                EditorialCalendarEntry.id.label("entry_id"),
                EditorialCalendarEntry.status.label("entry_status"),
                EditorialCalendarEntry.content_type.label("entry_content_type"),
                EditorialCalendarEntry.source.label("entry_source"),
                EditorialCalendarEntry.topic.label("entry_topic"),
                EditorialCalendarEntry.photo_id.label("entry_photo_id"),
                SportPublication.id.label("pub_id"),
                SportPublication.status.label("pub_status"),
                SportPublication.title.label("pub_title"),
                SportPublication.hashtags.label("pub_hashtags"),
                SportPublication.photo_id.label("pub_photo_id"),
            )
            .select_from(EditorialCalendarEntry)
            .outerjoin(
                SportPublication,
                SportPublication.calendar_entry_id == EditorialCalendarEntry.id,
            )
            .where(EditorialCalendarEntry.id.in_(entry_ids))
        )
        for row in pubs_result.all():
            pubs[row.entry_id] = {
                "entry_status": row.entry_status,
                "entry_content_type": row.entry_content_type,
                "entry_source": row.entry_source,
                "entry_topic": row.entry_topic,
                "pub_id": row.pub_id,
                "pub_status": row.pub_status,
                "pub_title": row.pub_title,
                "pub_hashtags": row.pub_hashtags,
                "photo_id": row.pub_photo_id or row.entry_photo_id,
            }

    days: dict[str, list[dict]] = {}
    for e in entries:
        day_key = e.date.isoformat()
        info = pubs.get(e.id, {})
        days.setdefault(day_key, []).append({
            "entry_id": e.id,
            "topic": info.get("entry_topic", e.topic),
            "content_type": info.get("entry_content_type", e.content_type),
            "source": info.get("entry_source", e.source),
            "status": info.get("entry_status", e.status),
            "pub_id": info.get("pub_id"),
            "pub_status": info.get("pub_status"),
            "pub_title": info.get("pub_title"),
            "pub_hashtags": info.get("pub_hashtags"),
            "photo_id": info.get("photo_id"),
        })

    return WeekCalendarResponse(
        monday=monday_date.isoformat(),
        sunday=sunday_date.isoformat(),
        days=days,
    )


@router.post("/suggestions/generate", response_model=SuggestionGenerateResponse)
async def generate_suggestions(
    service: EditorialSuggestionService = Depends(get_suggestion_service),
):
    """Génère les 3 suggestions de la semaine (idempotent)."""
    return await service.generate_weekly_suggestions()


@router.post("/suggestions/{entry_id}/accept", response_model=SuggestionActionResponse)
async def accept_suggestion(
    entry_id: int,
    service: EditorialSuggestionService = Depends(get_suggestion_service),
):
    """Accepte une suggestion (passe en 'accepted', modifiable dans le Studio)."""
    entry = await service.accept_suggestion(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Suggestion introuvable")
    return SuggestionActionResponse(
        id=entry.id,
        date=entry.date.isoformat(),
        topic=entry.topic,
        content_type=entry.content_type,
        status=entry.status,
    )


@router.post("/suggestions/{entry_id}/refuse", response_model=SuggestionActionResponse)
async def refuse_suggestion(
    entry_id: int,
    service: EditorialSuggestionService = Depends(get_suggestion_service),
):
    """Refuse une suggestion (passe en 'refused', conservée dans l'historique)."""
    entry = await service.refuse_suggestion(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Suggestion introuvable")
    return SuggestionActionResponse(
        id=entry.id,
        date=entry.date.isoformat(),
        topic=entry.topic,
        content_type=entry.content_type,
        status=entry.status,
    )


@router.post("/suggestions/{entry_id}/reschedule", response_model=SuggestionActionResponse)
async def reschedule_suggestion(
    entry_id: int,
    new_date: str = Query(..., description="Nouvelle date (YYYY-MM-DD)"),
    service: EditorialSuggestionService = Depends(get_suggestion_service),
):
    """Reporte une suggestion à une nouvelle date."""
    from datetime import datetime as _dt
    try:
        parsed = _dt.strptime(new_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Format de date invalide")
    entry = await service.reschedule_suggestion(entry_id, parsed)
    if not entry:
        raise HTTPException(status_code=404, detail="Suggestion introuvable")
    return SuggestionActionResponse(
        id=entry.id,
        date=entry.date.isoformat(),
        topic=entry.topic,
        content_type=entry.content_type,
        status=entry.status,
    )


@router.post("/studio/draft/{publication_id}/regenerate", response_model=RegenerateResponse)
async def regenerate_publication_content(
    publication_id: int,
    current_user: User = Depends(require_permission("community_manager.calendar_generate")),
    db: AsyncSession = Depends(get_db),
):
    """Relance la génération de contenu pour une publication (reprise après échec IA)."""
    garmin_service = SportGarminConnectService(db)
    pub = await garmin_service.regenerate_publication_content(publication_id, current_user)
    if not pub:
        raise HTTPException(status_code=404, detail="Publication introuvable")
    return RegenerateResponse(
        publication_id=pub.id,
        status=pub.status,
        error_message=pub.error_message,
    )
