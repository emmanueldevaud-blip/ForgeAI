from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from xml.etree.ElementTree import ParseError

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.sport import (
    SportActivityCreate,
    SportActivityListResponse,
    SportActivityResponse,
    SportDashboardResponse,
    SportGoalCreate,
    SportGoalResponse,
    GarminConnectRequest,
    GarminConnectionResponse,
    GarminSyncResponse,
)
from app.services.garmin import GarminServiceError, SportGarminConnectService
from app.services.sport import SportService


router = APIRouter(prefix="/sport", tags=["sport"])


async def get_sport_service(
    current_user: User = Depends(require_permission("sport.access")),
    db: AsyncSession = Depends(get_db),
) -> SportService:
    return SportService(db, current_user)


async def get_sport_activity_read_service(
    current_user: User = Depends(require_permission("sport.activities.read")),
    db: AsyncSession = Depends(get_db),
) -> SportService:
    return SportService(db, current_user)


async def get_sport_activity_write_service(
    current_user: User = Depends(require_permission("sport.activities.write")),
    db: AsyncSession = Depends(get_db),
) -> SportService:
    return SportService(db, current_user)


async def get_sport_goal_read_service(
    current_user: User = Depends(require_permission("sport.goals.read")),
    db: AsyncSession = Depends(get_db),
) -> SportService:
    return SportService(db, current_user)


async def get_sport_goal_write_service(
    current_user: User = Depends(require_permission("sport.goals.write")),
    db: AsyncSession = Depends(get_db),
) -> SportService:
    return SportService(db, current_user)


async def get_sport_athlete(service: SportService = Depends(get_sport_service)):
    return await service.get_or_create_athlete()


@router.get("/dashboard", response_model=SportDashboardResponse)
async def sport_dashboard(
    period: int = Query(28, description="Période en jours: 7, 28, 90 ou 365"),
    service: SportService = Depends(get_sport_service),
):
    return await service.dashboard(period)


@router.get("/activities", response_model=SportActivityListResponse)
async def list_sport_activities(
    page: int = 1,
    page_size: int = 20,
    service: SportService = Depends(get_sport_activity_read_service),
):
    return await service.list_activities(page, min(page_size, 100))


@router.post("/activities", response_model=SportActivityResponse, status_code=201)
async def create_sport_activity(
    data: SportActivityCreate,
    service: SportService = Depends(get_sport_activity_write_service),
):
    return await service.create_activity(data)


@router.post("/activities/import", response_model=SportActivityResponse, status_code=201)
async def import_sport_activity(
    file: UploadFile = File(...),
    service: SportService = Depends(get_sport_activity_write_service),
):
    try:
        return await service.import_activity(file)
    except (ValueError, ParseError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/goals", response_model=list[SportGoalResponse])
async def list_sport_goals(service: SportService = Depends(get_sport_goal_read_service)):
    return await service.list_goals()


@router.post("/goals", response_model=SportGoalResponse, status_code=201)
async def create_sport_goal(data: SportGoalCreate, service: SportService = Depends(get_sport_goal_write_service)):
    return await service.create_goal(data)


def _garmin_response(connection) -> GarminConnectionResponse:
    if not connection:
        return GarminConnectionResponse(connected=False)
    return GarminConnectionResponse(
        connected=connection.status == "connected",
        status=connection.status,
        garmin_email=connection.garmin_email,
        last_sync_at=connection.last_sync_at,
        last_sync_status=connection.last_sync_status,
        last_error=connection.last_error,
        initial_sync_days=connection.initial_sync_days,
    )


@router.get("/garmin", response_model=GarminConnectionResponse)
async def get_garmin_connection(
    service: SportService = Depends(get_sport_service),
):
    from app.services.garmin import SportGarminConnectService
    athlete = await service.get_or_create_athlete()
    return _garmin_response(await SportGarminConnectService(service.db).get_connection(athlete))


@router.post("/garmin/connect", response_model=GarminConnectionResponse)
async def connect_garmin(
    data: GarminConnectRequest,
    service: SportService = Depends(get_sport_activity_write_service),
):
    athlete = await service.get_or_create_athlete()
    garmin = SportGarminConnectService(service.db)
    try:
        result = await garmin.connect(athlete, data.email, data.password, data.mfa_code, data.initial_sync_days)
    except GarminServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result["status"] == "mfa_required":
        raise HTTPException(status_code=409, detail=result["message"])
    return _garmin_response(await garmin.get_connection(athlete))


@router.post("/garmin/sync", response_model=GarminSyncResponse)
async def sync_garmin(
    service: SportService = Depends(get_sport_activity_write_service),
):
    athlete = await service.get_or_create_athlete()
    try:
        return await SportGarminConnectService(service.db).sync_for_athlete(athlete)
    except GarminServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/garmin", response_model=dict)
async def disconnect_garmin(
    service: SportService = Depends(get_sport_activity_write_service),
):
    athlete = await service.get_or_create_athlete()
    deleted = await SportGarminConnectService(service.db).disconnect(athlete)
    return {"message": "Garmin déconnecté" if deleted else "Aucune connexion Garmin"}
