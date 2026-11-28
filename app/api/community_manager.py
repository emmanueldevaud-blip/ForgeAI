"""Routes API V1 pour le Community Manager IA."""

import asyncio
import logging
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, List, Dict, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func

from app.api.deps import get_db, require_module_enabled, require_permission
from app.models.user import User
from app.models.sport import EditorialCalendarEntry, SportAthlete, SportPublication, StoryDraft
from app.schemas.sport import (
    CalendarGenerateRequest,
    CalendarGenerateResponse,
    CommunityManagerStrategyCreate,
    CommunityManagerStrategyResponse,
    CommunityManagerStrategyUpdate,
    EditorialCalendarEntryResponse,
    EditorialCalendarEntryUpdate,
    PublicationDraftUpdate,
    PublicationDraftCreateRequest,
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
from app.services.story_orchestrator import StoryOrchestrator
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List, Dict, Any


class StoryDraftCreateRequest(BaseModel):
    # `activity_id` est optionnel pour les Stories standalone composées depuis
    # la bibliothèque : le Composer envoie alors ses slides et ses designs v2.
    activity_id: Optional[int] = None
    photo_ids: List[int] = []
    calendar_entry_id: Optional[int] = None
    source: str = "garmin"
    slides: List[Dict[str, Any]] = []
    design_documents: List[Dict[str, Any]] = []
    caption: Optional[str] = None
    hashtags: Optional[str] = None


class StoryDraftResponse(BaseModel):
    id: int
    athlete_id: int
    source: str
    source_activity_id: Optional[int]
    calendar_entry_id: Optional[int]
    selected_asset_ids: List[int]
    slides: List[Dict[str, Any]]
    design_documents: List[Dict[str, Any]]
    caption: Optional[str]
    hashtags: Optional[str]
    audio_configuration: Optional[Dict[str, Any]]
    status: str
    render_jobs: List[Dict[str, Any]]
    publication_results: List[Dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    prepared_at: Optional[datetime]
    validated_at: Optional[datetime]
    published_at: Optional[datetime]

    class Config:
        from_attributes = True


class StoryDraftListResponse(BaseModel):
    items: List[StoryDraftResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class StoryDraftUpdateRequest(BaseModel):
    slides: Optional[List[Dict[str, Any]]] = None
    design_documents: Optional[List[Dict[str, Any]]] = None
    caption: Optional[str] = None
    hashtags: Optional[str] = None
    audio_configuration: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class StoryDraftSlideUpdate(BaseModel):
    slide_index: int
    design: Dict[str, Any]


class StoryDraftStatusUpdate(BaseModel):
    status: str


class StoryDraftPublishRequest(BaseModel):
    confirm: bool = True
    # Lot 1 / A06 : une seule vérité, la règle métier autorise Instagram uniquement.
    # facebook / both sont rejetés par Pydantic avant même d'atteindre le handler.
    platforms: List[Literal["instagram"]] = ["instagram"]


# Lot 1 / A04 : la programmation n'est pas exécutée (aucun worker ne consomme
# le statut « scheduled »). Le code de service est conservé pour un futur
# scheduler idempotent, mais l'endpoint et l'export client sont désactivés.
SCHEDULING_DISABLED_MESSAGE = (
    "La programmation de publications est désactivée : aucun worker n'exécute les "
    "publications planifiées. Utilisez « Publier maintenant » ou attendez un "
    "scheduler idempotent (Europe/Paris)."
)

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


async def get_story_orchestrator(
    current_user: User = Depends(require_permission("community_manager.calendar_generate")),
    db: AsyncSession = Depends(get_db),
) -> StoryOrchestrator:
    return StoryOrchestrator(db, current_user)


async def get_story_orchestrator_write(
    current_user: User = Depends(require_permission("community_manager.calendar_generate")),
    db: AsyncSession = Depends(get_db),
) -> StoryOrchestrator:
    return StoryOrchestrator(db, current_user)


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


@router.post("/calendar/{entry_id}/regenerate-hashtags", response_model=EditorialCalendarEntryResponse)
async def regenerate_calendar_entry_hashtags(
    entry_id: int,
    service: CommunityManagerService = Depends(get_cm_generate_service),
):
    """Regenerer les hashtags d'une entree du calendrier selon la strategie editeeionale."""
    entry = await service.regenerate_calendar_entry_hashtags(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entrée de calendrier introuvable")
    return entry


@router.delete("/calendar/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_entry(
    entry_id: int,
    service: CommunityManagerService = Depends(get_cm_generate_service),
):
    """Supprimer une entrée du calendrier (refus définitif)."""
    try:
        deleted = await service.delete_calendar_entry(entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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


@router.post("/studio/draft", response_model=PublicationDraftResponse, status_code=status.HTTP_201_CREATED)
async def create_standalone_draft(
    data: PublicationDraftCreateRequest,
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Créer un brouillon standalone (sans entrée de calendrier ni activité Garmin).

    Lot 0 (A01) : le parcours de création standalone (Publisher / « Créer une
    publication ») passe par cette création serveur avant la sauvegarde puis la
    publication.
    """
    try:
        publication = await service.create_standalone_draft(data)
        return PublicationDraftResponse.model_validate(publication)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[CM-STUDIO] Erreur création brouillon standalone")
        raise HTTPException(status_code=503, detail="Création impossible") from exc


@router.patch("/studio/draft/{publication_id}", response_model=PublicationDraftResponse)
async def update_studio_draft(
    publication_id: int,
    data: PublicationDraftUpdate,
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Mettre à jour un brouillon (texte, hashtags, visuel, ton, propositions)."""
    try:
        publication = await service.update_draft(publication_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not publication:
        raise HTTPException(status_code=404, detail="Brouillon introuvable")
    return PublicationDraftResponse.model_validate(publication)


@router.get("/studio/draft/{publication_id}/music")
async def search_studio_music(
    publication_id: int,
    query: str = Query("trail running", min_length=2, max_length=80),
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    """Retourne les musiques Instagram disponibles, notamment avec paroles."""
    publication = await service.get_draft(publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Brouillon introuvable")
    from app.services.community_manager.ig_music import search_ig_audio
    return {"items": await search_ig_audio(service.db, query, limit=10)}


@router.get("/instagram/music/search")
async def search_instagram_music(
    query: str = Query(..., min_length=2, max_length=80),
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    """Recherche le catalogue audio Instagram sans exiger un brouillon préalable."""
    from app.services.community_manager.ig_music import search_ig_audio
    return {"items": await search_ig_audio(service.db, query, limit=10)}


@router.get("/studio/draft/{publication_id}/local-music")
async def list_local_studio_music(
    publication_id: int,
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    """Catalogue local vérifié, utilisable par le lecteur et FFmpeg."""
    publication = await service.get_draft(publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Brouillon introuvable")
    from app.services.community_manager.audio import list_tracks
    return {"items": [track for track in list_tracks() if track.get("available")]}


@router.get("/studio/draft/{publication_id}/audio-match")
async def suggest_local_studio_audio(
    publication_id: int,
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    publication = await service.get_draft(publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Brouillon introuvable")
    from app.services.community_manager.audio_matching import recommend_track
    design = publication.design if isinstance(publication.design, dict) else {}
    style = str((design.get("editorial_engine") or {}).get("style") or "performance")
    return {"item": recommend_track(style, 12.0)}


@router.get("/studio/draft/{publication_id}/audio-proposals")
async def suggest_local_studio_audio_proposals(
    publication_id: int,
    exclude: str = Query(""),
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    publication = await service.get_draft(publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Brouillon introuvable")
    from app.services.community_manager.ig_music import pick_audio_for_photos_bounded, search_ig_audio
    design = publication.design if isinstance(publication.design, dict) else {}
    style = str((design.get("editorial_engine") or {}).get("style") or "performance")
    excluded = {value for value in exclude.split(",") if value}
    carousel = design.get("carousel") if isinstance(design.get("carousel"), list) else []
    if not carousel and publication.photo_id:
        carousel = [publication.photo_id]
    result = await pick_audio_for_photos_bounded(
        service.db,
        service.current_user,
        carousel,
        title=f"{publication.title or ''} {style}".strip(),
        hashtags=publication.hashtags,
        timeout_seconds=25.0,
    )
    suggestions = (result or {}).get("suggestions") or []
    # L'analyse vision est enrichissante mais ne doit pas rendre la recherche
    # Instagram impossible. Repli contextualisé sur le titre/ambiance lorsque
    # les photos ne peuvent pas être analysées ou que l'appel IA expire.
    if not suggestions:
        activity = await service._get_activity_for_publication(publication)
        sport = str(getattr(activity, "sport_type", "trail running") or "trail running").replace("_", " ")
        distance = getattr(activity, "distance_m", None)
        distance_query = f"{float(distance) / 1000:.0f} km" if distance else ""
        elevation = getattr(activity, "elevation_gain_m", None)
        terrain = "mountain" if elevation and float(elevation) >= 300 else "trail"
        fallback_queries = [
            "trail running",
            "running music",
            "running motivation",
            f"{publication.title or 'trail running'} {style}",
            f"{sport} {terrain} {style}",
            f"{sport} {distance_query} {style}".strip(),
            f"{sport} motivation",
        ]
        seen: set[str] = set()
        started = time.perf_counter()
        request_count = 0
        raw_count = 0

        async def run_search(query: str):
            try:
                return await search_ig_audio(service.db, query[:80], limit=10)
            except Exception as exc:  # une requête Meta ne bloque pas les autres
                logger.warning("[IG-MUSIC] Recherche concurrente échouée (%s): %s", query, exc)
                return []

        async def merge_results(results):
            nonlocal request_count, raw_count
            for result in results:
                request_count += 1
                raw_count += len(result)
                for candidate in result:
                    audio_id = str(candidate.get("audio_id") or "")
                    if audio_id and audio_id not in seen:
                        seen.add(audio_id)
                        suggestions.append(candidate)

        # Trois requêtes génériques concurrentes couvrent normalement le cas
        # nominal en un seul aller-retour Meta.
        batch_size = 3
        for offset in range(0, len(fallback_queries), batch_size):
            batch = fallback_queries[offset:offset + batch_size]
            results = await asyncio.gather(*(run_search(query) for query in batch))
            await merge_results(results)
            if len(suggestions) >= 10:
                break
        logger.info(
            "[IG-MUSIC] recommandations publication=%s durée=%.2fs requêtes=%s bruts=%s uniques=%s affichés=%s",
            publication_id, time.perf_counter() - started, request_count,
            raw_count, len(seen), min(10, len(suggestions)),
        )
    items = []
    for item in suggestions:
        audio_id = str(item.get("audio_id") or "")
        if not audio_id or audio_id in excluded:
            continue
        items.append({
            **item,
            "source": "instagram",
            "status": "available_on_meta",
            "reason": f"Proposition Instagram adaptée à l'ambiance {style} et aux photos sélectionnées.",
            "preview_link": (
                item.get("preview_link")
                or item.get("download_url")
                or item.get("preview_url")
            ),
            "platform_preview_link": item.get("platform_preview_link"),
        })
    return {"items": items[:10], "eligible_count": len(items[:10]), "source": "instagram", "local_render": False, "reason": "Catalogue Instagram Meta" if items else "Aucune réponse exploitable du catalogue Instagram Meta"}


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
    """Désactivé (Lot 1 / A04) : aucune file n'exécute les publications planifiées.

    Le service ``schedule_publication`` reste en place comme proposition
    documentée pour un futur scheduler, mais cette route n'écrit plus de statut
    « scheduled » et ne promet aucune publication à venir.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=SCHEDULING_DISABLED_MESSAGE,
    )


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


@router.get("/studio/activity/{activity_id}/suggested-photos")
async def get_suggested_photos_for_activity(
    activity_id: int,
    limit: int = Query(15, ge=1, le=50),
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    """Récupérer les photos suggérées pour une activité Garmin (targeting par activity_id).

    Lot 0 (A03) : le parcours Garmin exige désormais un identifiant d'activité
    réel (jamais null) pour obtenir des suggestions exploitables.
    """
    try:
        return await service.get_suggested_photos_for_activity(activity_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/studio/draft/{publication_id}/editorial-brief")
async def get_editorial_brief(
    publication_id: int,
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    """Analyse éditoriale V2 de la sortie Garmin, sans effet de bord."""
    try:
        return await service.get_editorial_brief(publication_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/studio/draft/{publication_id}/companion-video")
async def get_companion_video(
    publication_id: int,
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    """Diffuse le Reel Garmin généré, sans exposer son chemin serveur."""
    publication = await service.pub_service.get_publication(publication_id)
    if not publication or publication.companion_video_status != "ready":
        raise HTTPException(status_code=404, detail="Vidéo compagnon indisponible")
    path = Path(publication.companion_video_path or "")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier vidéo indisponible")
    return FileResponse(
        path,
        media_type="video/mp4",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Accept-Ranges": "bytes",
            "Content-Disposition": "inline",
        },
    )


@router.patch("/studio/draft/{publication_id}/lock/title", response_model=PublicationDraftResponse)
async def toggle_title_lock(
    publication_id: int,
    locked: bool = Query(...),
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Verrouiller ou déverrouiller le titre."""
    try:
        publication = await service.update_draft(publication_id, PublicationDraftUpdate(title_locked=locked))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    try:
        publication = await service.update_draft(publication_id, PublicationDraftUpdate(content_locked=locked))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    try:
        publication = await service.update_draft(publication_id, PublicationDraftUpdate(photo_locked=locked))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    background_tasks: BackgroundTasks,
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Mettre la publication Instagram en file (rendu et Meta hors requête)."""
    try:
        from app.services.photo.jobs import enqueue_job, run_pending_jobs_now
        from app.models.photo import PhotoJob

        publication = await service.pub_service.get_publication(publication_id)
        if not publication:
            raise HTTPException(status_code=404, detail="Publication introuvable")
        # Lot 1 / A05 : refuser le carrousel avant d'enfile un job qui n'enverrait
        # qu'une seule photo à Meta (le guard vit dans le service, source de vérité).
        service.assert_publishable_format(publication)
        active = await service.db.execute(
            select(PhotoJob).where(
                PhotoJob.type == "community_publish",
                PhotoJob.status.in_(("pending", "running")),
            )
        )
        for job in active.scalars():
            if (job.payload_json or {}).get("publication_id") == publication_id:
                return {"publication_id": publication_id, "job_id": job.id, "status": job.status}
        job = await enqueue_job(
            service.db,
            type="community_publish",
            photo_id=None,
            payload={"publication_id": publication_id, "user_id": service.current_user.id, "data": data.model_dump()},
        )
        background_tasks.add_task(run_pending_jobs_now)
        return PublicationPublishResponse(
            publication_id=publication.id,
            status="queued",
            job_id=job.id,
            instagram_media_id=getattr(publication, 'instagram_media_id', None),
            instagram_permalink=getattr(publication, 'instagram_permalink', None),
            facebook_media_id=getattr(publication, 'facebook_media_id', None),
            facebook_permalink=getattr(publication, 'facebook_permalink', None),
            shared_at=publication.shared_at,
            error_message=publication.error_message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[CM-STUDIO] Erreur publication Instagram")
        raise HTTPException(status_code=503, detail="Publication impossible") from exc


@router.get("/studio/publish-job/{job_id}")
async def get_publish_job(
    job_id: str,
    service: CommunityManagerStudioService = Depends(get_cm_studio_service),
):
    """Statut réel d'un job de publication (Studio ou slide Story)."""
    from app.models.photo import PhotoJob

    job = await service.db.get(PhotoJob, job_id)
    payload = (job.payload_json or {}) if job else {}
    if not job or payload.get("user_id") != service.current_user.id:
        raise HTTPException(status_code=404, detail="Job introuvable")

    result = {
        "job_id": job.id,
        "status": job.status,
        "error": job.error,
        "kind": payload.get("kind"),
        "attempts": job.attempts,
        "progress": job.progress,
    }

    # Une Story publie une slide par job : son payload n'a pas de publication_id.
    if payload.get("kind") == "story_slide_publish":
        draft_id = payload.get("draft_id")
        slide_index = payload.get("slide_index")
        draft = await service.db.get(StoryDraft, draft_id) if draft_id else None
        slide_result = None
        if draft:
            slide_result = next(
                (item for item in (draft.publication_results or [])
                 if item.get("slide_index") == slide_index),
                None,
            )
        result.update({
            "draft_id": draft_id,
            "slide_index": slide_index,
            "publication_status": getattr(draft, "status", None),
            "error_message": getattr(draft, "error_message", None) or job.error,
            "instagram_media_id": (slide_result or {}).get("media_id"),
            "instagram_permalink": (slide_result or {}).get("permalink"),
        })
        return result

    publication_id = payload.get("publication_id")
    publication = (
        await service.pub_service.get_publication(int(publication_id))
        if publication_id else None
    )
    result.update({
        "publication_id": publication_id,
        "publication_status": getattr(publication, "status", None),
        "error_message": getattr(publication, "error_message", None) or job.error,
        "instagram_media_id": getattr(publication, "instagram_media_id", None),
        "instagram_permalink": getattr(publication, "instagram_permalink", None),
        "shared_at": getattr(publication, "shared_at", None),
    })
    return result


@router.post("/studio/draft/{publication_id}/publish-facebook", response_model=PublicationPublishResponse)
async def publish_draft_facebook(
    publication_id: int,
    data: PublicationPublishRequest,
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Publier une publication validée sur Facebook Page."""
    try:
        publication = await service.publish_to_facebook_page(publication_id, data)
        if not publication:
            raise HTTPException(status_code=404, detail="Publication introuvable")
        return PublicationPublishResponse(
            publication_id=publication.id,
            status=publication.status,
            instagram_media_id=getattr(publication, 'instagram_media_id', None),
            instagram_permalink=getattr(publication, 'instagram_permalink', None),
            facebook_media_id=getattr(publication, 'facebook_media_id', None),
            facebook_permalink=getattr(publication, 'facebook_permalink', None),
            shared_at=publication.shared_at,
            error_message=publication.error_message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[CM-STUDIO] Erreur publication Facebook")
        raise HTTPException(status_code=503, detail="Publication impossible") from exc


@router.post("/studio/draft/{publication_id}/publish-both", response_model=PublicationPublishResponse)
async def publish_draft_both(
    publication_id: int,
    data: PublicationPublishRequest,
    service: CommunityManagerStudioService = Depends(get_cm_studio_write_service),
):
    """Publier une publication validée sur Instagram ET Facebook Page simultanément."""
    try:
        publication = await service.publish_to_both(publication_id, data)
        if not publication:
            raise HTTPException(status_code=404, detail="Publication introuvable")
        return PublicationPublishResponse(
            publication_id=publication.id,
            status=publication.status,
            instagram_media_id=getattr(publication, 'instagram_media_id', None),
            instagram_permalink=getattr(publication, 'instagram_permalink', None),
            facebook_media_id=getattr(publication, 'facebook_media_id', None),
            facebook_permalink=getattr(publication, 'facebook_permalink', None),
            shared_at=publication.shared_at,
            error_message=publication.error_message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[CM-STUDIO] Erreur publication multi-plateforme")
        raise HTTPException(status_code=503, detail="Publication impossible") from exc


# ============================================================
# STORY STUDIO — Nouvelle expérience Stories Instagram
# ============================================================


@router.post("/story-studio/draft", response_model=StoryDraftResponse, status_code=status.HTTP_201_CREATED)
async def create_story_draft(
    data: StoryDraftCreateRequest,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator_write),
):
    """Créer un brouillon Story Studio.

    Deux sources sont acceptées : une activité Garmin (préparation IA) ou une
    Story standalone déjà composée par le Composer (slides + designs v2).
    """
    try:
        if data.activity_id is not None:
            draft = await orchestrator.create_draft_from_garmin(
                activity_id=data.activity_id,
                selected_photo_ids=data.photo_ids,
                calendar_entry_id=data.calendar_entry_id,
            )
        else:
            draft = await orchestrator.create_manual_draft(
                photo_ids=data.photo_ids,
                slides=data.slides,
                design_documents=data.design_documents,
                caption=data.caption,
                hashtags=data.hashtags,
            )
        return StoryDraftResponse.model_validate(draft)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[STORY-STUDIO] Erreur création brouillon")
        raise HTTPException(status_code=503, detail="Création impossible") from exc


@router.get("/story-studio/drafts", response_model=StoryDraftListResponse)
async def list_story_drafts(
    status: Optional[str] = Query(None, description="Filtrer par statut"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator),
):
    """Lister les brouillons Story Studio de l'utilisateur."""
    result = await orchestrator.list_drafts(status=status, page=page, page_size=page_size)
    return StoryDraftListResponse(
        items=[StoryDraftResponse.model_validate(d) for d in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )


@router.get("/story-studio/draft/{draft_id}", response_model=StoryDraftResponse)
async def get_story_draft(
    draft_id: int,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator),
):
    """Récupérer un brouillon Story Studio avec ses slides et designs."""
    draft = await orchestrator.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Brouillon Story introuvable")
    return StoryDraftResponse.model_validate(draft)


async def _story_audio_proposals_response(
    db,
    current_user,
    photo_ids: list[int],
    *,
    title: str = "",
    hashtags: Optional[str] = None,
    timeout_seconds: float = 25.0,
) -> dict:
    """Construit la réponse d'audio-proposals pour des photos de la Story."""
    from app.services.community_manager.ig_music import pick_audio_for_photos_bounded, search_ig_audio

    result = await pick_audio_for_photos_bounded(
        db,
        current_user,
        photo_ids,
        title=title,
        hashtags=str(hashtags or ""),
        timeout_seconds=timeout_seconds,
    )
    suggestions = list((result or {}).get("suggestions") or [])
    reason = "Analyse IA des photos de la Story"
    if not suggestions:
        reason = "Repli catalogue Instagram (analyse IA indisponible)"
        # Sans compte Meta configuré, ni l'analyse IA ni le catalogue ne peuvent
        # renvoyer une piste. Le message doit le dire explicitement plutôt que
        # laisser l'étape musique silencieusement vide.
        from app.services.sport_instagram_publish import MetaPublishService

        try:
            if not await MetaPublishService(db).resolve_publish_context():
                reason = "Compte Instagram non configuré · connectez Meta dans Paramètres > Meta"
        except Exception:  # diagnostic best-effort : ne jamais casser les proposals
            logger.debug("[CM-STORY] Impossible de vérifier le contexte Meta", exc_info=True)
        seen: set[str] = set()
        started = time.perf_counter()
        queries = [
            query for query in (
                title.strip()[:80],
                str(hashtags or "").replace("#", " ").strip()[:80],
                "trail running motivation",
            ) if query
        ]
        for query in queries[:3]:
            try:
                candidates = await search_ig_audio(db, query, limit=10)
            except Exception as exc:
                logger.warning("[IG-MUSIC] Repli Story échoué (%s): %s", query, exc)
                continue
            for candidate in candidates:
                audio_id = str(candidate.get("audio_id") or "")
                if audio_id and audio_id not in seen:
                    seen.add(audio_id)
                    suggestions.append(candidate)
            if len(suggestions) >= 10:
                break
        logger.info(
            "[IG-MUSIC] Story audio-proposals durée=%.2fs uniques=%s affichés=%s",
            time.perf_counter() - started, len(seen), min(10, len(suggestions)),
        )

    items = []
    for item in suggestions:
        audio_id = str(item.get("audio_id") or "")
        if not audio_id:
            continue
        items.append({
            **item,
            "source": "instagram",
            "status": "available_on_meta",
            "reason": reason,
            "preview_link": (
                item.get("preview_link")
                or item.get("download_url")
                or item.get("preview_url")
            ),
            "platform_preview_link": item.get("platform_preview_link"),
        })
    return {
        "items": items[:10],
        "eligible_count": len(items[:10]),
        "source": "instagram",
        "local_render": False,
        "reason": reason if items else (
            reason if "non configuré" in reason else "Aucune réponse exploitable du catalogue Instagram Meta"
        ),
    }


@router.get("/story/photos/audio-proposals")
async def suggest_story_photo_audio_proposals(
    photo_ids: str = Query(..., min_length=1, max_length=64),
    title: str = Query("", max_length=200),
    hashtags: str = Query("", max_length=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("community_manager.calendar_generate")),
):
    """Proposer une musique Instagram via l'IA à partir de photos sélectionnées.

    Endpoint léger pour le déclenchement « juste après la sélection » du
    MediaPicker (Story) : les `photo_ids` sont transmis directement et aucune
    dépendance au brouillon serveur n'est requise (Story standalone). Aucune
    écriture n'est effectuée ici : le front décide de la présélection et peut
    toujours la remplacer. En cas d'échec IA, un repli catalogue contextuel est
    proposé et clairement mentionné dans `reason`.
    """
    ids: list[int] = []
    for raw in (photo_ids or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            photo_id = int(raw)
        except (TypeError, ValueError):
            continue
        if photo_id not in ids and len(ids) < 5:
            ids.append(photo_id)
    if not ids:
        return {
            "items": [],
            "eligible_count": 0,
            "source": "instagram",
            "local_render": False,
            "reason": "Aucune photo sélectionnée dans la Story",
        }
    return await _story_audio_proposals_response(
        db,
        current_user,
        ids,
        title=title,
        hashtags=hashtags,
        timeout_seconds=25.0,
    )


@router.get("/story-studio/draft/{draft_id}/audio-proposals")
async def suggest_story_audio_proposals(
    draft_id: int,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator),
    photo_ids: Optional[str] = Query(default=None),
):
    """Proposer une musique Instagram à partir des photos du brouillon Story.

    `photo_ids` permet de cibler explicitement des photos (ex : présélection
    déclenchée juste après une sélection) ; à défaut, les `selected_asset_ids`
    du brouillon sont utilisés. L'analyse vision est faite par `ig_music`.
    Aucune écriture n'est effectuée ici : le front décide de la présélection
    et peut toujours la remplacer. En cas d'échec IA, un repli catalogue
    contextuel est proposé et clairement mentionné dans `reason`.
    """

    draft = await orchestrator.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Brouillon Story introuvable")

    # Les tests appellent parfois la fonction directement : dans ce cas
    # `photo_ids` reste le descripteur FastAPI `Query`, pas une chaîne. ne pas
    # essayer de l'itérer (les appels HTTP reçoivent bien None ou une string).
    source_ids: list = (
        photo_ids.split(',')
        if isinstance(photo_ids, str)
        else (getattr(draft, "selected_asset_ids", None) or [])
    )
    selected_photo_ids: list[int] = []
    for raw_id in source_ids:
        try:
            photo_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if photo_id not in selected_photo_ids and len(selected_photo_ids) < 5:
            selected_photo_ids.append(photo_id)
    if not selected_photo_ids:
        return {
            "items": [],
            "eligible_count": 0,
            "source": "instagram",
            "local_render": False,
            "reason": "Aucune photo sélectionnée dans le brouillon Story",
        }

    return await _story_audio_proposals_response(
        orchestrator.db,
        orchestrator.current_user,
        selected_photo_ids,
        title=str(getattr(draft, "caption", None) or ""),
        hashtags=getattr(draft, "hashtags", None),
        timeout_seconds=25.0,
    )


@router.patch("/story-studio/draft/{draft_id}", response_model=StoryDraftResponse)
async def update_story_draft(
    draft_id: int,
    data: StoryDraftUpdateRequest,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator_write),
):
    """Mettre à jour un brouillon Story (slides, designs, caption, hashtags, audio, statut)."""
    # Pour l'instant, on met à jour directement via le service
    # Une implémentation complète ajouterait une méthode update_draft à l'orchestrator
    from sqlalchemy import select
    draft = await orchestrator.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Brouillon Story introuvable")

    if data.slides is not None:
        draft.slides = data.slides
    if data.design_documents is not None:
        draft.design_documents = data.design_documents
    if data.caption is not None:
        draft.caption = data.caption
    if data.hashtags is not None:
        draft.hashtags = data.hashtags
    if data.audio_configuration is not None:
        draft.audio_configuration = data.audio_configuration
    if data.status is not None:
        draft.status = data.status

    await orchestrator.db.commit()
    await orchestrator.db.refresh(draft)
    return StoryDraftResponse.model_validate(draft)


@router.patch("/story-studio/draft/{draft_id}/slide/{slide_index}", response_model=StoryDraftResponse)
async def update_story_slide_design(
    draft_id: int,
    slide_index: int,
    data: StoryDraftSlideUpdate,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator_write),
):
    """Mettre à jour le design d'une slide spécifique (depuis l'éditeur graphique)."""
    draft = await orchestrator.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Brouillon Story introuvable")

    if slide_index < 0 or slide_index >= len(draft.design_documents):
        raise HTTPException(status_code=422, detail="Index de slide invalide")

    designs = list(draft.design_documents)
    designs[slide_index] = data.design
    draft.design_documents = designs
    draft.status = "editing"
    draft.updated_at = datetime.now(timezone.utc)

    await orchestrator.db.commit()
    await orchestrator.db.refresh(draft)
    return StoryDraftResponse.model_validate(draft)


@router.post("/story-studio/draft/{draft_id}/render-slide/{slide_index}")
async def render_story_slide(
    draft_id: int,
    slide_index: int,
    background_tasks: BackgroundTasks,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator_write),
):
    """Lancer le rendu FFmpeg d'une slide individuelle."""
    from app.services.photo.jobs import enqueue_job, run_pending_jobs_now
    from app.models.photo import PhotoJob

    draft = await orchestrator.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Brouillon Story introuvable")

    if slide_index < 0 or slide_index >= len(draft.design_documents):
        raise HTTPException(status_code=422, detail="Index de slide invalide")

    design = draft.design_documents[slide_index]
    design["format"] = {"width": 1080, "height": 1920, "type": "story_916", "platform": "instagram"}

    # Vérifier s'il y a déjà un job en cours pour cette slide
    active = await orchestrator.db.execute(
        select(PhotoJob).where(
            PhotoJob.type == "studio_render",
            PhotoJob.status.in_(("pending", "running")),
        )
    )
    for job in active.scalars():
        payload = job.payload_json or {}
        if payload.get("kind") == "story_slide" and payload.get("draft_id") == draft_id and payload.get("slide_index") == slide_index:
            return {"job_id": job.id, "status": job.status, "slide_index": slide_index}

    job = await enqueue_job(
        orchestrator.db,
        type="studio_render",
        photo_id=None,
        payload={
            "kind": "story_slide",
            "draft_id": draft_id,
            "slide_index": slide_index,
            "design": design,
            "user_id": orchestrator.current_user.id,
        },
    )

    # Mettre à jour le statut du brouillon
    draft.status = "rendering"
    await orchestrator.add_render_job(draft_id, slide_index, job.id)
    background_tasks.add_task(run_pending_jobs_now)

    return {"job_id": job.id, "status": "pending", "slide_index": slide_index}


@router.get("/story-studio/draft/{draft_id}/render-jobs")
async def get_story_render_jobs(
    draft_id: int,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator),
):
    """Récupérer l'état des jobs de rendu pour un brouillon."""
    draft = await orchestrator.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Brouillon Story introuvable")
    return {"render_jobs": draft.render_jobs or []}


@router.post("/story-studio/draft/{draft_id}/render-slide/{slide_index}/cancel")
async def cancel_story_render_job(
    draft_id: int,
    slide_index: int,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator_write),
):
    """Annuler un job de rendu pour une slide Story."""
    from app.services.studio_render import StudioRenderService, StudioRenderError
    from app.models.photo import PhotoJob
    from sqlalchemy import select

    draft = await orchestrator.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Brouillon Story introuvable")

    # Trouver le job pour cette slide
    render_jobs = draft.render_jobs or []
    job_info = None
    for j in render_jobs:
        if j.get("slide_index") == slide_index:
            job_info = j
            break

    if not job_info:
        raise HTTPException(status_code=404, detail="Job de rendu introuvable pour cette slide")

    job_id = job_info.get("job_id")
    if not job_id:
        raise HTTPException(status_code=422, detail="Job ID manquant")

    job = await orchestrator.db.get(PhotoJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job introuvable en base")

    if job.status == "cancelled":
        return {"job_id": job_id, "status": "cancelled", "slide_index": slide_index}

    service = StudioRenderService(orchestrator.db, orchestrator.current_user)
    try:
        cancelled_job = await service.cancel_render_job(job_id)
    except StudioRenderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    # Mettre à jour le StoryDraft
    for j in render_jobs:
        if j.get("slide_index") == slide_index:
            j["status"] = "cancelled"
            j["updated_at"] = datetime.now(timezone.utc).isoformat()
            break
    draft.render_jobs = render_jobs
    await orchestrator.db.commit()

    return {"job_id": job_id, "status": cancelled_job.status, "slide_index": slide_index}


@router.post("/story-studio/draft/{draft_id}/validate", response_model=StoryDraftResponse)
async def validate_story_draft(
    draft_id: int,
    data: StoryDraftStatusUpdate,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator_write),
):
    """Valider le brouillon Story pour publication (passe en awaiting_validation)."""
    draft = await orchestrator.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Brouillon Story introuvable")

    if not draft.design_documents:
        raise HTTPException(status_code=422, detail="Aucune slide préparée")
    if len(draft.slides or []) != len(draft.design_documents) or any(
        not slide.get("published_photo_id") for slide in (draft.slides or [])
    ):
        raise HTTPException(status_code=422, detail="Exportez chaque slide depuis l'éditeur avant validation")

    draft.status = "awaiting_validation"
    draft.validated_at = datetime.now(timezone.utc)
    await orchestrator.db.commit()
    await orchestrator.db.refresh(draft)
    return StoryDraftResponse.model_validate(draft)


@router.post("/story-studio/draft/{draft_id}/publish", response_model=Dict[str, Any])
async def publish_story_draft(
    draft_id: int,
    data: StoryDraftPublishRequest,
    background_tasks: BackgroundTasks,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator_write),
):
    """Publier les Stories validées sur Instagram uniquement (Lot 1 / A06).

    A07 : une musique éventuellement sélectionnée reste un brouillon créatif ;
    aucun paramètre audio n'est transmis à Meta.
    """
    from app.services.photo.jobs import enqueue_job, run_pending_jobs_now
    from app.models.photo import PhotoJob

    draft = await orchestrator.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Brouillon Story introuvable")

    if draft.status != "awaiting_validation":
        raise HTTPException(status_code=422, detail="Le brouillon doit être validé avant publication")

    if not draft.design_documents:
        raise HTTPException(status_code=422, detail="Aucune slide à publier")

    slides = draft.slides or []
    if len(slides) != len(draft.design_documents or []):
        raise HTTPException(status_code=422, detail="Chaque Story doit avoir un design enregistré")
    if any(not slide.get("published_photo_id") for slide in slides):
        raise HTTPException(status_code=422, detail="Préparez et validez le rendu de chaque Story avant publication")
    if not data.platforms or any(platform != "instagram" for platform in data.platforms):
        raise HTTPException(status_code=422, detail="La publication Story est disponible sur Instagram uniquement")

    # Créer un job de publication pour chaque slide
    published_count = 0
    results = []

    for slide_index, design in enumerate(draft.design_documents):
        # Rendre la slide en MP4 si vidéo, sinon image
        # Pour l'instant, on crée un job de publication par slide
        job = await enqueue_job(
            orchestrator.db,
            type="community_publish",
            photo_id=None,
            payload={
                "kind": "story_slide_publish",
                "draft_id": draft_id,
                "slide_index": slide_index,
                # Correction minimaliste : la boucle itère sur les designs ;
                # le visuel validé correspond à la même position dans `slides`.
                "photo_id": slides[slide_index]["published_photo_id"],
                "design": design,
                "caption": draft.caption,
                "hashtags": draft.hashtags,
                # Pas de champ « platforms » : le handler est Instagram uniquement.
                "user_id": orchestrator.current_user.id,
            },
        )
        results.append({"slide_index": slide_index, "job_id": job.id, "status": "queued"})
        published_count += 1

    draft.status = "publishing"
    await orchestrator.db.commit()

    background_tasks.add_task(run_pending_jobs_now)

    return {
        "draft_id": draft_id,
        "published_slides": published_count,
        "jobs": results,
        "message": (
            f"{published_count} Story(s) Instagram en file de publication · "
            "musique sélectionnée : brouillon créatif uniquement, non publiée"
        ),
    }


@router.delete("/story-studio/draft/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_story_draft(
    draft_id: int,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator_write),
):
    """Supprimer un brouillon Story (si pas publié)."""
    try:
        deleted = await orchestrator.delete_draft(draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Brouillon Story introuvable")


# Importer la route pour l'aperçu des Stories
@router.post("/story-studio/draft/{draft_id}/preview")
async def preview_story_draft(
    draft_id: int,
    orchestrator: StoryOrchestrator = Depends(get_story_orchestrator),
):
    """Générer un aperçu HTML de toutes les slides."""
    draft = await orchestrator.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Brouillon Story introuvable")

    # Construire un aperçu HTML simple pour chaque slide
    slides_html = []
    for i, design in enumerate(draft.design_documents):
        slide = draft.slides[i] if i < len(draft.slides) else {}
        slides_html.append({
            "index": i,
            "type": slide.get("type", "photo"),
            "hook": slide.get("hook"),
            "caption": slide.get("caption"),
            "design": design,
        })

    return {
        "draft_id": draft_id,
        "total_slides": len(draft.design_documents),
        "caption": draft.caption,
        "hashtags": draft.hashtags,
        "slides": slides_html,
    }


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
                SportPublication.story_draft_id.label("pub_story_draft_id"),
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
                "pub_story_draft_id": row.pub_story_draft_id,
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
            "story_draft_id": info.get("pub_story_draft_id"),
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
                SportPublication.story_draft_id.label("pub_story_draft_id"),
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
                "pub_story_draft_id": row.pub_story_draft_id,
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
            "story_draft_id": info.get("pub_story_draft_id"),
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
