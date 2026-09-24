from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.agenda import (
    AgendaExternalPresenceCreate,
    AgendaPlanningResponse,
    AgendaPresenceResponse,
    AgendaPresenceUpsert,
)
from app.services.agenda import AgendaService
from app.services.rbac import RBACService

router = APIRouter(prefix="/agenda", tags=["agenda"])


class AgendaPresenceUpdate(BaseModel):
    needs_workstation: Optional[bool] = None
    is_present: Optional[bool] = None


async def get_agenda_service(
    current_user: User = Depends(require_permission("agenda.access")),
    db: AsyncSession = Depends(get_db),
) -> AgendaService:
    return AgendaService(db, current_user)


@router.get("/planning", response_model=AgendaPlanningResponse)
async def get_planning(
    view: str = Query("week", pattern="^(week|month|quarter)$"),
    anchor: Optional[date] = Query(None, description="Date de référence (aujourd'hui par défaut)"),
    service: AgendaService = Depends(get_agenda_service),
):
    try:
        return await service.get_planning(view, anchor or date.today())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/presences", response_model=AgendaPresenceResponse)
async def upsert_own_presence(
    payload: AgendaPresenceUpsert,
    service: AgendaService = Depends(get_agenda_service),
):
    try:
        return await service.upsert_own_presence(payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/presences/external",
    response_model=AgendaPresenceResponse,
)
async def create_external_presence(
    payload: AgendaExternalPresenceCreate,
    current_user: User = Depends(require_permission("agenda.manage")),
    db: AsyncSession = Depends(get_db),
):
    service = AgendaService(db, current_user)
    try:
        return await service.create_external_presence(payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch("/presences/{presence_id}", response_model=AgendaPresenceResponse)
async def update_presence(
    presence_id: int,
    payload: AgendaPresenceUpdate,
    current_user: User = Depends(require_permission("agenda.access")),
    db: AsyncSession = Depends(get_db),
):
    service = AgendaService(db, current_user)
    presence = await service.get_presence(presence_id)
    if not presence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Présence introuvable")

    is_owner = presence.user_id == current_user.id
    if not is_owner:
        rbac = RBACService(db)
        if not await rbac.user_has_permission(current_user, "agenda.manage"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission 'agenda.manage' requise")

    try:
        return await service.update_presence(
            presence_id,
            needs_workstation=payload.needs_workstation,
            is_present=payload.is_present,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/presences/{presence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_presence(
    presence_id: int,
    current_user: User = Depends(require_permission("agenda.access")),
    db: AsyncSession = Depends(get_db),
):
    service = AgendaService(db, current_user)
    presence = await service.get_presence(presence_id)
    if not presence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Présence introuvable")

    is_owner = presence.user_id == current_user.id or (
        presence.user_id is None and presence.created_by == current_user.id
    )
    if not is_owner:
        rbac = RBACService(db)
        if not await rbac.user_has_permission(current_user, "agenda.manage"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission 'agenda.manage' requise")

    await service.delete_presence(presence_id)
    return None
