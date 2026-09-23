import asyncio
import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from xml.etree.ElementTree import ParseError

from app.api.deps import get_db, require_permission
from app.db.session import get_db_context
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
    SportCoachRequest,
    SportCoachResponse,
    SportCoachConversationResponse,
    SportObservationCreate,
    SportObservationResponse,
    SportAthleteProfileResponse,
    SportHeartRateConfig,
)
from app.services.garmin import GarminServiceError, SportGarminConnectService
from app.services.sport import SportService

logger = logging.getLogger(__name__)

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


async def get_sport_analysis_service(
    current_user: User = Depends(require_permission("sport.analysis.read")),
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


async def _run_activity_ai_analysis(activity_id: int, user_id: int) -> None:
    for attempt in range(2):
        try:
            async with get_db_context() as db:
                user = await db.get(User, user_id)
                if user and await SportService(db, user).generate_activity_ai_analysis(activity_id):
                    return
        except Exception:
            logger.exception("Unable to run background Sport AI analysis for activity %s", activity_id)
        if attempt == 0:
            await asyncio.sleep(0.5)


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


@router.get("/analysis/period")
async def sport_period_analysis(
    period: int = Query(28),
    service: SportService = Depends(get_sport_analysis_service),
):
    return await service.analyze_period(period)


@router.get("/analysis/week")
async def sport_week_analysis(service: SportService = Depends(get_sport_analysis_service)):
    return await service.analyze_week()


@router.get("/analysis/day")
async def sport_day_analysis(
    day: date | None = Query(None),
    service: SportService = Depends(get_sport_analysis_service),
):
    return await service.analyze_day(day)


@router.get("/analysis/goals")
async def sport_goals_analysis(service: SportService = Depends(get_sport_analysis_service)):
    return await service.analyze_goals()


@router.get("/analysis/month")
async def sport_month_analysis(service: SportService = Depends(get_sport_analysis_service)):
    return await service.analyze_month()


@router.get("/athlete/profile", response_model=SportAthleteProfileResponse)
async def sport_athlete_profile(service: SportService = Depends(get_sport_analysis_service)):
    return await service.athlete_profile()


@router.put("/athlete/heart-rate", response_model=SportAthleteProfileResponse)
async def update_sport_heart_rate(
    data: SportHeartRateConfig,
    service: SportService = Depends(get_sport_analysis_service),
):
    try:
        return await service.update_heart_rate_config(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/analysis/activities/{activity_id}")
async def sport_activity_analysis(
    activity_id: int,
    service: SportService = Depends(get_sport_analysis_service),
):
    analysis = await service.analyze_activity(activity_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Activité non trouvée")
    return analysis


@router.post("/coach", response_model=SportCoachResponse)
async def sport_coach(
    data: SportCoachRequest,
    service: SportService = Depends(get_sport_analysis_service),
):
    try:
        return await service.coach(data.question, data.conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/coach/conversations", response_model=list[SportCoachConversationResponse])
async def list_sport_coach_conversations(service: SportService = Depends(get_sport_analysis_service)):
    return await service.list_coach_conversations()


@router.get("/coach/conversations/{conversation_id}", response_model=SportCoachConversationResponse)
async def get_sport_coach_conversation(
    conversation_id: int,
    service: SportService = Depends(get_sport_analysis_service),
):
    conversation = await service.get_coach_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation Sport introuvable")
    return conversation


@router.get("/observations", response_model=list[SportObservationResponse])
async def list_sport_observations(service: SportService = Depends(get_sport_analysis_service)):
    return [{"id": item.id, "activity_id": item.activity_id, "kind": item.kind, "content": item.content,
             "status": item.status, "sources": item.sources_json, "created_at": item.created_at,
             "confirmed_at": item.confirmed_at} for item in await service.list_observations()]


@router.post("/observations", response_model=SportObservationResponse, status_code=201)
async def create_sport_observation(
    data: SportObservationCreate,
    service: SportService = Depends(get_sport_analysis_service),
):
    try:
        item = await service.create_observation(data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": item.id, "activity_id": item.activity_id, "kind": item.kind, "content": item.content,
            "status": item.status, "sources": item.sources_json, "created_at": item.created_at,
            "confirmed_at": item.confirmed_at}


@router.post("/activities", response_model=SportActivityResponse, status_code=201)
async def create_sport_activity(
    data: SportActivityCreate,
    background_tasks: BackgroundTasks,
    service: SportService = Depends(get_sport_activity_write_service),
):
    activity = await service.create_activity(data)
    background_tasks.add_task(_run_activity_ai_analysis, activity.id, service.current_user.id)
    return activity


@router.post("/activities/import", response_model=SportActivityResponse, status_code=201)
async def import_sport_activity(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    service: SportService = Depends(get_sport_activity_write_service),
):
    try:
        activity = await service.import_activity(file)
        background_tasks.add_task(_run_activity_ai_analysis, activity.id, service.current_user.id)
        return activity
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
