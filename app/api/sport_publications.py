"""Routes API pour les publications Instagram (module Sport)."""

import logging
from typing import Optional
from urllib.parse import urlencode

import httpx
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

# Callback OAuth public (redirection depuis Meta, sans session) :
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
# Instagram Unified Login — connexion Meta centralisee (SUAT partage)
# --------------------------------------------------------------------------- #


@router.get("/meta/auth")
async def instagram_login_authorize(
    current_user: User = Depends(require_permission("settings_update")),
    db: AsyncSession = Depends(get_db),
):
    """URL d'autorisation Instagram Unified Login (config_id)."""
    service = SportInstagramConnectService(db)
    authorize_url, _state = await service.build_authorization_url(current_user.id)
    return {"authorize_url": authorize_url}


@router.get("/meta/preflight")
async def instagram_login_preflight(
    current_user: User = Depends(require_permission("settings_update")),
    db: AsyncSession = Depends(get_db),
):
    """Pré-vérification de la configuration Meta avant connexion OAuth.

    Vérifie sans déclencher l'OAuth : présence des paramètres requis,
    validité de l'App ID (client_credentials), et cohérence du redirect_uri.
    Retourne des messages d'erreur exploitables si la configuration est
    incomplète ou invalide.
    """
    service = SportInstagramConnectService(db)
    values = await service.load_meta_values()
    checks = []

    # 1. Vérification de la configuration locale
    missing = []
    if not values["app_id"]:
        missing.append("App ID")
    if not values["app_secret"]:
        missing.append("App Secret")
    if not values["config_id"]:
        missing.append("Config ID")
    if not values["redirect_uri"]:
        missing.append("Redirect URI")
    if missing:
        checks.append({
            "key": "configuration",
            "status": "error",
            "detail": f"Paramètre(s) manquant(s) : {', '.join(missing)}",
        })
        return {
            "ready": False,
            "checks": checks,
            "message": f"Configuration incomplète : {', '.join(missing)}",
        }
    checks.append({"key": "configuration", "status": "ok", "detail": "Tous les paramètres sont renseignés."})

    # 2. Vérification HTTPS du redirect_uri
    redirect_uri = values["redirect_uri"]
    if not redirect_uri.startswith("https://") and not redirect_uri.startswith("http://localhost"):
        checks.append({
            "key": "redirect_uri_https",
            "status": "warning",
            "detail": "Le redirect_uri n'utilise pas HTTPS. Meta exige HTTPS en production.",
        })
    else:
        checks.append({"key": "redirect_uri_https", "status": "ok", "detail": "Le redirect_uri utilise HTTPS."})

    # 3. Vérification de l'App ID via client_credentials (sans exposer de secrets)
    base_url = f"https://graph.facebook.com/{values['api_version']}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            resp = await http_client.get(
                f"{base_url}/oauth/access_token",
                params={
                    "grant_type": "client_credentials",
                    "client_id": values["app_id"],
                    "client_secret": values["app_secret"],
                },
            )
        if resp.status_code == 200 and resp.json().get("access_token"):
            checks.append({
                "key": "app_credentials",
                "status": "ok",
                "detail": f"App ID {values['app_id']} accepté par Meta.",
            })
        else:
            try:
                meta_msg = resp.json().get("error", {}).get("message", resp.text)
            except ValueError:
                meta_msg = resp.text
            checks.append({
                "key": "app_credentials",
                "status": "error",
                "detail": f"App ID ou App Secret rejeté par Meta : {meta_msg}",
            })
    except httpx.HTTPError as exc:
        checks.append({
            "key": "app_credentials",
            "status": "warning",
            "detail": f"Impossible de joindre Meta pour vérifier les identifiants : {exc}",
        })

    has_error = any(c["status"] == "error" for c in checks)
    has_warning = any(c["status"] == "warning" for c in checks)
    if has_error:
        message = "Configuration Meta invalide. Corrigez les erreurs avant de tenter la connexion."
    elif has_warning:
        message = "Configuration Meta prête avec avertissements."
    else:
        message = "Configuration Meta prête pour la connexion."

    return {
        "ready": not has_error,
        "checks": checks,
        "message": message,
    }


@router.get("/meta/status")
async def instagram_connection_status(
    current_user: User = Depends(require_permission("settings_view")),
    db: AsyncSession = Depends(get_db),
):
    """Statut de la connexion Meta (configuration + jeton SUAT centralise)."""
    service = SportInstagramConnectService(db)
    return await service.connection_status()


@router.delete("/meta")
async def disconnect_instagram_connection(
    current_user: User = Depends(require_permission("settings_update")),
    db: AsyncSession = Depends(get_db),
):
    """Retire le jeton SUAT et le contexte de connexion Meta (configuration conservee)."""
    service = SportInstagramConnectService(db)
    disconnected = await service.clear_meta_credentials()
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
# Callback OAuth (public — redirection depuis www.facebook.com)
# --------------------------------------------------------------------------- #


@public_router.get("/meta/callback")
async def instagram_oauth_callback(
    request: Request,
    code: str | None = Query(None, description="Code OAuth Meta"),
    state: str | None = Query(None, description="State OAuth (CSRF)"),
    error: str | None = Query(None, description="Erreur renvoyee par Meta"),
    error_reason: str | None = Query(None, description="Raison du refus Meta"),
    db: AsyncSession = Depends(get_db),
):
    """Callback Instagram Unified Login : consomme le state, echange le code
    contre le SUAT, enregistre le contexte Meta, puis redirige vers /settings.

    Sans authentification (le state CSRF protege la route) : la livraison du
    code se fait par redirection navigateur depuis Meta.
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
        # Diagnostic détaillé des refus Meta connus.
        reason = error_reason or error
        detail = f"Meta a refusé la connexion ({reason})"
        if error == "access_denied":
            detail = (
                "Meta a refusé l'accès. L'utilisateur a annulé la connexion "
                "ou n'a pas les droits nécessaires sur l'application Meta."
            )
        logger.warning(
            "META OAuth callback : refus Meta (error=%s, error_reason=%s)",
            error, error_reason,
        )
        return _response(
            {"status": "error", "detail": detail},
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
        result = await service.exchange_business_code(code)
    except HTTPException as exc:
        return _response(
            {"status": "error", "detail": str(exc.detail)},
            code_http=exc.status_code if exc.status_code >= 400 else 502,
        )
    except Exception:
        logger.exception("Echange OAuth Meta impossible")
        return _response(
            {"status": "error", "detail": "Echange du code OAuth Meta impossible"},
            code_http=502,
        )

    accounts = result.get("instagram_accounts") or []
    instagram_user_id = next(
        (str(account.get("id")) for account in accounts if account.get("id")), None
    )
    if not instagram_user_id:
        return _response(
            {"status": "error", "detail": "Aucun compte Instagram assigné au jeton Meta"},
            code_http=502,
        )
    username = next(
        (account.get("username") for account in accounts if str(account.get("id")) == instagram_user_id),
        None,
    )

    await service.save_meta_credentials(
        token=result["access_token"],
        client_business_id=result.get("client_business_id") or "",
        instagram_user_id=instagram_user_id,
        username=username,
    )
    return _response({"status": "connected"})
