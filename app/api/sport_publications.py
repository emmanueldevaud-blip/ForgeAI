"""Routes API pour les publications Instagram (module Sport)."""

import logging
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
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

# Callback OAuth public (redirection depuis Instagram, sans session) :
# la protection CSRF repose sur le state, pas sur l'authentification.
public_router = APIRouter(
    prefix="/sport/publications",
    tags=["sport"],
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


# --------------------------------------------------------------------------- #
# Instagram Login (voie B) — connexions par utilisateur
# --------------------------------------------------------------------------- #


@router.get("/meta/auth")
async def instagram_login_authorize(
    current_user: User = Depends(require_permission("settings_update")),
    db: AsyncSession = Depends(get_db),
):
    """URL d'autorisation Instagram Login pour l'utilisateur courant."""
    service = SportInstagramConnectService(db)
    authorize_url, _state = await service.build_authorization_url(current_user.id)
    return {"authorize_url": authorize_url}


@router.get("/meta/status")
async def instagram_connection_status(
    current_user: User = Depends(require_permission("settings_view")),
    db: AsyncSession = Depends(get_db),
):
    """Statut de la connexion Instagram de l'utilisateur courant."""
    service = SportInstagramConnectService(db)
    values = await service.load_instagram_login_values()
    configured = bool(values["app_id"] and values["app_secret"] and values["redirect_uri"])
    connection = await service.get_connection(current_user.id)
    connected = bool(
        connection
        and connection.status == "active"
        and connection.instagram_business_account_id
    )
    metadata = (connection.metadata_json or {}) if connection is not None else {}
    return {
        "configured": configured,
        "connected": connected,
        "status": connection.status if connection is not None else None,
        "instagram_business_account_id": (
            connection.instagram_business_account_id if connection is not None else None
        ),
        "username": metadata.get("username"),
        "scopes": connection.scopes if connection is not None else None,
    }


@router.delete("/meta")
async def disconnect_instagram_connection(
    current_user: User = Depends(require_permission("settings_update")),
    db: AsyncSession = Depends(get_db),
):
    """Desactive la connexion Instagram de l'utilisateur courant (isole)."""
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


# --------------------------------------------------------------------------- #
# Callback OAuth Instagram (public — redirection depuis www.instagram.com)
# --------------------------------------------------------------------------- #


@public_router.get("/meta/callback")
async def instagram_oauth_callback(
    request: Request,
    code: str | None = Query(None, description="Code OAuth Instagram"),
    state: str | None = Query(None, description="State OAuth (CSRF)"),
    error: str | None = Query(None, description="Erreur renvoyée par Instagram"),
    error_reason: str | None = Query(None, description="Raison du refus Instagram"),
    db: AsyncSession = Depends(get_db),
):
    """Callback Instagram Login : consomme le state, echange le code, enregistre
    la connexion de l'utilisateur, puis redirige vers /settings.

    Sans authentification (le state CSRF protege la route) : la livraison du
    code se fait par redirection navigateur depuis Instagram.
    """
    service = SportInstagramConnectService(db)
    wants_json = "application/json" in request.headers.get("accept", "")

    def _response(payload: dict, code_http: int = 200):
        if wants_json:
            return JSONResponse(
                status_code=code_http, content=payload, headers={"Cache-Control": "no-store"}
            )
        if payload.get("status") == "connected":
            url = "/settings?connected=1"
        else:
            url = "/settings?" + urlencode({"error": payload.get("detail") or "erreur"})
        return RedirectResponse(
            url=url, status_code=302, headers={"Cache-Control": "no-store"}
        )

    if error:
        return _response(
            {"status": "error", "detail": f"Instagram a refusé la connexion ({error_reason or error})"},
            code_http=400,
        )
    if not code or not state:
        return _response(
            {"status": "error", "detail": "Paramètres OAuth manquants (code ou state)"},
            code_http=400,
        )

    user_id = await service.consume_state(state)
    if user_id is None:
        return _response(
            {"status": "error", "detail": "State OAuth invalide ou expiré"},
            code_http=400,
        )

    try:
        result = await service.exchange_instagram_code(code)
    except HTTPException as exc:
        return _response(
            {"status": "error", "detail": str(exc.detail)},
            code_http=exc.status_code if exc.status_code >= 400 else 502,
        )
    except Exception:
        logger.exception("Echange OAuth Instagram impossible")
        return _response(
            {"status": "error", "detail": "Echange du code OAuth Instagram impossible"},
            code_http=502,
        )

    if not result.get("instagram_business_account_id"):
        return _response(
            {"status": "error", "detail": "Compte Instagram Business introuvable pour ce jeton"},
            code_http=502,
        )

    await service.save_connection(
        user_id,
        access_token=result["access_token"],
        expires_in=result.get("expires_in"),
        instagram_business_account_id=result.get("instagram_business_account_id"),
        username=result.get("username"),
    )
    return _response({"status": "connected"})
